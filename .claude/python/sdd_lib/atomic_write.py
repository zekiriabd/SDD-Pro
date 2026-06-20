"""SDD_Pro atomic write helper (v7.0.0 audit P1 R4 fix 2026-05-20).

Pattern : write content to `{path}.tmp` then `os.replace()` atomic rename.
Eliminates the half-written file vulnerability when an agent dev-* crashes
mid-write on `{LibName}/{Entity}.cs`. The next agent that acquires the
stale lock (30min TTL) reads either the previous full content or the new
full content — never a truncated mix.

Usage:
    from sdd_lib.atomic_write import atomic_write_text
    atomic_write_text(Path("Shared/BebeDto.cs"), generated_content)

Cross-platform notes:
- POSIX: `os.replace()` is atomic at the inode level (Python ≥ 3.3).
- Windows: `os.replace()` calls `MoveFileExW(MOVEFILE_REPLACE_EXISTING)`.
  Atomic at the MFT level, BUT fails with `WinError 5` (ERROR_ACCESS_DENIED)
  when the destination is open elsewhere (e.g. read by a SubagentStop hook,
  scanned by antivirus, indexed by Windows Search). Mitigated by the retry
  loop below (audit 2026-06-06 RUPT-5).

Idempotent : re-applying the same content is a no-op (still atomic on disk).

Cleanup : the `.tmp` is removed if the rename succeeds. If the script
crashes between write and rename, `.tmp` remains as a forensic trace —
caller can detect orphan tmps via `find_orphan_tmps()`.

Not designed for huge files (writes whole content in one syscall) — fine
for SDD_Pro use case where each entity file is < 50 KB.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Iterable

DEFAULT_TMP_SUFFIX = ".sddtmp"

#: Audit 2026-06-06 RUPT-5 — `os.replace` on Windows NTFS is not atomic
#: under sharing violations (live test 5 threads = 1 PermissionError out
#: of 5 reproducible). Retry with linear backoff + JITTER to absorb
#: transient holders (audit hooks, AV scan, indexer). On POSIX the loop
#: usually succeeds on first try (no sharing violation semantics).
#:
#: Audit CTO 2026-06-07 — added jitter (random 0.8x-1.2x multiplier) to
#: prevent thundering-herd : without jitter, N synchronized agents
#: (typical `/dev-run --max-parallel 6`) collide every 50ms repeatedly
#: until last_exc fires. With jitter, retry windows desynchronize and
#: the effective contention drops.
_REPLACE_MAX_RETRIES = 5
_REPLACE_BACKOFF_S = 0.05  # 50 ms × 5 × jitter = 50-300 ms worst case


def _backoff_with_jitter(attempt: int) -> float:
    """Return jittered backoff duration in seconds for `attempt` (0-indexed).

    Linear progression base = ``_REPLACE_BACKOFF_S × (attempt + 1)`` ;
    multiplied by uniform jitter [0.8, 1.2] to desynchronize parallel
    retries (audit CTO 2026-06-07).
    """
    import random
    base = _REPLACE_BACKOFF_S * (attempt + 1)
    return base * random.uniform(0.8, 1.2)


def _replace_with_retry(tmp: Path, dst: Path) -> None:
    """`os.replace(tmp, dst)` with retry on Windows sharing violations.

    Raises the last exception if all retries exhaust. On POSIX this is
    effectively a single-shot rename (no PermissionError semantics on
    `rename()`).
    """
    last_exc: BaseException | None = None
    for attempt in range(_REPLACE_MAX_RETRIES):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError as exc:
            # Windows ERROR_ACCESS_DENIED (5) — destination held open by
            # another process. Sleep and retry. On the last attempt, let
            # the exception propagate.
            last_exc = exc
            if attempt == _REPLACE_MAX_RETRIES - 1:
                break
            time.sleep(_backoff_with_jitter(attempt))
        except OSError as exc:
            # Other transient OS error (rare). Retry on Windows only —
            # POSIX rename is atomic so any OSError there is terminal.
            if sys.platform != "win32":
                raise
            last_exc = exc
            if attempt == _REPLACE_MAX_RETRIES - 1:
                break
            time.sleep(_backoff_with_jitter(attempt))
    # All retries exhausted — re-raise the last captured exception
    assert last_exc is not None
    raise last_exc


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
    tmp_suffix: str = DEFAULT_TMP_SUFFIX,
) -> None:
    """Write text atomically : `{path}{tmp_suffix}` then `os.replace`.

    Creates parent dir if absent (`mkdir -p` semantics).
    On Windows, the destination must NOT be open elsewhere or replace fails.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + tmp_suffix)
    try:
        with open(tmp, "w", encoding=encoding, newline=newline) as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())  # durability — survives kernel panic
            except OSError:
                # Some FS (e.g. network mounts) don't support fsync — best effort.
                pass
        _replace_with_retry(tmp, path)  # atomic + Windows retry (RUPT-5)
    except Exception:
        # Cleanup tmp if rename failed but file was created
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    tmp_suffix: str = DEFAULT_TMP_SUFFIX,
) -> None:
    """Binary variant of atomic_write_text. Same semantics."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + tmp_suffix)
    try:
        with open(tmp, "wb") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        _replace_with_retry(tmp, path)  # atomic + Windows retry (RUPT-5)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def find_orphan_tmps(
    root: Path,
    *,
    tmp_suffix: str = DEFAULT_TMP_SUFFIX,
) -> Iterable[Path]:
    """Walk `root` and yield orphan `.sddtmp` files (mid-write crashes).

    Useful for diagnostic / cleanup scripts. Caller decides what to do
    (delete, inspect, archive)."""
    return Path(root).rglob(f"*{tmp_suffix}")
