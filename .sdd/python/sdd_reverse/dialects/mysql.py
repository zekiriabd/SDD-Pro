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

# Authoritative object→object dependencies (audit 2026-08-25). MySQL has no
# dependency catalog as such; VIEW_TABLE_USAGE (MySQL 8.0.13+) is the closest
# native source. Absent on MariaDB and older MySQL → the query simply fails and
# the graph stays body-derived, which is the documented degradation.
_DEPS_SQL = (
    "SELECT v.VIEW_SCHEMA AS from_schema, v.VIEW_NAME AS from_name, "
    "v.TABLE_SCHEMA AS to_schema, v.TABLE_NAME AS to_name, "
    "'OBJECT_OR_COLUMN' AS dep_type "
    "FROM information_schema.VIEW_TABLE_USAGE v "
    f"WHERE v.VIEW_SCHEMA NOT IN {_SKIP_SCHEMAS}"
)

# --------------------------------------------------------------------------- #
# Live relational structure (C1, audit 2026-08-25)
# --------------------------------------------------------------------------- #
# COLUMN_TYPE (`varchar(50)`, `decimal(12,2) unsigned`) is preferred over
# DATA_TYPE: it is the type as declared, which is what a faithful reverse must
# report. `EXTRA` carries auto_increment and the generated-column kind.
_COLUMNS_SQL = (
    "SELECT c.TABLE_SCHEMA AS schema_name, c.TABLE_NAME AS table_name, "
    "c.COLUMN_NAME AS column_name, c.ORDINAL_POSITION AS ordinal, "
    "c.COLUMN_TYPE AS data_type, c.CHARACTER_MAXIMUM_LENGTH AS max_length, "
    "c.NUMERIC_PRECISION AS precision, c.NUMERIC_SCALE AS scale, "
    "CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END AS is_nullable, "
    "c.COLUMN_DEFAULT AS column_default, "
    "CASE WHEN c.EXTRA LIKE '%auto_increment%' THEN 1 ELSE 0 END AS is_identity, "
    "CASE WHEN c.EXTRA LIKE '%GENERATED%' THEN 1 ELSE 0 END AS is_computed, "
    "c.GENERATION_EXPRESSION AS computed_definition "
    "FROM information_schema.COLUMNS c "
    "JOIN information_schema.TABLES t ON t.TABLE_SCHEMA = c.TABLE_SCHEMA "
    "AND t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_TYPE = 'BASE TABLE' "
    f"WHERE c.TABLE_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION"
)

_PK_SQL = (
    "SELECT k.TABLE_SCHEMA AS schema_name, k.TABLE_NAME AS table_name, "
    "k.CONSTRAINT_NAME AS constraint_name, k.COLUMN_NAME AS column_name, "
    "k.ORDINAL_POSITION AS ordinal "
    "FROM information_schema.KEY_COLUMN_USAGE k "
    f"WHERE k.CONSTRAINT_NAME = 'PRIMARY' AND k.TABLE_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "ORDER BY k.TABLE_SCHEMA, k.TABLE_NAME, k.ORDINAL_POSITION"
)

_FK_SQL = (
    "SELECT k.CONSTRAINT_NAME AS constraint_name, "
    "k.TABLE_SCHEMA AS from_schema, k.TABLE_NAME AS from_table, "
    "k.COLUMN_NAME AS from_column, "
    "k.REFERENCED_TABLE_SCHEMA AS to_schema, "
    "k.REFERENCED_TABLE_NAME AS to_table, "
    "k.REFERENCED_COLUMN_NAME AS to_column "
    "FROM information_schema.KEY_COLUMN_USAGE k "
    "WHERE k.REFERENCED_TABLE_NAME IS NOT NULL "
    f"AND k.TABLE_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "ORDER BY k.CONSTRAINT_NAME, k.ORDINAL_POSITION"
)

_INDEX_SQL = (
    "SELECT s.TABLE_SCHEMA AS schema_name, s.TABLE_NAME AS table_name, "
    "s.INDEX_NAME AS index_name, s.COLUMN_NAME AS column_name, "
    "CASE WHEN s.NON_UNIQUE = 0 THEN 1 ELSE 0 END AS is_unique, "
    "CASE WHEN s.INDEX_NAME = 'PRIMARY' THEN 1 ELSE 0 END AS is_primary, "
    "s.SEQ_IN_INDEX AS ordinal "
    "FROM information_schema.STATISTICS s "
    f"WHERE s.TABLE_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "ORDER BY s.TABLE_SCHEMA, s.TABLE_NAME, s.INDEX_NAME, s.SEQ_IN_INDEX"
)

# CHECK_CONSTRAINTS exists on MySQL 8.0.16+ and MariaDB 10.2+ only.
_CHECK_SQL = (
    "SELECT tc.TABLE_SCHEMA AS schema_name, tc.TABLE_NAME AS table_name, "
    "cc.CONSTRAINT_NAME AS constraint_name, cc.CHECK_CLAUSE AS definition "
    "FROM information_schema.CHECK_CONSTRAINTS cc "
    "JOIN information_schema.TABLE_CONSTRAINTS tc "
    "ON tc.CONSTRAINT_SCHEMA = cc.CONSTRAINT_SCHEMA "
    "AND tc.CONSTRAINT_NAME = cc.CONSTRAINT_NAME "
    f"WHERE tc.TABLE_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "ORDER BY tc.TABLE_SCHEMA, tc.TABLE_NAME, cc.CONSTRAINT_NAME"
)

# --------------------------------------------------------------------------- #
# Body-less catalog objects (P2.1)
# --------------------------------------------------------------------------- #
# The MySQL event scheduler IS the job layer — `EVENT_DEFINITION` holds the SQL
# run on schedule, so a nightly purge or aggregation is finally visible.
_EVENTS_SQL = (
    "SELECT 'job' AS kind, e.EVENT_SCHEMA AS schema_name, "
    "e.EVENT_NAME AS name, "
    "CONCAT('status=', e.STATUS, ' | type=', e.EVENT_TYPE, "
    "' | interval=', COALESCE(CONCAT(e.INTERVAL_VALUE, ' ', e.INTERVAL_FIELD), 'once'), "
    "' | action=', COALESCE(LEFT(e.EVENT_DEFINITION, 500), '')) AS detail "
    "FROM information_schema.EVENTS e "
    f"WHERE e.EVENT_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "ORDER BY e.EVENT_SCHEMA, e.EVENT_NAME"
)

# MariaDB 10.3+ SEQUENCE objects surface as a TABLE_TYPE in the catalog.
_SEQUENCES_SQL = (
    "SELECT 'sequence' AS kind, t.TABLE_SCHEMA AS schema_name, "
    "t.TABLE_NAME AS name, 'engine=' AS detail "
    "FROM information_schema.TABLES t "
    f"WHERE t.TABLE_TYPE = 'SEQUENCE' AND t.TABLE_SCHEMA NOT IN {_SKIP_SCHEMAS} "
    "ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME"
)

DIALECT = Dialect(
    id="mysql",
    label="MySQL / MariaDB",
    language_id="mysql",
    default_port=3306,
    driver_hint="mysql-connector-python or PyMySQL (extra: reverse-db)",
    list_routines_sql=_LIST_SQL,
    single_routine_sql=_SINGLE_SQL,
    dependency_query=_DEPS_SQL,
    schema_queries=(
        ("columns", _COLUMNS_SQL),
        ("primary_keys", _PK_SQL),
        ("foreign_keys", _FK_SQL),
        ("indexes", _INDEX_SQL),
        ("checks", _CHECK_SQL),
    ),
    catalog_object_queries=(
        ("job", _EVENTS_SQL),
        ("sequence", _SEQUENCES_SQL),
    ),
)
