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


# Anthropic pricing 2026 (USD per 1M tokens) — kept in sync with
# docs/poc-roi-methodology.md. Update on pricing change.
# Pattern : (input_per_M, output_per_M, cache_creation_per_M, cache_read_per_M)
PRICING_TABLE: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-4-7":          (15.00, 75.00, 18.75, 1.50),
    "claude-opus-4-6":          (15.00, 75.00, 18.75, 1.50),
    "claude-sonnet-4-6":        (3.00,  15.00, 3.75,  0.30),
    "claude-sonnet-4-5":        (3.00,  15.00, 3.75,  0.30),
    "claude-haiku-4-5":         (1.00,  5.00,  1.25,  0.10),
    "claude-haiku-4-5-20251001": (1.00,  5.00,  1.25,  0.10),
}
DEFAULT_PRICING = (3.00, 15.00, 3.75, 0.30)  # Sonnet fallback for unknown models


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
    if model is None:
        rates = DEFAULT_PRICING
    else:
        rates = PRICING_TABLE.get(model, DEFAULT_PRICING)
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
    lines.append("| FEAT | Runs | Wall-clock | Tokens billed | Cost USD | Coverage | ACs verified | Issues C/S/M | Rework |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---:|")

    totals_cost = 0.0
    totals_tokens = 0
    for p in payloads:
        n = p["feat_n"]
        cov = p["coverage"] or {}
        sc = p["spec_compliance"] or {}
        i = p["issues"]
        cov_str = f"{cov.get('lines_pct', '—')}%" if cov else "—"
        ac_str = (
            f"{sc.get('verification_rate_pct', '—')}% ({sc.get('verified', 0)}/{sc.get('total_acs', 0)})"
            if sc else "—"
        )
        issue_str = f"{i.get('critical', 0)}/{i.get('serious', 0)}/{i.get('moderate', 0)}"
        token_str = f"{p['tokens']['billed_total']:,}" if p["tokens_recorded"] else "(no record)"
        cost_str = f"${p['cost_usd']:.2f}" if p["tokens_recorded"] else "—"

        lines.append(
            f"| {n} | {p['run_count']} | {fmt_duration(p['wall_clock_ms'])} | "
            f"{token_str} | {cost_str} | {cov_str} | {ac_str} | "
            f"{issue_str} | {p['rework']} |"
        )
        if p["tokens_recorded"]:
            totals_cost += p["cost_usd"]
            totals_tokens += p["tokens"]["billed_total"]

    lines.append("")
    lines.append(f"**Totals** : ${totals_cost:.2f} · {totals_tokens:,} billed tokens "
                 f"across {len(payloads)} FEATs.")
    lines.append("")

    # Per-FEAT detail (tokens by agent if recorded)
    for p in payloads:
        if not p["tokens_by_agent"]:
            continue
        lines.append(f"## FEAT {p['feat_n']} — tokens by agent")
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
        return 1

    with ro_ctx as conn:
        if args.feat is not None:
            payloads = [collect_feat_data(conn, args.feat)]
            if payloads[0]["run_count"] == 0 and payloads[0]["coverage"] is None:
                print(f"ERROR: report_roi — FEAT {args.feat} unknown "
                      f"(no runs and no coverage row)", file=sys.stderr)
                print(f"CAUSE: [FEAT_NOT_FOUND] feat_n={args.feat}", file=sys.stderr)
                return 2
        else:
            feat_ns = list_feats(conn)
            payloads = [collect_feat_data(conn, n) for n in feat_ns]

    if args.json:
        print(json.dumps({"feats": payloads}, separators=(",", ":"), default=str))
    else:
        print(render_markdown(payloads))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
