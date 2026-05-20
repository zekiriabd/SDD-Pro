#!/usr/bin/env python3
"""SDD_Pro: atomic per-entity lock for shared LibName projects.

Externalises the lock file procedure (L2, file-ownership.md §4) used by
dev-backend and dev-frontend when writing under
`workspace/output/src/{LibName}/`.

Usage (acquire):
    python acquire_libname_lock.py \\
        --lib-path workspace/output/src/Shared \\
        --entity BebeDto \\
        --agent-id "dev-backend-1-2"

Usage (release):
    python acquire_libname_lock.py \\
        --lib-path workspace/output/src/Shared \\
        --entity BebeDto \\
        --agent-id "dev-backend-1-2" \\
        --release

Exit codes:
    0  Lock acquired (or re-entrant same agent) / Released
    1  Lock held by another agent → STOP + ERROR [LIBNAME_LOCK_HELD]
    2  Stale lock detected and overridden (recovery)
    3  Error (path invalid, permission, etc.)

Output: single JSON line on stdout.

Migrated from .claude/scripts/acquire-libname-lock.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.file_locks import (  # noqa: E402
    overwrite_lock,
    read_lock,
    try_create_exclusive,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--lib-path", required=True)
    p.add_argument("--entity", required=True)
    p.add_argument("--agent-id", required=True)
    p.add_argument("--release", action="store_true")
    p.add_argument("--stale-threshold-seconds", type=int, default=1800,
                   help="Lock older than this is considered stale (default 30 min)")
    return p.parse_args()


def emit(obj: dict, exit_code: int) -> int:
    print(json.dumps(obj, separators=(",", ":")))
    return exit_code


def main() -> int:
    args = parse_args()
    lib_path = Path(args.lib_path)
    if not lib_path.is_dir():
        return emit({"status": "ERROR", "message": f"LibPath not found: {args.lib_path}"}, 3)

    locks_dir = lib_path / ".locks"
    lock_file = locks_dir / f"{args.entity}.lock"

    # RELEASE
    if args.release:
        if not lock_file.is_file():
            return emit({
                "status": "NO-LOCK",
                "entity": args.entity,
                "message": "Lock already released or never existed",
            }, 0)
        existing = read_lock(lock_file)
        owner = existing[0] if existing else ""
        if owner != args.agent_id:
            return emit({
                "status": "ERROR",
                "message": f"Cannot release lock owned by another agent ({owner})",
                "entity": args.entity,
                "owner": owner,
            }, 3)
        try:
            lock_file.unlink()
        except OSError:
            pass
        return emit({
            "status": "RELEASED",
            "entity": args.entity,
            "agent": args.agent_id,
        }, 0)

    # ACQUIRE
    locks_dir.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    payload = f"{args.agent_id}:{now}"

    # Attempt atomic create first
    created = False
    try:
        created = try_create_exclusive(lock_file, payload)
    except OSError as e:
        return emit({"status": "ERROR", "message": f"create failed: {e}"}, 3)

    if created:
        return emit({
            "status": "ACQUIRED",
            "entity": args.entity,
            "agent": args.agent_id,
            "message": "Lock acquired successfully",
        }, 0)

    # Lock file already existed — inspect ownership + age
    existing = read_lock(lock_file)
    if not existing:
        # Corrupt or unreadable; treat as stale and override
        overwrite_lock(lock_file, payload)
        return emit({
            "status": "ACQUIRED-STALE-OVERRIDE",
            "entity": args.entity,
            "agent": args.agent_id,
            "message": "Existing lock unreadable, overridden",
        }, 2)

    owner, ts = existing
    age = now - ts if ts else 0

    if owner == args.agent_id:
        return emit({
            "status": "RE-ENTRANT",
            "entity": args.entity,
            "agent": args.agent_id,
            "message": "Lock already held by same agent (idempotent)",
        }, 0)

    if age > args.stale_threshold_seconds:
        overwrite_lock(lock_file, payload)
        return emit({
            "status": "ACQUIRED-STALE-OVERRIDE",
            "entity": args.entity,
            "agent": args.agent_id,
            "previous_owner": owner,
            "previous_age_seconds": age,
            "message": (
                f"Stale lock (age {age} s > {args.stale_threshold_seconds} s) overridden"
            ),
        }, 2)

    return emit({
        "status": "LOCK-HELD",
        "entity": args.entity,
        "agent": args.agent_id,
        "held_by": owner,
        "held_for_seconds": age,
        "error_class": "[LIBNAME_LOCK_HELD]",
        "message": (
            f"Entity locked by {owner} (held for {age} seconds). "
            "STOP + ERROR for the calling agent."
        ),
    }, 1)


if __name__ == "__main__":
    sys.exit(main())
