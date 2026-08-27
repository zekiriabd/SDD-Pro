"""db_context.py — the Database Context / SSoT of the db-reverse pipeline.

Phase 0 of the reworked db-reverse workflow. Answers, once and for the whole
run, the question every downstream agent used to answer alone and badly: *what
is in this database, and how does it hang together?*

Two rungs, and the separation is the point:

    0.A  deterministic extraction (this module)  -> **facts**
    0.B  the Database Architect agent            -> **hypotheses**

A fact is verifiable in a catalog or a body snapshot and carries an evidence
`file:line`. A hypothesis is an interpretation and is stored in a separate
branch of the document, so nothing downstream can mistake one for the other.
An LLM never invents a table, a column, a relation or a CRUD operation here,
because it never produces this half of the document.

Structure only, never business data: the context is derived from
`db-introspection.json` (object bodies + static signals) and `db-schema.json`
(live catalog structure), both already produced under `readonly_guard`. This
module opens no connection and imports no driver.

The document is versioned (`contextVersion`, a hash of the facts) so that a run
whose database has not changed reuses the architect's interpretation instead of
paying for it again, and so that two runs can be **diffed** to show schema drift.

Public API:
    build_facts(introspection, schema)                 -> dict
    context_version(facts)                             -> str
    build_context(introspection, schema, project=...)  -> dict
    diff_contexts(old, new)                            -> dict
    merge_architect_output(context, architect)         -> dict
    record_finding(context, fq, finding)               -> dict
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from sdd_reverse.db_wave_planner import plan_waves

SCHEMA_VERSION = 1

# Write verbs, mapped onto the CRUD letters a functional reader expects.
_WRITE_TO_CRUD = {
    "INSERT": "C",
    "UPDATE": "U",
    "DELETE": "D",
    # MERGE is the one statement that can do all three in a single pass; saying
    # so is more honest than picking the most likely branch.
    "MERGE": "CUD",
}


def _norm(ident: str) -> str:
    if not ident:
        return ""
    return ident.strip().strip("[]`\"").strip().lower()


def _tail(ident: str) -> str:
    n = _norm(ident)
    return n.rsplit(".", 1)[-1] if "." in n else n


# --------------------------------------------------------------------------- #
# Facts
# --------------------------------------------------------------------------- #

def _crud_for(obj: dict[str, Any]) -> dict[str, str]:
    """CRUD letters per table touched by ONE object (SPXray-style fact layer).

    `writeKinds` gives the statement that touched each table, so C/U/D are
    distinguishable. When it is absent (an introspection produced before this
    field was carried), the write degrades to `W` — an explicit "written, verb
    unknown" rather than a guess.
    """
    crud: dict[str, set[str]] = {}
    write_kinds = obj.get("writeKinds") or {}
    covered: set[str] = set()
    for kind, tables in write_kinds.items():
        letters = _WRITE_TO_CRUD.get(str(kind).upper(), "W")
        for t in tables or []:
            crud.setdefault(t, set()).update(letters)
            covered.add(_norm(t))
    for t in obj.get("tablesWritten") or []:
        if _norm(t) not in covered:
            crud.setdefault(t, set()).add("W")
    for t in obj.get("tablesRead") or []:
        crud.setdefault(t, set()).add("R")
    # Stable letter order so the hash — and therefore contextVersion — is stable.
    order = "CRUDW"
    return {t: "".join(sorted(v, key=order.index)) for t, v in sorted(crud.items())}


def _table_facts(schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Tables with their columns, keys, indexes and CHECK constraints.

    CHECK constraints travel with the table on purpose: with triggers, they are
    the business rules least visible to the applications that sit on top.
    """
    schema = schema or {}
    idx_by_table: dict[str, list[dict[str, Any]]] = {}
    for i in schema.get("indexes") or []:
        idx_by_table.setdefault(_norm(str(i.get("table", ""))), []).append({
            "name": i.get("name"),
            "columns": list(i.get("columns") or []),
            "unique": bool(i.get("unique")),
            "primary": bool(i.get("primary")),
        })
    chk_by_table: dict[str, list[dict[str, Any]]] = {}
    for c in schema.get("checks") or []:
        chk_by_table.setdefault(_norm(str(c.get("table", ""))), []).append({
            "name": c.get("name"),
            "definition": c.get("definition"),
        })

    tables: list[dict[str, Any]] = []
    for ent in schema.get("entities") or []:
        qname = str(ent.get("qualifiedName") or ent.get("name") or "")
        key = _norm(qname)
        columns = [{
            "name": f.get("name"),
            "type": f.get("type"),
            "primaryKey": bool(f.get("primaryKey")),
            "nullable": bool(f.get("nullable")),
            "identity": bool(f.get("identity")),
            "computed": bool(f.get("computed")),
            "default": f.get("default"),
        } for f in ent.get("fields") or []]
        tables.append({
            "qualifiedName": qname,
            "schema": ent.get("schema"),
            "name": ent.get("name"),
            "columns": columns,
            "primaryKey": [c["name"] for c in columns if c["primaryKey"]],
            "indexes": idx_by_table.get(key, []),
            "checks": chk_by_table.get(key, []),
            "evidence": ent.get("evidence") or [],
        })
    return sorted(tables, key=lambda t: _norm(t["qualifiedName"]))


def _object_facts(introspection: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in introspection.get("procedures") or []:
        out.append({
            "fqName": p.get("fqName"),
            "schema": p.get("schema"),
            "name": p.get("name"),
            "routineType": p.get("routineType"),
            "encrypted": bool(p.get("encrypted")),
            "lineCount": p.get("lineCount", 0),
            "params": list(p.get("params") or []),
            "tablesRead": list(p.get("tablesRead") or []),
            "tablesWritten": list(p.get("tablesWritten") or []),
            "writeKinds": dict(p.get("writeKinds") or {}),
            "callsProcs": list(p.get("callsProcs") or []),
            "branches": p.get("branches", 0),
            "cursors": p.get("cursors", 0),
            "raises": list(p.get("raises") or []),
            "hasTransaction": bool(p.get("hasTransaction")),
            "hasTryCatch": bool(p.get("hasTryCatch")),
            "dynamicSql": bool(p.get("dynamicSql")),
            "snapshotFile": p.get("snapshotFile"),
            "evidence": p.get("evidence"),
            "confidenceEstimate": p.get("confidenceEstimate", "high"),
        })
    return sorted(out, key=lambda o: _norm(str(o["fqName"])))


def build_facts(
    introspection: dict[str, Any], schema: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Everything the pipeline knows for certain, before any interpretation."""
    objects = _object_facts(introspection)
    tables = _table_facts(schema)

    crud = {str(o["fqName"]): _crud_for(o) for o in objects}
    crud = {k: v for k, v in crud.items() if v}

    # Which objects touch each table, and how. This is what makes a table
    # "pivot": not its column count, but how much behaviour depends on it.
    touched: dict[str, dict[str, str]] = {}
    known_tables = {_norm(t["qualifiedName"]): t["qualifiedName"] for t in tables}
    known_tails: dict[str, list[str]] = {}
    for k, v in known_tables.items():
        known_tails.setdefault(_tail(k), []).append(v)

    for fq, per_table in crud.items():
        for raw, letters in per_table.items():
            canon = known_tables.get(_norm(raw))
            if canon is None:
                cands = known_tails.get(_tail(raw), [])
                canon = cands[0] if len(cands) == 1 else raw
            touched.setdefault(canon, {})[fq] = letters

    table_metrics = {
        name: {
            "readers": sum(1 for l in users.values() if "R" in l),
            "writers": sum(1 for l in users.values() if set(l) & set("CUDW")),
            "objects": len(users),
        }
        for name, users in touched.items()
    }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "database": {
            # Structure only. The host lives in db-introspection.json and the
            # password never leaves RAM; neither belongs in a shared context.
            "type": introspection.get("databaseType"),
            "name": introspection.get("database"),
            "language": introspection.get("languageId"),
        },
        "tables": tables,
        "relations": list((schema or {}).get("relations") or []),
        "catalogObjects": list((schema or {}).get("catalogObjects") or []),
        "objects": objects,
        "crud": crud,
        "tableUsage": {k: dict(sorted(v.items())) for k, v in sorted(touched.items())},
        "tableMetrics": dict(sorted(table_metrics.items())),
        "summary": {
            "tables": len(tables),
            "columns": sum(len(t["columns"]) for t in tables),
            "relations": len((schema or {}).get("relations") or []),
            "objects": len(objects),
            "encrypted": sum(1 for o in objects if o["encrypted"]),
            "dynamicSql": sum(1 for o in objects if o["dynamicSql"]),
            "schemaCompleteness": (schema or {}).get("completeness", "absent"),
        },
    }


def context_version(facts: dict[str, Any]) -> str:
    """sha256 over the canonical facts — the cache and drift key.

    Stable across runs and platforms: sorted keys, no whitespace, no timestamp.
    Any structural change to the database (a column, a body, a call) changes it;
    re-running an unchanged database does not.
    """
    payload = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Document assembly
# --------------------------------------------------------------------------- #

def build_context(
    introspection: dict[str, Any],
    schema: dict[str, Any] | None = None,
    *,
    project: str = "",
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble `db-context.json`.

    `prior` carries the previous document: when the facts hash is unchanged, the
    architect's hypotheses and the accumulated findings are carried over, which
    is what makes the context reusable instead of rebuilt. When it changed, the
    hypotheses are dropped — a stale interpretation of a changed database is
    worse than none — and `staleHypotheses` records what was discarded.
    """
    facts = build_facts(introspection, schema)
    version = context_version(facts)
    plan = plan_waves(facts["objects"])

    prior_version = (prior or {}).get("contextVersion")
    reusable = bool(prior) and prior_version == version

    hypotheses = (prior or {}).get("hypotheses") if reusable else None
    findings = (prior or {}).get("findings") if reusable else None

    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": project or (prior or {}).get("project", ""),
        "contextVersion": version,
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "facts": facts,
        "executionPlan": plan,
        # Written by the Database Architect agent (0.B). Empty until it runs —
        # and an empty block is a legitimate state, not a failure.
        "hypotheses": hypotheses or {
            "glossary": [],
            "subdomains": [],
            "objectRoles": [],
            "risks": [],
            "openQuestions": [],
        },
        # Written back by the orchestrator at each wave barrier.
        "findings": findings or {},
        "reuse": {
            "priorVersion": prior_version,
            "reused": reusable,
            "staleHypotheses": (
                bool((prior or {}).get("hypotheses", {}).get("glossary"))
                and not reusable
            ),
        },
    }


def merge_architect_output(
    context: dict[str, Any], architect: dict[str, Any]
) -> dict[str, Any]:
    """Fold the architect agent's interpretation into the context.

    Only the `hypotheses` branch is writable by the agent. Any attempt to write
    facts is dropped silently here and loudly by the validator: the deterministic
    layer is the only source of facts, by construction.
    """
    allowed = ("glossary", "subdomains", "objectRoles", "risks", "openQuestions")
    merged = dict(context)
    hyp = dict(context.get("hypotheses") or {})
    for key in allowed:
        if key in architect:
            hyp[key] = architect[key]
    hyp["contextVersion"] = context.get("contextVersion")
    merged["hypotheses"] = hyp
    return merged


def record_finding(
    context: dict[str, Any], fq: str, finding: dict[str, Any]
) -> dict[str, Any]:
    """Write one analysed object's summary back into the shared context.

    Called by the orchestrator at a wave barrier, never by an agent: agents
    write only their own User Story, so their writes stay disjoint and the
    intra-wave parallelism needs no new lock.
    """
    merged = dict(context)
    findings = dict(context.get("findings") or {})
    findings[fq] = {
        "summary": finding.get("summary", ""),
        "contract": finding.get("contract", ""),
        "businessRules": list(finding.get("businessRules") or []),
        "callees": list(finding.get("callees") or []),
        "usPath": finding.get("usPath"),
        "confidence": finding.get("confidence", "medium"),
        "wave": context.get("executionPlan", {}).get("metrics", {}).get(fq, {}).get("wave"),
    }
    merged["findings"] = findings
    return merged


# --------------------------------------------------------------------------- #
# Diff — schema drift between two reverse runs
# --------------------------------------------------------------------------- #

def _index_tables(facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_norm(str(t["qualifiedName"])): t for t in facts.get("tables") or []}


def _index_objects(facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_norm(str(o["fqName"])): o for o in facts.get("objects") or []}


def diff_contexts(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Structural diff between two context documents.

    Answers "what moved in the database since the last reverse?" — the question
    that decides whether a FEAT written three months ago still describes reality.
    """
    of, nf = old.get("facts", {}), new.get("facts", {})
    ot, nt = _index_tables(of), _index_tables(nf)
    oo, no = _index_objects(of), _index_objects(nf)

    tables_added = sorted(nt[k]["qualifiedName"] for k in nt.keys() - ot.keys())
    tables_removed = sorted(ot[k]["qualifiedName"] for k in ot.keys() - nt.keys())

    tables_changed = []
    for k in sorted(nt.keys() & ot.keys()):
        ocols = {c["name"]: c for c in ot[k]["columns"]}
        ncols = {c["name"]: c for c in nt[k]["columns"]}
        added = sorted(ncols.keys() - ocols.keys())
        removed = sorted(ocols.keys() - ncols.keys())
        retyped = sorted(
            c for c in ncols.keys() & ocols.keys()
            if ncols[c]["type"] != ocols[c]["type"]
            or ncols[c]["nullable"] != ocols[c]["nullable"]
        )
        ochk = {c["name"]: c["definition"] for c in ot[k]["checks"]}
        nchk = {c["name"]: c["definition"] for c in nt[k]["checks"]}
        checks_changed = sorted(
            set(nchk.keys()) ^ set(ochk.keys())
            | {c for c in nchk.keys() & ochk.keys() if nchk[c] != ochk[c]}
        )
        if added or removed or retyped or checks_changed:
            tables_changed.append({
                "table": nt[k]["qualifiedName"],
                "columnsAdded": added,
                "columnsRemoved": removed,
                "columnsRetyped": retyped,
                "checksChanged": checks_changed,
            })

    objects_added = sorted(no[k]["fqName"] for k in no.keys() - oo.keys())
    objects_removed = sorted(oo[k]["fqName"] for k in oo.keys() - no.keys())
    objects_changed = []
    for k in sorted(no.keys() & oo.keys()):
        a, b = oo[k], no[k]
        reasons = []
        if a.get("evidence") != b.get("evidence"):
            reasons.append("body")
        if sorted(a.get("callsProcs") or []) != sorted(b.get("callsProcs") or []):
            reasons.append("calls")
        if sorted(a.get("tablesWritten") or []) != sorted(b.get("tablesWritten") or []):
            reasons.append("writes")
        if sorted(a.get("params") or []) != sorted(b.get("params") or []):
            reasons.append("contract")
        if reasons:
            objects_changed.append({"object": b["fqName"], "changed": reasons})

    impacted = sorted({o["object"] for o in objects_changed} | set(objects_added))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "fromVersion": old.get("contextVersion"),
        "toVersion": new.get("contextVersion"),
        "identical": old.get("contextVersion") == new.get("contextVersion"),
        "tables": {
            "added": tables_added,
            "removed": tables_removed,
            "changed": tables_changed,
        },
        "objects": {
            "added": objects_added,
            "removed": objects_removed,
            "changed": objects_changed,
        },
        # What a Tech Lead actually needs: the User Stories to re-derive.
        "reAnalysisRequired": impacted,
        "stats": {
            "tablesAdded": len(tables_added),
            "tablesRemoved": len(tables_removed),
            "tablesChanged": len(tables_changed),
            "objectsAdded": len(objects_added),
            "objectsRemoved": len(objects_removed),
            "objectsChanged": len(objects_changed),
        },
    }
