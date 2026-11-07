"""atomic_write_local.py — Anti-corruption helper (ADV-2 closure).

Duplicate of sdd_lib/atomic_write.py for module isolation (D4 strict —
`sdd_reverse/*` MUST NOT import from `sdd_lib/`). The isolation is wanted
(audit 2026-06-11 MA-9), so the fix below is applied to the copy rather than
replaced by an import. Parity tests against the original live in
tests/test_local_helpers_parity.py.

Public API:
    atomic_write_text(path, content, encoding="utf-8") -> None
    atomic_write_bytes(path, content) -> None
    find_orphan_tmps(root) -> Iterator[Path]

Crash safety: writes to a UNIQUE temp file `.{name}.{random}.sddtmp` in the
destination directory, fsync, then os.replace().

Audit « fiabilité des données et des états » (2026-11-07 — synced with
sdd_lib/atomic_write.py) : the temp name used to be deterministic
(`{name}.sddtmp`) → two concurrent writers of the same destination shared
one temp file and corrupted each other. `tempfile.NamedTemporaryFile(
dir=parent, delete=False)` gives each writer its own O_EXCL file.

Windows hardening (synced 2026-06-10 — sdd_lib v7.0.0 RUPT-5 closure):
    `os.replace()` on Windows NTFS is NOT atomic under sharing violations
    (PermissionError WinError 5) when destination is held open by another
    process (AV scan, indexer, hook scan). Mitigated by `_replace_with_retry`
    with jittered linear backoff. On POSIX the loop succeeds on first try.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterator

TMP_SUFFIX = ".sddtmp"

# Mirror of sdd_lib/atomic_write.py constants (RUPT-5 mitigation).
# Keep values in sync — parity test verifies semantic equivalence.
_REPLACE_MAX_RETRIES = 5
_REPLACE_BACKOFF_S = 0.05  # 50 ms × 5 × jitter = 50-300 ms worst case


def _backoff_with_jitter(attempt: int) -> float:
    """Jittered linear backoff for `attempt` (0-indexed).

    base = ``_REPLACE_BACKOFF_S × (attempt + 1)`` × uniform[0.8, 1.2].
    Jitter prevents thundering-herd when N agents collide on replace.
    """
    base = _REPLACE_BACKOFF_S * (attempt + 1)
    return base * random.uniform(0.8, 1.2)


def _replace_with_retry(tmp: Path, dst: Path) -> None:
    """`os.replace(tmp, dst)` with retry on Windows sharing violations.

    Raises the last exception if all retries exhaust. POSIX = effectively
    single-shot (no PermissionError semantics on `rename()`).
    """
    last_exc: BaseException | None = None
    for attempt in range(_REPLACE_MAX_RETRIES):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError as exc:
            last_exc = exc
            if attempt == _REPLACE_MAX_RETRIES - 1:
                break
            time.sleep(_backoff_with_jitter(attempt))
        except OSError as exc:
            if sys.platform != "win32":
                raise
            last_exc = exc
            if attempt == _REPLACE_MAX_RETRIES - 1:
                break
            time.sleep(_backoff_with_jitter(attempt))
    assert last_exc is not None
    raise last_exc


def atomic_write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically (POSIX + Windows NT+).

    Strategy: create parent dirs, write a unique `.sddtmp`, fsync, os.replace
    with Windows sharing-violation retry. If anything fails after open(),
    best-effort cleanup of OUR tmp file (never another writer's).
    """
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=TMP_SUFFIX,
            delete=False,
        ) as f:
            tmp = Path(f.name)
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # Some FS (network mounts) don't support fsync — best effort.
                pass
        _replace_with_retry(tmp, target)
    except Exception:
        # Best-effort cleanup; re-raise the original exception.
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def find_orphan_tmps(root: str | Path) -> Iterator[Path]:
    """Yield .sddtmp files left over from crashes.

    Forensic helper — does NOT delete. Tech Lead inspects/archives/removes.
    """
    root_path = Path(root)
    if not root_path.exists():
        return
    for p in root_path.rglob(f"*{TMP_SUFFIX}"):
        if p.is_file():
            yield p
