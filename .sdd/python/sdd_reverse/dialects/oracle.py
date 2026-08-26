"""dialects/oracle.py — Oracle (PL/SQL) dialect for DB reverse.

READ-ONLY catalog access only. Covered objects: PROCEDURE, FUNCTION, PACKAGE +
PACKAGE BODY (the richest business-logic reservoir in Oracle shops), VIEW,
TRIGGER. Bodies are read losslessly via `DBMS_METADATA.GET_DDL(type, name,
owner)` (returns a CLOB per object). System schemas are excluded.

Validation status (2026-07-24): scaffold-validated — the query shape is
read-only (asserted at construction + reverse_smoke) and the offline flow is
tested with synthetic rows. LIVE runtime is pending (no Oracle driver/instance
at the bench). Provision `oracledb` via the `reverse-db` extra to run live.

Encryption: Oracle "wrapped" PL/SQL still returns (obfuscated) text via GET_DDL;
`is_encrypted` stays 0 and the body analyzer degrades confidence on unreadable
content. Placeholders use python-oracledb positional binds `:1 :2 :3`.
"""

from __future__ import annotations

from sdd_reverse.dialects.base import Dialect

# System/maintenance schemas to skip (never business logic).
_SYS_SCHEMAS = (
    "'SYS','SYSTEM','XDB','MDSYS','CTXSYS','OLAPSYS','ORDSYS','WMSYS',"
    "'OUTLN','DBSNMP','APPQOSSYS','GSMADMIN_INTERNAL','ORDDATA','LBACSYS',"
    "'DVSYS','AUDSYS','OJVMSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT'"
)

# object_type must be underscore-formatted for GET_DDL ('PACKAGE BODY' → 'PACKAGE_BODY').
_BASE = (
    "SELECT o.owner AS schema_name, o.object_name AS routine_name, "
    "o.object_type AS routine_type, "
    "DBMS_METADATA.GET_DDL(REPLACE(o.object_type, ' ', '_'), o.object_name, o.owner) AS routine_definition, "
    "TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD\"T\"HH24:MI:SS') AS modified, "
    "0 AS is_encrypted "
    "FROM all_objects o "
    "WHERE o.object_type IN ('PROCEDURE','FUNCTION','PACKAGE','PACKAGE BODY','VIEW','TRIGGER') "
    f"AND o.owner NOT IN ({_SYS_SCHEMAS})"
)

_LIST_SQL = _BASE + " ORDER BY o.owner, o.object_name"

_SINGLE_SQL = (
    _BASE
    + " AND lower(o.object_name) = lower(:1) "
    "AND (lower(o.owner) = lower(:2) OR :3 IS NULL OR :3 = '')"
)

# Authoritative object→object dependencies (P0.2 catalog augmentation).
# all_dependencies is Oracle's native, exhaustive static dependency view.
_DEPS_SQL = (
    "SELECT d.owner AS from_schema, d.name AS from_name, "
    "d.referenced_owner AS to_schema, d.referenced_name AS to_name, "
    "d.referenced_type AS dep_type "
    "FROM all_dependencies d "
    f"WHERE d.owner NOT IN ({_SYS_SCHEMAS}) "
    f"AND d.referenced_owner NOT IN ({_SYS_SCHEMAS})"
)

# --------------------------------------------------------------------------- #
# Live relational structure (C1, audit 2026-08-25)
# --------------------------------------------------------------------------- #
# `all_tab_cols` (not `all_tab_columns`) is used because only it exposes
# `identity_column` and `virtual_column`; hidden columns are filtered out.
# String building uses `||`, not CONCAT — Oracle's CONCAT takes exactly 2 args.
_COLUMNS_SQL = (
    "SELECT c.owner AS schema_name, c.table_name, c.column_name, "
    "c.column_id AS ordinal, c.data_type, c.data_length AS max_length, "
    "c.data_precision AS precision, c.data_scale AS scale, "
    "CASE WHEN c.nullable = 'Y' THEN 1 ELSE 0 END AS is_nullable, "
    "c.data_default AS column_default, "
    "CASE WHEN c.identity_column = 'YES' THEN 1 ELSE 0 END AS is_identity, "
    "CASE WHEN c.virtual_column = 'YES' THEN 1 ELSE 0 END AS is_computed, "
    "CAST(NULL AS VARCHAR2(1)) AS computed_definition "
    "FROM all_tab_cols c "
    "JOIN all_tables t ON t.owner = c.owner AND t.table_name = c.table_name "
    f"WHERE c.owner NOT IN ({_SYS_SCHEMAS}) AND c.hidden_column = 'NO' "
    "ORDER BY c.owner, c.table_name, c.column_id"
)

_PK_SQL = (
    "SELECT con.owner AS schema_name, con.table_name, "
    "con.constraint_name, col.column_name, col.position AS ordinal "
    "FROM all_constraints con "
    "JOIN all_cons_columns col ON col.owner = con.owner "
    "AND col.constraint_name = con.constraint_name "
    f"WHERE con.constraint_type = 'P' AND con.owner NOT IN ({_SYS_SCHEMAS}) "
    "ORDER BY con.owner, con.table_name, col.position"
)

_FK_SQL = (
    "SELECT con.constraint_name, "
    "con.owner AS from_schema, con.table_name AS from_table, "
    "col.column_name AS from_column, "
    "rcon.owner AS to_schema, rcon.table_name AS to_table, "
    "rcol.column_name AS to_column "
    "FROM all_constraints con "
    "JOIN all_cons_columns col ON col.owner = con.owner "
    "AND col.constraint_name = con.constraint_name "
    "JOIN all_constraints rcon ON rcon.owner = con.r_owner "
    "AND rcon.constraint_name = con.r_constraint_name "
    "JOIN all_cons_columns rcol ON rcol.owner = rcon.owner "
    "AND rcol.constraint_name = rcon.constraint_name "
    "AND rcol.position = col.position "
    f"WHERE con.constraint_type = 'R' AND con.owner NOT IN ({_SYS_SCHEMAS}) "
    "ORDER BY con.constraint_name, col.position"
)

_INDEX_SQL = (
    "SELECT ic.table_owner AS schema_name, ic.table_name, ic.index_name, "
    "ic.column_name, "
    "CASE WHEN i.uniqueness = 'UNIQUE' THEN 1 ELSE 0 END AS is_unique, "
    "CASE WHEN con.constraint_type = 'P' THEN 1 ELSE 0 END AS is_primary, "
    "ic.column_position AS ordinal "
    "FROM all_ind_columns ic "
    "JOIN all_indexes i ON i.owner = ic.index_owner AND i.index_name = ic.index_name "
    "LEFT JOIN all_constraints con ON con.owner = i.owner "
    "AND con.index_name = i.index_name AND con.constraint_type = 'P' "
    f"WHERE ic.table_owner NOT IN ({_SYS_SCHEMAS}) "
    "ORDER BY ic.table_owner, ic.table_name, ic.index_name, ic.column_position"
)

# Oracle reports NOT NULL as a check constraint too; those are already carried by
# the column's `is_nullable`, so the SYS_C%-generated ones are filtered out to
# keep only the checks a developer actually wrote.
_CHECK_SQL = (
    "SELECT con.owner AS schema_name, con.table_name, con.constraint_name, "
    "con.search_condition AS definition "
    "FROM all_constraints con "
    f"WHERE con.constraint_type = 'C' AND con.owner NOT IN ({_SYS_SCHEMAS}) "
    "AND con.generated = 'USER NAME' "
    "ORDER BY con.owner, con.table_name, con.constraint_name"
)

# --------------------------------------------------------------------------- #
# Body-less catalog objects (P2.1)
# --------------------------------------------------------------------------- #
_SEQUENCES_SQL = (
    "SELECT 'sequence' AS kind, s.sequence_owner AS schema_name, "
    "s.sequence_name AS name, "
    "'min=' || s.min_value || ' | max=' || s.max_value || "
    "' | increment=' || s.increment_by AS detail "
    "FROM all_sequences s "
    f"WHERE s.sequence_owner NOT IN ({_SYS_SCHEMAS}) "
    "ORDER BY s.sequence_owner, s.sequence_name"
)

_SYNONYMS_SQL = (
    "SELECT 'synonym' AS kind, sy.owner AS schema_name, sy.synonym_name AS name, "
    "'target=' || sy.table_owner || '.' || sy.table_name || "
    "' | link=' || NVL(sy.db_link, '') AS detail "
    "FROM all_synonyms sy "
    f"WHERE sy.owner NOT IN ({_SYS_SCHEMAS}) "
    "ORDER BY sy.owner, sy.synonym_name"
)

_DB_LINKS_SQL = (
    "SELECT 'linked_server' AS kind, l.owner AS schema_name, l.db_link AS name, "
    "'host=' || NVL(l.host, '') || ' | user=' || NVL(l.username, '') AS detail "
    "FROM all_db_links l "
    "ORDER BY l.owner, l.db_link"
)

# DBMS_SCHEDULER jobs — the Oracle equivalent of SQL Agent. `job_action` holds
# the PL/SQL actually run on schedule, which is how a nightly batch is linked to
# a business package.
_JOBS_SQL = (
    "SELECT 'job' AS kind, j.owner AS schema_name, j.job_name AS name, "
    "'enabled=' || j.enabled || ' | state=' || j.state || "
    "' | type=' || NVL(j.job_type, '') || "
    "' | interval=' || NVL(j.repeat_interval, '') || "
    "' | action=' || NVL(SUBSTR(j.job_action, 1, 500), '') AS detail "
    "FROM all_scheduler_jobs j "
    f"WHERE j.owner NOT IN ({_SYS_SCHEMAS}) "
    "ORDER BY j.owner, j.job_name"
)

_USER_TYPES_SQL = (
    "SELECT 'user_type' AS kind, t.owner AS schema_name, t.type_name AS name, "
    "'typecode=' || t.typecode || ' | attributes=' || NVL(t.attributes, 0) AS detail "
    "FROM all_types t "
    f"WHERE t.owner NOT IN ({_SYS_SCHEMAS}) "
    "ORDER BY t.owner, t.type_name"
)

DIALECT = Dialect(
    id="oracle",
    label="Oracle (PL/SQL)",
    language_id="plsql",
    default_port=1521,
    driver_hint="python-oracledb (extra: reverse-db) — thin mode, no Oracle client needed",
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
        ("synonym", _SYNONYMS_SQL),
        ("linked_server", _DB_LINKS_SQL),
        ("job", _JOBS_SQL),
        ("user_type", _USER_TYPES_SQL),
    ),
)
