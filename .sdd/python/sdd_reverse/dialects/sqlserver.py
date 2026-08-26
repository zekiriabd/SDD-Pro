"""dialects/sqlserver.py — SQL Server (T-SQL) dialect for db-reverse (MVP).

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

# --------------------------------------------------------------------------- #
# Live relational structure (C1, audit 2026-08-25) — all pure SELECT.
# --------------------------------------------------------------------------- #
# Deliberately `sys.*` rather than INFORMATION_SCHEMA: only the native catalog
# exposes IDENTITY, computed columns and filtered/included index metadata, and
# INFORMATION_SCHEMA lies about types on some SQL Server versions.
# NB read-only guard: `delete_referential_action_desc`-style names contain no
# word boundary before `_`, so they never trip the DDL/DML blocklist.

_COLUMNS_SQL = (
    "SELECT s.name AS schema_name, t.name AS table_name, c.name AS column_name, "
    "c.column_id AS ordinal, ty.name AS data_type, c.max_length, c.precision, "
    "c.scale, c.is_nullable, dc.definition AS column_default, c.is_identity, "
    "c.is_computed, cc.definition AS computed_definition "
    "FROM sys.tables t "
    "JOIN sys.schemas s ON s.schema_id = t.schema_id "
    "JOIN sys.columns c ON c.object_id = t.object_id "
    "JOIN sys.types ty ON ty.user_type_id = c.user_type_id "
    "LEFT JOIN sys.default_constraints dc ON dc.parent_object_id = c.object_id "
    "AND dc.parent_column_id = c.column_id "
    "LEFT JOIN sys.computed_columns cc ON cc.object_id = c.object_id "
    "AND cc.column_id = c.column_id "
    "WHERE t.is_ms_shipped = 0 "
    "ORDER BY s.name, t.name, c.column_id"
)

_PK_SQL = (
    "SELECT s.name AS schema_name, t.name AS table_name, kc.name AS constraint_name, "
    "c.name AS column_name, ic.key_ordinal AS ordinal "
    "FROM sys.key_constraints kc "
    "JOIN sys.tables t ON t.object_id = kc.parent_object_id "
    "JOIN sys.schemas s ON s.schema_id = t.schema_id "
    "JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id "
    "AND ic.index_id = kc.unique_index_id "
    "JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
    "WHERE kc.type = 'PK' AND t.is_ms_shipped = 0 "
    "ORDER BY s.name, t.name, ic.key_ordinal"
)

_FK_SQL = (
    "SELECT fk.name AS constraint_name, "
    "ps.name AS from_schema, pt.name AS from_table, pc.name AS from_column, "
    "rs.name AS to_schema, rt.name AS to_table, rc.name AS to_column "
    "FROM sys.foreign_keys fk "
    "JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id "
    "JOIN sys.tables pt ON pt.object_id = fkc.parent_object_id "
    "JOIN sys.schemas ps ON ps.schema_id = pt.schema_id "
    "JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id "
    "AND pc.column_id = fkc.parent_column_id "
    "JOIN sys.tables rt ON rt.object_id = fkc.referenced_object_id "
    "JOIN sys.schemas rs ON rs.schema_id = rt.schema_id "
    "JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id "
    "AND rc.column_id = fkc.referenced_column_id "
    "ORDER BY fk.name, fkc.constraint_column_id"
)

_INDEX_SQL = (
    "SELECT s.name AS schema_name, t.name AS table_name, i.name AS index_name, "
    "c.name AS column_name, i.is_unique, i.is_primary_key, ic.key_ordinal AS ordinal "
    "FROM sys.indexes i "
    "JOIN sys.tables t ON t.object_id = i.object_id "
    "JOIN sys.schemas s ON s.schema_id = t.schema_id "
    "JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
    "JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
    "WHERE i.name IS NOT NULL AND t.is_ms_shipped = 0 AND ic.is_included_column = 0 "
    "ORDER BY s.name, t.name, i.name, ic.key_ordinal"
)

# CHECK constraints are business rules written in SQL — the single richest
# structural source of validation logic, and previously invisible entirely.
_CHECK_SQL = (
    "SELECT s.name AS schema_name, t.name AS table_name, cc.name AS constraint_name, "
    "cc.definition "
    "FROM sys.check_constraints cc "
    "JOIN sys.tables t ON t.object_id = cc.parent_object_id "
    "JOIN sys.schemas s ON s.schema_id = t.schema_id "
    "WHERE t.is_ms_shipped = 0 "
    "ORDER BY s.name, t.name, cc.name"
)

# --------------------------------------------------------------------------- #
# Body-less catalog objects (P2.1) — one query per kind, each best-effort.
# --------------------------------------------------------------------------- #
# SQL Agent jobs live in msdb and are the classic invisible batch layer: nightly
# recalculations, purges, imports. A reverse that ignores them misses scheduled
# business behaviour entirely. Requires read access to msdb (SQLAgentReaderRole);
# a denied grant degrades to a warning.
_JOBS_SQL = (
    "SELECT 'job' AS kind, 'msdb' AS schema_name, j.name, "
    "CONCAT('enabled=', j.enabled, ' | steps=', "
    "(SELECT COUNT(1) FROM msdb.dbo.sysjobsteps st WHERE st.job_id = j.job_id), "
    "' | schedules=', "
    "(SELECT COUNT(1) FROM msdb.dbo.sysjobschedules js WHERE js.job_id = j.job_id), "
    "' | description=', COALESCE(j.description, '')) AS detail "
    "FROM msdb.dbo.sysjobs j "
    "ORDER BY j.name"
)

# Each job STEP carries the actual command (often `EXEC dbo.usp_X`), which is
# what links a schedule to a business procedure.
_JOB_STEPS_SQL = (
    "SELECT 'job_step' AS kind, 'msdb' AS schema_name, "
    "CONCAT(j.name, ' / ', st.step_name) AS name, "
    "CONCAT('subsystem=', st.subsystem, ' | database=', COALESCE(st.database_name, ''), "
    "' | command=', COALESCE(st.command, '')) AS detail "
    "FROM msdb.dbo.sysjobsteps st "
    "JOIN msdb.dbo.sysjobs j ON j.job_id = st.job_id "
    "ORDER BY j.name, st.step_id"
)

_SEQUENCES_SQL = (
    "SELECT 'sequence' AS kind, s.name AS schema_name, sq.name, "
    "CONCAT('type=', ty.name, ' | start=', CAST(sq.start_value AS nvarchar(64)), "
    "' | increment=', CAST(sq.increment AS nvarchar(64))) AS detail "
    "FROM sys.sequences sq "
    "JOIN sys.schemas s ON s.schema_id = sq.schema_id "
    "JOIN sys.types ty ON ty.user_type_id = sq.user_type_id "
    "ORDER BY s.name, sq.name"
)

_SYNONYMS_SQL = (
    "SELECT 'synonym' AS kind, s.name AS schema_name, sy.name, "
    "CONCAT('target=', sy.base_object_name) AS detail "
    "FROM sys.synonyms sy "
    "JOIN sys.schemas s ON s.schema_id = sy.schema_id "
    "ORDER BY s.name, sy.name"
)

_LINKED_SERVERS_SQL = (
    "SELECT 'linked_server' AS kind, '' AS schema_name, sv.name, "
    "CONCAT('product=', COALESCE(sv.product, ''), ' | provider=', "
    "COALESCE(sv.provider, ''), ' | datasource=', COALESCE(sv.data_source, '')) AS detail "
    "FROM sys.servers sv "
    "WHERE sv.is_linked = 1 "
    "ORDER BY sv.name"
)

# User-defined types, including table types used as TVP parameters — without
# them a procedure signature `@rows dbo.OrderList READONLY` is unreadable.
_USER_TYPES_SQL = (
    "SELECT 'user_type' AS kind, s.name AS schema_name, ty.name, "
    "CONCAT('table_type=', ty.is_table_type, ' | base=', "
    "COALESCE(bt.name, ''), ' | max_length=', CAST(ty.max_length AS nvarchar(16))) AS detail "
    "FROM sys.types ty "
    "JOIN sys.schemas s ON s.schema_id = ty.schema_id "
    "LEFT JOIN sys.types bt ON bt.user_type_id = ty.system_type_id "
    "WHERE ty.is_user_defined = 1 "
    "ORDER BY s.name, ty.name"
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
    schema_queries=(
        ("columns", _COLUMNS_SQL),
        ("primary_keys", _PK_SQL),
        ("foreign_keys", _FK_SQL),
        ("indexes", _INDEX_SQL),
        ("checks", _CHECK_SQL),
    ),
    catalog_object_queries=(
        ("job", _JOBS_SQL),
        ("job_step", _JOB_STEPS_SQL),
        ("sequence", _SEQUENCES_SQL),
        ("synonym", _SYNONYMS_SQL),
        ("linked_server", _LINKED_SERVERS_SQL),
        ("user_type", _USER_TYPES_SQL),
    ),
)
