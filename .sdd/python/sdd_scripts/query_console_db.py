#!/usr/bin/env python3
"""SDD_Pro v6.10 — Read-only queries against workspace/db/console.db.

Thin CLI on top of common questions slash commands ask the DB (gate
decision, run status, feat overview, perf verdict, …). Output is JSON
so PowerShell / Bash callers can pipe through `jq` / `python -c`.

Subcommands:
    api-gate    --feat N            → {gate_passed, tests_total, tests_failed, endpoints_total}
    coverage    --feat N            → {lines_pct_avg, coverage_passed, stacks: [...]}
    quality     --feat N            → {errors, warnings, info, total}
    perf        --feat N            → {verdict, critical, serious, moderate, minor}
    spec        --feat N            → {verified, not_verified, partial}
    security    --feat N            → {scan_verdict, threats_total, critical, serious}
    a11y        --feat N            → {verdict, critical, serious, moderate, minor}
    run-latest  --feat N            → {run_id, status, current_phase, started_at}
    feat-stats  --feat N            → consolidated overview across all qa_*

Predicate subcommands (exit 0 = fresh findings present, exit 1 = absent/stale ;
TTL via --max-age-hours, default 24h) :
    arch-review-present      --feat N   → qa_code_review, classes ARCH_*
    code-review-present      --feat N   → qa_code_review, classes non-ARCH_*
    security-present         --feat N   → qa_security, mode 'scan'
    spec-compliance-present  --feat N   → qa_spec_compliance

Output format:
    --format json (default)   → machine-readable JSON on stdout
    --format md               → human-readable Markdown (on-demand render;
                                 no file is ever written to disk). For
                                 `review` the full consolidated report is
                                 recomputed live from the qa_* tables — this
                                 replaces the former workspace/qa/
                                 feat-{n}/review.md file (removed 2026-07-06).

Exit codes:
    0 = data present (query succeeded, even if empty result)
    1 = DB unreachable / corrupted
    2 = unknown subcommand
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect_ro  # noqa: E402  (RO reader — no WAL, no init)
from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402


def _dict_row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def query_api_gate(feat: int) -> dict:
    """Return the most recent API Gate row for `feat`.

    v7.0.0-alpha audit P3 (2026-06-06) — exposes both `status` (canonical
    PASS|WARN|FAIL|SKIPPED|INFRA_BLOCKED, cf. build-and-loop.md §1.3) and
    `gate_passed` (legacy boolean). Callers should prefer `status` when
    available so that SKIPPED is distinguishable from PASS.

    On pre-v5 DBs where the column did not yet exist, the `status` field is
    derived from the boolean+counters for forward compatibility.
    """
    with connect_ro() as conn:
        # Detect column presence to stay tolerant of pre-migration DBs opened
        # for read-only inspection (no auto-migration on RO connections).
        cols = {r[1] for r in conn.execute("PRAGMA table_info(qa_api_tests)")}
        has_status = "status" in cols
        select = (
            "SELECT gate_passed, status, tests_total, tests_passed, "
            "tests_failed, endpoints_total, extracted_at"
            if has_status else
            "SELECT gate_passed, tests_total, tests_passed, tests_failed, "
            "endpoints_total, extracted_at"
        )
        row = conn.execute(
            f"{select} FROM qa_api_tests WHERE feat_n = ? "
            "ORDER BY id DESC LIMIT 1",
            (feat,),
        ).fetchone()
    if row is None:
        return {"present": False}
    d = dict(row)
    d["present"] = True
    d["gate_passed"] = bool(d["gate_passed"])
    if not has_status or not d.get("status"):
        # Derive canonical status for legacy rows / pre-migration DBs.
        if (d.get("tests_failed") or 0) >= 1:
            d["status"] = "FAIL"
        elif d["gate_passed"] and (d.get("tests_total") or 0) == 0:
            d["status"] = "SKIPPED"
        elif d["gate_passed"]:
            d["status"] = "PASS"
        else:
            d["status"] = "FAIL"
    return d


def query_coverage(feat: int) -> dict:
    with connect_ro() as conn:
        rows = conn.execute(
            """
            SELECT stack, lines_pct, lines_covered, lines_total,
                   tests_total, tests_passed, tests_failed,
                   coverage_min, coverage_passed
              FROM qa_coverage WHERE feat_n = ? ORDER BY stack
            """,
            (feat,),
        ).fetchall()
    if not rows:
        return {"present": False}
    stacks = [dict(r) for r in rows]
    total_covered = sum(s["lines_covered"] or 0 for s in stacks)
    total_lines = sum(s["lines_total"] or 0 for s in stacks)
    avg_pct = round((total_covered / total_lines) * 100, 2) if total_lines else 0.0
    cov_min = max((s["coverage_min"] or 0) for s in stacks)
    return {
        "present": True,
        "stacks": stacks,
        "lines_pct_avg": avg_pct,
        "coverage_min": cov_min,
        "coverage_passed": avg_pct >= cov_min,
    }


def query_quality(feat: int) -> dict:
    with connect_ro() as conn:
        rows = conn.execute(
            "SELECT severity, COUNT(*) FROM qa_quality WHERE feat_n = ? GROUP BY severity",
            (feat,),
        ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    return {
        "present": bool(rows),
        "errors":   counts.get("error", 0),
        "warnings": counts.get("warning", 0),
        "info":     counts.get("info", 0),
        "total":    sum(counts.values()),
    }


def _severity_counts(conn: sqlite3.Connection, table: str, feat: int, extra_where: str = "",
                     params: tuple = ()) -> dict:
    sql = f"""
        SELECT severity, COUNT(*) FROM {table}
         WHERE feat_n = ? {extra_where}
         GROUP BY severity
    """
    rows = conn.execute(sql, (feat,) + params).fetchall()
    return {r[0]: r[1] for r in rows}


def query_perf(feat: int) -> dict:
    with connect_ro() as conn:
        c = _severity_counts(conn, "qa_performance", feat)
        verdict_row = conn.execute(
            "SELECT verdict FROM qa_performance WHERE feat_n = ? "
            "ORDER BY id DESC LIMIT 1",
            (feat,),
        ).fetchone()
    return {
        "present": bool(c) or verdict_row is not None,
        "verdict": _dict_row(verdict_row).get("verdict") if verdict_row else None,
        "critical": c.get("critical", 0),
        "serious":  c.get("serious", 0),
        "moderate": c.get("moderate", 0),
        "minor":    c.get("minor", 0),
    }


def query_a11y(feat: int) -> dict:
    with connect_ro() as conn:
        c = _severity_counts(conn, "qa_a11y", feat)
        verdict_row = conn.execute(
            "SELECT verdict FROM qa_a11y WHERE feat_n = ? "
            "ORDER BY id DESC LIMIT 1",
            (feat,),
        ).fetchone()
    return {
        "present": bool(c) or verdict_row is not None,
        "verdict": _dict_row(verdict_row).get("verdict") if verdict_row else None,
        "critical": c.get("critical", 0),
        "serious":  c.get("serious", 0),
        "moderate": c.get("moderate", 0),
        "minor":    c.get("minor", 0),
    }


def query_spec(feat: int) -> dict:
    with connect_ro() as conn:
        rows = conn.execute(
            "SELECT verdict, COUNT(*) FROM qa_spec_compliance WHERE feat_n = ? GROUP BY verdict",
            (feat,),
        ).fetchall()
    by_status = {r[0]: r[1] for r in rows}
    return {
        "present":      bool(rows),
        "verified":     by_status.get("verified", 0),
        "not_verified": by_status.get("not_verified", 0),
        "partial":      by_status.get("partial", 0),
        "ambiguous":    by_status.get("ambiguous", 0),
        "total":        sum(by_status.values()),
    }


def query_security(feat: int) -> dict:
    with connect_ro() as conn:
        scan = _severity_counts(conn, "qa_security", feat, "AND mode = ?", ("scan",))
        threats = conn.execute(
            "SELECT COUNT(*) FROM qa_security WHERE feat_n = ? AND mode = 'threat-model'",
            (feat,),
        ).fetchone()[0]
        verdict = conn.execute(
            "SELECT verdict FROM qa_security WHERE feat_n = ? AND mode = 'scan' "
            "ORDER BY id DESC LIMIT 1",
            (feat,),
        ).fetchone()
    return {
        "present":        bool(scan) or threats > 0,
        "scan_verdict":   verdict[0] if verdict else None,
        "scan_critical":  scan.get("critical", 0),
        "scan_serious":   scan.get("serious", 0),
        "scan_moderate":  scan.get("moderate", 0),
        "scan_minor":     scan.get("minor", 0),
        "threats_total":  threats,
    }


def query_run_latest(feat: int) -> dict:
    with connect_ro() as conn:
        row = conn.execute(
            "SELECT run_id, command, status, current_phase, started_at, ended_at "
            "FROM runs WHERE feat_n = ? ORDER BY started_at DESC LIMIT 1",
            (feat,),
        ).fetchone()
    if row is None:
        return {"present": False}
    d = dict(row)
    d["present"] = True
    return d


def query_feat_stats(feat: int) -> dict:
    return {
        "feat":      feat,
        "api_gate":  query_api_gate(feat),
        "coverage":  query_coverage(feat),
        "quality":   query_quality(feat),
        "perf":      query_perf(feat),
        "a11y":      query_a11y(feat),
        "security":  query_security(feat),
        "spec":      query_spec(feat),
        "run":       query_run_latest(feat),
    }


def query_arch_review_present(feat: int, max_age_hours: int = 24) -> dict:
    """Predicate query : are there FRESH `[ARCH_*]` findings persisted for this FEAT ?

    v7.0.0-alpha (audit CRIT-4) : used by `/sdd-review §3.0` to decide
    whether to spawn `arch-reviewer` as a standalone fallback. When the
    invocation arrives downstream of `/dev-run §6.4`, the agent has
    already run and findings exist — fallback is skipped.

    v7.0.1 (audit C4 closure 2026-06-07) : added TTL filter (default 24h)
    via `max_age_hours`. Stale findings (e.g. /dev-run ran 7 days ago and
    the code has since changed) are ignored → fallback re-runs the agent.
    This eliminates the silent "skip on stale data" failure mode that
    earlier audit feared. Override via CLI flag `--max-age-hours N`
    (0 = disable TTL, accept any age — legacy v7.0.0 behavior).

    Predicate semantics : main() returns exit 0 when ≥ 1 fresh ``[ARCH_*]``
    row exists in `qa_code_review` for this FEAT, exit 1 otherwise. The
    JSON payload (always emitted on stdout) carries count + max_age_hours
    for debugging.
    """
    with connect_ro() as conn:
        if max_age_hours and max_age_hours > 0:
            row = conn.execute(
                "SELECT COUNT(*) FROM qa_code_review "
                "WHERE feat_n = ? AND issue_class LIKE 'ARCH_%' "
                f"AND extracted_at > datetime('now', '-{int(max_age_hours)} hours')",
                (feat,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM qa_code_review "
                "WHERE feat_n = ? AND issue_class LIKE 'ARCH_%'",
                (feat,),
            ).fetchone()
    count = int(row[0]) if row else 0
    return {
        "present":   count > 0,
        "feat":      feat,
        "count":     count,
        "max_age_hours": max_age_hours,
        "_exit_code": 0 if count > 0 else 1,
    }


def query_spec_compliance_present(feat: int, max_age_hours: int = 24) -> dict:
    """Predicate query : are there FRESH spec-compliance findings persisted for this FEAT ?

    v7.0.0+ (two-stage auditor pattern, superpowers v5.1) : used by
    `/sdd-review §3.0.bis` and `/dev-run §6.4.A` to decide whether to
    spawn `spec-compliance-reviewer` as Stage A gate. When the invocation
    arrives downstream of a recent run, the agent has already run and
    findings exist — fallback is skipped.

    TTL filter (default 24h) via `max_age_hours`. Stale findings (e.g.
    code changed since last run) are ignored → fallback re-runs the agent.
    Override via CLI flag `--max-age-hours N` (0 = disable TTL).

    Predicate semantics : main() returns exit 0 when ≥ 1 fresh row exists
    in `qa_spec_compliance` for this FEAT, exit 1 otherwise. The JSON
    payload (always emitted on stdout) carries count + max_age_hours.
    """
    with connect_ro() as conn:
        if max_age_hours and max_age_hours > 0:
            row = conn.execute(
                "SELECT COUNT(*) FROM qa_spec_compliance "
                "WHERE feat_n = ? "
                f"AND extracted_at > datetime('now', '-{int(max_age_hours)} hours')",
                (feat,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM qa_spec_compliance WHERE feat_n = ?",
                (feat,),
            ).fetchone()
    count = int(row[0]) if row else 0
    return {
        "present":   count > 0,
        "feat":      feat,
        "count":     count,
        "max_age_hours": max_age_hours,
        "_exit_code": 0 if count > 0 else 1,
    }


def query_code_review_present(feat: int, max_age_hours: int = 24) -> dict:
    """Predicate query : are there FRESH code-review findings persisted for this FEAT ?

    v7.0.1 (audit F-M1 2026-08-30) : used by `/sdd-review §3.0` (fallback
    standalone) to decide whether to spawn `code-reviewer`. Miroir exact de
    `query_arch_review_present` — même table `qa_code_review`, mais en
    EXCLUANT les classes `[ARCH_*]` (persistées dans la même table par
    `arch-reviewer` et déjà couvertes par `arch-review-present`).

    TTL filter (default 24h) via `max_age_hours`. Stale findings (code
    changed since last run) are ignored → fallback re-runs the agent.
    Override via CLI flag `--max-age-hours N` (0 = disable TTL).

    Predicate semantics : main() returns exit 0 when ≥ 1 fresh non-ARCH row
    exists in `qa_code_review` for this FEAT, exit 1 otherwise. The JSON
    payload (always emitted on stdout) carries count + max_age_hours.
    """
    with connect_ro() as conn:
        if max_age_hours and max_age_hours > 0:
            row = conn.execute(
                "SELECT COUNT(*) FROM qa_code_review "
                "WHERE feat_n = ? AND issue_class NOT LIKE 'ARCH_%' "
                f"AND extracted_at > datetime('now', '-{int(max_age_hours)} hours')",
                (feat,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM qa_code_review "
                "WHERE feat_n = ? AND issue_class NOT LIKE 'ARCH_%'",
                (feat,),
            ).fetchone()
    count = int(row[0]) if row else 0
    return {
        "present":   count > 0,
        "feat":      feat,
        "count":     count,
        "max_age_hours": max_age_hours,
        "_exit_code": 0 if count > 0 else 1,
    }


def query_security_present(feat: int, max_age_hours: int = 24) -> dict:
    """Predicate query : are there FRESH security-scan findings persisted for this FEAT ?

    v7.0.1 (audit F-M1 2026-08-30) : used by `/sdd-review §3.0` (fallback
    standalone) to decide whether to spawn `security-reviewer`. Miroir exact
    de `query_spec_compliance_present`, source `qa_security` restreinte au
    mode `scan` (le mode `threat-model` pré-dev ne prouve pas qu'un scan
    post-dev a tourné).

    TTL filter (default 24h) via `max_age_hours`. Stale findings (code
    changed since last run) are ignored → fallback re-runs the agent.
    Override via CLI flag `--max-age-hours N` (0 = disable TTL).

    Predicate semantics : main() returns exit 0 when ≥ 1 fresh scan row
    exists in `qa_security` for this FEAT, exit 1 otherwise. The JSON
    payload (always emitted on stdout) carries count + max_age_hours.
    """
    with connect_ro() as conn:
        if max_age_hours and max_age_hours > 0:
            row = conn.execute(
                "SELECT COUNT(*) FROM qa_security "
                "WHERE feat_n = ? AND mode = 'scan' "
                f"AND extracted_at > datetime('now', '-{int(max_age_hours)} hours')",
                (feat,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM qa_security WHERE feat_n = ? AND mode = 'scan'",
                (feat,),
            ).fetchone()
    count = int(row[0]) if row else 0
    return {
        "present":   count > 0,
        "feat":      feat,
        "count":     count,
        "max_age_hours": max_age_hours,
        "_exit_code": 0 if count > 0 else 1,
    }


def query_review(feat: int) -> dict:
    """Read latest /sdd-review run for FEAT (table validation_reports, type='review')."""
    with connect_ro() as conn:
        row = conn.execute(
            "SELECT verdict, score, summary, payload_json, extracted_at, file_path "
            "FROM validation_reports "
            "WHERE feat_n=? AND report_type='review' "
            "ORDER BY id DESC LIMIT 1",
            (feat,),
        ).fetchone()
    if not row:
        return {"present": False}
    payload = {}
    try:
        payload = json.loads(row[3]) if row[3] else {}
    except Exception:
        payload = {"_parse_error": True}
    return {
        "present":      True,
        "verdict":      row[0],
        "total":        row[1],
        "summary":      row[2],
        "extracted_at": row[4],
        "markdown":     row[5],
        "counts":       payload.get("counts", {}),
        "fail_on":      payload.get("fail_on"),
        "top_classes":  payload.get("top_classes", {}),
        "scans_run":    payload.get("scans_run", []),
        "skipped_sources": payload.get("skipped_sources", []),
    }


DISPATCH = {
    "api-gate":              query_api_gate,
    "coverage":              query_coverage,
    "quality":               query_quality,
    "perf":                  query_perf,
    "a11y":                  query_a11y,
    "spec":                  query_spec,
    "security":              query_security,
    "review":                query_review,
    "arch-review-present":         query_arch_review_present,    # v7.0.0-alpha audit CRIT-4
    "spec-compliance-present":     query_spec_compliance_present, # v7.0.0+ two-stage gate
    "code-review-present":         query_code_review_present,     # v7.0.1 audit F-M1 2026-08-30
    "security-present":            query_security_present,        # v7.0.1 audit F-M1 2026-08-30
    "run-latest":            query_run_latest,
    "feat-stats":            query_feat_stats,
}

# Predicate-style subcommands : main() propagates `_exit_code` from the
# payload so callers can use the script as a shell predicate (exit 0 = yes,
# exit 1 = no), in addition to consuming the JSON on stdout.
_PREDICATE_SUBCOMMANDS = {
    "arch-review-present",
    "spec-compliance-present",
    "code-review-present",
    "security-present",
}


def _render_review_md(feat: int, result: dict) -> str:
    """Recompute the consolidated /sdd-review report live from qa_* tables and
    render it as Markdown. Replaces the former review.md disk file (2026-07-06)."""
    from sdd_scripts._review_fetch import fetch_findings
    from sdd_scripts._review_report import compute_report, render_markdown
    findings, missing = fetch_findings(feat)
    fail_on = (result.get("fail_on") or "serious")
    report = compute_report(feat, findings, missing, fail_on)
    return render_markdown(report)


def _render_generic_md(subcommand: str, feat: int, result: dict) -> str:
    """Fallback Markdown for the flat per-dimension queries (quality, coverage,
    security, spec, api-gate, perf, a11y, feat-stats)."""
    lines = [f"# console.db — `{subcommand}` — FEAT {feat}", ""]

    def _kv_table(title: str, d: dict) -> None:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Champ | Valeur |")
        lines.append("|---|---|")
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            lines.append(f"| `{k}` | {str(v).replace(chr(124), chr(92) + chr(124))} |")
        lines.append("")

    if subcommand == "feat-stats":
        for dim, payload in result.items():
            if isinstance(payload, dict):
                _kv_table(dim, payload)
            else:
                lines.append(f"- **{dim}** : {payload}")
        lines.append("")
    else:
        _kv_table(subcommand, result)

    lines.append("---")
    lines.append(f"Source de vérité : `console.db` (rendu à la demande, "
                 f"aucun fichier écrit). Re-run : "
                 f"`query_console_db.py {subcommand} --feat {feat} --format md`")
    return "\n".join(lines) + "\n"


def render_markdown_output(subcommand: str, feat: int, result: dict) -> str:
    # `review` is recomputed live from the qa_* tables — always render it even
    # when no consolidated validation_reports row was persisted yet.
    if subcommand == "review":
        return _render_review_md(feat, result)
    if not result.get("present", True):
        return (f"# console.db — `{subcommand}` — FEAT {feat}\n\n"
                f"_Aucune donnée en base pour cette FEAT._\n")
    return _render_generic_md(subcommand, feat, result)


def main(argv: list[str] | None = None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(prog="query_console_db",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("subcommand", choices=sorted(DISPATCH.keys()))
    parser.add_argument("--feat", type=int, required=True)
    parser.add_argument("--format", choices=("json", "md"), default="json",
                        help="Output format. `md` renders a human-readable report "
                             "on-demand from console.db (no file written).")
    parser.add_argument("--max-age-hours", type=int, default=24,
                        help="(*-present predicate subcommands, v7.0.1 audit C4) TTL "
                             "filter for freshness check ; 0 disables. Default 24h.")
    args = parser.parse_args(argv)

    try:
        if args.subcommand in _PREDICATE_SUBCOMMANDS:
            result = DISPATCH[args.subcommand](args.feat, max_age_hours=args.max_age_hours)
        else:
            result = DISPATCH[args.subcommand](args.feat)
    except FileNotFoundError as exc:
        sys.stderr.write(f"ERROR: query_console_db: {exc}\n")
        return CORRECTIBLE
    except Exception as exc:
        sys.stderr.write(f"ERROR: query_console_db: {exc}\n")
        return FAIL_FAST

    if args.format == "md" and args.subcommand not in _PREDICATE_SUBCOMMANDS:
        try:
            sys.stdout.write(render_markdown_output(args.subcommand, args.feat, result))
        except Exception as exc:
            sys.stderr.write(f"ERROR: query_console_db: markdown render failed: {exc}\n")
            return FAIL_FAST
    else:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        sys.stdout.write("\n")
    if args.subcommand in _PREDICATE_SUBCOMMANDS:
        return int(result.get("_exit_code", 0))
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
