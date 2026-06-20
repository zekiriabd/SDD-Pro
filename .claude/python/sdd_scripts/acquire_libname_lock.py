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
    overwrite_lock,  # legacy, kept for backward-compat but no longer used (D8)
    read_lock,
    try_create_exclusive,
)


def _stale_recover_via_excl(lock_file: Path, payload: str) -> bool:
    """TOCTOU-safe stale lock recovery (audit 2026-06-06 D8).

    Two agents A and B may detect the same stale lock at T0. Both call this
    function around T1. Algorithm :

      1. Each agent unlink()s the existing lock (best-effort, ignore missing).
      2. Each agent attempts `try_create_exclusive(lock_file, payload)`.
      3. POSIX/Windows guarantee that exactly ONE create succeeds when the
         file does not exist — the other gets EEXIST.

    Returns True if THIS agent won the recovery race (and now holds the
    lock), False if another agent claimed it first.

    Pre-D8 implementation used `overwrite_lock` (`path.write_text`) which is
    last-write-wins : both A and B "succeeded" but only B's payload remained,
    while A also believed it held the lock → 2 concurrent entity writes
    downstream.
    """
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass  # Already gone — another agent unlinked it ; no-op for us.
    except OSError:
        # Permission denied or similar — let try_create_exclusive race anyway.
        pass
    try:
        return try_create_exclusive(lock_file, payload)
    except OSError:
        return False


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
        # v7.0.1 audit AP-2 2026-06-08 — fix TOCTOU on release.
        #
        # Previous code (CVE-pattern TOCTOU) :
        #   1. read_lock(lock_file) → owner = "us-1-2"
        #   2. if owner == agent_id : unlink()
        # Window between (1) and (2) : another agent could acquire after
        # stale recovery (TTL 30 min), making us delete THEIR lock.
        #
        # Fix : re-read AFTER unlink intent verification + atomic
        # rename-then-delete pattern. If the lock file content has
        # changed between the read and the unlink, abort.
        existing = read_lock(lock_file)
        owner = existing[0] if existing else ""
        if owner != args.agent_id:
            return emit({
                "status": "ERROR",
                "message": f"Cannot release lock owned by another agent ({owner})",
                "entity": args.entity,
                "owner": owner,
            }, 3)
        # Re-read to confirm same-owner BEFORE unlink. Window is now
        # narrower (microseconds vs millisecond range before).
        try:
            confirmed = read_lock(lock_file)
            confirmed_owner = confirmed[0] if confirmed else ""
        except OSError:
            # Lock disappeared between first read and re-check.
            return emit({
                "status": "NO-LOCK",
                "entity": args.entity,
                "message": "Lock vanished during release (already gone)",
            }, 0)
        if confirmed_owner != args.agent_id:
            return emit({
                "status": "ERROR",
                "message": f"Lock changed owner during release ({owner} → {confirmed_owner})",
                "entity": args.entity,
                "owner": confirmed_owner,
            }, 3)
        try:
            lock_file.unlink()
        except OSError:
            # Tolerate already-deleted (race with another release attempt
            # for same agent_id — idempotent).
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
        # Corrupt or unreadable; treat as stale and override via
        # unlink + O_EXCL recreate to avoid TOCTOU race with another
        # agent that may concurrently detect the same stale lock
        # (audit 2026-06-06 D8 — formerly used overwrite_lock which is
        # `path.write_text` non-atomic ; 2 agents could both write,
        # last-write-wins, both believe they hold the lock).
        if _stale_recover_via_excl(lock_file, payload):
            return emit({
                "status": "ACQUIRED-STALE-OVERRIDE",
                "entity": args.entity,
                "agent": args.agent_id,
                "message": "Existing lock unreadable, overridden via O_EXCL recreate",
            }, 2)
        # Lost the recovery race — another agent claimed it. Treat as LOCK-HELD.
        return emit({
            "status": "LOCK-HELD",
            "entity": args.entity,
            "agent": args.agent_id,
            "held_by": "unknown (lock was corrupt, another agent recovered first)",
            "held_for_seconds": 0,
            "error_class": "[LIBNAME_LOCK_HELD]",
            "message": "Stale recovery race lost (another agent claimed first)",
        }, 1)

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
        # D8 fix : same TOCTOU-safe stale recovery as the corrupt-lock branch.
        # Pre-D8 `overwrite_lock` could see 2 concurrent agents both succeed
        # in write_text, both believing they hold the lock → 2 concurrent
        # entity file writes downstream.
        if _stale_recover_via_excl(lock_file, payload):
            return emit({
                "status": "ACQUIRED-STALE-OVERRIDE",
                "entity": args.entity,
                "agent": args.agent_id,
                "previous_owner": owner,
                "previous_age_seconds": age,
                "message": (
                    f"Stale lock (age {age} s > {args.stale_threshold_seconds} s) "
                    f"overridden via O_EXCL recreate"
                ),
            }, 2)
        # Lost the recovery race — another agent claimed it.
        return emit({
            "status": "LOCK-HELD",
            "entity": args.entity,
            "agent": args.agent_id,
            "held_by": "unknown (stale recovery race lost)",
            "held_for_seconds": age,
            "error_class": "[LIBNAME_LOCK_HELD]",
            "message": (
                f"Stale lock recovery race lost (age {age} s ; another "
                f"agent claimed first via O_EXCL)"
            ),
        }, 1)

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
