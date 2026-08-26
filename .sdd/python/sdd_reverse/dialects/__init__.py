"""dialects — DB-engine-specific catalog access for db-reverse.

One generic SQL analyst agent + N small read-only dialects. MVP ships SQL Server;
the seam below is where Postgres / Oracle / MySQL plug in (V2/V3) with no change
to the agent or pipeline.

Public API:
    get_dialect(db_type) -> Dialect
    supported_db_types() -> list[str]
    class UnsupportedDialect(Exception)   # .error_class
"""

from __future__ import annotations

from sdd_reverse.dialects.base import Dialect, ROUTINE_COLUMNS  # re-export
from sdd_reverse.dialects.mysql import DIALECT as _MYSQL
from sdd_reverse.dialects.oracle import DIALECT as _ORACLE
from sdd_reverse.dialects.postgresql import DIALECT as _POSTGRES
from sdd_reverse.dialects.sqlserver import DIALECT as _SQLSERVER

# Normalised DatabaseType (from stack.md ## Active Database) → Dialect.
# Keys are lowercased on lookup, so list every common alias once.
# The 4 principal engines (2026-07-24). SQL Server + PostgreSQL are
# live-validated; Oracle + MySQL/MariaDB are scaffold-validated (read-only
# query shape + offline flow tested, live runtime pending — no driver at bench).
_REGISTRY: dict[str, Dialect] = {
    "sqlserver": _SQLSERVER,
    "mssql": _SQLSERVER,
    "sql-server": _SQLSERVER,
    "sql_server": _SQLSERVER,
    "postgresql": _POSTGRES,
    "postgres": _POSTGRES,
    "pgsql": _POSTGRES,
    "oracle": _ORACLE,
    "plsql": _ORACLE,
    "mysql": _MYSQL,
    "mariadb": _MYSQL,
}

# Engines recognised but not yet implemented — clearer error than "unknown".
_PLANNED = {
    "db2": "db2 (SYSCAT.ROUTINES) — roadmap",
    "sqlite": "sqlite (sqlite_master) — roadmap",
}

ERROR_CLASS = "[REVERSE_DB_CONFIG_MISSING]"


class UnsupportedDialect(Exception):
    """Raised when the stack.md DatabaseType maps to no implemented dialect."""

    error_class = ERROR_CLASS


def supported_db_types() -> list[str]:
    return sorted({d.id for d in _REGISTRY.values()})


def get_dialect(db_type: str | None) -> Dialect:
    key = (db_type or "").strip().lower()
    if key in _REGISTRY:
        return _REGISTRY[key]
    if key in _PLANNED:
        raise UnsupportedDialect(
            f"{ERROR_CLASS} DatabaseType {db_type!r} not yet implemented: "
            f"{_PLANNED[key]}. Supported now: {supported_db_types()}"
        )
    raise UnsupportedDialect(
        f"{ERROR_CLASS} unknown DatabaseType {db_type!r}. "
        f"Supported: {supported_db_types()}"
    )


__all__ = [
    "Dialect", "ROUTINE_COLUMNS", "get_dialect",
    "supported_db_types", "UnsupportedDialect",
]
