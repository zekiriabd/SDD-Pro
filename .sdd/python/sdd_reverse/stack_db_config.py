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
# Keys under `## Active Database` that may hold a full connection string (M6).
_CONNSTR_KEYS = ("DB_CONNECTION_STRING", "CONNECTIONSTRING", "CONNECTION_STRING",
                 "DB_CONNSTR", "CONNSTR")
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


def _dotenv_bases(stack_path: Path) -> list[Path]:
    """Directories to search for a `.env`, most specific first.

    Audit 2026-08-25: the search used to be relative to `Path.cwd()` ONLY. Run
    from anywhere but the repo root — a subdirectory, a hook, a CI step with its
    own working directory, or simply `--stack` given as an absolute path — the
    `.env` was silently missed and the run failed with "references unset
    environment variable(s)", which is actively misleading: the variables ARE
    set, in a file the loader never looked at.

    Anchoring on stack.md's own location fixes that, because `workspace/stack/`
    is where the file lives by convention and the repo root is two levels up.
    `Path.cwd()` is kept last for backward compatibility.
    """
    bases: list[Path] = []
    try:
        anchor = stack_path.resolve().parent
    except OSError:                          # pragma: no cover - exotic FS
        anchor = Path.cwd()
    # Walk up from stack.md: workspace/stack → workspace → repo root → above.
    current = anchor
    for _ in range(4):
        bases.append(current)
        if current.parent == current:
            break
        current = current.parent
    bases.append(Path.cwd())
    seen: set[Path] = set()
    unique: list[Path] = []
    for b in bases:
        if b not in seen:
            seen.add(b)
            unique.append(b)
    return unique


def _load_dotenv(bases: Path | list[Path]) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from candidate .env files (zero-dep)."""
    env: dict[str, str] = {}
    base_list = [bases] if isinstance(bases, Path) else list(bases)
    for base in base_list:
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
                env.setdefault(k, v)   # first file wins (most specific base)
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
    # Bases are anchored on stack.md's own location, not the cwd — see
    # `_dotenv_bases`. The real environment always wins over a .env file.
    bases = _dotenv_bases(p)
    env_map = {**_load_dotenv(bases), **os.environ}
    missing: set[str] = set()
    kv = {k: _resolve(v, env_map, missing) for k, v in kv.items()}
    if missing:
        searched = ", ".join(
            str(base / rel) for base in bases[:3] for rel in _DOTENV_CANDIDATES
        )
        raise StackConfigError(
            f"{ERROR_CLASS} stack.md '## Active Database' references unset "
            f"environment variable(s): {sorted(missing)}. Set them (shell or .env) "
            f"or put literal values in stack.md. Searched for .env in: {searched}"
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
                            "DB_NAME", "DB_USER", "DB_PASSWORD",
                            *_CONNSTR_KEYS}},
    )

    # M6 (audit 2026-08-25) — accept a whole connection string, the form the Tech
    # Lead actually holds (appsettings.json, persistence.xml, k8s secret). The
    # decomposed keys stay authoritative where both are present: an explicit
    # DB_HOST is a deliberate override, the connection string only fills gaps.
    raw_cs = next((kv[k] for k in _CONNSTR_KEYS if kv.get(k)), "")
    if raw_cs:
        from sdd_reverse.conn_string import ConnStringError, parse_connection_string
        try:
            parsed = parse_connection_string(raw_cs, db_type_hint=cfg.db_type)
        except ConnStringError as exc:
            raise StackConfigError(str(exc)) from exc
        for attr in ("db_type", "host", "port", "name", "user", "password"):
            if not getattr(cfg, attr):
                setattr(cfg, attr, getattr(parsed, attr))
        cfg.extra.setdefault("_connStringFormat", parsed.fmt)
    return cfg
