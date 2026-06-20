#!/usr/bin/env python3
"""Strip UTF-8 BOM (U+FEFF) from all .md files under .claude/.

Why: Claude Code's subagent loader requires files to start exactly with
`---` to parse YAML frontmatter. A leading BOM (often introduced by
PowerShell `Out-File -Encoding UTF8`) breaks the parser → agents are
not registered → orchestrator commands like /sdd-full can't invoke
their subagents.

Idempotent: re-running on already-clean files is a no-op.

Usage:
    python .claude/python/sdd_admin/strip_bom.py
    python .claude/python/sdd_admin/strip_bom.py --check   # report only, no write
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure sdd_lib is importable when script invoked directly (no PYTHONPATH).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import SUCCESS  # noqa: E402

BOM = b"\xef\xbb\xbf"

SEARCH_ROOTS = [
    Path(".claude/agents"),
    Path(".claude/commands"),
    Path(".claude/rules"),
    Path(".claude/stacks"),
    Path(".claude/templates"),
    Path(".claude/docs"),
    Path(".claude"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="Report files with BOM without modifying them")
    args = ap.parse_args()

    scanned = 0
    fixed: list[Path] = []
    seen: set[Path] = set()

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        files = root.rglob("*.md") if root.is_dir() else [root]
        for p in files:
            if not p.is_file() or p in seen:
                continue
            seen.add(p)
            scanned += 1
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            if raw.startswith(BOM):
                if not args.check:
                    p.write_bytes(raw[len(BOM):])
                fixed.append(p)

    label = "would strip" if args.check else "BOM removed from"
    print(f"Scanned {scanned} .md files")
    print(f"{label} {len(fixed)} files:")
    for p in fixed:
        print(f"  {p.as_posix()}")

    return SUCCESS
if __name__ == "__main__":
    raise SystemExit(main())
