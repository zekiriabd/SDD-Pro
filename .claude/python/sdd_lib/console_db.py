"""SDD_Pro Console DB — helper module for SQLite access.

Source de vérité unique pour télémétrie/QA/runs.
Localisation par défaut : workspace/output/db/console.db

Usage minimal :
    from sdd_lib.console_db import connect, insert_event, upsert_run

    with connect() as conn:
        upsert_run(conn, run_id=..., command=..., feat_n=..., status="running")

Pragmas appliqués automatiquement à la connexion :
    - journal_mode = WAL          → lectures concurrentes pendant écritures
    - synchronous  = NORMAL       → bon compromis durabilité/perf en WAL
    - busy_timeout = 5000 ms      → tolère 5s d'attente sur lock
    - foreign_keys = ON
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from sdd_lib.paths import iso_now_ms, repo_root

SCHEMA_VERSION = 1
SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "console_db_schema.sql"


def default_db_path() -> Path:
    """Resolve workspace/output/db/console.db relative to the repo root."""
    return repo_root() / "workspace" / "output" / "db" / "console.db"


DEFAULT_DB_PATH = default_db_path()


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")


def _apply_pragmas_ro(conn: sqlite3.Connection) -> None:
    """Read-only pragmas: skip journal_mode mutation (read-only TX cannot ALTER
    the journal mode), but still set query_only as a defense-in-depth and a
    timeout to coexist with writers in WAL mode."""
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 5000")


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection with pragmas applied, commit on success, rollback on exception."""
    db_path = Path(db_path) if db_path is not None else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _apply_pragmas(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def connect_ro(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Read-only connection — safe on read-only filesystems / sandboxes.

    Unlike ``connect()``:
    - Opens via URI with ``mode=ro`` (no implicit CREATE).
    - Does NOT mkdir the parent directory (no write to FS).
    - Does NOT issue ``PRAGMA journal_mode=WAL`` (which requires writing the
      ``-wal``/``-shm`` files; harmless on RW DBs, but breaks on RO mounts).
    - Does NOT call ``ensure_initialized()`` — caller responsibility.
    - Raises a clear ``FileNotFoundError`` if the DB does not exist.

    Used by pure readers : ``report_token_usage.py``, ``query_console_db.py``,
    and the Node-side ``/api/audit`` / ``/api/state`` via the same convention.
    """
    db_path = Path(db_path) if db_path is not None else default_db_path()
    if not db_path.exists():
        raise FileNotFoundError(
            f"console.db not found at {db_path} — run /sdd-full or "
            f"init_console_db.py to bootstrap before opening in read-only mode."
        )
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        _apply_pragmas_ro(conn)
        yield conn
    finally:
        conn.close()


def load_schema_sql() -> str:
    return SCHEMA_SQL_PATH.read_text(encoding="utf-8")


def current_schema_version(conn: sqlite3.Connection) -> int | None:
    """Return current schema_version row, or None if table is missing or empty."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return None
    row = conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def ensure_initialized(db_path: Path | str | None = None) -> None:
    """Initialize the DB lazily if it does not yet exist.

    Allows writer scripts to be safe even if /sdd-full has not run init_console_db
    explicitly. Idempotent: no-op if the DB is already at SCHEMA_VERSION.
    """
    with connect(db_path) as conn:
        v = current_schema_version(conn)
        if v == SCHEMA_VERSION:
            return
        if v is None:
            conn.executescript(load_schema_sql())
            conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
                (SCHEMA_VERSION, iso_now_ms()),
            )


def _jdumps(obj: Any) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def ensure_feat_row(
    conn: sqlite3.Connection,
    *,
    feat_n: int,
    name: str | None = None,
    file_path: str | None = None,
) -> None:
    """Ensure a minimal `feats` row exists (FK target for qa_* tables).

    Used by writers that arrive before a full metadata ingest has run. Idempotent:
    leaves an existing row untouched. Caller is responsible for richer metadata
    via a dedicated ingest path (see future ingest_metadata.py)."""
    conn.execute(
        """
        INSERT OR IGNORE INTO feats(feat_n, name, file_path, ingested_at)
        VALUES(?, ?, ?, ?)
        """,
        (feat_n, name or f"feat-{feat_n}", file_path or "", iso_now_ms()),
    )


def ensure_us_row(
    conn: sqlite3.Connection,
    *,
    us_id: str,
    feat_n: int,
    n: int | None = None,
    m: int | None = None,
    name: str | None = None,
    file_path: str | None = None,
) -> None:
    """Ensure a minimal `us` row exists. Idempotent INSERT OR IGNORE."""
    if n is None or m is None:
        # parse "n-m-..." or "n-m"
        parts = us_id.split("-", 2)
        if len(parts) >= 2:
            try:
                n = int(parts[0]) if n is None else n
                m = int(parts[1]) if m is None else m
            except ValueError:
                n = n or 0
                m = m or 0
    ensure_feat_row(conn, feat_n=feat_n)
    conn.execute(
        """
        INSERT OR IGNORE INTO us(us_id, feat_n, n, m, name, file_path, ingested_at)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (us_id, feat_n, n or 0, m or 0, name or us_id, file_path or "", iso_now_ms()),
    )


# ============================================================
# RUNS / PHASES / EVENTS
# ============================================================

def upsert_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    command: str,
    feat_n: int | None = None,
    feat_name: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    status: str = "running",
    current_phase: str | None = None,
    tags: list[str] | None = None,
    params: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    now = iso_now_ms()
    conn.execute(
        """
        INSERT INTO runs(run_id, command, feat_n, feat_name, started_at, ended_at,
                          updated_at, status, current_phase, tags_json, params_json,
                          error_message)
        VALUES(?, ?, ?, ?, COALESCE(?, ?), ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            command       = excluded.command,
            feat_n        = COALESCE(excluded.feat_n, runs.feat_n),
            feat_name     = COALESCE(excluded.feat_name, runs.feat_name),
            ended_at      = COALESCE(excluded.ended_at, runs.ended_at),
            updated_at    = ?,
            status        = excluded.status,
            current_phase = COALESCE(excluded.current_phase, runs.current_phase),
            tags_json     = COALESCE(excluded.tags_json, runs.tags_json),
            params_json   = COALESCE(excluded.params_json, runs.params_json),
            error_message = COALESCE(excluded.error_message, runs.error_message)
        """,
        (
            run_id, command, feat_n, feat_name, started_at, now, ended_at, now,
            status, current_phase, _jdumps(tags), _jdumps(params), error_message,
            now,
        ),
    )


def upsert_run_phase(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    phase: str,
    status: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    payload: Any = None,
) -> None:
    """Upsert (run_id, phase) row. New rows get started_at; updates preserve it."""
    conn.execute(
        """
        INSERT INTO run_phases(run_id, phase, started_at, ended_at, status, payload_json)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id, phase) DO UPDATE SET
            ended_at     = COALESCE(excluded.ended_at, run_phases.ended_at),
            status       = excluded.status,
            payload_json = COALESCE(excluded.payload_json, run_phases.payload_json)
        """,
        (run_id, phase, started_at, ended_at, status, _jdumps(payload)),
    )


def insert_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    ts: str | None = None,
    run_id: str | None = None,
    feat_n: int | None = None,
    us_id: str | None = None,
    agent: str | None = None,
    phase: str | None = None,
    payload: Any = None,
) -> None:
    conn.execute(
        """
        INSERT INTO events(ts, run_id, feat_n, us_id, event_type, agent, phase, payload_json)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts or iso_now_ms(), run_id, feat_n, us_id, event_type, agent, phase,
            _jdumps(payload),
        ),
    )


def list_runs(
    conn: sqlite3.Connection,
    *,
    feat_n: int | None = None,
    limit: int = 20,
) -> list[sqlite3.Row]:
    if feat_n is not None and feat_n > 0:
        return conn.execute(
            "SELECT * FROM runs WHERE feat_n = ? ORDER BY started_at DESC LIMIT ?",
            (feat_n, limit),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,),
    ).fetchall()


def get_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()


def get_run_phases(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM run_phases WHERE run_id = ? ORDER BY started_at",
        (run_id,),
    ).fetchall()


# ============================================================
# GATES
# ============================================================

def insert_gate(
    conn: sqlite3.Connection,
    *,
    gate_name: str,
    decision: str,
    feat_n: int | None = None,
    run_id: str | None = None,
    decided_at: str | None = None,
    by_user: str | None = None,
    payload: Any = None,
) -> None:
    conn.execute(
        """
        INSERT INTO gates(run_id, feat_n, gate_name, decided_at, decision, by_user, payload_json)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, feat_n, gate_name, decided_at or iso_now_ms(), decision, by_user,
         _jdumps(payload)),
    )


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
        conn.execute(f"DELETE FROM qa_coverage_files WHERE coverage_id IN ({placeholders})", ids)
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
) -> int:
    ensure_feat_row(conn, feat_n=feat_n)
    cur = conn.execute(
        """
        INSERT INTO qa_api_tests(feat_n, extracted_at, gate_passed,
            endpoints_total, tests_total, tests_passed, tests_failed)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (feat_n, extracted_at or iso_now_ms(), 1 if gate_passed else 0,
         endpoints_total, tests_total, tests_passed, tests_failed),
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
