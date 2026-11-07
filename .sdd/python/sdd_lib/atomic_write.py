"""SDD_Pro atomic write helper (v7.0.0 audit P1 R4 fix 2026-05-20).

Pattern : write content to a **unique** temp file next to the destination
(``tempfile.NamedTemporaryFile(dir=path.parent, prefix=".{name}.",
suffix=".sddtmp", delete=False)``) then ``os.replace()`` atomic rename.
Eliminates the half-written file vulnerability when an agent dev-* crashes
mid-write on `{LibName}/{Entity}.cs`. The next agent that acquires the
stale lock (30min TTL) reads either the previous full content or the new
full content — never a truncated mix.

Audit « fiabilité des données et des états » (2026-11-07) : the temp name
used to be DETERMINISTIC (``{name}.sddtmp``) — two concurrent writers of the
same destination (parallel hooks on ``run-id.current``, two agents on a
shared DTO) opened the SAME temp file, interleaved their bytes, and one of
them renamed the corrupted mix over the destination while the other hit
``FileNotFoundError`` on its own replace. Temp names are now unique per
writer (``.{name}.{random}.sddtmp``) so each writer renames its own complete
content ; last ``os.replace`` wins, atomically.

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

Cleanup : the temp file is removed if the rename succeeds. If the script
crashes between write and rename, it remains as a forensic trace —
caller can detect orphan tmps via `find_orphan_tmps()` (suffix ``.sddtmp``
is preserved for that purpose).

Not designed for huge files (writes whole content in one syscall) — fine
for SDD_Pro use case where each entity file is < 50 KB.
"""
from __future__ import annotations

import os
import sys
import tempfile
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


def _open_unique_tmp(path: Path, tmp_suffix: str):
    """Create a unique temp file in ``path.parent`` (O_EXCL, never shared).

    Name pattern ``.{name}.{random}{tmp_suffix}`` — same directory as the
    destination so ``os.replace`` stays a same-filesystem rename.
    """
    return tempfile.NamedTemporaryFile(
        mode="wb",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=tmp_suffix,
        delete=False,
    )


def _write_atomic(path: Path, data: bytes, tmp_suffix: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with _open_unique_tmp(path, tmp_suffix) as f:
            tmp_path = Path(f.name)
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())  # durability — survives kernel panic
            except OSError:
                # Some FS (e.g. network mounts) don't support fsync — best effort.
                pass
        _replace_with_retry(tmp_path, path)  # atomic + Windows retry (RUPT-5)
    except Exception:
        # Cleanup OUR tmp if rename failed but file was created. Never touch
        # another writer's tmp (names are unique per writer).
        if tmp_path is not None:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
        raise


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
    tmp_suffix: str = DEFAULT_TMP_SUFFIX,
) -> None:
    """Write text atomically : unique ``.{name}.*{tmp_suffix}`` then `os.replace`.

    Creates parent dir if absent (`mkdir -p` semantics).
    ``newline`` follows ``open()`` semantics : ``None`` translates ``\\n`` to
    ``os.linesep``, ``""``/``"\\n"`` keep ``\\n`` verbatim, ``"\\r\\n"`` forces CRLF.
    On Windows, the destination must NOT be open elsewhere or replace fails.
    """
    if newline is None:
        text = content.replace("\n", os.linesep) if os.linesep != "\n" else content
    elif newline in ("", "\n"):
        text = content
    else:
        text = content.replace("\n", newline)
    _write_atomic(Path(path), text.encode(encoding), tmp_suffix)


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    tmp_suffix: str = DEFAULT_TMP_SUFFIX,
) -> None:
    """Binary variant of atomic_write_text. Same semantics."""
    _write_atomic(Path(path), content, tmp_suffix)


def find_orphan_tmps(
    root: Path,
    *,
    tmp_suffix: str = DEFAULT_TMP_SUFFIX,
) -> Iterable[Path]:
    """Walk `root` and yield orphan `.sddtmp` files (mid-write crashes).

    Useful for diagnostic / cleanup scripts. Caller decides what to do
    (delete, inspect, archive)."""
    return Path(root).rglob(f"*{tmp_suffix}")
