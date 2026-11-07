#!/usr/bin/env python3
"""SDD_Pro PreToolUse.Agent hook — secrets réels dans le contexte d'un sous-agent.

Audit sécurité 2026-11 (refonte ; audit R5 2026-07-26 pour la partie provider).

Avant chaque spawn d'agent (tool `Agent`/`Task`) :

  1. **DENY** (exit 2, `[SECRET_ACCESS_FORBIDDEN]`) — quel que soit le
     provider — si un fichier que l'agent spawné VA LIRE contient une valeur
     réelle (ni vide, ni `${VAR}`) sur une clé Password/Secret/Token/ApiKey/
     ConnectionString :
       * `workspace/stack/stack.md`, si l'agent le liste dans ses `reads:`
         (`loader.yml`) ;
       * un fichier de config généré sous `workspace/src/`
         (`appsettings*.json`, `application*.yml|yaml|properties`,
         `config/default.json`) couvert par un glob `reads:` de l'agent.
     Les agents absents de `loader.yml` (built-ins du harnais, module reverse)
     ne sont pas bloqués ici : leurs lectures directes sont filtrées par
     `block_secret_access`.
  2. **WARN** si `.env` contient des secrets réels (jamais lu par un agent —
     `block_secret_access` — mais signalé).
  3. **WARN** `[SECRET_PROVIDER_LEAK_RISK]` (comportement R5 conservé) si le
     provider actif n'est pas Anthropic et que stack.md contient des secrets.

Correctif : `${DB_PASSWORD}` n'est plus pris pour un secret réel (faux
positif historique — le stack.md committé ne contient que des placeholders).

Bypass : `SDD_ALLOW_SECRET_IN_CONTEXT=1` (DENY → WARN) ;
`SDD_ALLOW_SECRET_TO_PROVIDER=1` (WARN provider muet). Les deux sont
protégés par `block_env_bypass` : uniquement via l'environnement du process
Claude Code.
"""
from __future__ import annotations

import os
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import read_hook_input, get_subagent_type  # noqa: E402
from sdd_lib.run_id import get_or_create_run_id  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_hooks.block_secret_access import (  # noqa: E402
    file_secret_findings,
    generated_config_files,
    is_placeholder,
)


_LEAK_RISK_PROVIDERS: tuple[str, ...] = (
    "openai",       # 30-day retention default; enterprise ZDR opt-in
    "google",       # Gemini API : 55-day retention default on consumer projects
    "moonshot",     # policy undocumented at 2026-07-26 (per moonshot.yaml notes)
)

_SECRET_KEYS: tuple[str, ...] = (
    "DB_PASSWORD",
    "DB_ROOTPASSWORD",
    "AUTH_JWT_SECRET",
    "AUTH_SESSION_SECRET",
    "AZ_CLIENTSECRET",
    "AZ_CLIENTSECRETVALUE",
    "SMTP_PASSWORD",
    "REDIS_PASSWORD",
    "OAUTH_CLIENT_SECRET",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "MOONSHOT_API_KEY",
)

_STACK_REL = "workspace/stack/stack.md"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _read_active_provider(stack_md: Path) -> str | None:
    """Extract the `Provider:` value from `## Active Model Provider` section."""
    try:
        text = stack_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = re.search(
        r"^##\s+Active\s+Model\s+Provider\s*$([\s\S]*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE,
    )
    if not m:
        return None
    p = re.search(r"^\s*Provider\s*:\s*([A-Za-z][A-Za-z0-9_-]*)", m.group(1), re.MULTILINE)
    return p.group(1).strip().lower() if p else None


def _stack_has_secrets(stack_md: Path) -> tuple[str, ...]:
    """Return the canonical secret keys with a REAL value in stack.md.

    Accepte `KEY=val`, `KEY: val` et la forme liste ` - KEY: val` de
    `## Active Database`. Placeholders ignorés (`${VAR}`, TODO, `<...>`).
    """
    try:
        text = stack_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ()
    found: list[str] = []
    for key in _SECRET_KEYS:
        pattern = (
            rf"^[^\S\n]*(?:-[^\S\n]+)?{re.escape(key)}[^\S\n]*[:=][^\S\n]*"
            rf"([^\s].*?)[^\S\n]*$"
        )
        for m in re.finditer(pattern, text, re.MULTILINE):
            val = re.sub(r"\s+#.*$", "", m.group(1)).strip().strip("\"'")
            if val and not is_placeholder(val):
                found.append(key)
                break
    return tuple(sorted(set(found)))


def _marker_path(run_id: str) -> Path | None:
    try:
        from sdd_lib.paths import audit_dir_path, workspace_root, repo_root
        d = audit_dir_path(repo_root())
        d.mkdir(parents=True, exist_ok=True)
        return d / f"secret-scan-warned-{run_id}.marker"
    except Exception:
        return None


def _resolve_stack_md() -> Path | None:
    try:
        from sdd_lib.paths import workspace_root, repo_root
        sp = workspace_root(repo_root()) / "stack" / "stack.md"
        return sp if sp.is_file() else None
    except Exception:
        return None


def _agent_read_globs(agent: str) -> list[str]:
    """`reads:` de l'agent dans loader.yml, placeholders `{X}` → `*`."""
    try:
        from sdd_lib.loader_yml import parse_agent_section
        reads = parse_agent_section(agent, "reads")
    except Exception:
        return []
    out = []
    for r in reads:
        g = re.sub(r"\{[^}]*\}", "*", r.strip().replace("\\", "/"))
        if g:
            out.append(g)
    return out


def _glob_covers(glob: str, rel: str) -> bool:
    if glob.endswith("/"):
        return rel.startswith(glob)
    g = glob.replace("**/*", "*").replace("**", "*")
    return fnmatch(rel, g) or fnmatch(rel, glob)


def _exposures(agent: str, stack_md: Path | None) -> list[str]:
    """Fichiers lus par `agent` qui contiennent un secret réel."""
    globs = _agent_read_globs(agent)
    if not globs:
        return []
    out: list[str] = []
    if stack_md is not None and any(_glob_covers(g, _STACK_REL) for g in globs):
        hits = file_secret_findings(stack_md)
        if hits:
            out.append(f"{_STACK_REL} ({', '.join(sorted({k for k, _, _ in hits}))})")
    try:
        from sdd_lib.paths import workspace_root, repo_root
        root = repo_root()
        ws = workspace_root(root)
        for cfg in generated_config_files(ws):
            try:
                rel = "workspace/" + cfg.resolve().relative_to(ws.resolve()).as_posix()
            except ValueError:
                continue
            if not any(_glob_covers(g, rel) for g in globs):
                continue
            hits = file_secret_findings(cfg)
            if hits:
                lines = ", ".join(f"{k}:L{n}" for k, _, n in hits[:4])
                out.append(f"{rel} ({lines})")
    except Exception:
        pass
    return out


def _dotenv_findings() -> list[str]:
    try:
        from sdd_lib.paths import workspace_root, repo_root
        ws = workspace_root(repo_root())
        cands = [ws.parent / ".env", ws / ".env", ws / "stack" / ".env"]
    except Exception:
        return []
    out = []
    for c in cands:
        hits = file_secret_findings(c)
        if hits:
            out.append(f"{c.name} ({len(hits)} valeur(s))")
    return out


def _provider_warning(stack_md: Path, session_id: str | None = None) -> None:
    """Comportement R5 (WARN, debounce par run_id)."""
    if _truthy("SDD_ALLOW_SECRET_TO_PROVIDER"):
        return
    provider = _read_active_provider(stack_md)
    if provider is None or provider not in _LEAK_RISK_PROVIDERS:
        return
    secrets = _stack_has_secrets(stack_md)
    if not secrets:
        return
    run_id = get_or_create_run_id(session_id=session_id)
    marker = _marker_path(run_id)
    if marker is not None and marker.is_file():
        return
    warn(
        f"WARN preflight-secret-scan : stack.md contains {len(secrets)} secret key(s) "
        f"({', '.join(secrets)}) AND active provider is `{provider}` — a non-Anthropic "
        f"endpoint may retain prompts for 30-55 days by default."
    )
    warn(
        f"CAUSE: [SECRET_PROVIDER_LEAK_RISK] stack.md secrets sent to `{provider}` "
        f"without an explicit no-log / ZDR contract on this project."
    )
    warn(
        "FIX: replace the values by ${VAR} placeholders, or verify the provider's "
        "ZDR / no-log flag, or accept the risk : SDD_ALLOW_SECRET_TO_PROVIDER=1 in the "
        "environment of the Claude Code process (audit-logged)."
    )
    if marker is not None:
        try:
            marker.write_text(f"warned at run_id={run_id}\n", encoding="utf-8")
        except Exception:
            pass


def main() -> int:
    payload = read_hook_input()
    if not payload:
        return HOOK_ALLOW
    agent = get_subagent_type(payload)
    if not agent:
        return HOOK_ALLOW

    stack_md = _resolve_stack_md()
    exposures = _exposures(agent, stack_md)
    dotenv = _dotenv_findings()
    if dotenv:
        warn(f"WARN preflight-secret-scan : .env contient des secrets reels ({'; '.join(dotenv)}) "
             "— jamais lisible par un sous-agent (block_secret_access), a garder hors du depot.")
    if stack_md is not None:
        sid = payload.get("session_id")
        _provider_warning(stack_md, sid if isinstance(sid, str) and sid.strip() else None)

    if not exposures:
        return HOOK_ALLOW
    detail = " ; ".join(exposures[:4])
    if _truthy("SDD_ALLOW_SECRET_IN_CONTEXT"):
        warn(f"WARN [SECRET_ACCESS_FORBIDDEN] bypass SDD_ALLOW_SECRET_IN_CONTEXT=1 — agent "
             f"'{agent}' va lire des secrets reels : {detail}")
        return HOOK_ALLOW
    warn(f"ERROR: preflight-secret-scan — spawn de '{agent}' refuse : secrets reels dans ses lectures")
    warn(f"CAUSE: [SECRET_ACCESS_FORBIDDEN] {detail}")
    warn("FIX: remplacer les valeurs par des placeholders ${VAR} (stack.md, configs generees) et "
         "fournir les valeurs reelles via l'environnement / .env ; bypass Tech Lead : "
         "SDD_ALLOW_SECRET_IN_CONTEXT=1 dans l'environnement du process Claude Code")
    return HOOK_DENY


if __name__ == "__main__":
    sys.exit(main())
