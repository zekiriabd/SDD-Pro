#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Edit|Write|MultiEdit).

Warns when an agent targets a framework-owned file. Non-blocking:
emit WARNING on stderr and exit 0.

Migrated from .claude/hooks/protect-framework.ps1 (2026-05-13).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.hook_input import get_file_path, read_hook_input  # noqa: E402
from sdd_lib.paths import normalize  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


FRAMEWORK_OWNED: tuple[str, ...] = (
    ".claude/rules/",
    ".claude/stacks/",
    ".claude/agents/",
    ".claude/templates/",
    ".claude/commands/",
    ".claude/python/",
    ".claude/loader.yml",
    ".claude/CLAUDE.md",
    ".claude/MIGRATION.md",
    ".claude/CHANGELOG.md",
)


def main() -> int:
    payload = read_hook_input()
    file_path = get_file_path(payload)
    if not file_path:
        return 0

    norm = normalize(file_path)
    if any(p in norm for p in FRAMEWORK_OWNED):
        warn(f"WARNING: '{file_path}' est un fichier propriete framework SDD_Pro.")
        warn("         Les agents produit (po, arch, dev-*, qa, dashboard) ne doivent pas le modifier.")
        warn("         Maintenance framework autorisee deliberement (Tech Lead).")

    if ".claude/CLAUDE.md" in norm:
        warn("         Rappel: synchroniser .claude/CHANGELOG.md et docs/ si changement architectural.")
    if ".claude/loader.yml" in norm:
        warn("         Rappel: loader.yml doit refleter les reads/writes reels des agents.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
