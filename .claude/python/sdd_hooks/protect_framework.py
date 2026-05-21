#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Edit|Write|MultiEdit).

Detects when an agent targets a framework-owned file.

Mode (v7.0.0 audit hardening 2026-05-20) :
  - Interactive (default) : WARN on stderr, exit 0 (Tech Lead may
    deliberately edit framework in dev — current behavior preserved).
  - CI auto-detect     : BLOCKING exit 2 (an agent must NEVER modify
    framework in CI — that's a regression vector).
  - $SDD_PROTECT_FRAMEWORK_MODE = warn|strict|off : explicit override.

Migrated from .claude/hooks/protect-framework.ps1 (2026-05-13).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_DENY  # noqa: E402
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


def _detect_ci() -> bool:
    """Best-effort CI detection (mirror preflight_agent_budget.py)."""
    ci_signals = (
        "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
        "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
        "BITBUCKET_BUILD_NUMBER",
    )
    return any(
        (os.environ.get(v, "").strip().lower() not in ("", "0", "false", "no"))
        for v in ci_signals
    )


def _resolve_mode() -> str:
    """Precedence : env override > CI auto-detect > 'warn' default."""
    explicit = (os.environ.get("SDD_PROTECT_FRAMEWORK_MODE") or "").strip().lower()
    if explicit in ("warn", "strict", "off"):
        return explicit
    return "strict" if _detect_ci() else "warn"


def main() -> int:
    mode = _resolve_mode()
    if mode == "off":
        return 0

    payload = read_hook_input()
    file_path = get_file_path(payload)
    if not file_path:
        return 0

    norm = normalize(file_path)
    if not any(p in norm for p in FRAMEWORK_OWNED):
        return 0

    if mode == "strict":
        warn(f"ERROR: protect-framework — '{file_path}' est propriete framework SDD_Pro")
        warn(f"CAUSE: [FRAMEWORK_PROTECTED] tentative d'edit en mode strict (CI ou explicite)")
        warn(f"FIX: (a) si edit legitime Tech Lead : export SDD_PROTECT_FRAMEWORK_MODE=warn")
        warn(f"     (b) si agent produit modifie le framework : c'est un BUG, ne pas bypass")
        return HOOK_DENY

    # warn mode (default interactive)
    warn(f"WARNING: '{file_path}' est un fichier propriete framework SDD_Pro.")
    warn("         Les agents produit (po, arch, dev-*, qa) ne doivent pas le modifier.")
    warn("         Maintenance framework autorisee deliberement (Tech Lead).")

    if ".claude/CLAUDE.md" in norm:
        warn("         Rappel: synchroniser .claude/CHANGELOG.md et docs/ si changement architectural.")
    if ".claude/loader.yml" in norm:
        warn("         Rappel: loader.yml doit refleter les reads/writes reels des agents.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
