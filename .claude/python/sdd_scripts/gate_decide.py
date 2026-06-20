#!/usr/bin/env python3
"""SDD_Pro: atomic read/write of workspace/console/status.json -> gates.{n}.afterX.

Shares the same lock file (workspace/console/.status.lock) as the Node console.
Called by /sdd-full to pose pending gates and detect human decisions.

CROSS-LANGUAGE SYMMETRY (load-bearing): this module shares the same
lock protocol as workspace/console/lib/atomic-write.js:
  - same lock path: <dirname(filePath)>/.status.lock
  - same stale TTL: 10000 ms (10_000 on Node side)
  - same retry count: 5
  - same atomicity: O_EXCL create
Any change must be replicated on both sides. Verified by
framework_smoke.py check `console-lock-symmetry`.

CONCURRENCY MODEL (audit C6 closure, 2026-06-07):
  - `pose-pending` and `set`: ACQUIRE the lock for the whole read-modify-write
    cycle → safe under concurrent writers (both this script AND the Fastify
    console).
  - `read` and `is-resolved`: LOCKLESS by design (cheap predicate queries).
    They MAY see slightly-stale state between a concurrent `set` and the
    fsync-replace. This is acceptable because:
      (a) gate state transitions are monotonic (pending → validated|skipped
          terminal — no back-transitions in normal flow), so a stale read
          can only delay action by one polling cycle, never corrupt logic.
      (b) callers that need transactional read-then-act should use
          `is-resolved` (idempotent predicate) in a retry loop, NOT
          `read` → app logic → `set`. Pattern:
              while ! python gate_decide.py is-resolved --feat-num X --phase Y ; do
                  sleep 5  # poll until human resolves
              done
      (c) the only legitimate writer of `validated|skipped` is the Fastify
          console (or a human via gate_decide.py set). /sdd-full never
          writes `validated` from the read-set pattern — it only writes
          `pending` via pose-pending (already locked).
  If a caller really needs a CAS (compare-and-set) atomic op, the future
  v7.1.0 `gate_decide.py cas-set` action will provide it (out of scope here).

Usage:
    python gate_decide.py read         --feat-num 1 --phase afterUS
        -> stdout: pending|validated|skipped|none

    python gate_decide.py pose-pending --feat-num 1 --phase afterUS
        -> sets decision=pending, askedAt=now

    python gate_decide.py set --feat-num 1 --phase afterUS \\
                             --decision skipped --answered-by "user@x.fr"
        -> sets decision=skipped|validated, answeredAt=now

    python gate_decide.py is-resolved --feat-num 1 --phase afterUS
        -> exit 0 if validated|skipped, exit 1 otherwise

Migrated from .claude/scripts/gate-decide.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

# sdd_lib is sibling package — add parent dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.console_db import connect, ensure_initialized, insert_gate  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.file_locks import acquire_with_retry, release  # noqa: E402
from sdd_lib.paths import iso_now  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


VALID_PHASES = ("afterUS", "afterReadiness", "afterPlan", "afterCode")
VALID_DECISIONS = ("pending", "validated", "skipped", "none")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)

    for name in ("read", "pose-pending", "set", "is-resolved"):
        s = sub.add_parser(name)
        s.add_argument("--feat-num", type=int, required=True)
        s.add_argument("--phase", required=True, choices=VALID_PHASES)
        s.add_argument("--status-file", default="workspace/console/status.json")
        s.add_argument("--json", action="store_true")
        if name == "set":
            s.add_argument("--decision", required=True,
                           choices=[d for d in VALID_DECISIONS if d != "none"])
            s.add_argument(
                "--answered-by",
                default=f"{os.environ.get('USERNAME') or getpass.getuser()}@local",
            )
    return p.parse_args()


def acquire_lock(lock_path: Path) -> None:
    """Acquire the status.json lock — identical protocol as Fastify console
    (`workspace/console/lib/atomic-write.js`). 10s TTL, 5 retries, 50ms backoff."""
    acquire_with_retry(lock_path, payload_prefix="py", ttl_ms=10000, retry_count=5, backoff_ms=50)


def release_lock(lock_path: Path) -> None:
    release(lock_path)


def read_status(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "version":   1,
            "updatedAt": iso_now(),
            "FEATs":     {},
            "gates":     {},
        }
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw = ""
    if not raw.strip():
        return {"version": 1, "FEATs": {}, "gates": {}}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = {"version": 1, "FEATs": {}, "gates": {}}
    if not isinstance(obj, dict):
        obj = {"version": 1, "FEATs": {}, "gates": {}}
    obj.setdefault("FEATs", {})
    obj.setdefault("gates", {})
    return obj


def write_status(path: Path, status: dict[str, Any]) -> None:
    status["updatedAt"] = iso_now()
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(
        json.dumps(status, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(path)


def ensure_gate(status: dict[str, Any], feat_key: str, phase: str) -> dict[str, Any]:
    gates = status.setdefault("gates", {})
    feat_gates = gates.setdefault(feat_key, {})
    return feat_gates.setdefault(phase, {})


def get_gate(status: dict[str, Any], feat_key: str, phase: str) -> dict[str, Any] | None:
    gates = status.get("gates", {})
    if not isinstance(gates, dict):
        return None
    feat_gates = gates.get(feat_key)
    if not isinstance(feat_gates, dict):
        return None
    g = feat_gates.get(phase)
    return g if isinstance(g, dict) else None


def main() -> int:
    args = parse_args()
    status_file = Path(args.status_file)
    feat_key = str(args.feat_num)
    lock_path = status_file.parent / ".status.lock"

    if args.action == "read":
        if not status_file.is_file():
            print('{"decision":"none"}' if args.json else "none")
            return SUCCESS
        status = read_status(status_file)
        gate = get_gate(status, feat_key, args.phase)
        decision = gate.get("decision", "none") if gate else "none"
        if args.json:
            payload = gate if gate else {"decision": "none"}
            print(json.dumps(payload, separators=(",", ":")))
        else:
            print(decision)
        return SUCCESS

    if args.action == "is-resolved":
        # is-resolved predicate: returns 0/1 as boolean answer (not error code)
        if not status_file.is_file():
            return FAIL_FAST
        status = read_status(status_file)
        gate = get_gate(status, feat_key, args.phase)
        if not gate:
            return FAIL_FAST
        return 0 if gate.get("decision") in ("validated", "skipped") else 1

    if args.action == "pose-pending":
        acquire_lock(lock_path)
        try:
            status = read_status(status_file)
            gate = ensure_gate(status, feat_key, args.phase)
            gate["decision"] = "pending"
            gate["askedAt"] = iso_now()
            gate.pop("answeredAt", None)
            gate.pop("answeredBy", None)
            write_status(status_file, status)
            # Mirror into console.db (table gates). The status.json file remains
            # the source for the Fastify console UI; the DB row is the queryable
            # history for future dashboards.
            try:
                ensure_initialized()
                with connect() as conn:
                    insert_gate(
                        conn, gate_name=args.phase, decision="pending",
                        feat_n=args.feat_num, payload={"askedAt": gate["askedAt"]},
                    )
            except Exception:  # pragma: no cover — telemetry must not break gates
                pass
            if args.json:
                print(json.dumps(gate, separators=(",", ":")))
            else:
                print("pending")
        finally:
            release_lock(lock_path)
        return SUCCESS

    if args.action == "set":
        acquire_lock(lock_path)
        try:
            status = read_status(status_file)
            gate = ensure_gate(status, feat_key, args.phase)
            gate["decision"] = args.decision
            gate["answeredAt"] = iso_now()
            gate["answeredBy"] = args.answered_by
            write_status(status_file, status)
            # Mirror into console.db (table gates).
            try:
                ensure_initialized()
                with connect() as conn:
                    insert_gate(
                        conn, gate_name=args.phase, decision=args.decision,
                        feat_n=args.feat_num, by_user=args.answered_by,
                        payload={"answeredAt": gate["answeredAt"]},
                    )
            except Exception:  # pragma: no cover
                pass
            if args.json:
                print(json.dumps(gate, separators=(",", ":")))
            else:
                print(args.decision)
        finally:
            release_lock(lock_path)
        return SUCCESS

    warn(f"Unknown action: {args.action}")
    return FAIL_FAST


if __name__ == "__main__":
    sys.exit(main())
