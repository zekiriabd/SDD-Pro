"""env_placeholders.py — Resolve ${VAR}/$VAR placeholders in stack.md values.

Zero-dependency, best-effort placeholder expansion shared by the Project
Config readers (`project_config.read_project_config` and
`layered_config._read_project_section`).

Rationale (2026-07-02) : the `## Active Database` / `## Active Auth` /
`## Active SMTP Server` sections already support `${VAR}` expansion (see
`sdd_reverse/stack_db_config.py`, which RAISES on unresolved vars because a
DB connection needs every field). The `## Project Config` block did NOT —
its parser returned the literal string, so `FrontendLocalPort: ${FrontendLocalPort}`
was read as the 6-char string "${...}", breaking arch STEP 4.5.quart port
propagation and JSON-Schema int validation.

This module fills that gap with **best-effort** semantics that differ from
the DB resolver on purpose :
    - Unresolved placeholders are LEFT AS-IS (literal `${VAR}`), never raise.
      `read_project_config` has ~10 callers on hot paths; a transiently
      unset env var must not blow up the whole pipeline. A stderr WARN is
      emitted instead so the Tech Lead sees the miss.
    - Values without any `$` are returned unchanged (fast no-op) — byte
      identical to pre-2026-07-02 behaviour for every existing literal config.

Resolution order per key : `.env` file (first candidate that defines it)
then the real process environment (which OVERRIDES the .env — shell wins).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# `${VAR}` or bare `$VAR`. Mirrors the convention in stack_db_config.py so
# both resolvers accept the exact same placeholder syntax.
_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}|\$(\w+)")

# .env candidates searched relative to the repo root (first hit wins per key;
# the real environment still overrides). Same list as the DB resolver.
_DOTENV_CANDIDATES: tuple[str, ...] = (
    ".env",
    "workspace/.env",
    "workspace/stack/.env",
)


def load_dotenv(base: Path) -> dict[str, str]:
    """Parse simple `KEY=VALUE` lines from candidate .env files (zero-dep).

    First file that defines a key wins; later candidates do not override.
    Quotes around the value are stripped. Comment lines (`#`) and lines
    without `=` are ignored. Missing/unreadable files are skipped silently.
    """
    env: dict[str, str] = {}
    for rel in _DOTENV_CANDIDATES:
        p = base / rel
        try:
            text = p.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            env.setdefault(k, v)  # first file wins
    return env


def resolve_value(value: str, env: dict[str, str], unresolved: set[str]) -> str:
    """Expand ${VAR}/$VAR in `value` from `env`; record misses in `unresolved`.

    Unresolved placeholders are left literal (returned as `${VAR}`). Non-string
    input is returned unchanged.
    """
    if not isinstance(value, str) or "$" not in value:
        return value

    def _sub(m: re.Match) -> str:
        var = m.group(1) or m.group(2)
        if var in env:
            return env[var]
        unresolved.add(var)
        return m.group(0)

    return _PLACEHOLDER_RE.sub(_sub, value)


#: Signatures de variables non resolues deja signalees dans ce process.
#: Evite N WARN identiques par run (cf. dedupe dans `resolve_config`).
_WARNED_UNRESOLVED: set[tuple[str, ...]] = set()


def reset_env_warn_cache() -> None:
    """Vide le cache de dedupe des WARN (usage : tests unitaires)."""
    _WARNED_UNRESOLVED.clear()


def resolve_config(
    config: dict[str, str],
    root: Path,
    *,
    warn_unresolved: bool = True,
) -> dict[str, str]:
    """Return a copy of `config` with every value's ${VAR}/$VAR expanded.

    `.env` (under `root`) provides defaults; the real process environment
    overrides them. Unresolved placeholders stay literal; when
    `warn_unresolved` is True a single stderr WARN lists the missing vars.
    """
    if not any(isinstance(v, str) and "$" in v for v in config.values()):
        return config  # fast path: nothing to expand

    # `.env` lives at the project root (parent of the workspace). In a split
    # layout the framework's repo root differs from the project root, so anchor
    # the search on the workspace parent (audit 2026-07-06). Nested layout:
    # workspace_root(root).parent == root → identical behaviour.
    from sdd_lib.paths import workspace_root
    env_base = workspace_root(root).parent
    env_map = {**load_dotenv(env_base), **os.environ}
    unresolved: set[str] = set()
    out = {k: resolve_value(v, env_map, unresolved) for k, v in config.items()}

    if warn_unresolved and unresolved:
        # Dedupe par set de variables (audit 2026-08-26). `resolve_config` est
        # appele par CHAQUE `read_project_config` / `read_layered_config`, soit
        # ~20+ fois sur un `/sdd-full` : le meme WARN etait reemis a l'identique
        # a chaque appel, contre `output-protocol.md` §5 ("ne jamais dupliquer la
        # meme ligne"). On ne re-avertit que si l'ensemble des variables
        # manquantes CHANGE (nouvelle info reelle pour le Tech Lead).
        signature = tuple(sorted(unresolved))
        if signature not in _WARNED_UNRESOLVED:
            _WARNED_UNRESOLVED.add(signature)
            sys.stderr.write(
                "WARN [ENV_MISSING] Project Config references unset env var(s): "
                f"{sorted(unresolved)}. Set them in the shell or a .env file at the "
                "repo root (or put literal values in stack.md ## Project Config). "
                "Left as literal placeholders for now.\n"
            )
    return out
