#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Write/Edit/MultiEdit/NotebookEdit + Bash/PowerShell)
— confinement des reviewers read-only (2026-11-07).

Problème (audit 2026-11-07) : les 5 reviewers (`code-reviewer`,
`security-reviewer`, `spec-compliance-reviewer`, `arch-reviewer`,
`adversarial-reviewer`) se déclarent « strictement read-only sur le code »
mais disposent de `Write` et `Bash` — nécessaires pour écrire leur rapport et
lancer les scripts de validation/ingestion. Rien ne les empêchait de modifier
`workspace/src/**`, et ils sont exclus du hook `audit_file_ownership`.

Décision Tech Lead : garder les outils, confiner par hook.

**Écritures (Write/Edit/MultiEdit/NotebookEdit)** : autorisées UNIQUEMENT
sous `workspace/.sys/.validation/` (rapports `{n}-*.md|json`, `.tmp` atomiques,
`.flag`). Tout autre chemin → DENY.

**Shell (Bash/PowerShell)** — liste blanche par segment (`;`, `&&`, `|`…) :
  - lecture seule : grep/rg/cat/head/tail/wc/ls/find (sans -delete/-exec)/
    sort/uniq/cut/diff/jq/echo/cd/pwd…, équivalents PowerShell en lecture ;
  - `git` en lecture : diff/log/status/show/ls-files/rev-parse/blame/grep ;
  - `python` : uniquement `python -m sdd_scripts.*|sdd_lib.*|sdd_admin.*`
    ou un script `.sdd/python/**.py` (code framework, protégé) — jamais
    `python -c` ni `python -` (code inline arbitraire) ;
  - interdits : substitution `$(…)` / backticks / `<(…)`, préfixe
    d'assignation `VAR=x cmd`, toute cible d'écriture shell (redirection,
    tee, cp…) hors `workspace/.sys/.validation/`.

**Pas de bypass** : comme le mode strict sous-agent de `protect_framework`,
le confinement est une constante de module — un reviewer ne peut pas le
désactiver. Les appels hors reviewers (session principale, autres agents)
ne sont pas concernés (exit 0 immédiat).

Fail-closed : une commande que le hook ne sait pas analyser est refusée.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_caller_agent_type,
    get_file_path,
    read_hook_input,
)
from sdd_lib.paths import repo_root  # noqa: E402

#: Agents confinés (read-only sur le code, écriture limitée à leurs rapports).
REVIEWERS = frozenset({
    "code-reviewer",
    "security-reviewer",
    "spec-compliance-reviewer",
    "arch-reviewer",
    "adversarial-reviewer",
})

#: Seul répertoire où un reviewer peut écrire.
ALLOWED_WRITE_PREFIX = "workspace/.sys/.validation/"

_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

#: Commandes en lecture seule autorisées en tête de segment (minuscules).
_READONLY_HEADS = frozenset({
    # POSIX
    "grep", "egrep", "fgrep", "rg", "cat", "head", "tail", "wc", "ls", "dir",
    "find", "sort", "uniq", "cut", "diff", "jq", "file", "stat", "basename",
    "dirname", "realpath", "tr", "echo", "printf", "pwd", "cd", "test",
    "true", "false",
    # PowerShell (lecture)
    "get-content", "gc", "select-string", "sls", "get-childitem", "gci",
    "measure-object", "select-object", "where-object", "sort-object",
    "format-table", "format-list", "out-string", "convertfrom-json",
    "test-path", "resolve-path", "get-item", "write-output", "set-location",
})

_GIT_READONLY = frozenset({
    "diff", "log", "status", "show", "ls-files", "rev-parse", "blame",
    "grep", "cat-file",
})

_FIND_FORBIDDEN = frozenset({
    "-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0",
    "-fprintf", "-fls",
})

_PYTHON_HEADS = frozenset({"python", "python3", "py"})
_PYTHON_OK_FLAGS = frozenset({"-I", "-u", "-B", "-E", "-s"})
_PY_MODULE_RE = re.compile(r"^(sdd_scripts|sdd_lib|sdd_admin)(\.[A-Za-z_]\w*)+$")

_SUBST_RE = re.compile(r"\$\(|`|<\(|>\(")
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _norm_rel(path: str, root: Path) -> str:
    """Chemin relatif au dépôt, slashs avant ; absolu hors dépôt inchangé."""
    p = path.replace("\\", "/").strip().strip('"').strip("'")
    try:
        cand = Path(p)
        if not cand.is_absolute():
            cand = root / cand
        rel = cand.resolve().relative_to(root.resolve())
        return rel.as_posix()
    except (ValueError, OSError, RuntimeError):
        return p


def _write_allowed(path: str, root: Path) -> bool:
    if "$" in path or "%" in path:
        return False  # cible non résolue → fail-closed
    rel = _norm_rel(path, root)
    if Path(rel).is_absolute() or rel.startswith("../") or "/../" in f"/{rel}/":
        return False
    return rel.startswith(ALLOWED_WRITE_PREFIX)


def _head_of(token: str) -> str:
    name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for ext in (".exe", ".cmd", ".bat"):
        if name.endswith(ext):
            name = name[: -len(ext)]
    return name


def _python_allowed(tokens: list[str]) -> str | None:
    """None si l'invocation python est autorisée, sinon la raison du refus."""
    i = 1
    while i < len(tokens) and tokens[i] in _PYTHON_OK_FLAGS:
        i += 1
    if i >= len(tokens):
        return "python interactif / stdin interdit"
    arg = tokens[i]
    if arg == "-m":
        mod = tokens[i + 1] if i + 1 < len(tokens) else ""
        if _PY_MODULE_RE.match(mod):
            return None
        return f"module `{mod or '?'}` hors sdd_scripts/sdd_lib/sdd_admin"
    if arg.startswith("-"):
        return f"option python `{arg}` interdite (code inline arbitraire)"
    script = arg.replace("\\", "/")
    while script.startswith("./"):
        script = script[2:]
    in_framework = script.startswith(".sdd/python/") or "/.sdd/python/" in script
    if script.endswith(".py") and in_framework and ".." not in script.split("/"):
        return None
    return f"script `{arg}` hors .sdd/python/"


def _segment_violation(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    first = tokens[0]
    if _ASSIGN_RE.match(first):
        return "préfixe d'assignation de variable interdit"
    head = _head_of(first)
    if head in _READONLY_HEADS:
        if head == "find":
            bad = [t for t in tokens[1:] if t.lower() in _FIND_FORBIDDEN]
            if bad:
                return f"`find {bad[0]}` interdit"
        return None
    if head == "git":
        sub = next((t for t in tokens[1:] if not t.startswith("-")), "")
        if sub.lower() in _GIT_READONLY:
            return None
        return f"`git {sub or '?'}` hors lecture seule"
    if head in _PYTHON_HEADS:
        return _python_allowed(tokens)
    return f"commande `{head}` hors liste blanche"


def _shell_violation(cmd: str, root: Path, cwd: str | None) -> str | None:
    from sdd_lib.shell_write_targets import (
        extract_write_targets,
        resolve_target,
        split_segments,
        tokenize,
    )
    if _SUBST_RE.search(cmd):
        return "substitution de commande `$(…)` / backticks / `<(…)` interdite"
    try:
        segments = split_segments(cmd)
    except Exception:  # noqa: BLE001 — non analysable → fail-closed
        return "commande non analysable"
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        try:
            tokens = [t for t in tokenize(text) if t not in (">", ">>", "<")]
        except Exception:  # noqa: BLE001
            return "segment non analysable"
        why = _segment_violation(tokens)
        if why:
            return why
    base = Path(cwd) if cwd and Path(cwd).is_dir() else root
    try:
        targets = extract_write_targets(cmd)
    except Exception:  # noqa: BLE001
        return "cibles d'écriture non analysables"
    for t in targets:
        if t.cwd == "?":
            return f"répertoire courant inconnu pour {t.describe()}"
        abs_p = resolve_target(t, base)
        path = str(abs_p) if abs_p is not None else t.path
        if not _write_allowed(path, root):
            return f"écriture hors {ALLOWED_WRITE_PREFIX} : {t.describe()}"
    return None


def _audit(agent: str, tool: str, subject: str, reason: str) -> None:
    try:
        from sdd_lib.paths import audit_dir_path, project_root_for_hook
        d = audit_dir_path(project_root_for_hook())
        d.mkdir(parents=True, exist_ok=True)
        line = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "event": "reviewer_confinement_deny",
            "agent": agent, "tool": tool, "subject": subject[:500],
            "reason": reason,
        }
        with (d / "reviewer-confinement.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — l'audit ne casse jamais le hook
        pass


def _deny(agent: str, tool: str, subject: str, reason: str) -> int:
    sys.stderr.write(
        f"ERROR: {agent} {tool} refusé (reviewer read-only)\n"
        f"CAUSE: [REVIEWER_CONFINEMENT_VIOLATION] {reason}\n"
        f"FIX: un reviewer n'écrit que ses rapports sous {ALLOWED_WRITE_PREFIX} "
        "et ne lance que des commandes de lecture ou les scripts .sdd/python ; "
        "toute correction de code relève de /dev-backend ou /dev-frontend.\n"
    )
    _audit(agent, tool, subject, reason)
    return HOOK_DENY


def main() -> int:
    try:
        payload = read_hook_input()
    except (json.JSONDecodeError, OSError, UnicodeError, ValueError):
        return HOOK_ALLOW  # pas de payload → pas un appel reviewer identifiable
    agent = get_caller_agent_type(payload)
    if agent not in REVIEWERS:
        return HOOK_ALLOW
    tool = payload.get("tool_name", "") or ""
    try:
        root = repo_root()
    except (OSError, RuntimeError):
        return _deny(agent, tool, "", "racine du dépôt introuvable (fail-closed)")

    if tool in _WRITE_TOOLS:
        tool_input = payload.get("tool_input") or {}
        path = get_file_path(payload) or tool_input.get("notebook_path") or ""
        if not path:
            return _deny(agent, tool, "", "chemin d'écriture absent (fail-closed)")
        if _write_allowed(path, root):
            return HOOK_ALLOW
        return _deny(agent, tool, path, f"écriture hors {ALLOWED_WRITE_PREFIX} : {path}")

    if tool in _SHELL_TOOLS:
        cmd = (payload.get("tool_input") or {}).get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            return HOOK_ALLOW
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
        why = _shell_violation(cmd, root, cwd)
        if why:
            return _deny(agent, tool, cmd, why)
        return HOOK_ALLOW

    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
