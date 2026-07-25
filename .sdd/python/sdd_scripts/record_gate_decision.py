#!/usr/bin/env python3
"""Record a console-initiated gate decision into console.db (table `gates`).

v7.0.0 P0 C2 fix : console.web `/api/gate-decide` was writing only to
`workspace/console/status.json` + SSE broadcast — the `gates` table
(historical analytics) was left empty, so /api/gates returned a partial
history and the Analytics dashboard diverged from the actual workflow.

This script is invoked by `workspace/console/server.js` after a
successful status.json write. It is best-effort : the user's gate
action is already persisted in status.json (the runtime source of
truth), so a DB write failure here is logged but does NOT fail the
HTTP response. status.json remains canonical for live state ; the
`gates` table is for cross-FEAT historical queries.

Usage (spawned from Node) :
    python -m sdd_scripts.record_gate_decision \\
        --feat-n 1 \\
        --gate-name us \\
        --decision validated \\
        --by-user alice@example.com \\
        --comment "reviewed AC-3 mapping" \\
        [--decided-at 2026-05-20T14:32:18Z]

Exit codes :
    0 : row inserted
    2 : invalid argument (bad enum, missing required field)
    3 : DB write failed (console.db absent / locked / corrupt)

The Node caller treats exit ≠ 0 as a warning, not an error — see
server.js /api/gate-decide handler.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect, ensure_initialized, insert_gate  # noqa: E402
from sdd_lib.paths import iso_now_ms  # noqa: E402
from sdd_lib.exit_codes import INFRA_BLOCKED, SUCCESS  # noqa: E402


# Canonical gate names recognized by the historical analytics.
# Symmetric with workspace/console/server.js VALID_PHASES.
VALID_GATE_NAMES = ("us", "readiness", "plan", "code", "api", "qa")

# Decision values are stored verbatim — preserves UI fidelity and avoids
# lossy mapping. The `gates.decision` column is TEXT with no CHECK
# constraint, so any value the API accepts can land here.
VALID_DECISIONS = ("validated", "skipped", "pending", "pass", "fail", "wait")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--feat-n", type=int, required=True,
                   help="FEAT number (integer).")
    p.add_argument("--gate-name", required=True, choices=VALID_GATE_NAMES,
                   help="Canonical gate identifier.")
    p.add_argument("--decision", required=True, choices=VALID_DECISIONS,
                   help="Decision value (stored verbatim).")
    p.add_argument("--by-user", default=None,
                   help="User identifier (email/login). Optional.")
    p.add_argument("--comment", default=None,
                   help="Free-text comment (max 1000 chars, truncated). Optional.")
    p.add_argument("--decided-at", default=None,
                   help="ISO-8601 UTC timestamp. Default: now.")
    p.add_argument("--run-id", default=None,
                   help="Associated run_id (FK to runs). Optional — console "
                        "gates rarely have one (they happen between runs).")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    payload: dict[str, object] = {"source": "console-web"}
    if args.comment:
        payload["comment"] = args.comment[:1000]

    try:
        ensure_initialized()
        with connect() as conn:
            insert_gate(
                conn,
                gate_name=args.gate_name,
                decision=args.decision,
                feat_n=args.feat_n,
                run_id=args.run_id,
                decided_at=args.decided_at or iso_now_ms(),
                by_user=args.by_user,
                payload=payload,
            )
    except Exception as e:
        # Best-effort : caller (Node) decides whether to surface this as
        # a warning. status.json already holds the user-visible decision.
        print(f"ERROR: console.db gate insert failed: {e}", file=sys.stderr)
        return INFRA_BLOCKED
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
