"""sql_app_correlation.py — correlate DB objects ↔ consuming applications (P0.3).

Audit reverse-db 2026-07-24 (P0.3). A large share of business logic lives in
the database and is consumed by *several* applications. The DB reverse
(`db-introspection.json`) knows the objects; the application reverse
(`data-access.json`, produced by `data_access_extractor`) knows which code
files call which stored procedures and touch which tables. This module JOINS
the two artefacts to answer:

    * which application code consumes a given DB procedure / table?
    * which DB procedures are never called by any scanned app (orphan/dead or
      external-only)?
    * which app proc-calls reference a procedure ABSENT from the DB (drift /
      different database / renamed object)?

Fully deterministic (0 token). Matching is by trailing object name,
case-insensitive (schema-qualification is lenient — legacy code rarely
qualifies consistently).

Public API:
    correlate(introspection, data_access) -> dict
    to_mermaid(correlation, max_edges=120) -> str
"""
from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = 1


def _tail(ident: str) -> str:
    t = (ident or "").strip().strip("[]`\"").strip().lower()
    t = t.rsplit(".", 1)[-1] if "." in t else t
    return t


def _display(ident: str) -> str:
    return (ident or "").strip().strip("[]`\"").strip()


def correlate(introspection: dict[str, Any], data_access: dict[str, Any]) -> dict[str, Any]:
    """Join DB introspection with application data-access into a consumption map."""
    objects = introspection.get("procedures", []) or []
    calls = data_access.get("storedProcedureCalls", []) or []
    queries = data_access.get("queries", []) or []

    # Index DB objects by trailing name → fqName (procedures/functions callable).
    db_by_tail: dict[str, str] = {}
    for o in objects:
        fq = _display(o.get("fqName") or o.get("name", ""))
        db_by_tail[_tail(fq)] = fq

    # --- Object (proc/function) consumers -------------------------------- #
    object_consumers: dict[str, dict[str, Any]] = {}
    missing: dict[str, list[str]] = {}
    for c in calls:
        cname = c.get("name", "")
        cfile = c.get("file", "")
        tail = _tail(cname)
        if tail in db_by_tail:
            fq = db_by_tail[tail]
            entry = object_consumers.setdefault(fq, {"calledByFiles": [], "callCount": 0})
            entry["callCount"] += 1
            if cfile and cfile not in entry["calledByFiles"]:
                entry["calledByFiles"].append(cfile)
        else:
            files = missing.setdefault(_display(cname), [])
            if cfile and cfile not in files:
                files.append(cfile)

    # --- Table consumers (from inline SQL in app code) ------------------- #
    table_consumers: dict[str, dict[str, Any]] = {}
    for q in queries:
        qfile = q.get("file", "")
        for t in q.get("tables", []) or []:
            td = _display(t)
            entry = table_consumers.setdefault(td, {"accessedByFiles": [], "queryCount": 0})
            entry["queryCount"] += 1
            if qfile and qfile not in entry["accessedByFiles"]:
                entry["accessedByFiles"].append(qfile)

    # --- Orphan DB procedures/functions (never called by scanned app) ---- #
    callable_types = ("PROCEDURE", "FUNCTION")
    orphans: list[str] = []
    for o in objects:
        fq = _display(o.get("fqName") or o.get("name", ""))
        rtype = str(o.get("routineType") or "").upper()
        is_callable = any(k in rtype for k in callable_types) or rtype == ""
        if is_callable and fq not in object_consumers:
            orphans.append(fq)

    for e in object_consumers.values():
        e["calledByFiles"].sort()
    for e in table_consumers.values():
        e["accessedByFiles"].sort()

    return {
        "schemaVersion": SCHEMA_VERSION,
        "dbProject": introspection.get("database") or introspection.get("databaseType"),
        "appProject": data_access.get("project"),
        "objectConsumers": dict(sorted(object_consumers.items())),
        "tableConsumers": dict(sorted(table_consumers.items())),
        "orphanDbProcedures": sorted(orphans),
        "missingProcedures": {k: sorted(v) for k, v in sorted(missing.items())},
        "summary": {
            "dbObjects": len(objects),
            "consumedObjects": len(object_consumers),
            "orphanObjects": len(orphans),
            "consumedTables": len(table_consumers),
            "missingProcedures": len(missing),
        },
    }


def to_mermaid(correlation: dict[str, Any], max_edges: int = 120) -> str:
    """Render app-file → DB-object consumption as a bounded Mermaid graph."""
    def sid(nid: str) -> str:
        return "c_" + re.sub(r"[^0-9A-Za-z]+", "_", nid)

    def short(path: str) -> str:
        return path.replace("\\", "/").rsplit("/", 1)[-1] or path

    lines = ["graph LR"]
    edges: list[tuple[str, str, str]] = []
    for fq, e in correlation.get("objectConsumers", {}).items():
        for f in e["calledByFiles"]:
            edges.append((short(f), fq, "calls"))
    for tbl, e in correlation.get("tableConsumers", {}).items():
        for f in e["accessedByFiles"]:
            edges.append((short(f), tbl, "uses"))
    edges = edges[:max_edges]
    seen: set[str] = set()
    for src, dst, _rel in edges:
        for n in (src, dst):
            if n not in seen:
                seen.add(n)
                shape = f'{sid(n)}["{n}"]'
                lines.append(f"    {shape}")
    for src, dst, rel in edges:
        lines.append(f'    {sid(src)} -->|{rel}| {sid(dst)}')
    return "\n".join(lines)
