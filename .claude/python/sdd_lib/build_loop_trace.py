"""Build-loop trace + convergence detection (audit T2.6 — 2026-06-08).

Provides two primitives :

1. `record_iter(...)` — persist one iteration in `build_loop_traces`.
2. `should_stop_for_convergence(...)` — query the table and return True if
   the same `[CLASS]` has been emitted N times in a row (default 2) — signal
   that the LLM is looping on the same error without progress.

Rationale (Anthropic recommendation §3.2) :
    `BuildLoopMaxIter: 3` is arbitrary. Without convergence detection, the
    framework spends 3× the budget on identical failure patterns, then
    emits [BUILD_LOOP_EXHAUSTED]. With convergence detection, we cut the
    cost as soon as the loop is provably non-progressing.

Usage in dev-* agents (or wrapping scripts) :

    from sdd_lib.build_loop_trace import record_iter, should_stop_for_convergence

    for i in range(1, max_iter + 1):
        rc, stderr = run_build()
        err_class = parse_error_class(stderr)  # [BUILD_CORRECTIBLE], etc.
        prev = record_iter(
            run_id=run_id, feat_n=1, us_id="1-2", agent="dev-backend",
            iter=i, error_class_after=err_class, converged=(rc == 0),
        )
        if rc == 0:
            break
        if should_stop_for_convergence(us_id="1-2", agent="dev-backend",
                                       streak_threshold=2):
            # Same [CLASS] twice → loop is stuck, no point retrying
            raise BuildLoopStuck(err_class)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from sdd_lib.paths import repo_root


def _connect() -> sqlite3.Connection | None:
    db_path = repo_root() / "workspace" / "output" / "db" / "console.db"
    if not db_path.is_file():
        return None
    try:
        return sqlite3.connect(str(db_path))
    except sqlite3.Error:
        return None


def record_iter(
    *,
    run_id: str | None,
    feat_n: int | None,
    us_id: str,
    agent: str,
    iter: int,
    error_class_before: str | None = None,
    error_class_after: str | None = None,
    fix_strategy: str | None = None,
    converged: bool = False,
    duration_ms: int | None = None,
    notes: str | None = None,
) -> int | None:
    """Persist one build_loop iteration. Returns rowid (or None if DB unavailable).

    Computes `same_class_streak` automatically from previous rows : if the
    previous iter for the same (us_id, agent) had `error_class_after` equal
    to the new one, streak = previous_streak + 1, else 1.
    """
    conn = _connect()
    if conn is None:
        return None

    try:
        # Compute streak by reading previous iter for same (us_id, agent)
        streak = 1
        if error_class_after and not converged:
            cur = conn.execute(
                """
                SELECT error_class_after, same_class_streak
                  FROM build_loop_traces
                 WHERE us_id = ? AND agent = ?
              ORDER BY id DESC
                 LIMIT 1
                """,
                (us_id, agent),
            )
            row = cur.fetchone()
            if row and row[0] == error_class_after:
                streak = (row[1] or 0) + 1

        cur = conn.execute(
            """
            INSERT INTO build_loop_traces (
                run_id, feat_n, us_id, agent, iter,
                error_class_before, error_class_after, fix_strategy,
                converged, same_class_streak, duration_ms, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, feat_n, us_id, agent, iter,
                error_class_before, error_class_after, fix_strategy,
                1 if converged else 0, streak, duration_ms, notes,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def should_stop_for_convergence(
    *,
    us_id: str,
    agent: str,
    streak_threshold: int = 2,
) -> bool:
    """Return True if the latest iter recorded for (us_id, agent) has
    `same_class_streak >= streak_threshold` — meaning the same [CLASS]
    has appeared `streak_threshold` times in a row.

    Default threshold = 2 : the second time we see the same error,
    the loop is provably stuck. Stricter than the old BuildLoopMaxIter:3
    which waited for the 3rd failure to give up.

    Returns False if no trace yet (first iter) or DB unavailable.
    """
    conn = _connect()
    if conn is None:
        return False
    try:
        cur = conn.execute(
            """
            SELECT same_class_streak, converged
              FROM build_loop_traces
             WHERE us_id = ? AND agent = ?
          ORDER BY id DESC
             LIMIT 1
            """,
            (us_id, agent),
        )
        row = cur.fetchone()
        if not row:
            return False
        streak, converged = row
        if converged:
            return False  # build went green, no convergence problem
        return (streak or 0) >= streak_threshold
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def get_loop_stats(*, feat_n: int | None = None) -> dict:
    """Return aggregate stats for monitoring / dashboards.

    Useful for `/sdd-status` and ROI reports : how many loops converged on
    first iter, how many got stuck, which [CLASS] are most pathological.
    """
    conn = _connect()
    if conn is None:
        return {"available": False}
    try:
        where = "WHERE feat_n = ?" if feat_n is not None else ""
        params = (feat_n,) if feat_n is not None else ()

        cur = conn.execute(
            f"""
            SELECT
                COUNT(DISTINCT us_id || '|' || agent) AS total_loops,
                SUM(CASE WHEN converged = 1 THEN 1 ELSE 0 END) AS convergence_events,
                MAX(iter) AS max_iter_reached,
                MAX(same_class_streak) AS max_streak,
                COUNT(*) AS total_iters
              FROM build_loop_traces
            {where}
            """,
            params,
        )
        row = cur.fetchone()

        cur2 = conn.execute(
            f"""
            SELECT error_class_after, COUNT(*) AS n
              FROM build_loop_traces
              {where}
              {'AND' if where else 'WHERE'} converged = 0 AND error_class_after IS NOT NULL
          GROUP BY error_class_after
          ORDER BY n DESC
             LIMIT 5
            """,
            params,
        )
        top_classes = [{"class": r[0], "occurrences": r[1]} for r in cur2.fetchall()]

        return {
            "available": True,
            "total_loops": row[0] or 0,
            "convergence_events": row[1] or 0,
            "max_iter_reached": row[2] or 0,
            "max_streak": row[3] or 0,
            "total_iters": row[4] or 0,
            "top_pathological_classes": top_classes,
        }
    except sqlite3.Error as e:
        return {"available": False, "error": str(e)}
    finally:
        conn.close()
