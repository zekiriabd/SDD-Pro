"""Cross-platform atomic file lock helpers.

Uses `O_EXCL` semantics via `os.open(O_CREAT | O_EXCL | O_WRONLY)` which is
atomic on POSIX (Linux/macOS) and Windows alike (via Python's CRT layer).
"""
from __future__ import annotations

import errno
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path


def try_create_exclusive(path: Path, content: str) -> bool:
    """Atomically create `path` with the given content if it does not exist.

    Returns:
        True if created (lock acquired), False if the file already exists.
    Raises:
        OSError for any failure other than EEXIST.
    """
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags, 0o644)
    except OSError as e:
        if e.errno == errno.EEXIST:
            return False
        raise
    try:
        os.write(fd, content.encode("ascii", errors="strict"))
    finally:
        os.close(fd)
    return True


def read_lock(path: Path) -> tuple[str, int] | None:
    """Read a `lockfile` and return (agent_id, unix_timestamp_seconds).

    Supports both lock payload formats coexisting in the SDD_Pro framework :

    1. **2-part** : `AGENT_ID:UNIX_TS_SECONDS` — produced by
       `acquire_libname_lock.py` (Python only, LibName entity locks).
    2. **3-part** : `PREFIX:PID:UNIX_TS_MS` — produced by
       `acquire_with_retry()` and the Node.js console
       (`workspace/console/.status.lock` cross-language symmetry).

    The two payload zones (`{LibName}/.locks/*.lock` vs
    `workspace/console/.status.lock`) do not overlap in current callers,
    but `read_lock()` is defensive : it detects the 3-part format by
    counting `:` separators and converts ms → seconds so downstream
    stale detection (`now - ts > threshold_seconds`) works regardless
    of which writer produced the lock.

    Returns (agent_id_or_prefix, timestamp_seconds) or None if missing
    /malformed.
    """
    try:
        raw = path.read_text(encoding="ascii", errors="replace").strip()
    except (OSError, UnicodeError):
        return None
    if not raw:
        return None
    parts_all = raw.split(":")
    agent = parts_all[0].strip()
    if len(parts_all) >= 3:
        # 3-part format: PREFIX:PID:TS_MS — last segment is ms timestamp.
        try:
            ts_ms = int(parts_all[-1].strip())
        except ValueError:
            return (agent, 0)
        # Heuristic: a ms timestamp post-2001 is >= 1e12 ; a seconds
        # timestamp post-2001 is >= 1e9. Convert iff in ms range.
        ts = ts_ms // 1000 if ts_ms >= 1_000_000_000_000 else ts_ms
        return (agent, ts)
    # 2-part format: AGENT:TS_SECONDS.
    if len(parts_all) >= 2:
        try:
            ts = int(parts_all[1].strip())
        except ValueError:
            ts = 0
        return (agent, ts)
    return (agent, 0)


def overwrite_lock(path: Path, content: str) -> None:
    """Overwrite an existing lock file (used for stale recovery)."""
    path.write_text(content, encoding="ascii", newline="")


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def acquire_with_retry(
    lock_path: Path,
    *,
    payload_prefix: str = "py",
    ttl_ms: int = 10000,
    retry_count: int = 5,
    backoff_ms: int = 50,
) -> None:
    """O_EXCL atomic lock acquire with stale detection + retry-with-backoff.

    Lock payload format: `{payload_prefix}:{pid}:{unix_ts_ms}`.
    Mirrors the console Node.js side (`workspace/console/lib/atomic-write.js`)
    for cross-language symmetry on `workspace/console/.status.lock`.

    Stale recovery: if the existing lock file is older than `ttl_ms`,
    it is unlinked and the loop retries.

    Raises RuntimeError ([LOCK_HELD]) after `retry_count` failed attempts.
    """
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY

    for attempt in range(retry_count):
        try:
            fd = os.open(str(lock_path), flags, 0o644)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            try:
                content = lock_path.read_text(encoding="ascii", errors="replace").strip()
                parts = content.split(":")
                ts_str = parts[-1] if parts else ""
                ts = int(ts_str) if ts_str.isdigit() else 0
            except (OSError, ValueError):
                ts = 0
            now = _now_ms()
            if ts and (now - ts) > ttl_ms:
                try:
                    lock_path.unlink()
                except OSError:
                    pass
                continue
            # v7.0.1 audit AP-3 2026-06-08 — backoff WITH jitter to avoid
            # thundering herd under high MaxParallel. Previous : pure linear
            # backoff_ms*(attempt+1) caused all parallel agents to retry in
            # lockstep (same delay → same collision next round). With ±20%
            # jitter (uniform), retries decorrelate.
            #
            # Aligned with sdd_lib/atomic_write.py `_backoff_with_jitter`
            # (audit CTO 2026-06-07 fixed atomic_write but missed file_locks).
            base_delay = backoff_ms * (attempt + 1)
            jittered_ms = base_delay * random.uniform(0.8, 1.2)
            time.sleep(jittered_ms / 1000.0)
            continue

        try:
            payload = f"{payload_prefix}:{os.getpid()}:{_now_ms()}".encode("ascii")
            os.write(fd, payload)
        finally:
            os.close(fd)
        return

    raise RuntimeError(f"[LOCK_HELD] Cannot acquire {lock_path} after {retry_count} attempts")


def release(lock_path: Path) -> None:
    """Remove a lock file (best effort, no-op if absent)."""
    try:
        lock_path.unlink()
    except OSError:
        pass
