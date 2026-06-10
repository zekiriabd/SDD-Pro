"""atomic_write_local.py — Anti-corruption helper (ADV-2 closure).

Duplicate of sdd_lib/atomic_write.py for module isolation (D4 strict).
Parity tests against the original live in tests/test_local_helpers_parity.py.

Public API:
    atomic_write_text(path, content, encoding="utf-8") -> None
    atomic_write_bytes(path, content) -> None
    find_orphan_tmps(root) -> Iterator[Path]

Crash safety: writes to {path}.sddtmp, fsync, then os.replace().
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

TMP_SUFFIX = ".sddtmp"


def atomic_write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically (POSIX + Windows NT+).

    Strategy: create parent dirs, write `.sddtmp`, fsync, os.replace.
    If anything fails after open(), best-effort cleanup of the tmp file.
    """
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + TMP_SUFFIX)
    try:
        with open(tmp, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception:
        # Best-effort cleanup; re-raise the original exception.
        if tmp.exists():
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
