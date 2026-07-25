r"""config_extractor.py — Extract connection strings + app settings (L1).

Closes the 0%-coverage gap on configuration: before L1, `web.config` /
`app.config` / `appsettings.json` were only counted as manifest files, never
parsed. For a faithful migration the Tech Lead needs to know the DB provider,
server and catalog the legacy targeted, plus the app settings that drive
behaviour — WITHOUT leaking credentials into the FEAT.

Secrets (password/pwd/user id/account key/secret) are masked to `***` in the
stored value; structural fields (Data Source / Server / Initial Catalog /
Database / Provider) are preserved because they are migration-relevant.

Public API:
    extract_config(project_root, scan_result) -> dict        # config.json
    mask_secrets(conn_string) -> str                          # reusable, testable
    parse_dotnet_connection_strings(text, source) -> list[dict]
    parse_appsettings_json(text, source) -> list[dict]
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import normalize_bytes, read_text_normalized as _read_text

CONFIG_SCHEMA_VERSION = 1

_CONFIG_FILENAMES = {"web.config", "app.config"}
_APPSETTINGS_RE = re.compile(r"appsettings.*\.json$", re.IGNORECASE)

# <add name="X" connectionString="..." providerName="..."/>
_CONN_ADD_RE = re.compile(
    r"<add\s+[^>]*?name\s*=\s*\"([^\"]+)\"[^>]*?"
    r"connectionString\s*=\s*\"([^\"]*)\""
    r"(?:[^>]*?providerName\s*=\s*\"([^\"]*)\")?",
    re.IGNORECASE | re.DOTALL,
)
# <add key="K" value="V"/>  (appSettings)
_APPSETTING_ADD_RE = re.compile(
    r"<add\s+[^>]*?key\s*=\s*\"([^\"]+)\"[^>]*?value\s*=\s*\"([^\"]*)\"",
    re.IGNORECASE | re.DOTALL,
)

# Secret-bearing keys inside a connection string.
_SECRET_KV_RE = re.compile(
    r"\b(password|pwd|user\s*id|uid|account\s*key|accountkey|secret|api[_-]?key|token)\s*=\s*[^;\"]*",
    re.IGNORECASE,
)

_SERVER_RE = re.compile(r"\b(?:data\s*source|server|host|addr|address)\s*=\s*([^;\"]+)", re.IGNORECASE)
_DB_RE = re.compile(r"\b(?:initial\s*catalog|database|dbname)\s*=\s*([^;\"]+)", re.IGNORECASE)


def mask_secrets(conn_string: str) -> str:
    """Replace credential values in a connection string with `***`."""
    def _repl(m: re.Match) -> str:
        key = m.group(0).split("=", 1)[0]
        return f"{key}=***"
    return _SECRET_KV_RE.sub(_repl, conn_string)


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _derive_server_db(value: str) -> tuple[str | None, str | None]:
    sm = _SERVER_RE.search(value)
    dm = _DB_RE.search(value)
    return (sm.group(1).strip() if sm else None, dm.group(1).strip() if dm else None)


def parse_dotnet_connection_strings(text: str, source: str) -> list[dict[str, Any]]:
    """Parse <connectionStrings> add entries from web.config / app.config."""
    out: list[dict[str, Any]] = []
    for m in _CONN_ADD_RE.finditer(text):
        name, raw_value, provider = m.group(1), m.group(2), m.group(3)
        server, database = _derive_server_db(raw_value)
        out.append({
            "name": name,
            "value": mask_secrets(raw_value),
            "provider": provider or None,
            "server": server,
            "database": database,
            "file": source,
            "line": _line_at(text, m.start()),
        })
    return out


def parse_app_settings(text: str, source: str) -> list[dict[str, Any]]:
    """Parse <appSettings> add key/value entries from .config files."""
    out: list[dict[str, Any]] = []
    for m in _APPSETTING_ADD_RE.finditer(text):
        key, value = m.group(1), m.group(2)
        # Mask if the key name itself hints at a secret.
        if re.search(r"password|secret|key|token|pwd", key, re.IGNORECASE):
            value = "***"
        out.append({
            "key": key,
            "value": value,
            "file": source,
            "line": _line_at(text, m.start()),
        })
    return out


def parse_appsettings_json(text: str, source: str) -> list[dict[str, Any]]:
    """Parse ConnectionStrings from appsettings*.json (regex, tolerant)."""
    out: list[dict[str, Any]] = []
    block = re.search(r"\"ConnectionStrings\"\s*:\s*\{(.*?)\}", text, re.DOTALL)
    if not block:
        return out
    body = block.group(1)
    base_off = block.start(1)
    for m in re.finditer(r"\"([^\"]+)\"\s*:\s*\"([^\"]*)\"", body):
        name, raw_value = m.group(1), m.group(2)
        server, database = _derive_server_db(raw_value)
        out.append({
            "name": name,
            "value": mask_secrets(raw_value),
            "provider": None,
            "server": server,
            "database": database,
            "file": source,
            "line": _line_at(text, base_off + m.start()),
        })
    return out


# _read_text centralise dans scan_legacy (audit 2026-06-11 B5 — cap 5 Mo).


def extract_config(project_root: str | Path, scan_result: Any) -> dict[str, Any]:
    """Scan config files for connection strings + app settings."""
    root = Path(project_root).resolve()
    conn_strings: list[dict[str, Any]] = []
    app_settings: list[dict[str, Any]] = []

    excl = {".git", "bin", "obj", "packages", "node_modules", "vendor"}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in excl for part in p.relative_to(root).parts):
            continue
        name_low = p.name.lower()
        rel = p.relative_to(root).as_posix()
        if name_low in _CONFIG_FILENAMES:
            text = _read_text(p)
            conn_strings.extend(parse_dotnet_connection_strings(text, rel))
            app_settings.extend(parse_app_settings(text, rel))
        elif _APPSETTINGS_RE.search(name_low):
            text = _read_text(p)
            conn_strings.extend(parse_appsettings_json(text, rel))

    return {
        "schemaVersion": CONFIG_SCHEMA_VERSION,
        "project": root.name,
        "extractDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "connectionStrings": conn_strings,
        "appSettings": app_settings,
        "summary": {
            "connectionStringsCount": len(conn_strings),
            "appSettingsCount": len(app_settings),
        },
    }
