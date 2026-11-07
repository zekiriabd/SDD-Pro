#!/usr/bin/env python3
"""SDD_Pro: close a pipeline run explicitly (audit « fiabilité des états » 2026-11-07).

Background
----------
`runs` accumulated rows stuck in `status='running'` forever (8/8 in the live
DB, all `command='hook'`) : hooks open a run lazily, nothing ever closed it.
This CLI is the explicit close path, idempotent, for orchestrators, the
console, or a human :

    python run_close.py --run-id 20261107T101500-ab12 --status completed --verdict GREEN
    python run_close.py --current --status failed          # run of this session
    python run_close.py --run-id X --status partial --error "QA infra down"

Statuses : completed | partial | failed (+ cancelled). Closing also removes the
session run_id marker (`workspace/.sys/.state/run-id.<session>`) when it still
points to that run, so the next hook opens a NEW run.

Exit codes : 0 closed (or already closed the same way — idempotent),
1 unknown run / invalid args, 2 success close downgraded to `failed` by the
delivery gate ([DELIVERY_GATE_BLOCKED]), 3 console.db unavailable ([INFRA_BLOCKED]).
Output : one JSON line on stdout.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect, ensure_initialized, get_run, run_end  # noqa: E402
from sdd_lib.delivery_wiring import gate_run_close  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.run_id import clear_run_id_marker, get_or_create_run_id  # noqa: E402
from sdd_lib.stderr import error_block  # noqa: E402

CLOSE_STATUSES = ("completed", "partial", "failed", "cancelled")
#: Exit code quand une clôture en succès est rétrogradée par le gate de livraison.
DELIVERY_BLOCKED_EXIT = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Close a run in console.db (idempotent).")
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--run-id", help="run_id to close")
    target.add_argument("--current", action="store_true",
                        help="close the run of the current session (env/marker)")
    p.add_argument("--session-id", default=None,
                   help="session id used with --current (default: $CLAUDE_SESSION_ID)")
    p.add_argument("--status", required=True, choices=CLOSE_STATUSES)
    p.add_argument("--verdict", default=None, help="GREEN|WARN|RED (optional)")
    p.add_argument("--error", default=None, help="error message (optional)")
    return p.parse_args(argv)


def close_run(run_id: str, status: str, verdict: str | None = None,
              error: str | None = None, session_id: str | None = None) -> dict:
    """Close `run_id` ; returns a result dict (raises sqlite3.Error on DB issue).

    Gate de livraison (2026-11-07, `.sdd/docs/delivery-gates.md`) : une clôture
    `completed|partial` d'un run de workflow de livraison (/sdd-full, /sdd-poc,
    /dev-run, /qa-generate, /sdd-review, /sdd-deploy) passe par
    `authorize_delivery` ; refus → `failed` + RED + `[DELIVERY_GATE_BLOCKED]`
    (`delivery_blocked: true` dans le résultat). Aucun flag ne lève ce gate.
    """
    ensure_initialized()
    requested = status
    status, verdict, error, decision = gate_run_close(run_id, status, verdict, error)
    blocked = status != requested
    with connect() as conn:
        if get_run(conn, run_id) is None:
            return {"status": "UNKNOWN_RUN", "run_id": run_id}
        updated = run_end(conn, run_id, status, verdict,
                          error_message=error, source="run_close.py")
        row = get_run(conn, run_id)
    marker_cleared = clear_run_id_marker(session_id, run_id=run_id)
    result = {
        "status": "CLOSED" if updated else "ALREADY_CLOSED",
        "run_id": run_id,
        "run_status": row["status"],
        "ended_at": row["ended_at"],
        "marker_cleared": marker_cleared,
    }
    if decision is not None:
        result["delivery_gate"] = decision
    if blocked:
        result["delivery_blocked"] = True
        result["requested_status"] = requested
        result["error"] = error
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = args.run_id or get_or_create_run_id(session_id=args.session_id)
    try:
        result = close_run(run_id, args.status, args.verdict, args.error, args.session_id)
    except (sqlite3.Error, OSError) as exc:
        error_block(
            f"run_close {run_id} failed",
            f"[INFRA_BLOCKED] console.db indisponible ({type(exc).__name__}: {exc})",
            "vérifier workspace/db/console.db puis relancer run_close.py",
        )
        return INFRA_BLOCKED
    print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
    if result.get("delivery_blocked"):
        error_block(
            f"run_close {run_id} — livraison refusée (statut demandé "
            f"{result['requested_status']}, run clos failed)",
            result.get("error") or "[DELIVERY_GATE_BLOCKED]",
            "exécuter verify_build.py / verify_tests.py / delivery_gate.py record-* "
            "puis `delivery_gate.py authorize` (exit 0) avant de relancer la clôture",
        )
        return DELIVERY_BLOCKED_EXIT
    return FAIL_FAST if result["status"] == "UNKNOWN_RUN" else SUCCESS


if __name__ == "__main__":
    sys.exit(main())
