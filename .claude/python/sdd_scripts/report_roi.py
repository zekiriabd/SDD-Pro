"""SDD_Pro : aggregated ROI report per FEAT (or global) from console.db.

Addresses codex audit P0 #10 (2026-05-20) : "Ajouter un rapport ROI
automatique : temps, tokens, coût, AC vérifiés, coverage, rework."

Reads :
- runs                  → wall-clock time, status, command
- run_phases            → phase-by-phase timing
- token_usage           → real input/output/cache token deltas (v6.5.1+,
                          requires TokenUsageMode != "off")
- context_budget        → estimated token budget consumed
- qa_coverage           → coverage_lines_pct + tests pass/fail
- qa_quality            → quality scan issues count
- qa_code_review        → code review findings (severity)
- qa_security           → security findings (severity)
- qa_spec_compliance    → AC verification verdicts (verified/not_verified)

Computes :
- Wall-clock duration per FEAT
- Total billed tokens (input + output + cache_creation) per FEAT
- Estimated cost ($USD) per FEAT — model-aware pricing table
- Coverage % + tests verified
- AC verification rate (verified / total ACs)
- Rework signal : count of run-restart events on the same FEAT

Usage :
    python -m sdd_scripts.report_roi --feat 1
    python -m sdd_scripts.report_roi --all
    python -m sdd_scripts.report_roi --feat 1 --json
    python -m sdd_scripts.report_roi --all --markdown > workspace/output/qa/roi-report.md

Exit codes :
    0 = OK
    1 = console.db missing or unreadable
    2 = FEAT not found (when --feat is set)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.console_db import connect_ro  # noqa: E402
from sdd_lib.pricing import as_tuple, FALLBACK_PRICING  # noqa: E402  # v7.0.1 SSoT
from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402

# Pricing SSoT moved to sdd_lib/pricing.py (v7.0.1). DEFAULT_PRICING kept
# here as a tuple-shaped alias for the legacy model_cost() signature.
DEFAULT_PRICING = (
    FALLBACK_PRICING["input"],
    FALLBACK_PRICING["output"],
    FALLBACK_PRICING["cache_creation"],
    FALLBACK_PRICING["cache_read"],
)


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Tolerant : strip trailing Z, normalize +HH:MM, fallback fromisoformat
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def duration_ms(started: str | None, ended: str | None) -> int | None:
    a = parse_iso(started)
    b = parse_iso(ended)
    if a is None or b is None:
        return None
    return int((b - a).total_seconds() * 1000)


def fmt_duration(ms: int | None) -> str:
    if ms is None:
        return "—"
    s = ms / 1000.0
    if s < 60:
        return f"{s:.1f}s"
    m = s / 60.0
    if m < 60:
        return f"{m:.1f}m"
    h = m / 60.0
    return f"{h:.2f}h"


def model_cost(model: str | None, in_t: int, out_t: int,
               cache_c: int, cache_r: int) -> float:
    """Return cost in USD given token counts and the model id."""
    rates = DEFAULT_PRICING if model is None else as_tuple(model)
    in_rate, out_rate, cc_rate, cr_rate = rates
    return (
        in_t * in_rate / 1_000_000
        + out_t * out_rate / 1_000_000
        + cache_c * cc_rate / 1_000_000
        + cache_r * cr_rate / 1_000_000
    )


def collect_feat_data(conn, feat_n: int) -> dict[str, Any]:
    """Aggregate every signal from console.db for a single FEAT."""
    out: dict[str, Any] = {"feat_n": feat_n}

    # Runs : sum durations, count restarts
    rows = conn.execute(
        "SELECT run_id, command, started_at, ended_at, status "
        "FROM runs WHERE feat_n = ? ORDER BY started_at",
        (feat_n,),
    ).fetchall()
    runs = []
    total_ms = 0
    for r in rows:
        d = duration_ms(r["started_at"], r["ended_at"])
        if d is not None:
            total_ms += d
        runs.append({
            "run_id": r["run_id"],
            "command": r["command"],
            "started_at": r["started_at"],
            "ended_at": r["ended_at"],
            "status": r["status"],
            "duration_ms": d,
        })
    out["runs"] = runs
    out["run_count"] = len(runs)
    out["wall_clock_ms"] = total_ms

    # Rework signal : how many separate `/sdd-full` runs on the same FEAT
    full_runs = [r for r in runs if r["command"] in ("/sdd-full", "sdd-full")]
    out["rework"] = max(0, len(full_runs) - 1)
    # Rework rate : reworks / (total successful runs) — 0.0 if no successful runs
    successful = sum(1 for r in runs if r["status"] in ("success", "partial"))
    out["rework_rate"] = round(out["rework"] / successful, 3) if successful else 0.0
    # Failed/partial runs flag — every failed run is implicit rework signal
    out["failed_runs"] = sum(1 for r in runs if r["status"] in ("failed", "cancelled"))

    # Phase-by-phase timing (codex audit follow-up) :
    # Aggregate run_phases across all runs for this FEAT, group by phase
    # name, sum durations.
    run_ids = [r["run_id"] for r in runs]
    phase_rows: list[dict[str, Any]] = []
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        ph_rows = conn.execute(
            f"SELECT phase, started_at, ended_at, status "
            f"FROM run_phases WHERE run_id IN ({placeholders}) "
            f"ORDER BY phase, started_at",
            run_ids,
        ).fetchall()
        # Group by phase
        by_phase: dict[str, dict[str, Any]] = {}
        for r in ph_rows:
            ph_name = r["phase"]
            d = duration_ms(r["started_at"], r["ended_at"])
            bucket = by_phase.setdefault(ph_name, {
                "phase": ph_name,
                "executions": 0,
                "total_ms": 0,
                "pass_count": 0,
                "fail_count": 0,
                "warn_count": 0,
                "skip_count": 0,
            })
            bucket["executions"] += 1
            if d is not None:
                bucket["total_ms"] += d
            status = (r["status"] or "").lower()
            if status == "pass":
                bucket["pass_count"] += 1
            elif status == "fail":
                bucket["fail_count"] += 1
            elif status == "warn":
                bucket["warn_count"] += 1
            elif status == "skip":
                bucket["skip_count"] += 1
        # Sort by total duration descending — highlight expensive phases
        phase_rows = sorted(by_phase.values(), key=lambda b: -b["total_ms"])
    out["phases"] = phase_rows

    # Token usage : real billed tokens per model
    tk_rows = conn.execute(
        "SELECT agent, model, "
        "SUM(input_tokens) AS in_t, SUM(output_tokens) AS out_t, "
        "SUM(cache_creation_tokens) AS cc_t, SUM(cache_read_tokens) AS cr_t, "
        "COUNT(*) AS calls "
        "FROM token_usage WHERE feat_n = ? "
        "GROUP BY agent, model",
        (feat_n,),
    ).fetchall()
    total_in = total_out = total_cc = total_cr = total_cost = total_calls = 0
    by_agent: list[dict[str, Any]] = []
    for r in tk_rows:
        in_t = r["in_t"] or 0
        out_t = r["out_t"] or 0
        cc_t = r["cc_t"] or 0
        cr_t = r["cr_t"] or 0
        cost = model_cost(r["model"], in_t, out_t, cc_t, cr_t)
        by_agent.append({
            "agent": r["agent"],
            "model": r["model"],
            "calls": r["calls"],
            "input_tokens": in_t,
            "output_tokens": out_t,
            "cache_creation_tokens": cc_t,
            "cache_read_tokens": cr_t,
            "cost_usd": round(cost, 4),
        })
        total_in += in_t
        total_out += out_t
        total_cc += cc_t
        total_cr += cr_t
        total_cost += cost
        total_calls += r["calls"]
    out["tokens_by_agent"] = by_agent
    out["tokens"] = {
        "input": total_in,
        "output": total_out,
        "cache_creation": total_cc,
        "cache_read": total_cr,
        "agent_calls": total_calls,
        "billed_total": total_in + total_out + total_cc,  # cache_read excluded
    }
    out["cost_usd"] = round(total_cost, 4)
    out["tokens_recorded"] = total_calls > 0  # signals TokenUsageMode!=off

    # Cache hit ratio (T1.4 audit 2026-06-08) — Anthropic recommendation §3.3
    # cache_read tokens are free ; the ratio cache_read / (cache_read + input)
    # measures how well the prompt cache is exploited. >50% = good ; <10% =
    # prompts not stable enough between calls.
    cache_billed = total_in + total_cc
    cache_total = total_in + total_cc + total_cr
    out["cache"] = {
        "cache_read_tokens": total_cr,
        "cache_billed_tokens": cache_billed,
        "hit_ratio_pct": round(100.0 * total_cr / cache_total, 2) if cache_total else 0.0,
    }

    # Build loop convergence stats (T2.6 audit 2026-06-08)
    # Surfaces : (a) total loops run, (b) convergence success rate, (c) max
    # streak observed (>= 2 means LLM looped on same [CLASS]), (d) top 5
    # pathological classes for this FEAT.
    try:
        from sdd_lib.build_loop_trace import get_loop_stats
        loop_stats = get_loop_stats(feat_n=feat_n)
        if loop_stats.get("available"):
            total_loops = loop_stats.get("total_loops", 0) or 0
            converged = loop_stats.get("convergence_events", 0) or 0
            out["build_loop"] = {
                "total_loops": total_loops,
                "convergence_events": converged,
                "convergence_rate_pct": round(100.0 * converged / total_loops, 2) if total_loops else 0.0,
                "max_iter_reached": loop_stats.get("max_iter_reached", 0),
                "max_streak": loop_stats.get("max_streak", 0),
                "total_iters": loop_stats.get("total_iters", 0),
                "top_pathological_classes": loop_stats.get("top_pathological_classes", []),
            }
        else:
            out["build_loop"] = None
    except Exception:  # noqa: BLE001
        out["build_loop"] = None

    # Context budget (fallback when token_usage is empty)
    cb_row = conn.execute(
        "SELECT SUM(tokens_used) AS used, "
        "       SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) AS failures, "
        "       COUNT(*) AS checks "
        "FROM context_budget WHERE feat_n = ?",
        (feat_n,),
    ).fetchone()
    out["context_budget"] = {
        "tokens_used_estimated": cb_row["used"] or 0,
        "checks": cb_row["checks"] or 0,
        "budget_failures": cb_row["failures"] or 0,
    }

    # Coverage (latest row per FEAT — schema columns per console_db_schema.sql)
    cov_row = conn.execute(
        "SELECT lines_pct, tests_total, tests_passed, tests_failed, "
        "       coverage_passed "
        "FROM qa_coverage WHERE feat_n = ? "
        "ORDER BY extracted_at DESC LIMIT 1",
        (feat_n,),
    ).fetchone()
    if cov_row:
        out["coverage"] = {
            "lines_pct": cov_row["lines_pct"],
            "tests_total": cov_row["tests_total"],
            "tests_passed": cov_row["tests_passed"],
            "tests_failed": cov_row["tests_failed"],
            "gate_passed": bool(cov_row["coverage_passed"]),
        }
    else:
        out["coverage"] = None

    # Spec compliance : AC verification rate
    sc_row = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN verdict='verified' THEN 1 ELSE 0 END) AS verified, "
        "  SUM(CASE WHEN verdict='not_verified' THEN 1 ELSE 0 END) AS not_verified, "
        "  SUM(CASE WHEN verdict='partial' THEN 1 ELSE 0 END) AS partial, "
        "  COUNT(*) AS total "
        "FROM qa_spec_compliance WHERE feat_n = ?",
        (feat_n,),
    ).fetchone()
    if sc_row and (sc_row["total"] or 0) > 0:
        total = sc_row["total"] or 0
        verified = sc_row["verified"] or 0
        out["spec_compliance"] = {
            "verified": verified,
            "not_verified": sc_row["not_verified"] or 0,
            "partial": sc_row["partial"] or 0,
            "total_acs": total,
            "verification_rate_pct": round(verified * 100.0 / total, 2),
        }
    else:
        out["spec_compliance"] = None

    # Issues count by severity (qa_quality + qa_code_review + qa_security)
    issues = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0, "info": 0}
    for table in ("qa_quality", "qa_code_review", "qa_security"):
        try:
            rows = conn.execute(
                f"SELECT severity, COUNT(*) AS n FROM {table} "
                f"WHERE feat_n = ? GROUP BY severity",
                (feat_n,),
            ).fetchall()
            for r in rows:
                sev = (r["severity"] or "").lower()
                if sev in issues:
                    issues[sev] += r["n"]
        except Exception:  # noqa: BLE001
            # Table may be missing in older DBs — skip
            pass
    out["issues"] = issues

    return out


def list_feats(conn) -> list[int]:
    """Return all feat_n values that appear in runs OR qa_coverage."""
    rows = conn.execute(
        "SELECT DISTINCT feat_n FROM runs WHERE feat_n IS NOT NULL "
        "UNION SELECT DISTINCT feat_n FROM qa_coverage WHERE feat_n IS NOT NULL "
        "ORDER BY 1"
    ).fetchall()
    return [r[0] for r in rows]


def render_markdown(payloads: list[dict[str, Any]]) -> str:
    """Render a human-readable markdown table summary for all FEATs."""
    lines = []
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines.append(f"# SDD_Pro ROI Report")
    lines.append("")
    lines.append(f"Generated : `{generated_at}`")
    lines.append(f"FEATs covered : **{len(payloads)}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| FEAT | Runs | Wall-clock | Tokens billed | Cost USD | Coverage | ACs verified | Issues C/S/M | Rework | Rework rate |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---:|---:|")

    totals_cost = 0.0
    totals_tokens = 0
    for p in payloads:
        n = p["feat_n"]
        cov = p["coverage"] or {}
        sc = p["spec_compliance"] or {}
        i = p["issues"]
        cov_str = f"{cov.get('lines_pct', '-')}%" if cov else "-"
        ac_str = (
            f"{sc.get('verification_rate_pct', '-')}% ({sc.get('verified', 0)}/{sc.get('total_acs', 0)})"
            if sc else "-"
        )
        issue_str = f"{i.get('critical', 0)}/{i.get('serious', 0)}/{i.get('moderate', 0)}"
        token_str = f"{p['tokens']['billed_total']:,}" if p["tokens_recorded"] else "(no record)"
        cost_str = f"${p['cost_usd']:.2f}" if p["tokens_recorded"] else "-"
        rework_rate_str = f"{p['rework_rate']*100:.0f}%" if p["rework_rate"] else "0%"

        lines.append(
            f"| {n} | {p['run_count']} | {fmt_duration(p['wall_clock_ms'])} | "
            f"{token_str} | {cost_str} | {cov_str} | {ac_str} | "
            f"{issue_str} | {p['rework']} | {rework_rate_str} |"
        )
        if p["tokens_recorded"]:
            totals_cost += p["cost_usd"]
            totals_tokens += p["tokens"]["billed_total"]

    lines.append("")
    lines.append(f"**Totals** : ${totals_cost:.2f} | {totals_tokens:,} billed tokens "
                 f"across {len(payloads)} FEATs.")
    lines.append("")

    # Per-FEAT detail
    for p in payloads:
        feat_label = f"FEAT {p['feat_n']}"
        # Tokens by agent (only if recorded)
        if p["tokens_by_agent"]:
            lines.append(f"## {feat_label} -- tokens by agent")
            lines.append("")
            lines.append("| Agent | Model | Calls | Input | Output | Cache C | Cache R | Cost |")
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
            for a in p["tokens_by_agent"]:
                lines.append(
                    f"| {a['agent']} | {a['model'] or '?'} | {a['calls']} | "
                    f"{a['input_tokens']:,} | {a['output_tokens']:,} | "
                    f"{a['cache_creation_tokens']:,} | {a['cache_read_tokens']:,} | "
                    f"${a['cost_usd']:.4f} |"
                )
            lines.append("")
        # Cache hit ratio (T1.4 audit 2026-06-08)
        if p.get("cache") and p["tokens_recorded"]:
            c = p["cache"]
            lines.append(f"## {feat_label} -- prompt cache utilization")
            lines.append("")
            verdict = "good (>=50%)" if c["hit_ratio_pct"] >= 50 else (
                "moderate (10-50%)" if c["hit_ratio_pct"] >= 10 else "poor (<10%)"
            )
            lines.append(f"- Cache hit ratio : **{c['hit_ratio_pct']}%** ({verdict})")
            lines.append(f"- Cache read tokens (free) : {c['cache_read_tokens']:,}")
            lines.append(f"- Billed tokens : {c['cache_billed_tokens']:,}")
            lines.append("")

        # Build loop convergence (T2.6 audit 2026-06-08)
        if p.get("build_loop"):
            bl = p["build_loop"]
            lines.append(f"## {feat_label} -- build_loop convergence")
            lines.append("")
            lines.append(f"- Total loops : {bl['total_loops']} | Convergence rate : **{bl['convergence_rate_pct']}%**")
            lines.append(f"- Total iterations : {bl['total_iters']} | Max iter reached : {bl['max_iter_reached']} | Max streak : {bl['max_streak']}")
            if bl.get("top_pathological_classes"):
                lines.append("- Top pathological `[CLASS]` :")
                for tc in bl["top_pathological_classes"]:
                    lines.append(f"  - `{tc['class']}` × {tc['occurrences']}")
            lines.append("")

        # Phase-by-phase timing (codex audit follow-up)
        if p.get("phases"):
            lines.append(f"## {feat_label} -- phase timing")
            lines.append("")
            lines.append("| Phase | Executions | Total time | Pass | Fail | Warn | Skip |")
            lines.append("|---|---:|---:|---:|---:|---:|---:|")
            for ph in p["phases"]:
                lines.append(
                    f"| {ph['phase']} | {ph['executions']} | "
                    f"{fmt_duration(ph['total_ms'])} | {ph['pass_count']} | "
                    f"{ph['fail_count']} | {ph['warn_count']} | {ph['skip_count']} |"
                )
            lines.append("")

    # Warnings (ASCII-only to avoid Windows cp1252 codec issues on stdout)
    no_token_feats = [p["feat_n"] for p in payloads if not p["tokens_recorded"]]
    if no_token_feats:
        lines.append("## WARN : token_usage not recorded")
        lines.append("")
        lines.append(
            f"FEATs without per-call token records : `{no_token_feats}`. "
            "Real cost cannot be computed. Set `TokenUsageMode: record` in "
            "`workspace/input/stack/stack.md` `## Project Config` (or env "
            "var `SDD_TOKEN_USAGE_MODE=record`) before running `/sdd-full` "
            "to enable per-invocation accounting via the PostToolUse.Agent hook."
        )
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().split("\n", 1)[0])
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--feat", type=int, help="Aggregate one FEAT")
    grp.add_argument("--all", action="store_true", help="Aggregate all FEATs")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--markdown", action="store_true",
                   help="Markdown output (default if neither --json nor stdout-redirected)")
    args = p.parse_args(argv)

    try:
        ro_ctx = connect_ro()
    except FileNotFoundError as exc:
        print(f"ERROR: report_roi — console.db not found", file=sys.stderr)
        print(f"CAUSE: [NOT_FOUND] {exc}", file=sys.stderr)
        print("FIX: run /sdd-full at least once to bootstrap, OR run "
              "init_console_db.py", file=sys.stderr)
        return FAIL_FAST
    with ro_ctx as conn:
        if args.feat is not None:
            payloads = [collect_feat_data(conn, args.feat)]
            if payloads[0]["run_count"] == 0 and payloads[0]["coverage"] is None:
                print(f"ERROR: report_roi — FEAT {args.feat} unknown "
                      f"(no runs and no coverage row)", file=sys.stderr)
                print(f"CAUSE: [FEAT_NOT_FOUND] feat_n={args.feat}", file=sys.stderr)
                return CORRECTIBLE
        else:
            feat_ns = list_feats(conn)
            payloads = [collect_feat_data(conn, n) for n in feat_ns]

    if args.json:
        print(json.dumps({"feats": payloads}, separators=(",", ":"), default=str))
    else:
        print(render_markdown(payloads))
    return SUCCESS
if __name__ == "__main__":
    raise SystemExit(main())
