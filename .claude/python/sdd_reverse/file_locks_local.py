"""file_locks_local.py — Cross-platform file lock (ADV-2 closure).

Duplicate of sdd_lib/file_locks.py for module isolation (D4 strict).
Parity tests against the original live in tests/test_local_helpers_parity.py.

Public API:
    acquire_lock(lock_path, agent_id, ttl=30) -> int  # exit code
    release_lock(lock_path, agent_id) -> int          # exit code
    read_lock(lock_path) -> dict | None

Exit codes (mirror ownership.md §4 / build-and-loop.md §2):
    0  : ACQUIRED (creation or re-entrant same agent) | RELEASED
    1  : LOCK_HELD by other agent
    2  : stale lock (>ttl seconds) OR corrupted lock OVERWRITTEN — continue
    3  : I/O error (bad path, permission denied, foreign release)

ADV-10 mitigations:
    - psutil is OPTIONAL — if missing, fallback to TTL-only (no hard dep)
    - Windows PID recycling: TTL stays the authority, pid is opportunistic
    - host field included to short-circuit cross-machine confusion
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any

from sdd_reverse.atomic_write_local import atomic_write_text

DEFAULT_TTL_SECONDS = 30

# psutil is optional (ADV-10) — keep dependency soft.
try:
    import psutil  # type: ignore[import-not-found]

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _host() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def _is_pid_alive(pid: int) -> bool | None:
    """Return True/False if known, None if cannot check (no psutil)."""
    if not _HAS_PSUTIL:
        return None
    try:
        return psutil.pid_exists(pid)  # type: ignore[no-any-return]
    except Exception:
        return None


def read_lock(lock_path: str | Path) -> dict[str, Any] | None:
    """Read lock content; return None if absent or unreadable."""
    p = Path(lock_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def acquire_lock(
    lock_path: str | Path,
    agent_id: str,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> int:
    """Try to acquire `lock_path` for `agent_id`.

    Returns:
        0 : ACQUIRED (creation or re-entrant same agent)
        1 : LOCK_HELD by another agent (< TTL, OR pid alive on same host)
        2 : stale/corrupted lock overwritten — caller can continue
        3 : I/O error
    """
    p = Path(lock_path)
    now = int(time.time())
    pid = os.getpid()
    host = _host()
    payload = json.dumps(
        {"agent_id": agent_id, "pid": pid, "ts_unix": now, "host": host},
        ensure_ascii=False,
    )

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 3

    existing = read_lock(p)
    if existing is None:
        if p.exists():
            # Corrupted lock — overwrite (recovery).
            try:
                atomic_write_text(p, payload)
                return 2
            except OSError:
                return 3
        # No lock yet — create.
        try:
            atomic_write_text(p, payload)
            return 0
        except OSError:
            return 3

    # Existing lock found — decide.
    existing_agent = existing.get("agent_id", "")
    existing_ts = int(existing.get("ts_unix", 0))
    existing_pid = int(existing.get("pid", 0))
    existing_host = existing.get("host", "")
    age = now - existing_ts

    # Re-entrant : same agent_id wins.
    if existing_agent == agent_id:
        try:
            atomic_write_text(p, payload)  # refresh ts
            return 0
        except OSError:
            return 3

    # Stale by TTL : overwrite.
    if age >= ttl:
        try:
            atomic_write_text(p, payload)
            return 2
        except OSError:
            return 3

    # Within TTL but pid check : only if same host AND psutil available.
    if existing_host == host:
        alive = _is_pid_alive(existing_pid)
        if alive is False:
            # Pid dead on same host — overwrite even before TTL.
            try:
                atomic_write_text(p, payload)
                return 2
            except OSError:
                return 3
        # alive is True OR None (no psutil) → fall through to LOCK_HELD.

    return 1


def release_lock(lock_path: str | Path, agent_id: str) -> int:
    """Release lock if held by `agent_id`.

    Returns:
        0 : RELEASED (or already absent — idempotent)
        3 : foreign release attempt OR I/O error
    """
    p = Path(lock_path)
    existing = read_lock(p)
    if existing is None:
        return 0 if not p.exists() else 3
    if existing.get("agent_id") != agent_id:
        return 3
    try:
        p.unlink()
        return 0
    except OSError:
        return 3
