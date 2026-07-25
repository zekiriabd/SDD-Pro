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

DIALECT = Dialect(
    id="oracle",
    label="Oracle (PL/SQL)",
    language_id="plsql",
    default_port=1521,
    driver_hint="python-oracledb (extra: reverse-db) — thin mode, no Oracle client needed",
    list_routines_sql=_LIST_SQL,
    single_routine_sql=_SINGLE_SQL,
    dependency_query=_DEPS_SQL,
)
