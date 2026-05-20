#!/usr/bin/env python3
"""SDD_Pro v6.10 — Read-only queries against workspace/output/db/console.db.

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


def _dict_row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def query_api_gate(feat: int) -> dict:
    with connect_ro() as conn:
        row = conn.execute(
            """
            SELECT gate_passed, tests_total, tests_passed, tests_failed,
                   endpoints_total, extracted_at
              FROM qa_api_tests
             WHERE feat_n = ?
             ORDER BY id DESC LIMIT 1
            """,
            (feat,),
        ).fetchone()
    if row is None:
        return {"present": False}
    d = dict(row)
    d["present"] = True
    d["gate_passed"] = bool(d["gate_passed"])
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
    "api-gate":   query_api_gate,
    "coverage":   query_coverage,
    "quality":    query_quality,
    "perf":       query_perf,
    "a11y":       query_a11y,
    "spec":       query_spec,
    "security":   query_security,
    "review":     query_review,
    "run-latest": query_run_latest,
    "feat-stats": query_feat_stats,
}


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
    args = parser.parse_args(argv)

    try:
        result = DISPATCH[args.subcommand](args.feat)
    except FileNotFoundError as exc:
        sys.stderr.write(f"ERROR: query_console_db: {exc}\n")
        return 2
    except Exception as exc:
        sys.stderr.write(f"ERROR: query_console_db: {exc}\n")
        return 1

    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
