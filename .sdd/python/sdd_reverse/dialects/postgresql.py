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

DIALECT = Dialect(
    id="postgresql",
    label="PostgreSQL (PL/pgSQL)",
    language_id="plpgsql",
    default_port=5432,
    driver_hint="psycopg2 / psycopg (extra: reverse-db)",
    list_routines_sql=_LIST_SQL,
    single_routine_sql=_SINGLE_SQL,
)
