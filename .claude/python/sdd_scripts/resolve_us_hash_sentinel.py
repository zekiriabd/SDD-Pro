#!/usr/bin/env python3
"""SDD_Pro — Resolve `Parent FEAT hash: sha256:COMPUTE_REQUIRED` sentinel.

Audit P0-workflow (2026-06-05) — hoisted out of `commands/us-generate.md` STEP 3.0
inline python AND wrapped by `sdd_hooks/resolve_po_hash_sentinel.py` (SubagentStop
matcher=po). Rationale: previously the sentinel was resolved ONLY by /us-generate
command. If the agent `po` was invoked standalone (Agent: po, debug session,
custom orchestrator), the sentinel persisted in US files. All downstream agents
(dev-*, auditors) then emitted `[FEAT_HASH_MISMATCH]` because "COMPUTE_REQUIRED"
is not 8 hex chars.

Defense-in-depth: this script can now be invoked from:
  - `/us-generate` STEP 3.0 (orchestrator path, normal usage)
  - SubagentStop hook matcher=po (catches all standalone Agent: po invocations)

Usage:
  python resolve_us_hash_sentinel.py --feat-number N
  python resolve_us_hash_sentinel.py --feat-number N --quiet
  python resolve_us_hash_sentinel.py --auto-detect   (scans all US files for stale sentinels)

Exit codes:
  0 = success (N files patched, OR no sentinel found, OR no work needed)
  2 = sentinel persists after patch (corruption / write failure)
  3 = infra (FEAT file missing, FS error)

Idempotent: re-running on already-resolved US files is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import SUCCESS, INFRA_BLOCKED, CORRECTIBLE  # noqa: E402
from sdd_lib.paths import project_root_for_hook as _resolve_project_root

SENTINEL = "sha256:COMPUTE_REQUIRED"


def _find_feat_file(root: Path, feat_number: int) -> Path | None:
    """Glob workspace/input/feats/{n}-*.md."""
    feats_dir = root / "workspace" / "input" / "feats"
    if not feats_dir.is_dir():
        return None
    matches = sorted(feats_dir.glob(f"{feat_number}-*.md"))
    if len(matches) != 1:
        return None
    return matches[0]


def _us_files_for_feat(root: Path, feat_number: int) -> list[Path]:
    us_dir = root / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    return sorted(us_dir.glob(f"{feat_number}-*.md"))


def _all_us_files(root: Path) -> list[Path]:
    us_dir = root / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    return sorted(us_dir.glob("*.md"))


def _us_feat_number(us_file: Path) -> int | None:
    """Extract `{n}` from `{n}-{m}-{Name}.md`."""
    parts = us_file.stem.split("-", 2)
    if len(parts) < 2:
        return None
    try:
        return int(parts[0])
    except ValueError:
        return None


def _patch(us_file: Path, hash_short: str) -> bool:
    """Return True if a patch was applied."""
    txt = us_file.read_text(encoding="utf-8")
    if SENTINEL not in txt:
        return False
    new_txt = txt.replace(SENTINEL, f"sha256:{hash_short}")
    # write_text with newline='' preserves original line endings (no CRLF
    # injection on Windows), UTF-8 without BOM (Python default for write_text).
    us_file.write_text(new_txt, encoding="utf-8", newline="")
    return True


def _resolve_one_feat(root: Path, feat_number: int, quiet: bool) -> tuple[int, int]:
    """Return (patched_count, error_count)."""
    feat_file = _find_feat_file(root, feat_number)
    if not feat_file:
        if not quiet:
            sys.stderr.write(
                f"WARN: FEAT {feat_number} file missing or ambiguous under "
                f"workspace/input/feats/ — skipping hash resolution\n"
            )
        return (0, 0)  # not an error — the qa or other agent that produced the US
                      # may have been working on a draft. SubagentStop hook should
                      # not fail the agent because of this.

    h = hashlib.sha256(feat_file.read_bytes()).hexdigest()[:8]
    patched = 0
    for us in _us_files_for_feat(root, feat_number):
        if _patch(us, h):
            patched += 1

    if not quiet and patched > 0:
        sys.stderr.write(f"[resolve-hash] patched {patched} US file(s) for FEAT {feat_number} with sha256:{h}\n")

    # Validation post-patch: no sentinel must persist for this FEAT
    remaining = [us for us in _us_files_for_feat(root, feat_number)
                 if SENTINEL in us.read_text(encoding="utf-8")]
    if remaining:
        for us in remaining:
            sys.stderr.write(f"ERROR: sentinel persists after patch: {us}\n")
        return (patched, len(remaining))

    return (patched, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Parent FEAT hash sentinel in US files.")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--feat-number", type=int, help="Target a single FEAT.")
    grp.add_argument("--auto-detect", action="store_true",
                     help="Scan all US files, infer FEAT number per file, patch.")
    parser.add_argument("--quiet", action="store_true", help="Suppress stderr informational lines.")
    args = parser.parse_args()

    root = _resolve_project_root()

    if args.feat_number is not None:
        patched, errors = _resolve_one_feat(root, args.feat_number, args.quiet)
        if errors:
            return CORRECTIBLE
        return SUCCESS

    # auto-detect mode: enumerate distinct FEAT numbers from US filenames
    feat_numbers: set[int] = set()
    for us in _all_us_files(root):
        n = _us_feat_number(us)
        if n is not None:
            txt = us.read_text(encoding="utf-8")
            if SENTINEL in txt:
                feat_numbers.add(n)

    if not feat_numbers:
        return SUCCESS  # nothing to do, idempotent no-op

    total_errors = 0
    total_patched = 0
    for n in sorted(feat_numbers):
        patched, errors = _resolve_one_feat(root, n, args.quiet)
        total_patched += patched
        total_errors += errors

    if total_errors:
        return CORRECTIBLE
    return SUCCESS


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as e:
        sys.stderr.write(f"ERROR: resolve_us_hash_sentinel — FS error\nCAUSE: [INFRA_BLOCKED] {e}\nFIX: check FS perms\n")
        sys.exit(INFRA_BLOCKED)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"ERROR: resolve_us_hash_sentinel — crash\nCAUSE: [INFRA_BLOCKED] {type(e).__name__}: {e}\nFIX: report bug\n")
        sys.exit(INFRA_BLOCKED)
