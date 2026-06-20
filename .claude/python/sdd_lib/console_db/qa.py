"""sdd_lib.console_db.qa — QA inserts, telemetry, validation reports.

v7.0.0-alpha (audit CRIT-12, 2026-06-04) — extracted from the previous
monolithic `console_db.py`. Concerns : every write to a `qa_*` table,
plus token usage, context budget, and validation reports.

Public API (re-exported via `sdd_lib.console_db.__init__`) :
    insert_qa_coverage,           replace_qa_coverage_for_feat,
    insert_qa_quality_batch,      replace_qa_quality_for_feat,
    insert_qa_api_tests,          replace_qa_api_tests_for_feat,
    insert_qa_a11y_batch,
    insert_qa_code_review_batch,
    insert_qa_security_batch,
    insert_qa_performance_batch,
    insert_qa_spec_compliance_batch,
    replace_qa_auditor_for_feat,
    insert_token_usage, insert_context_budget,
    insert_validation_report, replace_validation_reports
"""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from sdd_lib.console_db.core import _jdumps, ensure_feat_row, ensure_us_row
from sdd_lib.paths import iso_now_ms


# ============================================================
# QA — coverage
# ============================================================

def insert_qa_coverage(
    conn: sqlite3.Connection,
    *,
    feat_n: int,
    stack: str,
    extracted_at: str | None = None,
    tool: str | None = None,
    tool_version: str | None = None,
    tests_total: int = 0,
    tests_passed: int = 0,
    tests_failed: int = 0,
    tests_skipped: int = 0,
    lines_covered: int = 0,
    lines_total: int = 0,
    lines_pct: float | None = None,
    branches_covered: int | None = None,
    branches_total: int | None = None,
    branches_pct: float | None = None,
    coverage_min: int | None = None,
    coverage_passed: bool = False,
    files: list[dict[str, Any]] | None = None,
) -> int:
    ensure_feat_row(conn, feat_n=feat_n)
    cur = conn.execute(
        """
        INSERT INTO qa_coverage(feat_n, extracted_at, stack, tool, tool_version,
            tests_total, tests_passed, tests_failed, tests_skipped,
            lines_covered, lines_total, lines_pct,
            branches_covered, branches_total, branches_pct,
            coverage_min, coverage_passed)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (feat_n, extracted_at or iso_now_ms(), stack, tool, tool_version,
         tests_total, tests_passed, tests_failed, tests_skipped,
         lines_covered, lines_total, lines_pct,
         branches_covered, branches_total, branches_pct,
         coverage_min, 1 if coverage_passed else 0),
    )
    coverage_id = cur.lastrowid
    if files:
        conn.executemany(
            "INSERT INTO qa_coverage_files(coverage_id, file_path, lines_pct) VALUES(?, ?, ?)",
            [(coverage_id, f.get("path"), f.get("lines_pct")) for f in files],
        )
    return coverage_id


def replace_qa_coverage_for_feat(conn: sqlite3.Connection, feat_n: int) -> None:
    """Wipe prior coverage rows for a FEAT before inserting fresh ones."""
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM qa_coverage WHERE feat_n = ?", (feat_n,)
    ).fetchall()]
    if ids:
        placeholders = ",".join("?" * len(ids))
        # f-string in cursor.execute is SAFE here : `placeholders` is a
        # generated string of `?` markers (count derived from `ids` length,
        # internal data). The actual values are passed parameterized in
        # the second argument. NOT user-controlled — no SQL injection
        # surface. (audit AP-5 # nosec annotation 2026-06-08)
        conn.execute(  # nosec — placeholders=trusted count, values parameterized
            f"DELETE FROM qa_coverage_files WHERE coverage_id IN ({placeholders})", ids
        )
        conn.execute("DELETE FROM qa_coverage WHERE feat_n = ?", (feat_n,))


# ============================================================
# QA — quality
# ============================================================

def insert_qa_quality_batch(
    conn: sqlite3.Connection,
    *,
    feat_n: int,
    extracted_at: str | None = None,
    issues: Iterable[dict[str, Any]],
) -> int:
    """Insert multiple quality issues. Each issue dict supports keys:
        severity, issue_class (or category), rule (or tag), file_path (or file),
        line, message.
    Returns the count inserted.
    """
    ensure_feat_row(conn, feat_n=feat_n)
    ts = extracted_at or iso_now_ms()
    rows = []
    for it in issues:
        rows.append((
            feat_n, ts,
            it.get("severity"),
            it.get("issue_class") or it.get("category"),
            it.get("rule") or it.get("tag"),
            it.get("file_path") or it.get("file"),
            it.get("line"),
            it.get("message"),
        ))
    if rows:
        conn.executemany(
            """
            INSERT INTO qa_quality(feat_n, extracted_at, severity, issue_class,
                                    rule, file_path, line, message)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def replace_qa_quality_for_feat(conn: sqlite3.Connection, feat_n: int) -> None:
    conn.execute("DELETE FROM qa_quality WHERE feat_n = ?", (feat_n,))


# ============================================================
# QA — api tests
# ============================================================

def insert_qa_api_tests(
    conn: sqlite3.Connection,
    *,
    feat_n: int,
    gate_passed: bool,
    extracted_at: str | None = None,
    endpoints_total: int = 0,
    tests_total: int = 0,
    tests_passed: int = 0,
    tests_failed: int = 0,
    endpoints: list[dict[str, Any]] | None = None,
    status: str | None = None,
) -> int:
    """Insert an API Gate run for `feat_n`.

    v7.0.0-alpha audit P3 (2026-06-06) — `status` is the canonical 5-valued
    verdict (PASS | WARN | FAIL | SKIPPED | INFRA_BLOCKED) defined in
    `build-and-loop.md §1.3`. When the caller doesn't provide it (legacy code
    paths), it is best-effort derived from `gate_passed` + `tests_failed` +
    `tests_total` so the column is never NULL on writes from current callers.

    `gate_passed` is preserved for backward-compat readers (cf. query_api_gate)
    and computed as `status ∈ {PASS, WARN, SKIPPED}`.
    """
    ensure_feat_row(conn, feat_n=feat_n)
    if status is None:
        # Legacy callers : derive from boolean. Subset of the canonical mapping.
        if tests_failed >= 1:
            status = "FAIL"
        elif gate_passed and tests_total == 0:
            status = "SKIPPED"
        elif gate_passed:
            status = "PASS"
        else:
            status = "FAIL"
    else:
        status = status.strip().upper()
    cur = conn.execute(
        """
        INSERT INTO qa_api_tests(feat_n, extracted_at, gate_passed, status,
            endpoints_total, tests_total, tests_passed, tests_failed)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (feat_n, extracted_at or iso_now_ms(), 1 if gate_passed else 0,
         status, endpoints_total, tests_total, tests_passed, tests_failed),
    )
    api_test_id = cur.lastrowid
    if endpoints:
        conn.executemany(
            """
            INSERT INTO qa_api_endpoints(api_test_id, verb, route,
                tests_total, tests_passed, tests_failed, cases_json)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            [(api_test_id, e.get("verb"), e.get("route"),
              (e.get("tests") or {}).get("total", 0),
              (e.get("tests") or {}).get("passed", 0),
              (e.get("tests") or {}).get("failed", 0),
              _jdumps(e.get("cases"))) for e in endpoints],
        )
    return api_test_id


def replace_qa_api_tests_for_feat(conn: sqlite3.Connection, feat_n: int) -> None:
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM qa_api_tests WHERE feat_n = ?", (feat_n,)
    ).fetchall()]
    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM qa_api_endpoints WHERE api_test_id IN ({placeholders})", ids)
        conn.execute("DELETE FROM qa_api_tests WHERE feat_n = ?", (feat_n,))


# ============================================================
# QA — auditor reports (a11y, code_review, security, performance)
# ============================================================

def insert_qa_a11y_batch(
    conn: sqlite3.Connection, *, feat_n: int, verdict: str | None,
    issues: Iterable[dict[str, Any]], extracted_at: str | None = None,
) -> int:
    ensure_feat_row(conn, feat_n=feat_n)
    ts = extracted_at or iso_now_ms()
    rows = [(
        feat_n, ts, verdict,
        it.get("issue_class") or it.get("class"),
        it.get("severity"), it.get("wcag"),
        it.get("file_path") or it.get("file"),
        it.get("line"), it.get("message"),
    ) for it in issues]
    if rows:
        conn.executemany(
            """
            INSERT INTO qa_a11y(feat_n, extracted_at, verdict, issue_class,
                                severity, wcag, file_path, line, message)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def insert_qa_code_review_batch(
    conn: sqlite3.Connection, *, feat_n: int, verdict: str | None,
    issues: Iterable[dict[str, Any]], extracted_at: str | None = None,
) -> int:
    ensure_feat_row(conn, feat_n=feat_n)
    ts = extracted_at or iso_now_ms()
    rows = [(
        feat_n, ts, verdict,
        it.get("issue_class") or it.get("class"),
        it.get("severity"),
        it.get("file_path") or it.get("file"),
        it.get("line"), it.get("message"),
    ) for it in issues]
    if rows:
        conn.executemany(
            """
            INSERT INTO qa_code_review(feat_n, extracted_at, verdict, issue_class,
                                        severity, file_path, line, message)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def insert_qa_security_batch(
    conn: sqlite3.Connection, *, feat_n: int, mode: str, verdict: str | None,
    issues: Iterable[dict[str, Any]], extracted_at: str | None = None,
) -> int:
    """mode: 'threat-model' or 'scan'."""
    ensure_feat_row(conn, feat_n=feat_n)
    ts = extracted_at or iso_now_ms()
    rows = [(
        feat_n, mode, ts, verdict,
        it.get("issue_class") or it.get("class"),
        it.get("severity"), it.get("owasp"), it.get("cwe"), it.get("stride"),
        it.get("file_path") or it.get("file"),
        it.get("line"), it.get("message"), it.get("control"),
    ) for it in issues]
    if rows:
        conn.executemany(
            """
            INSERT INTO qa_security(feat_n, mode, extracted_at, verdict, issue_class,
                                     severity, owasp, cwe, stride, file_path, line,
                                     message, control)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def insert_qa_performance_batch(
    conn: sqlite3.Connection, *, feat_n: int, verdict: str | None,
    issues: Iterable[dict[str, Any]], extracted_at: str | None = None,
) -> int:
    ensure_feat_row(conn, feat_n=feat_n)
    ts = extracted_at or iso_now_ms()
    rows = [(
        feat_n, ts, verdict,
        it.get("issue_class") or it.get("class"),
        it.get("severity"), it.get("metric"),
        it.get("metric_value"), it.get("metric_unit"),
        it.get("threshold"),
        it.get("file_path") or it.get("file"),
        it.get("line"), it.get("message"),
    ) for it in issues]
    if rows:
        conn.executemany(
            """
            INSERT INTO qa_performance(feat_n, extracted_at, verdict, issue_class,
                                        severity, metric, metric_value, metric_unit,
                                        threshold, file_path, line, message)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def insert_qa_spec_compliance_batch(
    conn: sqlite3.Connection, *, feat_n: int, entries: Iterable[dict[str, Any]],
    extracted_at: str | None = None,
) -> int:
    """Each entry dict: us_id, ac_id, verdict, severity, evidence_file, evidence_line, message."""
    ensure_feat_row(conn, feat_n=feat_n)
    ts = extracted_at or iso_now_ms()
    entries = list(entries)
    seen_us = {e["us_id"] for e in entries}
    for us_id in seen_us:
        ensure_us_row(conn, us_id=us_id, feat_n=feat_n)
    rows = [(
        feat_n, it["us_id"], it["ac_id"], ts,
        it.get("verdict") or it.get("status"),
        it.get("severity"),
        it.get("evidence_file"), it.get("evidence_line"),
        it.get("message"),
    ) for it in entries]
    if rows:
        conn.executemany(
            """
            INSERT INTO qa_spec_compliance(feat_n, us_id, ac_id, extracted_at,
                                            verdict, severity, evidence_file,
                                            evidence_line, message)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def replace_qa_auditor_for_feat(
    conn: sqlite3.Connection, table: str, feat_n: int, mode: str | None = None
) -> None:
    """Wipe prior rows for a FEAT in the given qa_* table before re-inserting."""
    valid = {
        "qa_a11y", "qa_code_review", "qa_security", "qa_performance",
        "qa_spec_compliance",
    }
    if table not in valid:
        raise ValueError(f"unsupported table {table!r}")
    if table == "qa_security" and mode:
        conn.execute(f"DELETE FROM {table} WHERE feat_n = ? AND mode = ?", (feat_n, mode))
    else:
        conn.execute(f"DELETE FROM {table} WHERE feat_n = ?", (feat_n,))


# ============================================================
# Telemetry — token_usage, context_budget, validation_reports
# ============================================================

def insert_token_usage(
    conn: sqlite3.Connection,
    *,
    agent: str,
    model: str | None = None,
    ts: str | None = None,
    run_id: str | None = None,
    feat_n: int | None = None,
    us_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO token_usage(ts, run_id, agent, model, feat_n, us_id,
            input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts or iso_now_ms(), run_id, agent, model, feat_n, us_id,
         input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens),
    )


def insert_context_budget(
    conn: sqlite3.Connection,
    *,
    agent: str,
    tokens_used: int,
    tokens_budget: int,
    passed: bool,
    ts: str | None = None,
    feat_n: int | None = None,
    us_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO context_budget(ts, agent, feat_n, us_id,
                                    tokens_used, tokens_budget, passed)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (ts or iso_now_ms(), agent, feat_n, us_id,
         tokens_used, tokens_budget, 1 if passed else 0),
    )


def insert_validation_report(
    conn: sqlite3.Connection,
    *,
    feat_n: int,
    report_type: str,
    verdict: str | None,
    extracted_at: str | None = None,
    score: int | None = None,
    summary: str | None = None,
    payload: Any = None,
    file_path: str | None = None,
) -> None:
    """report_type: 'readiness'|'plan-validate'|'fidelity'|'augment-contract'."""
    ensure_feat_row(conn, feat_n=feat_n)
    conn.execute(
        """
        INSERT INTO validation_reports(feat_n, report_type, extracted_at,
            verdict, score, summary, payload_json, file_path)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (feat_n, report_type, extracted_at or iso_now_ms(),
         verdict, score, summary, _jdumps(payload), file_path),
    )


def replace_validation_reports(
    conn: sqlite3.Connection, *, feat_n: int, report_type: str,
) -> None:
    conn.execute(
        "DELETE FROM validation_reports WHERE feat_n = ? AND report_type = ?",
        (feat_n, report_type),
    )
