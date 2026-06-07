#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Glob) — anti-explosion guard for unbounded Glob.

Audit CTO 2026-06-07 — post-mortem documented in
`agents/spec-compliance-reviewer.md` (line ~178) showed an unbounded
Glob `workspace/output/src/**/*` during a 1.8M-token / $35 reviewer session.
The spec-compliance + code-reviewer + security-reviewer + arch-reviewer
agents all carry "anti-pattern strict : pas de Glob workspace/output/src/**/*"
in their prompts, but a distracted Sonnet 4.6 can still emit the pattern.

This hook is a defense-in-depth runtime guard. It refuses :
  - bare ``workspace/output/src/**/*``
  - bare ``workspace/output/src/**``
  - bare ``**/*``
  - bare ``./**/*`` and equivalents

While allowing :
  - scoped globs (``workspace/output/src/{Project}/Services/**/*.cs``)
  - globs with explicit file extension (``workspace/output/src/**/*.cs``,
    ``workspace/output/src/**/*.ts``, ...) when caller adds suffix
  - any Glob outside ``workspace/output/src/`` (other dirs are typically
    small and don't risk token explosion)

Modes :
  - default WARN — exit 0 + stderr WARN (audit-log) for legacy callers
  - strict via ``SDD_GLOB_SCOPE_STRICT=1`` — exit 2 (BLOCK)
  - off via ``SDD_DISABLE_GLOB_SCOPE=1`` — bypass entirely

Wiring : ``settings.json`` `PreToolUse` matcher ``Glob`` (audit-logged).
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import read_hook_input  # noqa: E402
from sdd_lib.paths import project_root_for_hook  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


#: Patterns considered "broad" — match the entire src/ tree without scoping.
#: Note these are CASE-INSENSITIVE and normalize backslashes to forward slashes.
_BROAD_GLOB_PATTERNS: tuple[re.Pattern, ...] = (
    # workspace/output/src/**/* (no extension constraint)
    re.compile(r"^workspace/output/src/\*\*/\*$"),
    re.compile(r"^workspace/output/src/\*\*$"),
    # naked **/* or **
    re.compile(r"^\*\*/\*$"),
    re.compile(r"^\*\*$"),
    # ./**/*
    re.compile(r"^\./\*\*/\*$"),
)


def _normalize_pattern(pattern: str) -> str:
    """Lowercase + forward slashes + strip surrounding whitespace."""
    return pattern.strip().replace("\\", "/").lower()


def _is_broad_glob(pattern: str) -> bool:
    norm = _normalize_pattern(pattern)
    return any(p.match(norm) for p in _BROAD_GLOB_PATTERNS)


def _resolve_mode() -> str:
    if os.environ.get("SDD_DISABLE_GLOB_SCOPE") == "1":
        return "off"
    if os.environ.get("SDD_GLOB_SCOPE_STRICT") == "1":
        return "strict"
    return "warn"


def _audit_log(pattern: str, mode: str, decision: str) -> None:
    """Append JSONL audit line (best-effort, non-blocking on I/O failure)."""
    import json
    try:
        root = project_root_for_hook()
        audit_dir = root / "workspace" / "output" / ".sys" / ".audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        line = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "event": "glob_scope_broad",
            "pattern": pattern,
            "mode": mode,
            "decision": decision,
        }
        with (audit_dir / "glob-scope.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        # Audit must not break the hook. Swallow.
        pass


def main() -> int:
    mode = _resolve_mode()
    if mode == "off":
        return HOOK_ALLOW

    payload = read_hook_input()
    tool_input = payload.get("tool_input") or {}
    pattern = tool_input.get("pattern")
    if not pattern or not isinstance(pattern, str):
        # Defensive : missing pattern → not our concern, allow.
        return HOOK_ALLOW

    if not _is_broad_glob(pattern):
        return HOOK_ALLOW

    # Broad pattern detected.
    if mode == "strict":
        warn(f"ERROR: glob-scope — pattern '{pattern}' is too broad")
        warn(f"CAUSE: [GLOB_SCOPE_TOO_BROAD] unbounded Glob under workspace/output/src/ "
             f"would risk reading 1000s of files (token explosion documented in "
             f"agents/spec-compliance-reviewer.md post-mortem)")
        warn(f"FIX: scope the pattern (e.g. 'workspace/output/src/{{Project}}/Services/**/*.cs') "
             f"OR `export SDD_DISABLE_GLOB_SCOPE=1` for a session (audit-logged)")
        _audit_log(pattern, mode, "DENY")
        return HOOK_DENY

    # warn mode (default) : log but allow
    warn(f"WARN: glob-scope — broad pattern '{pattern}' detected "
         f"(would risk token explosion under workspace/output/src/). "
         f"Use scoped path or set SDD_GLOB_SCOPE_STRICT=1 to enforce.")
    _audit_log(pattern, mode, "ALLOW")
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
