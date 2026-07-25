"""stack_db_config.py — Read DB connection params from stack.md (READ-ONLY).

Reuses the EXACT forward convention: `workspace/stack/stack.md`, section
`## Active Database`, keys `DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD`
(+ `DatabaseType`). Same SSoT the arch agent uses (`arch.md` STEP 8). The file is
gitignored and holds secrets in clear — this module reads it, never writes it,
never logs the password, never persists the connection string.

Public API:
    read_db_config(stack_path) -> DbConfig
    class DbConfig                       # .masked() for safe logging
    class StackConfigError(Exception)    # .error_class = "[REVERSE_DB_CONFIG_MISSING]"
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ERROR_CLASS = "[REVERSE_DB_CONFIG_MISSING]"

# ${VAR} or $VAR placeholder in a stack.md value → resolved from a .env file
# (if present) then the real environment. Honors "connection via env-var files".
_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}|\$(\w+)")
# Candidate .env files searched (first hit wins per key; real env overrides).
_DOTENV_CANDIDATES = (
    ".env",
    "workspace/.env",
    "workspace/stack/.env",
)

_REQUIRED = ("DB_HOST", "DB_NAME")
_SECTION_RE = re.compile(r"^##\s+Active\s+Database\b", re.IGNORECASE)
_NEXT_SECTION_RE = re.compile(r"^##\s+")
# Accept "DB_HOST: x", "- DB_HOST: x", "DB_HOST = x", "`DB_HOST`: x"
_KV_RE = re.compile(
    r"^[\s\-*]*`?(?P<k>[A-Za-z_][A-Za-z0-9_]*)`?\s*[:=]\s*`?(?P<v>[^`\n]+?)`?\s*$"
)


class StackConfigError(Exception):
    error_class = ERROR_CLASS


@dataclass
class DbConfig:
    db_type: str = ""
    host: str = ""
    port: str = ""
    name: str = ""
    user: str = ""
    password: str = field(default="", repr=False)
    extra: dict[str, str] = field(default_factory=dict)

    def masked(self) -> str:
        """Safe one-liner for logs — never reveals the password."""
        pwd = "***" if self.password else "(none)"
        return (
            f"DatabaseType={self.db_type or '?'} host={self.host or '?'} "
            f"port={self.port or '?'} db={self.name or '?'} "
            f"user={self.user or '?'} password={pwd}"
        )

    def require_complete(self) -> None:
        missing = [k for k in _REQUIRED
                   if not getattr(self, {"DB_HOST": "host", "DB_NAME": "name"}[k])]
        if not self.db_type:
            missing.append("DatabaseType")
        if missing:
            raise StackConfigError(
                f"{ERROR_CLASS} stack.md '## Active Database' incomplete: "
                f"missing {missing}"
            )


def _load_dotenv(base: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from candidate .env files (zero-dep)."""
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
            env.setdefault(k, v)   # first file wins
    return env


def _resolve(value: str, env: dict[str, str], missing: set[str]) -> str:
    """Expand ${VAR}/$VAR placeholders from env; record unresolved names."""
    def _sub(m: re.Match) -> str:
        var = m.group(1) or m.group(2)
        if var in env:
            return env[var]
        missing.add(var)
        return m.group(0)
    return _PLACEHOLDER_RE.sub(_sub, value)


def _section_lines(content: str) -> list[str]:
    lines = content.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        if _SECTION_RE.match(line):
            in_section = True
            continue
        if in_section and _NEXT_SECTION_RE.match(line):
            break
        if in_section:
            out.append(line)
    return out


def read_db_config(stack_path: str | Path) -> DbConfig:
    """Parse `## Active Database` from stack.md. Raises if the file is absent."""
    p = Path(stack_path)
    try:
        content = p.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise StackConfigError(
            f"{ERROR_CLASS} cannot read stack.md at {p}: {exc}"
        ) from exc

    lines = _section_lines(content)
    if not lines:
        raise StackConfigError(
            f"{ERROR_CLASS} no '## Active Database' section in {p}"
        )

    kv: dict[str, str] = {}
    for line in lines:
        m = _KV_RE.match(line)
        if m:
            kv[m.group("k").strip().upper()] = m.group("v").strip()

    # Resolve ${VAR}/$VAR placeholders from .env (if any) then the real env.
    # .env candidates are relative to the project root = cwd when commands run.
    env_map = {**_load_dotenv(Path.cwd()), **os.environ}
    missing: set[str] = set()
    kv = {k: _resolve(v, env_map, missing) for k, v in kv.items()}
    if missing:
        raise StackConfigError(
            f"{ERROR_CLASS} stack.md '## Active Database' references unset "
            f"environment variable(s): {sorted(missing)}. Set them (shell or .env) "
            f"or put literal values in stack.md."
        )

    cfg = DbConfig(
        db_type=kv.get("DATABASETYPE", kv.get("DB_TYPE", "")),
        host=kv.get("DB_HOST", ""),
        port=kv.get("DB_PORT", ""),
        name=kv.get("DB_NAME", ""),
        user=kv.get("DB_USER", ""),
        password=kv.get("DB_PASSWORD", ""),
        extra={k: v for k, v in kv.items()
               if k not in {"DATABASETYPE", "DB_TYPE", "DB_HOST", "DB_PORT",
                            "DB_NAME", "DB_USER", "DB_PASSWORD"}},
    )
    return cfg
