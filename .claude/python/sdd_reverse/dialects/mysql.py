"""dialects/mysql.py — MySQL / MariaDB dialect for DB reverse.

READ-ONLY catalog access only. Bodies are read via `information_schema`
(pure SELECT — NOT `SHOW CREATE ...`, which is not a SELECT and would be
refused by the read-only guard). Covered objects: PROCEDURE + FUNCTION
(`ROUTINES.ROUTINE_DEFINITION`), VIEW (`VIEWS.VIEW_DEFINITION`), TRIGGER
(`TRIGGERS` — the action statement prefixed with its event so the analyst
sees "AFTER INSERT ON t" context).

Validation status (2026-07-24): scaffold-validated — read-only query shape +
offline flow tested; LIVE runtime pending (no MySQL driver/instance at the
bench). Provision `mysql-connector-python` (or PyMySQL) via `reverse-db`.

NULL ROUTINE_DEFINITION (insufficient privilege) → treated as encrypted by
build_introspection (never guessed). Placeholders use `%s` (connector/PyMySQL).
"""

from __future__ import annotations

from sdd_reverse.dialects.base import Dialect

_SKIP_SCHEMAS = "('mysql','sys','information_schema','performance_schema')"

# Column aliases pinned on the FIRST branch (define the union's column names).
_UNION = (
    "SELECT r.ROUTINE_SCHEMA AS schema_name, r.ROUTINE_NAME AS routine_name, "
    "r.ROUTINE_TYPE AS routine_type, r.ROUTINE_DEFINITION AS routine_definition, "
    "r.LAST_ALTERED AS modified, 0 AS is_encrypted "
    "FROM information_schema.ROUTINES r "
    f"WHERE r.ROUTINE_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "UNION ALL "
    "SELECT v.TABLE_SCHEMA, v.TABLE_NAME, 'VIEW', v.VIEW_DEFINITION, NULL, 0 "
    "FROM information_schema.VIEWS v "
    f"WHERE v.TABLE_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "UNION ALL "
    "SELECT t.TRIGGER_SCHEMA, t.TRIGGER_NAME, 'TRIGGER', "
    "CONCAT(t.ACTION_TIMING, ' ', t.EVENT_MANIPULATION, ' ON ', "
    "t.EVENT_OBJECT_TABLE, ' : ', t.ACTION_STATEMENT), t.CREATED, 0 "
    "FROM information_schema.TRIGGERS t "
    f"WHERE t.TRIGGER_SCHEMA NOT IN {_SKIP_SCHEMAS}"
)

_LIST_SQL = _UNION + " ORDER BY 1, 2"

_SINGLE_SQL = (
    "SELECT o.schema_name, o.routine_name, o.routine_type, "
    "o.routine_definition, o.modified, o.is_encrypted "
    f"FROM ({_UNION}) o "
    "WHERE lower(o.routine_name) = lower(%s) "
    "AND (lower(o.schema_name) = lower(%s) OR %s = '')"
)

DIALECT = Dialect(
    id="mysql",
    label="MySQL / MariaDB",
    language_id="mysql",
    default_port=3306,
    driver_hint="mysql-connector-python or PyMySQL (extra: reverse-db)",
    list_routines_sql=_LIST_SQL,
    single_routine_sql=_SINGLE_SQL,
)
