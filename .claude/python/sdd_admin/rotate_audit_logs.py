#!/usr/bin/env python3
"""SDD_Pro audit log rotation (v7.0.0 §6.17 + v7.0.1 audit P1 v2 2026-06-08).

Rotates append-only audit logs that would otherwise grow without bound.

v7.0.1 audit P1 v2 (2026-06-08) — étendu pour couvrir TOUS les audit logs
emis par les hooks/scripts SDD_Pro (avant : seulement 2 sur 7+). Plus :
ajout de rotation age-based (mtime > MAX_AGE_DAYS) en plus du size-based.

Couverture cumulée :
  - workspace/output/.sys/.audit/force-bypass.log       (legacy bypass)
  - workspace/output/.sys/.audit/legacy-parallel.log    (legacy parallel)
  - workspace/output/.sys/.audit/env-bypass.jsonl       (block_env_bypass)
  - workspace/output/.sys/.audit/glob-scope.jsonl       (glob-scope hook)
  - workspace/output/.sys/.audit/pre-write-lint.log     (pre-write linter)
  - workspace/output/.sys/.audit/untested-combo.log     (preflight stack combo)
  - workspace/output/.sys/.audit/arch-bootstrap-*.log   (arch bootstrap traces)
  - workspace/output/.sys/.audit/ownership-violations.log (audit_file_ownership)

Strategy : when a log file exceeds `MAX_BYTES` (default 1 MiB) OR
`MAX_LINES` (default 5000) OR mtime older than `MAX_AGE_DAYS` (default 30),
rename it to `{name}.{YYYY-MM-DD}.log` and start fresh. Keeps last
`KEEP_ROTATIONS` (default 12) rotations, deletes older ones.

Idempotent. Safe to call repeatedly. Designed to be invoked :
  - manually by Tech Lead (`python -m sdd_admin.rotate_audit_logs`)
  - via `Stop` / `SessionStart` hook (low-frequency, throttled — see
    `rotate_audit_logs_throttled.py` shim)

Usage:
    python -m sdd_admin.rotate_audit_logs [--dry-run] [--max-bytes N] [--max-lines N] [--keep N] [--max-age-days N]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.exit_codes import SUCCESS  # noqa: E402

DEFAULT_MAX_BYTES = 1 * 1024 * 1024   # 1 MiB
DEFAULT_MAX_LINES = 5000
DEFAULT_KEEP_ROTATIONS = 12
DEFAULT_MAX_AGE_DAYS = 30

# v7.0.1 audit P1 v2 (2026-06-08) — étendu pour couvrir tous les audit
# logs actuellement écrits par les hooks/scripts SDD_Pro. Le passage de
# 2 → 8 patterns ferme la dérive disk-fill identifiée par l'audit v2.
AUDIT_LOG_PATTERNS = (
    "force-bypass.log",
    "legacy-parallel.log",
    "env-bypass.jsonl",
    "glob-scope.jsonl",
    "pre-write-lint.log",
    "untested-combo.log",
    "ownership-violations.log",
)
# Wildcard patterns (matched via glob)
AUDIT_LOG_GLOB_PATTERNS = (
    "arch-bootstrap-*.log",
)


def _should_rotate(
    path: Path, max_bytes: int, max_lines: int, max_age_days: int
) -> tuple[bool, str]:
    """Decide if a single audit log file needs rotation.

    Triggers (any of) :
      1. size >= max_bytes
      2. line count >= max_lines
      3. mtime older than `max_age_days` days (v7.0.1 audit P1 v2 2026-06-08)

    Returns (should_rotate, reason_str_for_logging).
    """
    if not path.is_file():
        return False, "absent"
    stat = path.stat()
    size = stat.st_size
    if size >= max_bytes:
        return True, f"size {size} >= {max_bytes}"
    # v7.0.1 P1 v2 : age-based trigger (audit log rotation on inactivity).
    if max_age_days > 0:
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        age = datetime.now(timezone.utc) - mtime
        if age >= timedelta(days=max_age_days):
            return True, f"age {age.days}d >= {max_age_days}d"
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


def _expand_patterns(audit_dir: Path) -> list[Path]:
    """Resolve all audit log files (literal + glob patterns) under audit_dir."""
    paths: list[Path] = []
    for pattern in AUDIT_LOG_PATTERNS:
        path = audit_dir / pattern
        if path.is_file():
            paths.append(path)
    for glob_pat in AUDIT_LOG_GLOB_PATTERNS:
        # Exclude already-rotated files (they have a date suffix in stem)
        for p in audit_dir.glob(glob_pat):
            # Skip rotated copies (filename like base.2026-06-08.log).
            # Rotated copies have 2+ dots before the extension (base + date).
            if p.is_file() and not _is_rotated_copy(p):
                paths.append(p)
    return paths


def _is_rotated_copy(p: Path) -> bool:
    """Detect if `p` is already a rotated copy (e.g. `base.2026-06-08.log`).

    Heuristic : the stem contains a YYYY-MM-DD-shaped fragment AFTER the
    base name. Used to avoid recursively rotating rotated files.
    """
    import re
    return bool(re.search(r"\.\d{4}-\d{2}-\d{2}(\.\d+)?$", p.stem))


def rotate_if_due(throttle_hours: int = 24) -> bool:
    """v7.0.1 audit P1 v2 (2026-06-08) — throttled invocation for hooks.

    Designed to be called from low-frequency hooks (SessionStart, Stop)
    without becoming a perf burden. Reads `.last-rotation` marker file
    in the audit dir : if mtime is within `throttle_hours`, exit silently
    without doing any work. Otherwise, run full rotation with defaults and
    bump the marker.

    Returns True if rotation actually ran, False if throttled or skipped.

    Non-blocking by design : any I/O failure is swallowed (this is a
    best-effort housekeeping task, not a security gate).
    """
    try:
        audit_dir = repo_root() / "workspace" / "output" / ".sys" / ".audit"
        if not audit_dir.is_dir():
            return False
        marker = audit_dir / ".last-rotation"
        now = datetime.now(timezone.utc)
        if marker.is_file():
            last = datetime.fromtimestamp(marker.stat().st_mtime, tz=timezone.utc)
            if (now - last) < timedelta(hours=throttle_hours):
                return False
        # Run rotation with defaults, quiet.
        paths = _expand_patterns(audit_dir)
        for path in paths:
            rotate, _reason = _should_rotate(
                path, DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, DEFAULT_MAX_AGE_DAYS
            )
            if rotate:
                _rotate_one(path, dry_run=False)
            _prune_old(audit_dir, path.name, DEFAULT_KEEP_ROTATIONS, dry_run=False)
        # Bump marker (creates if absent).
        marker.touch()
        return True
    except Exception:
        # Best-effort : silent on failure.
        return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would happen, don't touch files.")
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    p.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    p.add_argument("--keep", type=int, default=DEFAULT_KEEP_ROTATIONS)
    p.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                   help="Rotate log if mtime older than this many days (audit P1 v2).")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-file 'skip' lines (only show actions).")
    args = p.parse_args()

    audit_dir = repo_root() / "workspace" / "output" / ".sys" / ".audit"
    if not audit_dir.is_dir():
        if not args.quiet:
            print(f"audit dir absent ({audit_dir}) — nothing to rotate")
        return SUCCESS
    any_action = False
    paths = _expand_patterns(audit_dir)
    for path in paths:
        rotate, reason = _should_rotate(
            path, args.max_bytes, args.max_lines, args.max_age_days
        )
        if rotate:
            any_action = True
            new_path = _rotate_one(path, args.dry_run)
            verb = "[DRY] would rotate" if args.dry_run else "rotated"
            print(f"{verb} {path.name} -> {new_path.name} ({reason})")
        elif not args.quiet:
            print(f"skip {path.name} ({reason})")

        # Prune old rotations
        deleted = _prune_old(audit_dir, path.name, args.keep, args.dry_run)
        for d in deleted:
            verb = "[DRY] would delete" if args.dry_run else "deleted old"
            print(f"  {verb} {d.name}")
            any_action = True

    if not any_action and not args.quiet:
        print("no rotation needed (logs under thresholds, no old rotations to prune)")
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
