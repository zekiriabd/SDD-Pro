"""sdd_lib.console_db.runs — execution model (runs / phases / events / gates / auditor_runs).

v7.0.0-alpha (audit CRIT-12, 2026-06-04) — extracted from the previous
monolithic `console_db.py`. Concerns : the lifecycle of a `/sdd-full`
or `/dev-run` execution and its auditor markers.

Public API (re-exported via `sdd_lib.console_db.__init__`) :
    upsert_run, upsert_run_phase, insert_event,
    list_runs, get_run, get_run_phases,
    insert_gate,
    record_auditor_run, auditor_ran
"""
from __future__ import annotations

import sqlite3
from typing import Any

from sdd_lib.console_db.core import _jdumps
from sdd_lib.paths import iso_now_ms


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
    """Upsert (run_id, phase) row.

    v7.0.0 audit fix 2026-05-20 — also backfills started_at on update when
    the existing row has NULL (defensive : callers historically only emitted
    end events, never start, so started_at was lost and phase timing = 0).
    """
    conn.execute(
        """
        INSERT INTO run_phases(run_id, phase, started_at, ended_at, status, payload_json)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id, phase) DO UPDATE SET
            started_at   = COALESCE(run_phases.started_at, excluded.started_at),
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
# AUDITOR_RUNS — presence markers for /sdd-review --ensure-scans
# ============================================================
# v7.0.0 P0 C3 fix : record ONE row per auditor invocation, regardless of
# findings count. fetch_findings() in sdd_review.py reads source presence
# from here instead of inferring from per-finding tables (which produced
# false-positive [REVIEW_SOURCES_MISSING] on clean scans).

def record_auditor_run(
    conn: sqlite3.Connection,
    *,
    feat_n: int,
    auditor: str,
    findings_count: int = 0,
    verdict: str | None = None,
    extracted_at: str | None = None,
    payload: Any = None,
) -> None:
    """Insert a presence marker for an auditor invocation.

    Idempotent semantics : multiple runs of the same auditor on the same
    FEAT produce multiple rows. /sdd-review reads only `EXISTS(...)` —
    duplicate rows are harmless, history-friendly, and avoid races.

    Args:
        feat_n: FEAT number.
        auditor: one of AUDITOR_IDS. Out-of-set values accepted (forward-compat
                 for future auditors) but logged callers should stay within.
        findings_count: 0 is valid (= clean scan).
        verdict: GREEN|YELLOW|RED|informational|None.
        extracted_at: ISO-8601 UTC (default: now).
        payload: optional dict (run_id, mode, etc.) — serialized as JSON.
    """
    conn.execute(
        """
        INSERT INTO auditor_runs(feat_n, auditor, extracted_at, findings_count, verdict, payload_json)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (feat_n, auditor, extracted_at or iso_now_ms(), findings_count, verdict, _jdumps(payload)),
    )


def auditor_ran(conn: sqlite3.Connection, *, feat_n: int, auditor: str) -> bool:
    """True iff at least one row exists for (feat_n, auditor) in auditor_runs."""
    row = conn.execute(
        "SELECT 1 FROM auditor_runs WHERE feat_n = ? AND auditor = ? LIMIT 1",
        (feat_n, auditor),
    ).fetchone()
    return row is not None
