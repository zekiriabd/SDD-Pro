#!/usr/bin/env python3
"""SDD_Pro audit log rotation (v7.0.0 audit §6.17).

Rotates append-only audit logs that would otherwise grow without bound :
  - workspace/output/.sys/.audit/force-bypass.log
  - workspace/output/.sys/.audit/legacy-parallel.log

Strategy : when a log file exceeds `MAX_BYTES` (default 1 MiB) OR
`MAX_LINES` (default 5000), rename it to `{name}.{YYYY-MM-DD}.log` and
start fresh. Keeps last `KEEP_ROTATIONS` (default 12) rotations,
deletes older ones.

Idempotent. Safe to call repeatedly. Designed to be invoked :
  - manually by Tech Lead (`python -m sdd_admin.rotate_audit_logs`)
  - or via a `Stop` hook (low-frequency cron-like)

Usage:
    python -m sdd_admin.rotate_audit_logs [--dry-run] [--max-bytes N] [--max-lines N] [--keep N]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.exit_codes import SUCCESS  # noqa: E402

DEFAULT_MAX_BYTES = 1 * 1024 * 1024   # 1 MiB
DEFAULT_MAX_LINES = 5000
DEFAULT_KEEP_ROTATIONS = 12

AUDIT_LOG_PATTERNS = (
    "force-bypass.log",
    "legacy-parallel.log",
)


def _should_rotate(path: Path, max_bytes: int, max_lines: int) -> tuple[bool, str]:
    if not path.is_file():
        return False, "absent"
    size = path.stat().st_size
    if size >= max_bytes:
        return True, f"size {size} >= {max_bytes}"
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            line_count = sum(1 for _ in f)
        if line_count >= max_lines:
            return True, f"{line_count} lines >= {max_lines}"
    except OSError:
        return False, "unreadable"
    return False, f"under thresholds ({size} bytes, {line_count} lines)"


def _rotate_one(path: Path, dry_run: bool) -> Path | None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = path.with_name(f"{path.stem}.{today}{path.suffix}")
    # If target exists (multiple rotations same day), suffix .1, .2, ...
    i = 1
    while target.exists():
        target = path.with_name(f"{path.stem}.{today}.{i}{path.suffix}")
        i += 1
    if dry_run:
        return target
    path.rename(target)
    # Re-create empty so callers don't crash on missing file
    path.touch()
    return target


def _prune_old(audit_dir: Path, base_name: str, keep: int, dry_run: bool) -> list[Path]:
    """Delete rotations older than `keep` for a given base name."""
    rotations = sorted(audit_dir.glob(f"{Path(base_name).stem}.*"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    to_delete = rotations[keep:]
    if not dry_run:
        for p in to_delete:
            p.unlink()
    return to_delete


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would happen, don't touch files.")
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    p.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    p.add_argument("--keep", type=int, default=DEFAULT_KEEP_ROTATIONS)
    args = p.parse_args()

    audit_dir = repo_root() / "workspace" / "output" / ".sys" / ".audit"
    if not audit_dir.is_dir():
        print(f"audit dir absent ({audit_dir}) — nothing to rotate")
        return SUCCESS
    any_action = False
    for pattern in AUDIT_LOG_PATTERNS:
        path = audit_dir / pattern
        rotate, reason = _should_rotate(path, args.max_bytes, args.max_lines)
        if rotate:
            any_action = True
            new_path = _rotate_one(path, args.dry_run)
            verb = "[DRY] would rotate" if args.dry_run else "rotated"
            print(f"{verb} {path.name} -> {new_path.name} ({reason})")
        else:
            print(f"skip {path.name} ({reason})")

        # Prune old rotations
        deleted = _prune_old(audit_dir, pattern, args.keep, args.dry_run)
        for d in deleted:
            verb = "[DRY] would delete" if args.dry_run else "deleted old"
            print(f"  {verb} {d.name}")
            any_action = True

    if not any_action:
        print("no rotation needed (logs under thresholds, no old rotations to prune)")
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
