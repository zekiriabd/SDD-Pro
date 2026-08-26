"""dialects/postgresql.py — PostgreSQL (PL/pgSQL) dialect for DB reverse.

READ-ONLY catalog access only. Covered objects (P0.1 2026-07-24 — was
functions/procedures only): FUNCTIONs + PROCEDUREs (`pg_get_functiondef`),
VIEWs (`pg_views.definition`), TRIGGERs (`pg_get_triggerdef`). One SELECT-only
UNION per object family; the whole statement passes `readonly_guard.is_readonly`.

PostgreSQL has no `WITH ENCRYPTION` concept → `is_encrypted` is always 0.
Parameter binding uses the libpq `%s` placeholder (psycopg/psycopg2).
"""

from __future__ import annotations

from sdd_reverse.dialects.base import Dialect

# Union of the three object families, returned in ROUTINE_COLUMNS order.
# NB: no forbidden DDL/DML token appears in the QUERY text (only in results,
# which the read-only guard does not inspect).
_UNION = (
    "SELECT n.nspname AS schema_name, p.proname AS routine_name, "
    "CASE p.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END AS routine_type, "
    "pg_get_functiondef(p.oid) AS routine_definition, "
    "NULL AS modified, 0 AS is_encrypted "
    "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
    "AND p.prokind IN ('f', 'p') "
    "UNION ALL "
    "SELECT v.schemaname, v.viewname, 'VIEW', v.definition, NULL, 0 "
    "FROM pg_views v "
    "WHERE v.schemaname NOT IN ('pg_catalog', 'information_schema') "
    "UNION ALL "
    "SELECT n.nspname, t.tgname, 'SQL_TRIGGER', pg_get_triggerdef(t.oid), NULL, 0 "
    "FROM pg_trigger t "
    "JOIN pg_class c ON c.oid = t.tgrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE t.tgisinternal = false "
    "AND n.nspname NOT IN ('pg_catalog', 'information_schema')"
)

_LIST_SQL = _UNION + " ORDER BY 1, 2"

# Derived-table wrapper so a single filtered SELECT works across PG versions.
_SINGLE_SQL = (
    "SELECT o.schema_name, o.routine_name, o.routine_type, "
    "o.routine_definition, o.modified, o.is_encrypted "
    f"FROM ({_UNION}) o "
    "WHERE lower(o.routine_name) = lower(%s) "
    "AND (lower(o.schema_name) = lower(%s) OR %s = '')"
)

# Authoritative object→object dependencies (audit 2026-08-25): PostgreSQL and
# MySQL were the two engines whose dependency graph stayed purely body-derived
# (regex) while SQL Server and Oracle read their catalog. `pg_depend` joined to
# `pg_rewrite` is the native source: it resolves views, functions and triggers to
# the relations they actually touch, including through search_path.
_DEPS_SQL = (
    "SELECT sn.nspname AS from_schema, dependent.relname AS from_name, "
    "tn.nspname AS to_schema, referenced.relname AS to_name, "
    "'OBJECT_OR_COLUMN' AS dep_type "
    "FROM pg_depend d "
    "JOIN pg_rewrite r ON r.oid = d.objid "
    "JOIN pg_class dependent ON dependent.oid = r.ev_class "
    "JOIN pg_namespace sn ON sn.oid = dependent.relnamespace "
    "JOIN pg_class referenced ON referenced.oid = d.refobjid "
    "JOIN pg_namespace tn ON tn.oid = referenced.relnamespace "
    "WHERE d.classid = 'pg_rewrite'::regclass "
    "AND d.refclassid = 'pg_class'::regclass "
    "AND dependent.oid <> referenced.oid "
    "AND sn.nspname NOT IN ('pg_catalog', 'information_schema') "
    "AND tn.nspname NOT IN ('pg_catalog', 'information_schema')"
)

_NOT_SYS = "NOT IN ('pg_catalog', 'information_schema', 'pg_toast')"

# --------------------------------------------------------------------------- #
# Live relational structure (C1, audit 2026-08-25)
# --------------------------------------------------------------------------- #
# `format_type` gives the type as a PostgreSQL user writes it (`numeric(12,2)`,
# `character varying(50)`) rather than a raw OID — the reverse must report the
# legacy type, not a normalisation of it.
_COLUMNS_SQL = (
    "SELECT c.table_schema AS schema_name, c.table_name, c.column_name, "
    "c.ordinal_position AS ordinal, "
    "format_type(a.atttypid, a.atttypmod) AS data_type, "
    "c.character_maximum_length AS max_length, "
    "c.numeric_precision AS precision, c.numeric_scale AS scale, "
    "CASE WHEN c.is_nullable = 'YES' THEN 1 ELSE 0 END AS is_nullable, "
    "c.column_default, "
    "CASE WHEN c.is_identity = 'YES' OR c.column_default LIKE 'nextval(%' "
    "THEN 1 ELSE 0 END AS is_identity, "
    "CASE WHEN c.is_generated = 'ALWAYS' THEN 1 ELSE 0 END AS is_computed, "
    "c.generation_expression AS computed_definition "
    "FROM information_schema.columns c "
    "JOIN information_schema.tables t ON t.table_schema = c.table_schema "
    "AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE' "
    "JOIN pg_namespace n ON n.nspname = c.table_schema "
    "JOIN pg_class cl ON cl.relname = c.table_name AND cl.relnamespace = n.oid "
    "JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attname = c.column_name "
    f"WHERE c.table_schema {_NOT_SYS} "
    "ORDER BY c.table_schema, c.table_name, c.ordinal_position"
)

_PK_SQL = (
    "SELECT n.nspname AS schema_name, cl.relname AS table_name, "
    "con.conname AS constraint_name, a.attname AS column_name, k.ord AS ordinal "
    "FROM pg_constraint con "
    "JOIN pg_class cl ON cl.oid = con.conrelid "
    "JOIN pg_namespace n ON n.oid = cl.relnamespace "
    "JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
    "JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attnum = k.attnum "
    f"WHERE con.contype = 'p' AND n.nspname {_NOT_SYS} "
    "ORDER BY n.nspname, cl.relname, k.ord"
)

_FK_SQL = (
    "SELECT con.conname AS constraint_name, "
    "n.nspname AS from_schema, cl.relname AS from_table, a.attname AS from_column, "
    "fn.nspname AS to_schema, fcl.relname AS to_table, fa.attname AS to_column "
    "FROM pg_constraint con "
    "JOIN pg_class cl ON cl.oid = con.conrelid "
    "JOIN pg_namespace n ON n.oid = cl.relnamespace "
    "JOIN pg_class fcl ON fcl.oid = con.confrelid "
    "JOIN pg_namespace fn ON fn.oid = fcl.relnamespace "
    "JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
    "JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord) "
    "ON fk.ord = k.ord "
    "JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attnum = k.attnum "
    "JOIN pg_attribute fa ON fa.attrelid = fcl.oid AND fa.attnum = fk.attnum "
    f"WHERE con.contype = 'f' AND n.nspname {_NOT_SYS} "
    "ORDER BY con.conname, k.ord"
)

_INDEX_SQL = (
    "SELECT n.nspname AS schema_name, cl.relname AS table_name, "
    "ic.relname AS index_name, a.attname AS column_name, "
    "CASE WHEN i.indisunique THEN 1 ELSE 0 END AS is_unique, "
    "CASE WHEN i.indisprimary THEN 1 ELSE 0 END AS is_primary, "
    "k.ord AS ordinal "
    "FROM pg_index i "
    "JOIN pg_class cl ON cl.oid = i.indrelid "
    "JOIN pg_class ic ON ic.oid = i.indexrelid "
    "JOIN pg_namespace n ON n.oid = cl.relnamespace "
    "JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true "
    "JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attnum = k.attnum "
    f"WHERE n.nspname {_NOT_SYS} "
    "ORDER BY n.nspname, cl.relname, ic.relname, k.ord"
)

_CHECK_SQL = (
    "SELECT n.nspname AS schema_name, cl.relname AS table_name, "
    "con.conname AS constraint_name, pg_get_constraintdef(con.oid) AS definition "
    "FROM pg_constraint con "
    "JOIN pg_class cl ON cl.oid = con.conrelid "
    "JOIN pg_namespace n ON n.oid = cl.relnamespace "
    f"WHERE con.contype = 'c' AND n.nspname {_NOT_SYS} "
    "ORDER BY n.nspname, cl.relname, con.conname"
)

# --------------------------------------------------------------------------- #
# Body-less catalog objects (P2.1) — each best-effort
# --------------------------------------------------------------------------- #
_SEQUENCES_SQL = (
    "SELECT 'sequence' AS kind, s.sequence_schema AS schema_name, "
    "s.sequence_name AS name, "
    "CONCAT('type=', s.data_type, ' | start=', s.start_value, "
    "' | increment=', s.increment) AS detail "
    "FROM information_schema.sequences s "
    f"WHERE s.sequence_schema {_NOT_SYS} "
    "ORDER BY s.sequence_schema, s.sequence_name"
)

# Foreign data wrappers are the PostgreSQL equivalent of a linked server.
_FOREIGN_SERVERS_SQL = (
    "SELECT 'linked_server' AS kind, '' AS schema_name, "
    "fs.foreign_server_name AS name, "
    "CONCAT('wrapper=', fs.foreign_data_wrapper_name, "
    "' | type=', COALESCE(fs.foreign_server_type, '')) AS detail "
    "FROM information_schema.foreign_servers fs "
    "ORDER BY fs.foreign_server_name"
)

# pg_cron is an extension: the table is absent on most instances, so this query
# failing is the NORMAL case and must only produce a warning.
_CRON_JOBS_SQL = (
    "SELECT 'job' AS kind, 'cron' AS schema_name, "
    "COALESCE(j.jobname, CAST(j.jobid AS text)) AS name, "
    "CONCAT('schedule=', j.schedule, ' | database=', j.database, "
    "' | active=', j.active, ' | command=', j.command) AS detail "
    "FROM cron.job j "
    "ORDER BY j.jobid"
)

_USER_TYPES_SQL = (
    "SELECT 'user_type' AS kind, n.nspname AS schema_name, t.typname AS name, "
    "CONCAT('category=', t.typcategory, ' | base=', "
    "COALESCE(format_type(t.typbasetype, t.typtypmod), '')) AS detail "
    "FROM pg_type t "
    "JOIN pg_namespace n ON n.oid = t.typnamespace "
    f"WHERE n.nspname {_NOT_SYS} AND t.typtype IN ('d', 'e', 'c') "
    "AND t.typname NOT LIKE 'pg_%' "
    "ORDER BY n.nspname, t.typname"
)

DIALECT = Dialect(
    id="postgresql",
    label="PostgreSQL (PL/pgSQL)",
    language_id="plpgsql",
    default_port=5432,
    driver_hint="psycopg2 / psycopg (extra: reverse-db)",
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
        ("sequence", _SEQUENCES_SQL),
        ("linked_server", _FOREIGN_SERVERS_SQL),
        ("job", _CRON_JOBS_SQL),
        ("user_type", _USER_TYPES_SQL),
    ),
)
