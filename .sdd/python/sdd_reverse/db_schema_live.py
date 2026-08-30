"""db_schema_live.py — LIVE relational schema from a database catalog (C1).

Audit finding C1 (2026-08-25): the DB-reverse flavour read only objects that
carry a BODY (procedures, functions, views, triggers). Tables, columns,
datatypes, keys, indexes and CHECK constraints were never read from the live
catalog — they were either guessed by regex from procedure bodies, or parsed by
`db_schema_extractor` from `.sql` files in a legacy repository. In the scenario
the module exists for — "here is a connection string" — that repository does not
exist, so the structure was simply missing, and with it the ERD, the datatypes
and the relations.

This module closes that gap. It consumes the `schema_queries` /
`catalog_object_queries` declared by each dialect and produces the SAME
`db-schema.json` contract already emitted by `db_schema_extractor`, with
`completeness: "live"` instead of `"basic"`. Every downstream consumer
(`reverse_synth` ERD, `reverse-tech-analyst` entities, the crosscutting DB FEAT)
therefore works unchanged.

Two design decisions worth stating:

1. **Snapshot on disk, so evidence stays `file:line`.** The anti-hallucination
   contract of the whole reverse is that every FEAT/US item points at a file and
   a line. A live catalog has no lines. So the builder writes a readable,
   never-executed `CREATE TABLE` rendering per table under
   `.sys/schema-snapshot/`, and anchors each entity and each column to a real
   line in it — exactly the idiom `proc-snapshot/` already uses for bodies. It
   also gives the Tech Lead something to read, and a diffable artifact for
   schema-drift detection later.

2. **Best-effort per query, never all-or-nothing.** `msdb` (SQL Agent jobs),
   `cron.job` (pg_cron) or `CHECK_CONSTRAINTS` (older MySQL) are routinely
   unreadable or absent. One denied grant must degrade the report with a warning,
   not abort an introspection that otherwise succeeded.

Public API:
    fetch_structure(conn, dialect) -> (rows_by_name, warnings)
    fetch_catalog_objects(conn, dialect) -> (objects, warnings)
    build_live_schema(rows_by_name, objects, *, project, database, db_type,
                      routines=None, warnings=None) -> dict
    write_live_schema(project_root, schema) -> dict     # adds evidence, writes files
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.dialects.base import (
    CATALOG_OBJECT_ROW,
    SCHEMA_QUERY_CONTRACTS,
    Dialect,
)
from sdd_reverse.readonly_guard import assert_readonly

SCHEMA_VERSION = 1
_SNAPSHOT_DIR = "schema-snapshot"
_SCHEMA_NAME = "db-schema.json"


# --------------------------------------------------------------------------- #
# Live fetch (guarded, best-effort per query)
# --------------------------------------------------------------------------- #

def _fetch(conn, sql: str) -> list[tuple]:
    assert_readonly(sql)                 # hard barrier before execution
    cur = conn.cursor()
    try:
        cur.execute(sql)
        return [tuple(r) for r in cur.fetchall()]
    finally:
        try:
            cur.close()
        except Exception:  # pragma: no cover
            pass


def fetch_structure(conn, dialect: Dialect) -> tuple[dict[str, list[tuple]], list[str]]:
    """Run the dialect's structure queries. Returns (rows_by_name, warnings)."""
    rows_by_name: dict[str, list[tuple]] = {}
    warnings: list[str] = []
    for name, sql in dialect.schema_queries:
        try:
            rows_by_name[name] = _fetch(conn, sql)
        except Exception as exc:  # permission, unsupported catalog, engine version
            warnings.append(
                f"[REVERSE_DB_SCHEMA_PARTIAL] structure query {name!r} failed on "
                f"{dialect.id}: {str(exc)[:160]}"
            )
    return rows_by_name, warnings


def fetch_catalog_objects(conn, dialect: Dialect) -> tuple[list[dict[str, Any]], list[str]]:
    """Run the dialect's body-less object queries (jobs, sequences, …)."""
    col = {c: i for i, c in enumerate(CATALOG_OBJECT_ROW)}
    objects: list[dict[str, Any]] = []
    warnings: list[str] = []
    for kind, sql in dialect.catalog_object_queries:
        try:
            for row in _fetch(conn, sql):
                objects.append({
                    "kind": str(row[col["kind"]] or kind),
                    "schema": str(row[col["schema"]] or ""),
                    "name": str(row[col["name"]] or ""),
                    "detail": str(row[col["detail"]] or ""),
                })
        except Exception as exc:
            # Absent on purpose in most installs (pg_cron, MariaDB sequences) or
            # denied to the introspection login (msdb). Never fatal.
            warnings.append(
                f"[REVERSE_DB_OBJECTS_PARTIAL] {kind!r} not readable on "
                f"{dialect.id}: {str(exc)[:160]}"
            )
    return objects, warnings


# --------------------------------------------------------------------------- #
# Pure builder (offline-testable)
# --------------------------------------------------------------------------- #

def _rows_as_dicts(rows: list[tuple], contract: tuple[str, ...]) -> list[dict[str, Any]]:
    return [dict(zip(contract, r)) for r in rows]


def _qual(schema: str, name: str) -> str:
    return f"{schema}.{name}" if schema else str(name)


def _truthy(value: Any) -> bool:
    """Engines return 0/1, '0'/'1', 'YES'/'NO' or bool for the same flag."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in ("1", "true", "yes", "y", "t")


def _render_type(field: dict[str, Any]) -> str:
    """Type as the engine declares it, with length/precision when meaningful.

    PostgreSQL's `format_type` and MySQL's `COLUMN_TYPE` already embed the
    length, so a second `(n)` must not be appended.
    """
    base = str(field.get("data_type") or "").strip()
    if not base or "(" in base:
        return base or "unknown"
    low = base.lower()
    max_len = field.get("max_length")
    precision = field.get("precision")
    scale = field.get("scale")
    if low in ("decimal", "numeric") and precision:
        return f"{base}({precision},{scale or 0})"
    # `-1` is SQL Server's encoding of `(max)` — it must reach the `n < 0` branch
    # below (m1, audit 2026-08-29). Excluding it here meant every `NVARCHAR(MAX)`
    # / `VARBINARY(MAX)` column was reported as the bare type, i.e. as BOUNDED,
    # in the very artefact a Tech Lead reads to size a migration.
    if max_len not in (None, "", 0) and low not in ("int", "bigint", "smallint",
                                                    "tinyint", "bit", "date",
                                                    "datetime", "datetime2",
                                                    "uniqueidentifier", "float",
                                                    "real", "money", "text"):
        try:
            n = int(max_len)
        except (TypeError, ValueError):
            return base
        if n < 0:
            return f"{base}(max)"
        # SQL Server reports max_length in BYTES for the Unicode string types:
        # nvarchar(50) comes back as 100. Only those three types are halved —
        # matching on a bare `n` prefix would also catch `numeric`, whose
        # max_length is a byte width that must NOT be divided.
        if low in ("nchar", "nvarchar", "ntext") and n % 2 == 0:
            n //= 2
        return f"{base}({n})"
    return base


def build_live_schema(
    rows_by_name: dict[str, list[tuple]],
    objects: list[dict[str, Any]] | None = None,
    *,
    project: str,
    database: str,
    db_type: str,
    routines: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Turn catalog rows into the `db-schema.json` contract (`completeness: live`).

    PURE: no connection, no filesystem. `rows_by_name` keys are the
    `SCHEMA_QUERY_CONTRACTS` names; a missing key simply yields an empty section
    plus a warning, so a partially-readable catalog still produces a usable file.
    """
    parse_warnings: list[str] = list(warnings or [])

    cols = _rows_as_dicts(rows_by_name.get("columns", []),
                          SCHEMA_QUERY_CONTRACTS["columns"])
    pks = _rows_as_dicts(rows_by_name.get("primary_keys", []),
                         SCHEMA_QUERY_CONTRACTS["primary_keys"])
    fks = _rows_as_dicts(rows_by_name.get("foreign_keys", []),
                         SCHEMA_QUERY_CONTRACTS["foreign_keys"])
    idxs = _rows_as_dicts(rows_by_name.get("indexes", []),
                          SCHEMA_QUERY_CONTRACTS["indexes"])
    checks = _rows_as_dicts(rows_by_name.get("checks", []),
                            SCHEMA_QUERY_CONTRACTS["checks"])

    # PK membership, keyed on (qualified table, lower column).
    pk_cols: set[tuple[str, str]] = {
        (_qual(str(p["schema"]), str(p["table"])).lower(), str(p["column"]).lower())
        for p in pks
    }

    entities: dict[str, dict[str, Any]] = {}
    for c in cols:
        schema = str(c["schema"] or "")
        table = str(c["table"])
        key = _qual(schema, table).lower()
        ent = entities.setdefault(key, {
            "name": table,                       # bare name: consumer compat
            "table": table,
            "schema": schema,
            "qualifiedName": _qual(schema, table),
            "evidence": [],                      # filled by write_live_schema
            "fields": [],
        })
        col_name = str(c["column"])
        ent["fields"].append({
            "name": col_name,
            "type": _render_type(c),
            "primaryKey": (key, col_name.lower()) in pk_cols,
            "identity": _truthy(c.get("is_identity")),
            "nullable": _truthy(c.get("is_nullable")),
            "default": (str(c["column_default"])
                        if c.get("column_default") not in (None, "") else None),
            # Additive keys — richer than the static extractor ever was.
            "ordinal": c.get("ordinal"),
            "rawType": str(c.get("data_type") or ""),
            "maxLength": c.get("max_length"),
            "precision": c.get("precision"),
            "scale": c.get("scale"),
            "computed": _truthy(c.get("is_computed")),
            "computedDefinition": (str(c["computed_definition"])
                                   if c.get("computed_definition") else None),
        })

    # Homonyms across schemas are legitimate; warn because consumers that key
    # entities by bare `name` (the static extractor's habit) will collapse them.
    by_bare: dict[str, list[str]] = {}
    for ent in entities.values():
        by_bare.setdefault(ent["name"].lower(), []).append(ent["qualifiedName"])
    for bare, quals in sorted(by_bare.items()):
        if len(quals) > 1:
            parse_warnings.append(
                f"[REVERSE_DB_HOMONYM] table name {bare!r} exists in "
                f"{len(quals)} schemas ({', '.join(sorted(quals))}) — use "
                f"qualifiedName to disambiguate"
            )

    relations = [{
        "name": str(f["constraint_name"]),
        "from": {"entity": _qual(str(f["from_schema"] or ""), str(f["from_table"])),
                 "field": str(f["from_column"])},
        "to": {"entity": _qual(str(f["to_schema"] or ""), str(f["to_table"])),
               "field": str(f["to_column"])},
        "type": "many-to-one",
        "evidence": f"catalog:{db_type}/foreign_keys",
    } for f in fks]

    # Collapse index rows (one per column) into one entry per index.
    index_map: dict[str, dict[str, Any]] = {}
    for i in idxs:
        table_q = _qual(str(i["schema"] or ""), str(i["table"]))
        key = f"{table_q}.{i['index_name']}".lower()
        entry = index_map.setdefault(key, {
            "name": str(i["index_name"]),
            "table": table_q,
            "columns": [],
            "unique": _truthy(i.get("is_unique")),
            "primary": _truthy(i.get("is_primary")),
            "evidence": f"catalog:{db_type}/indexes",
        })
        entry["columns"].append(str(i["column"]))

    check_list = [{
        "name": str(k["constraint_name"]),
        "table": _qual(str(k["schema"] or ""), str(k["table"])),
        "definition": str(k["definition"] or ""),
        "evidence": f"catalog:{db_type}/checks",
    } for k in checks]

    # Views and triggers come from the ROUTINE introspection, where their body is
    # already analysed — so db-schema.json stays consistent with the escalier
    # instead of listing names only, as the static extractor had to.
    views, triggers = [], []
    for r in routines or []:
        rtype = str(r.get("routineType") or "").upper()
        item = {"name": r.get("fqName") or r.get("name"),
                "evidence": r.get("evidence") or ""}
        if "VIEW" in rtype:
            views.append(item)
        elif "TRIGGER" in rtype:
            triggers.append(item)

    missing = [name for name in SCHEMA_QUERY_CONTRACTS if name not in rows_by_name]
    for name in missing:
        parse_warnings.append(
            f"[REVERSE_DB_SCHEMA_PARTIAL] no rows for {name!r} — section empty"
        )

    catalog_objects = list(objects or [])
    by_kind: dict[str, int] = {}
    for o in catalog_objects:
        by_kind[o["kind"]] = by_kind.get(o["kind"], 0) + 1

    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": project,
        "extractDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": f"live catalog introspection ({db_type}/{database})",
        # The whole point of C1: downstream can now tell a live read from a
        # best-effort regex parse of whatever .sql files happened to be around.
        "completeness": "live",
        "databaseType": db_type,
        "database": database,
        "entities": sorted(entities.values(), key=lambda e: e["qualifiedName"].lower()),
        "relations": relations,
        "views": views,
        "triggers": triggers,
        "indexes": sorted(index_map.values(), key=lambda i: (i["table"].lower(), i["name"].lower())),
        "checks": check_list,
        "catalogObjects": catalog_objects,
        "summary": {
            "tables": len(entities),
            "columns": len(cols),
            "relations": len(relations),
            "indexes": len(index_map),
            "checks": len(check_list),
            "catalogObjectsByKind": by_kind,
        },
        "parseWarnings": parse_warnings[:80],
        "missingPartsHint": [] if entities else [
            "Live catalog returned no user table. Check the login's rights "
            "(needs VIEW DEFINITION + read on the catalog views) or the "
            "DatabaseType in stack.md."
        ],
    }


# --------------------------------------------------------------------------- #
# Snapshot writer (keeps the file:line evidence contract)
# --------------------------------------------------------------------------- #

def render_table_ddl(entity: dict[str, Any], *,
                     relations: list[dict[str, Any]] | None = None,
                     indexes: list[dict[str, Any]] | None = None,
                     checks: list[dict[str, Any]] | None = None) -> list[str]:
    """Render one table as readable, NEVER-EXECUTED `CREATE TABLE` text.

    This is documentation, not a migration: it exists so every column can carry
    an honest `file:line` evidence pointer, and so a human can read the legacy
    structure without a SQL client. `[DB_STRUCTURE_CHANGE_FORBIDDEN]` is not in
    play — nothing here is ever sent to a server.
    """
    q = entity["qualifiedName"]
    lines = [
        f"-- Reverse-engineered from the live catalog (READ-ONLY). Never executed.",
        f"-- Table {q} — {len(entity['fields'])} column(s).",
        f"CREATE TABLE {q} (",
    ]
    for f in entity["fields"]:
        parts = [f"    {f['name']}", f["type"]]
        if f.get("identity"):
            parts.append("IDENTITY")
        if f.get("computed") and f.get("computedDefinition"):
            parts.append(f"AS ({f['computedDefinition']})")
        parts.append("NULL" if f.get("nullable") else "NOT NULL")
        if f.get("default") is not None:
            parts.append(f"DEFAULT {f['default']}")
        if f.get("primaryKey"):
            parts.append("PRIMARY KEY")
        lines.append(" ".join(parts) + ",")
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append(");")

    rels = [r for r in (relations or []) if r["from"]["entity"].lower() == q.lower()]
    if rels:
        lines.append("")
        lines.append("-- Foreign keys")
        for r in rels:
            lines.append(
                f"--   {r['name']}: {r['from']['field']} -> "
                f"{r['to']['entity']}({r['to']['field']})"
            )
    idx = [i for i in (indexes or []) if i["table"].lower() == q.lower()]
    if idx:
        lines.append("")
        lines.append("-- Indexes")
        for i in idx:
            flag = "UNIQUE " if i["unique"] else ""
            lines.append(f"--   {flag}{i['name']} ({', '.join(i['columns'])})")
    chk = [c for c in (checks or []) if c["table"].lower() == q.lower()]
    if chk:
        lines.append("")
        lines.append("-- CHECK constraints (business rules expressed in SQL)")
        for c in chk:
            lines.append(f"--   {c['name']}: {c['definition']}")
    return lines


def write_live_schema(project_root: str | Path, schema: dict[str, Any]) -> dict[str, Any]:
    """Write the per-table snapshots + `db-schema.json`, filling in evidence.

    Each entity gains `snapshotFile` and `evidence` (`path:1-N`); each field
    gains `evidence` (`path:LINE`) pointing at its own line in the snapshot, so
    a US or a FEAT can cite a single column faithfully.
    """
    root = Path(project_root).resolve()
    snap_dir = root / ".sys" / _SNAPSHOT_DIR

    for ent in schema.get("entities", []):
        fname = f"{ent['qualifiedName']}.sql".replace("/", "_").replace("\\", "_")
        rel = f".sys/{_SNAPSHOT_DIR}/{fname}"
        lines = render_table_ddl(
            ent,
            relations=schema.get("relations"),
            indexes=schema.get("indexes"),
            checks=schema.get("checks"),
        )
        # Column i is rendered at line 4+i (1-based: 3 header lines precede it).
        for i, field in enumerate(ent["fields"]):
            field["evidence"] = f"{rel}:{4 + i}"
        atomic_write_text(snap_dir / fname, "\n".join(lines) + "\n")
        ent["snapshotFile"] = rel
        ent["evidence"] = [f"{rel}:1-{len(lines)}"]

    # Catalog objects (jobs, sequences, synonyms, …) get one shared snapshot:
    # they have no columns, so a file per object would be noise.
    objs = schema.get("catalogObjects") or []
    if objs:
        rel = f".sys/{_SNAPSHOT_DIR}/_catalog-objects.txt"
        out: list[str] = [
            "-- Body-less catalog objects read from the live catalog (READ-ONLY).",
            "-- Jobs/events carry SCHEDULED business behaviour: read them.",
            "",
        ]
        for kind in sorted({o["kind"] for o in objs}):
            out.append(f"== {kind} ==")
            for o in [x for x in objs if x["kind"] == kind]:
                line_no = len(out) + 1
                o["evidence"] = f"{rel}:{line_no}"
                out.append(f"  {_qual(o['schema'], o['name'])} :: {o['detail']}")
            out.append("")
        atomic_write_text(root / ".sys" / _SNAPSHOT_DIR / "_catalog-objects.txt",
                          "\n".join(out) + "\n")

    atomic_write_text(
        root / ".sys" / _SCHEMA_NAME,
        json.dumps(schema, indent=2, ensure_ascii=False, default=str) + "\n",
    )
    return schema
