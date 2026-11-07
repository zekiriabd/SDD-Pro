"""sdd_lib.console_db.runs — execution model (runs / phases / events / gates / auditor_runs).

v7.0.0-alpha (audit CRIT-12, 2026-06-04) — extracted from the previous
monolithic `console_db.py`. Concerns : the lifecycle of a `/sdd-full`
or `/dev-run` execution and its auditor markers.

Public API (re-exported via `sdd_lib.console_db.__init__`) :
    upsert_run, upsert_run_phase, insert_event,
    list_runs, get_run, get_run_phases,
    run_end, RUN_TERMINAL_STATUSES, RUN_END_STATUSES,
    insert_gate, get_latest_gate, list_latest_gates,
    record_auditor_run, auditor_ran

Audit « fiabilité des données et des états » (2026-11-07) :
    - ``run_end()`` : clôture idempotente d'un run (``completed|partial|
      failed``) — avant, les runs ouverts par les hooks (``command='hook'``)
      restaient ``running`` pour toujours.
    - ``get_latest_gate()`` / ``list_latest_gates()`` : la table ``gates`` est
      désormais la **source de vérité** des gates manuels ; ``status.json``
      n'est plus qu'un export dérivé (cf. ``gate_decide.export_status_json``).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from sdd_lib.console_db.core import _jdumps
from sdd_lib.paths import iso_now_ms

#: Statuts acceptés par ``run_end()``. ``completed`` est le nom canonique ;
#: ``success`` reste accepté (alias historique de ``sdd_state.py end-run``).
RUN_END_STATUSES: frozenset[str] = frozenset(
    {"completed", "success", "partial", "failed", "cancelled", "stale"}
)
#: Statuts qui signifient « le run n'est plus actif ».
RUN_TERMINAL_STATUSES: frozenset[str] = RUN_END_STATUSES


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


def run_end(
    conn: sqlite3.Connection,
    run_id: str,
    status: str = "completed",
    verdict: str | None = None,
    *,
    ended_at: str | None = None,
    error_message: str | None = None,
    source: str | None = None,
) -> bool:
    """Close a run idempotently.

    Args:
        run_id: the run to close (must exist — returns False otherwise, no
            row is invented).
        status: ``completed`` (canonical) | ``success`` (alias) | ``partial``
            | ``failed`` | ``cancelled`` | ``stale``.
        verdict: optional aggregated verdict (``GREEN``/``WARN``/``RED``…),
            stored in ``params_json.verdict`` (the ``runs`` table has no
            dedicated column — schema unchanged).
        ended_at: ISO-8601 UTC ; defaults to now. An already-ended run keeps
            its original ``ended_at``.
        error_message / source: free-text context (source = who closed :
            ``sdd_state.end-run``, ``run_close.py``, ``set-phase:sdd_review``…).

    Idempotence : if the run is already terminal with the SAME status (and
    same verdict when one is given), nothing is written and no event is
    emitted → returns False. A different terminal status re-closes the run
    (last word wins) and emits a ``run.end`` event carrying ``previous``.

    Returns True if a row was updated.

    Raises ValueError on an unknown status.
    """
    if status not in RUN_END_STATUSES:
        raise ValueError(
            f"run_end: status {status!r} invalide — attendu un de "
            f"{sorted(RUN_END_STATUSES)}"
        )
    row = get_run(conn, run_id)
    if row is None:
        return False
    try:
        params = json.loads(row["params_json"]) if row["params_json"] else {}
    except (TypeError, ValueError):
        params = {"_raw_params": row["params_json"]}
    if not isinstance(params, dict):
        params = {"_raw_params": params}
    prev_status = row["status"]
    prev_verdict = params.get("verdict")
    if prev_status in RUN_TERMINAL_STATUSES and prev_status == status \
            and (verdict is None or verdict == prev_verdict):
        return False  # already closed the same way — no-op

    now = iso_now_ms()
    if verdict is not None:
        params["verdict"] = verdict
    if source:
        params["closed_by"] = source
    conn.execute(
        """
        UPDATE runs
           SET status = ?,
               ended_at = COALESCE(ended_at, ?),
               updated_at = ?,
               params_json = ?,
               error_message = COALESCE(?, error_message)
         WHERE run_id = ?
        """,
        (status, ended_at or now, now, _jdumps(params), error_message, run_id),
    )
    payload: dict[str, Any] = {"status": status}
    if verdict is not None:
        payload["verdict"] = verdict
    if prev_status in RUN_TERMINAL_STATUSES:
        payload["previous"] = prev_status
    if source:
        payload["source"] = source
    insert_event(
        conn, event_type="run.end", ts=now, run_id=run_id,
        feat_n=row["feat_n"], payload=payload,
    )
    return True


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


def _gate_row_to_state(row: sqlite3.Row) -> dict[str, Any]:
    """Project a ``gates`` row onto the status.json gate shape."""
    try:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
    except (TypeError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    state: dict[str, Any] = {"decision": row["decision"]}
    for key in ("askedAt", "answeredAt", "answeredBy"):
        if payload.get(key) is not None:
            state[key] = payload[key]
    if row["by_user"] and "answeredBy" not in state:
        state["answeredBy"] = row["by_user"]
    if row["decision"] in ("validated", "skipped") and "answeredAt" not in state:
        state["answeredAt"] = row["decided_at"]
    if row["decision"] == "pending" and "askedAt" not in state:
        state["askedAt"] = row["decided_at"]
    state["decidedAt"] = row["decided_at"]
    return state


def get_latest_gate(
    conn: sqlite3.Connection,
    *,
    feat_n: int,
    gate_name: str,
) -> dict[str, Any] | None:
    """Current state of a manual gate = its most recent ``gates`` row.

    Returns a dict shaped like a status.json gate
    (``decision`` + ``askedAt``/``answeredAt``/``answeredBy`` when known,
    plus ``decidedAt``), or None if the gate was never posed.
    """
    row = conn.execute(
        """
        SELECT * FROM gates
         WHERE feat_n = ? AND gate_name = ?
         ORDER BY id DESC
         LIMIT 1
        """,
        (feat_n, gate_name),
    ).fetchone()
    return _gate_row_to_state(row) if row is not None else None


def list_latest_gates(
    conn: sqlite3.Connection,
    *,
    feat_n: int | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """``{feat_key: {gate_name: state}}`` — latest row per (feat_n, gate_name).

    This is the projection exported to ``workspace/console/status.json``.
    """
    sql = """
        SELECT g.* FROM gates g
          JOIN (
            SELECT feat_n, gate_name, MAX(id) AS max_id
              FROM gates
             WHERE feat_n IS NOT NULL
             GROUP BY feat_n, gate_name
          ) last ON last.max_id = g.id
    """
    params: tuple[Any, ...] = ()
    if feat_n is not None:
        sql += " WHERE g.feat_n = ?"
        params = (feat_n,)
    sql += " ORDER BY g.feat_n, g.gate_name"
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in conn.execute(sql, params).fetchall():
        out.setdefault(str(row["feat_n"]), {})[row["gate_name"]] = _gate_row_to_state(row)
    return out


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
