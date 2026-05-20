"""SDD_Pro atomic write helper (v7.0.0 audit P1 R4 fix 2026-05-20).

Pattern : write content to `{path}.tmp` then `os.replace()` atomic rename.
Eliminates the half-written file vulnerability when an agent dev-* crashes
mid-write on `{LibName}/{Entity}.cs`. The next agent that acquires the
stale lock (30min TTL) reads either the previous full content or the new
full content — never a truncated mix.

Usage:
    from sdd_lib.atomic_write import atomic_write_text
    atomic_write_text(Path("Shared/BebeDto.cs"), generated_content)

Cross-platform : `os.replace()` is atomic on POSIX and Windows (Python ≥ 3.3).
Idempotent : re-applying the same content is a no-op (still atomic on disk).

Cleanup : the `.tmp` is removed if the rename succeeds. If the script
crashes between write and rename, `.tmp` remains as a forensic trace —
caller can detect orphan tmps via `find_orphan_tmps()`.

Not designed for huge files (writes whole content in one syscall) — fine
for SDD_Pro use case where each entity file is < 50 KB.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

DEFAULT_TMP_SUFFIX = ".sddtmp"


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
        os.replace(tmp, path)  # atomic on POSIX + Windows ≥ NT
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
        os.replace(tmp, path)
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
