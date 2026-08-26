"""conn_string.py — Parse a real-world connection string into DB parameters.

Audit finding M6 (2026-08-25): the DB-reverse advertises "reverse engineering
from a connection string", but the only accepted input was a set of decomposed
keys in `stack.md ## Active Database` (`DatabaseType`, `DB_HOST`, `DB_NAME`,
`DB_USER`, `DB_PASSWORD`). A connection string is the format the Tech Lead
actually HAS — copied from an `appsettings.json`, a `persistence.xml` or a
Kubernetes secret — so it had to be taken apart by hand before anything could
run. That is friction on the very first step of the workflow.

Four families are recognised, which covers what the four supported engines emit:

  ADO.NET / ODBC   Server=host,1433;Database=db;User Id=sa;Password=x;
  JDBC             jdbc:postgresql://host:5432/db?user=u&password=p
                   jdbc:sqlserver://host:1433;databaseName=db;user=u
                   jdbc:oracle:thin:@host:1521/ORCLPDB
  URI              postgresql://user:pass@host:5432/db
  libpq DSN        host=... port=... dbname=... user=... password=...

The engine is inferred from the scheme/driver when it is stated, so
`DatabaseType` becomes optional. Nothing is guessed silently: `parse()` reports
what it recognised, and an unparseable string raises rather than half-filling a
config that would then fail at connect time with a confusing driver error.

SECURITY: the password lives in the returned object and NOWHERE else — no
logging, no persistence. Use `DbConfig.masked()` for any human-facing output.

Public API:
    parse_connection_string(raw) -> ParsedConnString
    class ParsedConnString      # .to_db_config() -> stack_db_config.DbConfig
    class ConnStringError(Exception)   # .error_class
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote, urlsplit

ERROR_CLASS = "[REVERSE_DB_CONFIG_MISSING]"


class ConnStringError(Exception):
    """Raised when a connection string cannot be understood."""

    error_class = ERROR_CLASS


# Scheme / driver token → SDD_Pro DatabaseType (the dialect registry's keys).
_ENGINE_TOKENS = {
    "sqlserver": "sqlserver", "mssql": "sqlserver", "sqlsrv": "sqlserver",
    "odbc driver 18 for sql server": "sqlserver",
    "odbc driver 17 for sql server": "sqlserver",
    "sql server": "sqlserver", "sql server native client 11.0": "sqlserver",
    "postgresql": "postgresql", "postgres": "postgresql", "psql": "postgresql",
    "npgsql": "postgresql",
    "oracle": "oracle", "oracle.manageddataaccess.client": "oracle",
    "mysql": "mysql", "mariadb": "mysql",
}

# ADO.NET/ODBC key aliases → canonical field.
_ADO_KEYS = {
    "server": "host", "data source": "host", "datasource": "host",
    "addr": "host", "address": "host", "network address": "host",
    "host": "host", "hostname": "host",
    "database": "name", "initial catalog": "name", "databasename": "name",
    "dbname": "name", "db": "name", "service name": "name", "serviceid": "name",
    "user id": "user", "userid": "user", "uid": "user", "user": "user",
    "username": "user", "user name": "user",
    "password": "password", "pwd": "password",
    "port": "port",
    "driver": "_driver", "provider": "_driver",
    "trusted_connection": "_trusted", "integrated security": "_trusted",
}

_JDBC_RE = re.compile(r"^jdbc:([a-z0-9]+)(?::[a-z]+)?:", re.IGNORECASE)
_ORACLE_EZ_RE = re.compile(
    r"^(?:(?P<user>[^/\s@]+)(?:/(?P<password>[^@\s]*))?@)?"
    r"(?P<host>[^:/\s]+)(?::(?P<port>\d+))?[/:](?P<name>[\w.$-]+)$"
)


@dataclass
class ParsedConnString:
    db_type: str = ""
    host: str = ""
    port: str = ""
    name: str = ""
    user: str = ""
    password: str = field(default="", repr=False)
    trusted: bool = False
    fmt: str = ""                    # which family matched (diagnostics)
    extra: dict[str, str] = field(default_factory=dict)

    def masked(self) -> str:
        pwd = "***" if self.password else ("(integrated)" if self.trusted else "(none)")
        return (f"format={self.fmt} DatabaseType={self.db_type or '?'} "
                f"host={self.host or '?'} port={self.port or '?'} "
                f"db={self.name or '?'} user={self.user or '?'} password={pwd}")

    def to_db_config(self):  # noqa: ANN201 — stack_db_config.DbConfig
        """Convert to the DbConfig the introspection adapter already consumes."""
        from sdd_reverse.stack_db_config import DbConfig
        return DbConfig(
            db_type=self.db_type, host=self.host, port=self.port,
            name=self.name, user=self.user, password=self.password,
            extra=dict(self.extra),
        )


def _split_host_port(raw: str) -> tuple[str, str]:
    """`host,1433` / `host:5432` / `tcp:host,1433` / bare host."""
    value = (raw or "").strip()
    for prefix in ("tcp:", "np:", "lpc:"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
    # IPv6 in brackets: [::1]:5432
    m = re.match(r"^\[(?P<h>[^\]]+)\](?::(?P<p>\d+))?$", value)
    if m:
        return m.group("h"), (m.group("p") or "")
    for sep in (",", ":"):
        if sep in value:
            host, _, port = value.rpartition(sep)
            if port.isdigit():
                return host.strip(), port
    return value, ""


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("true", "yes", "sspi", "1", "on")


def _engine_from_token(token: str) -> str:
    key = (token or "").strip().strip("{}").lower()
    if key in _ENGINE_TOKENS:
        return _ENGINE_TOKENS[key]
    for name, engine in _ENGINE_TOKENS.items():
        if name in key:
            return engine
    return ""


# Keys that identify the engine on their own, for strings that name no driver.
# `Server=`/`Database=` alone are NOT here: SqlClient and the MySQL connector
# both use them, so guessing from those would be a coin toss. These keys are
# idiomatic to exactly one ecosystem.
_ENGINE_BY_KEY = {
    "initial catalog": "sqlserver",     # ADO.NET SqlClient
    "integrated security": "sqlserver",
    "trusted_connection": "sqlserver",
    "user id": "sqlserver",
    "userid": "sqlserver",
    "data source": "sqlserver",
    "multipleactiveresultsets": "sqlserver",
    "encrypt": "sqlserver",
    "trustservercertificate": "sqlserver",
    "dbname": "postgresql",             # libpq
    "sslmode": "postgresql",
    "service name": "oracle",
    "serviceid": "oracle",
}


def _engine_from_keys(keys: set[str]) -> str:
    for key, engine in _ENGINE_BY_KEY.items():
        if key in keys:
            return engine
    return ""


def _parse_kv(raw: str, *, separator: str) -> ParsedConnString:
    """ADO.NET/ODBC (`;`-separated) and libpq DSN (space-separated) share a shape."""
    out = ParsedConnString(fmt="ado" if separator == ";" else "dsn")
    seen_keys: set[str] = set()
    for chunk in raw.split(separator):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        key = key.strip().lower()
        value = value.strip()
        seen_keys.add(key)
        target = _ADO_KEYS.get(key)
        if target == "host":
            out.host, port = _split_host_port(value)
            out.port = out.port or port
        elif target == "_driver":
            out.db_type = out.db_type or _engine_from_token(value)
        elif target == "_trusted":
            out.trusted = _truthy(value)
        elif target:
            setattr(out, target, value)
        else:
            out.extra[key] = value
    if not out.db_type:
        out.db_type = _engine_from_keys(seen_keys)
    return out


def _parse_uri(raw: str) -> ParsedConnString:
    parts = urlsplit(raw)
    out = ParsedConnString(fmt="uri")
    out.db_type = _engine_from_token(parts.scheme)
    out.host = parts.hostname or ""
    out.port = str(parts.port) if parts.port else ""
    out.user = unquote(parts.username or "")
    out.password = unquote(parts.password or "")
    out.name = (parts.path or "").lstrip("/")
    for key, value in parse_qsl(parts.query):
        target = _ADO_KEYS.get(key.lower())
        if target in ("user", "password", "name", "port"):
            setattr(out, target, value)
        elif target == "_trusted":
            out.trusted = _truthy(value)
        else:
            out.extra[key.lower()] = value
    return out


def _parse_jdbc(raw: str) -> ParsedConnString:
    m = _JDBC_RE.match(raw)
    engine = _engine_from_token(m.group(1)) if m else ""
    body = raw[m.end():] if m else raw

    # Oracle thin: jdbc:oracle:thin:@host:1521/service (or :SID)
    if engine == "oracle":
        out = _parse_oracle_easy_connect(body.lstrip("@"))
        out.db_type = "oracle"
        out.fmt = "jdbc"
        return out

    # SQL Server JDBC uses `;key=value` after the authority, others use `?query`.
    authority, sep, tail = body.lstrip("/").partition(";")
    out = _parse_uri("scheme://" + authority) if "@" in authority or "/" in authority \
        else ParsedConnString()
    if not out.host:
        host_part, _, path = authority.partition("/")
        out.host, out.port = _split_host_port(host_part)
        out.name = path
    if sep:
        kv = _parse_kv(tail, separator=";")
        for attr in ("name", "user", "password", "port"):
            if not getattr(out, attr) and getattr(kv, attr):
                setattr(out, attr, getattr(kv, attr))
        out.trusted = out.trusted or kv.trusted
        out.extra.update(kv.extra)
    out.db_type = engine
    out.fmt = "jdbc"
    return out


def _parse_oracle_easy_connect(raw: str) -> ParsedConnString:
    m = _ORACLE_EZ_RE.match(raw.strip())
    if not m:
        raise ConnStringError(
            f"{ERROR_CLASS} unrecognised Oracle easy-connect string "
            f"(expected [user/password@]host[:port]/service)"
        )
    out = ParsedConnString(fmt="oracle-ez", db_type="oracle")
    out.user = m.group("user") or ""
    out.password = m.group("password") or ""
    out.host = m.group("host") or ""
    out.port = m.group("port") or ""
    out.name = m.group("name") or ""
    return out


def parse_connection_string(raw: str, *, db_type_hint: str = "") -> ParsedConnString:
    """Parse `raw` into connection parameters. Raises `ConnStringError` if opaque.

    `db_type_hint` (e.g. the `DatabaseType` already in stack.md) is used only
    when the string itself does not state its engine — an explicit driver or
    scheme in the string always wins, because it is the more specific evidence.
    """
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        raise ConnStringError(f"{ERROR_CLASS} empty connection string")

    if text.lower().startswith("jdbc:"):
        out = _parse_jdbc(text)
    elif "://" in text:
        out = _parse_uri(text)
    elif "=" in text and ";" in text:
        out = _parse_kv(text, separator=";")
    elif "=" in text and re.search(r"\b(host|dbname|port|user|password)\s*=", text, re.I):
        out = _parse_kv(text, separator=" ")
    elif "=" in text:
        out = _parse_kv(text, separator=";")
    elif "@" in text or "/" in text:
        # Bare Oracle easy-connect is the only engine that ships this shape.
        out = _parse_oracle_easy_connect(text)
    else:
        raise ConnStringError(
            f"{ERROR_CLASS} cannot recognise the connection string format. "
            f"Supported: ADO.NET/ODBC (key=value;…), JDBC (jdbc:…), URI "
            f"(engine://user:pass@host:port/db), libpq DSN (host=… dbname=…), "
            f"Oracle easy-connect (user/pass@host:port/service)"
        )

    if not out.db_type:
        out.db_type = _engine_from_token(db_type_hint) or db_type_hint.strip().lower()

    missing = [k for k, v in (("host", out.host), ("database", out.name)) if not v]
    if missing:
        raise ConnStringError(
            f"{ERROR_CLASS} connection string parsed as {out.fmt!r} but "
            f"{', '.join(missing)} is missing — {out.masked()}"
        )
    if not out.db_type:
        raise ConnStringError(
            f"{ERROR_CLASS} the connection string does not state its engine and "
            f"no DatabaseType was given — add DatabaseType to stack.md "
            f"({out.masked()})"
        )
    return out
