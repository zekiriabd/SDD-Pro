"""dialects/sqlserver.py — SQL Server (T-SQL) dialect for proc-reverse (MVP).

READ-ONLY catalog access only. The body of a routine is read losslessly from
`sys.sql_modules.definition` (nvarchar(max)) — NOT `sp_helptext`, which chunks
at 4000 chars and mangles indentation. Encrypted routines (`WITH ENCRYPTION`)
expose a NULL definition → flagged `is_encrypted`, never guessed.

Covered object types (all module-bodied via sys.sql_modules): P (procedure),
FN (scalar function), IF (inline TVF), TF (multi-statement TVF),
V (view — projection/reporting business logic), TR (trigger — integrity /
cascade / audit business rules). Views & triggers were added by the P0.1
extension (audit reverse-db 2026-07-24): a complex view or a trigger carries
business logic just like a procedure and rides the SAME escalier (1 SQL object
= 1 US). All of them expose their body in `sys.sql_modules.definition`; a NULL
definition means `WITH ENCRYPTION` → flagged, never guessed.
"""

from __future__ import annotations

from sdd_reverse.dialects.base import Dialect

# Object types whose body lives in sys.sql_modules and carries business logic.
_OBJ_TYPES = "('P','FN','IF','TF','V','TR')"

# All SELECT, no DDL/DML. Validated by Dialect.__post_init__ + reverse_smoke.
# is_encrypted = any module with a NULL definition (WITH ENCRYPTION), for every
# covered type — build_introspection also treats definition IS NULL as encrypted.
_LIST_SQL = (
    "SELECT s.name AS schema_name, "
    "o.name AS routine_name, "
    "o.type_desc AS routine_type, "
    "m.definition AS routine_definition, "
    "o.modify_date AS modified, "
    "CASE WHEN m.definition IS NULL THEN 1 ELSE 0 END AS is_encrypted "
    "FROM sys.objects o "
    "JOIN sys.schemas s ON s.schema_id = o.schema_id "
    "LEFT JOIN sys.sql_modules m ON m.object_id = o.object_id "
    f"WHERE o.type IN {_OBJ_TYPES} AND o.is_ms_shipped = 0 "
    "ORDER BY s.name, o.name"
)

_SINGLE_SQL = (
    "SELECT s.name AS schema_name, "
    "o.name AS routine_name, "
    "o.type_desc AS routine_type, "
    "m.definition AS routine_definition, "
    "o.modify_date AS modified, "
    "CASE WHEN m.definition IS NULL THEN 1 ELSE 0 END AS is_encrypted "
    "FROM sys.objects o "
    "JOIN sys.schemas s ON s.schema_id = o.schema_id "
    "LEFT JOIN sys.sql_modules m ON m.object_id = o.object_id "
    f"WHERE o.type IN {_OBJ_TYPES} AND o.is_ms_shipped = 0 "
    "AND o.name = ? AND (s.name = ? OR ? = '')"
)

# Authoritative object→object dependencies (P0.2 catalog augmentation) — exact
# name resolution the regex body scan cannot match (synonyms, cross-schema…).
# Static deps only; dynamic SQL is invisible to this catalog too (documented).
_DEPS_SQL = (
    "SELECT OBJECT_SCHEMA_NAME(d.referencing_id) AS from_schema, "
    "OBJECT_NAME(d.referencing_id) AS from_name, "
    "COALESCE(d.referenced_schema_name, 'dbo') AS to_schema, "
    "d.referenced_entity_name AS to_name, "
    "d.referenced_class_desc AS dep_type "
    "FROM sys.sql_expression_dependencies d "
    "WHERE d.referencing_id IS NOT NULL AND d.referenced_entity_name IS NOT NULL"
)

DIALECT = Dialect(
    id="sqlserver",
    label="SQL Server (T-SQL)",
    language_id="tsql",
    default_port=1433,
    driver_hint="pyodbc + ODBC Driver 18 for SQL Server (extra: reverse-db)",
    list_routines_sql=_LIST_SQL,
    single_routine_sql=_SINGLE_SQL,
    dependency_query=_DEPS_SQL,
)
