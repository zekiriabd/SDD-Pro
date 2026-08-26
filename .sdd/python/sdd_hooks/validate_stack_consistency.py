#!/usr/bin/env python3
"""SDD_Pro PostToolUse hook — refuse stack.md multi-stack incoherent.

Fires on PostToolUse (matcher=Edit|Write|MultiEdit). Filters internally to
only edits touching `workspace/stack/stack.md`.

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
from sdd_lib.paths import workspace_root, project_root_for_hook as _resolve_project_root
from sdd_lib.project_config import (  # noqa: E402
    STACK_CATEGORIES,
    parse_active_stack_ids,
)

import json
import os
import sys
from pathlib import Path


# Audit 2026-08-26 — le regex maison `ACTIVE_PATTERN` a ete supprime au profit
# de `project_config.parse_active_stack_ids` (parseur canonique, deja utilise par
# preflight.py et validate_stack_combo.py). Il exigeait `^\s+-\s+` (>= 1 espace
# de chaque cote du tiret) alors que le parseur de reference accepte `^\s*-\s*`
# (>= 0) : un `stack.md` ecrit sans indentation etait vu comme multi-backend par
# le pipeline et comme VIDE par ce hook, qui rendait donc "coherent" un fichier
# reellement incoherent. Regression couverte par
# tests/test_validate_stack_consistency.py.


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
    return path.endswith("/workspace/stack/stack.md")


def _parse_active_stacks(stack_md: Path) -> dict[str, list[str]]:
    """Categorie -> ids de stacks actifs, via le parseur canonique.

    `utf-8-sig` + `errors="replace"` : meme politique d'encodage que
    `project_config.read_stack_md_text` (audit 2026-08-26) — un `stack.md`
    re-sauve en ANSI ou avec BOM ne doit pas rendre ce hook aveugle.
    """
    try:
        content = stack_md.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}
    parsed = parse_active_stack_ids(content)
    return {cat: parsed.get(cat, []) for cat in STACK_CATEGORIES}


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
    stack_md = workspace_root(root) / "stack" / "stack.md"
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
    sys.stderr.write("FIX: commenter (#) les stacks excedentaires dans workspace/stack/stack.md ## Active *\n")
    sys.stderr.write("     OU bypass via env SDD_ALLOW_MULTISTACK=1 (bench / debug uniquement)\n")
    return HOOK_DENY
if __name__ == "__main__":
    sys.exit(main())
