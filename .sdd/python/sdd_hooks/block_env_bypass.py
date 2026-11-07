#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (matcher=`Bash|PowerShell`) — block envvar bypass attempts.

Ce que ce hook protège (audit sécurité 2026-11, docstring corrigé) :
  Les variables de bypass/mode des gardes SDD (`SDD_ALLOW_*`, `SDD_DISABLE_*`,
  `SDD_*_MODE`, `SDD_BYPASS_*`, `SDD_PROTECT_*`, `SDD_TDD_*`, `SDD_BUDGET_*`,
  `SDD_TOKEN_USAGE_*`, `SDD_AUDIT_*`, `SDD_PRE_WRITE_LINT_*`, `SDD_HOOK_*`,
  `SDD_*_STRICT`, `SDD_REPO_ROOT`, `SDD_CONSOLE_DB_PATH`, et `CI`) ne
  doivent JAMAIS être positionnées depuis une commande d'agent.

  Précision de modèle de menace : une assignation faite dans le shell de
  l'outil Bash/PowerShell n'atteint PAS l'environnement du process Claude
  Code — donc pas celui des hooks. Le risque réel est ailleurs : les
  *scripts* lancés depuis ce shell (ex. `SDD_ALLOW_ACCEPTANCE_BYPASS=1
  python validate_acceptance.py` écrit un verdict `bypass` que le gate lit
  ensuite), et la persistance éventuelle des variables d'une commande Bash
  à la suivante. Le seul canal légitime pour un bypass reste
  l'environnement du process Claude Code (shell parent, ou bloc `env` de
  `.claude/settings.local.json`), jamais une commande.

  Il n'existe PAS de règle `permissions.deny` correspondante dans
  `.claude/settings.json` (l'ancien docstring en citait) : ce hook est la
  seule barrière, et elle est heuristique (regex sur la ligne de commande,
  pas d'interprétation shell).

Formes détectées (insensible à la casse, après normalisation des quotes et
backslashes — `SDD_ALLOW_UNTESTED_COMB"O"=1` est vu comme
`SDD_ALLOW_UNTESTED_COMBO=1`) :
  - POSIX : `[export|declare -x|typeset -x|readonly] NAME=val`, inline
    `NAME=val cmd`, `env [-i] NAME=val`, `unset NAME`, `env -u NAME`,
    `bash -c "…NAME=…"`, `eval`/`source`/`printf` contenant NAME
  - PowerShell : `$env:NAME = …`, `${env:NAME} = …`, `Set-Item/New-Item/
    Set-Variable/Remove-Item env:NAME`, `[Environment]::SetEnvironmentVariable`
  - Windows : `setx NAME …`, `set NAME=…`
  - Interpréteurs inline : `os.environ[NAME] = …`, `os.environ.update/
    setdefault(…NAME…)`, `os.putenv(NAME…)`, `process.env.NAME = …`, dict
    `{NAME: …}` passé en `env=` à un sous-process
  - Indirection : `V=SDD_X; export $V`, `$v='SDD_X'; Set-Item "env:$v" 1`
    (nom protégé en VALEUR d'assignation + mot-clé de positionnement)
  - Heredocs : le corps est désormais SCANNÉ (bash l'exécute ; l'ancien
    strip ouvrait `bash <<EOF … SDD_ALLOW_X=1 … EOF`). Conséquence
    assumée : un message de commit en heredoc qui documente
    `SDD_ALLOW_X=1` est refusé — utiliser `git commit -F fichier`.

Contournements connus (non couverts, heuristique) : construction du nom par
concaténation dynamique (`"SDD_AL""LOW"` dans un langage tiers, base64,
`chr()`), script écrit sur disque puis exécuté, variables positionnées par
un outil externe.

Exit codes : 0 = ALLOW, 2 = DENY. Tout refus est journalisé
(`workspace/.sys/.audit/env-bypass.jsonl`, valeurs de secrets masquées).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.paths import audit_dir_path, workspace_root, project_root_for_hook  # noqa: E402


def _resolve_project_root() -> Path | None:
    """DRY shim — delegate to `sdd_lib.paths.project_root_for_hook`.

    Returns the resolved root if a `.claude/` or `.sdd/` directory exists at
    it, else None (preserves the "skip silently in isolated tmpdir" semantic).
    """
    root = project_root_for_hook()
    if (root / ".claude").is_dir() or (root / ".sdd").is_dir():
        return root
    return None


# v7.0.1 audit P1 v2 (2026-06-08) — secret masking before audit log write.
# If a user accidentally exports secrets inline with the bypass attempt
# (e.g. `export MY_DB_PASSWORD=foo SDD_ALLOW_FORCE=1 cmd`), the raw command
# excerpt would leak `MY_DB_PASSWORD=foo` to `.sys/.audit/env-bypass.jsonl`.
# This regex masks any `<NAME>=<value>` assignment where NAME matches
# common secret patterns (PASSWORD/SECRET/TOKEN/KEY/PASSWD/PWD/APIKEY/...).
# Tuned conservatively : only masks the VALUE, not the NAME, so forensics
# can still see WHICH key was exposed without the value itself.
_SECRET_MASK_RE = re.compile(
    r"(?P<prefix>(?P<name>[A-Za-z0-9_]*"
    r"(?:PASSWORD|PASSWD|PWD|SECRET|TOKEN|APIKEY|API_KEY|"
    r"PRIVATE_KEY|ACCESS_KEY|AUTH_KEY|JWT|BEARER|SESSION_ID|"
    r"COOKIE|CREDENTIAL|CRED))"
    r"[\s]*=[\s]*)"
    r"(?P<quote>[\"']?)"
    r"(?P<value>[^\s\"';|&]+)"
    r"(?P=quote)",
    re.IGNORECASE,
)


def _mask_secrets(text: str) -> str:
    """Replace `SECRET_NAME=value` patterns with `SECRET_NAME=***` in audit text.

    Conservative masking : only the VALUE is replaced. The key NAME is
    preserved so forensics can identify which secret was exposed.

    Example :
        in:  `export DB_PASSWORD=hunter2 SDD_ALLOW_FORCE=1`
        out: `export DB_PASSWORD=*** SDD_ALLOW_FORCE=1`
    """
    return _SECRET_MASK_RE.sub(r"\g<prefix>\g<quote>***\g<quote>", text)


def _audit_log(match: str, cmd: str, bypass_set: bool) -> None:
    """Persist a JSONL audit line for env-bypass denials (never raises)."""
    try:
        root = _resolve_project_root()
        if root is None:
            return  # no project — skip silently (e.g. pytest in isolated tmpdir)
        audit_dir = audit_dir_path(root)
        audit_dir.mkdir(parents=True, exist_ok=True)
        masked_excerpt = _mask_secrets(cmd[:240])
        line = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "event": "env_bypass_blocked",
            "matched_pattern": match,
            "command_excerpt": masked_excerpt,
            "bypass_flag_inherited": bypass_set,
            "decision": "DENY",
        }
        with (audit_dir / "env-bypass.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        # Audit must not break security. Swallow.
        pass


# Protected envvar name patterns (case-insensitive). Positionner l'une de
# ces variables désactive ou affaiblit un garde (cost cap, gates, TDD,
# ownership, protection framework, détection CI, emplacement de console.db…).
PROTECTED_PATTERNS = [
    r"SDD_(?:ALLOW|DISABLE|BYPASS|PROTECT|TDD|BUDGET|TOKEN_USAGE|AUDIT|"
    r"PRE_WRITE_LINT|HOOK)_[A-Z0-9_]*",
    r"SDD_[A-Z0-9_]*_(?:MODE|STRICT)",
    r"SDD_(?:REPO_ROOT|CONSOLE_DB_PATH)",
    r"CI",
]

_NAME = r"(?:" + "|".join(PROTECTED_PATTERNS) + r")(?![A-Za-z0-9_])"
#: Frontière gauche d'un nom en position d'assignation POSIX.
_LB = r"(?:^|(?<=[\s;&|`(){]))"

_BYPASS_REGEXES = [
    # POSIX : [export|declare -x|typeset -x|readonly|local] NAME=val, inline NAME=val
    re.compile(rf"{_LB}(?:(?:export|declare|typeset|readonly|local)\s+(?:-[a-zA-Z]+\s+)*)?{_NAME}=",
               re.IGNORECASE),
    # POSIX : env [-i] NAME=val / env -u NAME (unset) / unset NAME
    re.compile(rf"\benv\s+(?:-[a-zA-Z]+\s+)*{_NAME}=", re.IGNORECASE),
    re.compile(rf"\benv\s+(?:-[a-zA-Z]+\s+)*-u\s*{_NAME}", re.IGNORECASE),
    re.compile(rf"\bunset\s+(?:-[a-zA-Z]+\s+)*{_NAME}", re.IGNORECASE),
    # PowerShell : $env:NAME = …  /  ${env:NAME} = …
    re.compile(rf"\$\{{?env:{_NAME}\}}?\s*=", re.IGNORECASE),
    # PowerShell : Set-Item / New-Item / Set-Variable / Remove-Item / Clear-Item env:NAME
    re.compile(rf"\b(?:Set-Item|New-Item|Set-Variable|Remove-Item|Clear-Item|si|ni|ri|sv)\s+"
               rf"(?:-(?:Path|Name|LiteralPath)\s+)?env:{_NAME}", re.IGNORECASE),
    # .NET : [Environment]::SetEnvironmentVariable("NAME", …)
    re.compile(rf"\[(?:System\.)?Environment\]::SetEnvironmentVariable\s*\(\s*{_NAME}",
               re.IGNORECASE),
    # Windows : setx NAME val / set NAME=val (cmd.exe)
    re.compile(rf"\bsetx\s+(?:/[a-zA-Z]+\s+)*{_NAME}\s+\S", re.IGNORECASE),
    re.compile(rf"\bset\s+{_NAME}=", re.IGNORECASE),
    # Interpréteurs : os.environ[NAME] = / os.environ.update|setdefault(…NAME…) / os.putenv(NAME
    re.compile(rf"os\s*\.\s*environ\s*\[\s*{_NAME}\s*\]\s*=(?!=)", re.IGNORECASE),
    re.compile(rf"os\s*\.\s*environ\s*\.\s*(?:update|setdefault|__setitem__)\s*\([^)]*?{_NAME}",
               re.IGNORECASE | re.DOTALL),
    re.compile(rf"os\s*\.\s*putenv\s*\(\s*{_NAME}", re.IGNORECASE),
    # Node : process.env.NAME = / process.env[NAME] =
    re.compile(rf"process\s*\.\s*env\s*(?:\.\s*{_NAME}|\[\s*{_NAME}\s*\])\s*=(?!=)", re.IGNORECASE),
    # eval / source / . / printf / bash -c portant le nom protégé
    re.compile(rf"\b(?:eval|source)\s+.*?{_NAME}", re.IGNORECASE | re.DOTALL),
    re.compile(rf"(?:^|[\s;&|])\.\s+\S*.*?{_NAME}\s*=", re.IGNORECASE | re.DOTALL),
    re.compile(rf"\bprintf\s+.*?{_NAME}\s*=", re.IGNORECASE | re.DOTALL),
    re.compile(rf"\b(?:bash|sh|zsh|cmd|pwsh|powershell)(?:\.exe)?\s+(?:/c|-c|-Command)\s+.*?{_NAME}\s*=",
               re.IGNORECASE | re.DOTALL),
]

#: Dict passé en `env=` à un sous-process dans du code inline :
#: `{**os.environ, "SDD_X": "1"}` → normalisé `SDD_X:1`.
_INLINE_INTERP_RE = re.compile(r"\b(?:python3?|py|node)(?:\.exe)?\s+(?:-[a-zA-Z]*\s+)*-[ce]\b",
                               re.IGNORECASE)
_DICT_KEY_RE = re.compile(rf"(?:^|[\s{{,(]){_NAME}\s*:\s*\S", re.IGNORECASE)

#: Indirection : un nom protégé en VALEUR d'assignation, plus un mot-clé
#: de positionnement d'env quelque part dans la commande.
_VALUE_IS_NAME_RE = re.compile(rf"[A-Za-z_]\w*\s*=\s*{_NAME}", re.IGNORECASE)
_SETTER_KEYWORD_RE = re.compile(
    r"\bexport\b|\bdeclare\b|\btypeset\b|\benv\s|\bsetx\b|\$env:|env:\$|"
    r"Set-Item|New-Item|Set-Variable|SetEnvironmentVariable|os\.environ|os\.putenv|"
    r"process\.env|\beval\b",
    re.IGNORECASE,
)


def _normalize(cmd: str) -> str:
    """Retire les quotes, backticks d'échappement PowerShell et backslashes
    pour défaire le quoting partiel (`SDD_ALLOW_X"Y"` → `SDD_ALLOW_XY`,
    `SDD\\_ALLOW_X` → `SDD_ALLOW_X`, ``$env:SDD_`ALLOW_X`` → ...)."""
    return re.sub(r"[\"'`\\]", "", cmd)


def _matches_bypass(cmd: str) -> str | None:
    """Return the matching excerpt (for logging) or None if clean.

    Scan sur la commande brute ET sur sa forme normalisée. Les corps de
    heredoc ne sont plus retirés (audit 2026-11 — bash les exécute).
    """
    if not cmd:
        return None
    for text in (cmd, _normalize(cmd)):
        for rx in _BYPASS_REGEXES:
            m = rx.search(text)
            if m:
                return m.group(0)[:120]
        if _INLINE_INTERP_RE.search(text):
            m = _DICT_KEY_RE.search(text)
            if m:
                return m.group(0).strip()[:120]
        m = _VALUE_IS_NAME_RE.search(text)
        if m and _SETTER_KEYWORD_RE.search(text):
            return m.group(0)[:120]
    return None


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read() or "{}"
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _extract_command(payload: dict) -> str:
    # Bash and PowerShell tool payloads: {"tool_input": {"command": "..."}, ...}
    tool_input = payload.get("tool_input") or {}
    cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
    return cmd if isinstance(cmd, str) else ""


def main() -> int:
    payload = _read_payload()
    cmd = _extract_command(payload)
    match = _matches_bypass(cmd)
    if match is None:
        return HOOK_ALLOW

    # Même avec SDD_ALLOW_ENV_BYPASS hérité du process parent, une commande
    # ne peut pas positionner un nom protégé — defense-in-depth.
    bypass_set = os.environ.get("SDD_ALLOW_ENV_BYPASS", "").lower() in ("1", "true", "yes")
    if bypass_set:
        sys.stderr.write(
            "[block-env-bypass] WARN: SDD_ALLOW_ENV_BYPASS=1 inherited, but still "
            "blocking attempt to set protected envvar mid-session.\n"
            f"matched: {match}\n"
        )

    _audit_log(match, cmd, bypass_set)

    sys.stderr.write(
        "ERROR: shell command attempts to set/unset a protected SDD_* / CI envvar.\n"
        f"CAUSE: [ENV_BYPASS_BLOCKED] matched pattern: {match}\n"
        "FIX: protected envvars (SDD_ALLOW_*, SDD_DISABLE_*, SDD_*_MODE, SDD_BYPASS_*,\n"
        "     SDD_PROTECT_*, SDD_TDD_*, SDD_BUDGET_*, SDD_AUDIT_*, CI, ...) must be set in\n"
        "     the environment of the Claude Code process (parent shell or settings `env`),\n"
        "     never inline in a command. A commit message documenting one of them:\n"
        "     use `git commit -F <file>` instead of a heredoc.\n"
        "AUDIT: persisted to workspace/.sys/.audit/env-bypass.jsonl\n"
    )
    return HOOK_DENY


if __name__ == "__main__":
    sys.exit(main())
