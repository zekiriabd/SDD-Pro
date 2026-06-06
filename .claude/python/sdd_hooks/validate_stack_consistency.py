#!/usr/bin/env python3
"""SDD_Pro PostToolUse hook — refuse stack.md multi-stack incoherent.

Fires on PostToolUse (matcher=Edit|Write|MultiEdit). Filters internally to
only edits touching `workspace/input/stack/stack.md`.

Detects incoherent states from bench multi-stack (2026-06-05 bench had 4
backends + 2 fullstack + 4 SPA + 3 mobiles enabled together, combo signature
returned "invalid") :

1. >1 backend `backend/*` active (impossible: 1 process backend)
2. >1 fullstack `fullstack/*` active (impossible: 1 monolithe)
3. backend `backend/*` + fullstack `fullstack/*` together (incoherent: monolith vs back-front separate)
4. >1 frontend `frontend/*` SPA (1 project = 1 main SPA)

Exit semantics:
    0  coherent or non-applicable
    2  incoherent -> BLOCK + stderr message

Bypass: SDD_ALLOW_MULTISTACK=1 env var.

v7.0.0-alpha (audit P2 - 2026-06-05) - closes gap "stack.md can be set
to multi-stack incoherent via bootstrap/console/manual edit".
"""
from __future__ import annotations

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.paths import project_root_for_hook as _resolve_project_root

import json
import os
import re
import sys
from pathlib import Path


ACTIVE_PATTERN = re.compile(
    r"^\s+-\s+\.claude/stacks/(backend|frontend|fullstack|mobiles|archi|ui|qa|auth)/([\w-]+)\.md\s*$",
    re.MULTILINE,
)


def _read_payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def _extract_edited_path(payload: dict) -> str | None:
    tool_input = payload.get("tool_input") or {}
    p = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("filePath")
    if isinstance(p, str):
        return p.replace("\\", "/")
    return None


def _is_stack_md(path: str | None) -> bool:
    if not path:
        return False
    return path.endswith("/workspace/input/stack/stack.md")


def _parse_active_stacks(stack_md: Path) -> dict[str, list[str]]:
    try:
        content = stack_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    result: dict[str, list[str]] = {
        "backend": [], "frontend": [], "fullstack": [],
        "mobiles": [], "archi": [], "ui": [], "qa": [], "auth": [],
    }
    for m in ACTIVE_PATTERN.finditer(content):
        cat, stack_id = m.group(1), m.group(2)
        if cat in result:
            result[cat].append(stack_id)
    return result


def _check_coherence(active: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    n_backend = len(active.get("backend", []))
    n_frontend = len(active.get("frontend", []))
    n_fullstack = len(active.get("fullstack", []))

    if n_backend > 1:
        errors.append(f"backend multi-actif ({n_backend}): {', '.join(active['backend'])}. Un seul backend par projet.")
    if n_fullstack > 1:
        errors.append(f"fullstack multi-actif ({n_fullstack}): {', '.join(active['fullstack'])}. Un seul fullstack a la fois.")
    if n_backend >= 1 and n_fullstack >= 1:
        errors.append(f"backend + fullstack simultanes: backend={active['backend']}, fullstack={active['fullstack']}. Choisir un OU l'autre.")
    if n_frontend > 1:
        errors.append(f"frontend multi-actif ({n_frontend}): {', '.join(active['frontend'])}. Un projet = une SPA.")
    return errors


def main() -> int:
    payload = _read_payload()
    path = _extract_edited_path(payload)

    if not _is_stack_md(path):
        return HOOK_ALLOW
    if os.environ.get("SDD_ALLOW_MULTISTACK", "").lower() in ("1", "true", "yes"):
        sys.stderr.write("[stack-coherence] SDD_ALLOW_MULTISTACK=1 - bypass\n")
        return HOOK_ALLOW
    root = _resolve_project_root()
    stack_md = root / "workspace" / "input" / "stack" / "stack.md"
    if not stack_md.is_file():
        return HOOK_ALLOW
    active = _parse_active_stacks(stack_md)
    errors = _check_coherence(active)

    if not errors:
        return HOOK_ALLOW
    sys.stderr.write("ERROR: stack.md etat multi-stack incoherent\n")
    sys.stderr.write("CAUSE: [STACK_MULTI_INCOHERENT] regles violees :\n")
    for err in errors:
        sys.stderr.write(f"  - {err}\n")
    sys.stderr.write("FIX: commenter (#) les stacks excedentaires dans workspace/input/stack/stack.md ## Active *\n")
    sys.stderr.write("     OU bypass via env SDD_ALLOW_MULTISTACK=1 (bench / debug uniquement)\n")
    return HOOK_DENY
if __name__ == "__main__":
    sys.exit(main())
