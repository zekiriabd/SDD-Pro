"""sql_dependency_graph.py — object↔object dependency graph for DB reverse (P0.2).

Audit reverse-db 2026-07-24 (P0.2). The db-reverse pipeline already extracts,
per SQL object, the tables it reads/writes and the routines it calls
(`sql_body_analyzer` signals). This module turns that per-object data into a
**global dependency graph** — usable for impact analysis ("what breaks if I
change table X / proc Y?") and for **cohesion-based clustering** (group objects
that truly work together, more robust than naming conventions on un-disciplined
legacy DBs — audit weakness DB4).

Fully deterministic (0 token) and **cross-engine uniform**: it consumes the
already-normalised introspection objects, so SQL Server / PostgreSQL / Oracle /
MySQL all get the same graph without any extra live query (no read-only-guard
surface, offline-testable).

Public API:
    build_dependency_graph(objects) -> {nodes, edges, stats}
    cohesion_modules(objects) -> {objectFq: moduleName}
    impact_of(graph, fq) -> {dependsOn, dependents}
    to_mermaid(graph, max_edges=120) -> str
"""
from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- #
# Normalisation helpers
# --------------------------------------------------------------------------- #

def _norm(ident: str) -> str:
    """Canonical key for matching table/object identifiers across notations."""
    if not ident:
        return ""
    t = ident.strip().strip("[]`\"").strip()
    # keep only the trailing name if schema-qualified, for lenient matching
    return t.lower()


def _tail(ident: str) -> str:
    t = _norm(ident)
    return t.rsplit(".", 1)[-1] if "." in t else t


def _display(ident: str) -> str:
    return ident.strip().strip("[]`\"").strip()


def _resolve_callee(
    callee: str, by_fq: dict[str, str], by_tail: dict[str, list[str]],
) -> str | None:
    """Resolve a callee name to a known object, or None. NEVER guesses.

    Same policy as `db_wave_planner.resolve_calls` (m3, audit 2026-08-29): an
    exact qualified match wins; a bare name resolves only when exactly ONE object
    carries it. Two objects sharing a bare name across schemas (`dbo.usp_Do` and
    `sales.usp_Do`) is an ambiguity, and picking one of them writes a dependency
    that may simply be false into a graph used for impact analysis.
    """
    exact = by_fq.get(_norm(callee))
    if exact is not None:
        return exact
    candidates = by_tail.get(_tail(callee), [])
    return candidates[0] if len(candidates) == 1 else None


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #

def build_dependency_graph(objects: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a directed dependency graph from introspection objects.

    Each object contributes edges:
      * object --reads--> table   (from tablesRead)
      * object --writes--> table  (from tablesWritten)
      * object --calls--> object  (from callsProcs / callsInferred, resolved
        against the known object set — never guessed, see `_resolve_callee`)

    Nodes carry `kind` ('object' with routineType, or 'table', or 'external'
    for an unmatched callee). Stats include per-node in/out degree so callers
    can rank impact.
    """
    # Index objects by canonical fq and by trailing name (for call resolution).
    by_fq: dict[str, str] = {}
    by_tail: dict[str, list[str]] = {}
    for o in objects:
        fq = o.get("fqName") or o.get("name", "")
        by_fq[_norm(fq)] = fq
        by_tail.setdefault(_tail(fq), []).append(fq)

    nodes: dict[str, dict] = {}
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def _node(nid: str, kind: str, ntype: str) -> None:
        if nid not in nodes:
            nodes[nid] = {"id": nid, "kind": kind, "type": ntype,
                          "inDegree": 0, "outDegree": 0}

    def _edge(src: str, dst: str, rel: str, source: str = "body") -> None:
        # The same call can now arrive from two extraction sources (keyword and
        # keyword-less); one dependency must still be one edge.
        key = (_norm(src), _norm(dst), rel)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"from": src, "to": dst, "rel": rel, "source": source})
        nodes[src]["outDegree"] += 1
        nodes[dst]["inDegree"] += 1

    for o in objects:
        fq = _display(o.get("fqName") or o.get("name", ""))
        _node(fq, kind=str(o.get("routineType") or "OBJECT"), ntype="object")

    for o in objects:
        fq = _display(o.get("fqName") or o.get("name", ""))
        for t in o.get("tablesRead", []) or []:
            tid = _display(t)
            _node(tid, kind="TABLE", ntype="table")
            _edge(fq, tid, "reads")
        for t in o.get("tablesWritten", []) or []:
            tid = _display(t)
            _node(tid, kind="TABLE", ntype="table")
            _edge(fq, tid, "writes")
        for callee in o.get("callsProcs", []) or []:
            dst = _resolve_callee(callee, by_fq, by_tail)
            if dst is not None:
                _edge(fq, _display(dst), "calls")
            else:
                # Unresolvable (absent) or AMBIGUOUS (same bare name in two
                # schemas). m3, audit 2026-08-29: this used to take
                # `matches[0]` on ambiguity, silently asserting an edge to one
                # schema's object while `db_wave_planner.resolve_calls` — on
                # the same data — correctly refused to guess. Two components
                # disagreeing about the same graph is worse than either answer.
                # An `external` node says "we could not resolve this", which is
                # exactly what the reader needs to know.
                ext = _display(callee)
                _node(ext, kind="EXTERNAL", ntype="external")
                _edge(fq, ext, "calls")
        # Keyword-less invocations (C1): resolve or drop. Never an external node
        # — the heuristic is not authoritative enough to assert a missing object.
        for callee in o.get("callsInferred", []) or []:
            dst = _resolve_callee(callee, by_fq, by_tail)
            if dst is not None:
                _edge(fq, _display(dst), "calls")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "objectCount": sum(1 for n in nodes.values() if n["type"] == "object"),
            "tableCount": sum(1 for n in nodes.values() if n["type"] == "table"),
            "edgeCount": len(edges),
        },
    }


def merge_catalog_dependencies(
    graph: dict[str, Any], dep_rows: list[tuple], columns: tuple[str, ...],
) -> dict[str, Any]:
    """Fold AUTHORITATIVE catalog dependency edges into a body-derived graph (P0.2).

    `dep_rows` are rows in `columns` order (DEPENDENCY_COLUMNS:
    from_schema, from_name, to_schema, to_name, dep_type). Catalog deps resolve
    names exactly (synonyms, cross-schema, renames) where the regex body scan
    can miss. Each added edge carries ``source:"catalog"`` and ``rel:"depends"``
    (the catalog does not distinguish read vs write). Edges already present from
    the body scan (same from→to) are NOT duplicated. Nodes are created as
    needed; `dep_type` seeds the node kind (a *TABLE* dep_type → table node).

    Idempotent: re-merging the same rows is a no-op. Dynamic-SQL dependencies are
    invisible to the catalog too — this does not (and cannot) capture them.
    """
    col = {c: i for i, c in enumerate(columns)}
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    existing: dict[tuple[str, str], dict[str, str]] = {}
    for e in graph.get("edges", []):
        existing.setdefault((_norm(e["from"]), _norm(e["to"])), e)
    added = 0

    def _ensure(nid: str, kind: str, ntype: str) -> None:
        if nid not in nodes:
            nodes[nid] = {"id": nid, "kind": kind, "type": ntype, "inDegree": 0, "outDegree": 0}
            graph["nodes"].append(nodes[nid])

    for row in dep_rows:
        fs, fn = _display(row[col["from_schema"]] or ""), _display(row[col["from_name"]] or "")
        ts, tn = _display(row[col["to_schema"]] or ""), _display(row[col["to_name"]] or "")
        if not fn or not tn:
            continue
        dtype = str(row[col["dep_type"]] or "").upper()
        src = f"{fs}.{fn}" if fs else fn
        dst = f"{ts}.{tn}" if ts else tn
        if _norm(src) == _norm(dst):
            continue
        _ensure(src, "OBJECT", "object")
        ntype = "table" if "TABLE" in dtype else ("object" if dtype else "object")
        _ensure(dst, dtype or "OBJECT", ntype)
        key = (_norm(src), _norm(dst))
        prior = existing.get(key)
        if prior is not None:
            # Already known from the body scan. The catalog is the authority on
            # what depends on what, so the edge is RE-STAMPED as catalog-confirmed
            # rather than left looking purely regex-derived (C2, audit
            # 2026-08-29): `db_introspect.attach_catalog_calls` reads this
            # provenance to decide which edges the wave planner may trust.
            if "catalog" not in str(prior.get("source", "")):
                prior["source"] = "body+catalog"
            continue
        edge = {"from": src, "to": dst, "rel": "depends", "source": "catalog"}
        graph["edges"].append(edge)
        nodes[src]["outDegree"] += 1
        nodes[dst]["inDegree"] += 1
        existing[key] = edge
        added += 1

    st = graph.setdefault("stats", {})
    st["edgeCount"] = len(graph["edges"])
    st["catalogEdgesAdded"] = st.get("catalogEdgesAdded", 0) + added
    return graph


# --------------------------------------------------------------------------- #
# Cohesion clustering (union-find over shared tables + call edges)
# --------------------------------------------------------------------------- #

def cohesion_modules(objects: list[dict[str, Any]]) -> dict[str, str]:
    """Group objects into modules by cohesion, return {objectFq: moduleName}.

    Two objects are in the same module if they touch a common table (read or
    written) OR one calls the other. Each connected component is named after
    its most-shared table (singularised, PascalCase); ties fall back to the
    object-name heuristic. Deterministic — no reliance on naming conventions.
    """
    fqs = [_display(o.get("fqName") or o.get("name", "")) for o in objects]
    parent = {fq: fq for fq in fqs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # table → objects touching it
    table_to_objs: dict[str, list[str]] = {}
    # m3, audit 2026-08-29: `by_tail` was a plain dict keyed on the bare name, so
    # `dbo.usp_Do` and `sales.usp_Do` overwrote each other — the last one read
    # won, and every call to that bare name was silently attributed to it.
    # A multi-map keeps both, and an ambiguous name then resolves to neither.
    by_fq: dict[str, str] = {}
    by_tail: dict[str, list[str]] = {}
    for o, fq in zip(objects, fqs):
        by_fq[_norm(fq)] = fq
        by_tail.setdefault(_tail(fq), []).append(fq)
        for t in (o.get("tablesRead", []) or []) + (o.get("tablesWritten", []) or []):
            table_to_objs.setdefault(_norm(t), []).append(fq)
    for objs in table_to_objs.values():
        for other in objs[1:]:
            union(objs[0], other)
    # call edges — both extraction sources, resolved with the no-guess policy.
    for o, fq in zip(objects, fqs):
        callees = (o.get("callsProcs", []) or []) + (o.get("callsInferred", []) or [])
        for callee in callees:
            dst = _resolve_callee(callee, by_fq, by_tail)
            if dst:
                union(fq, dst)

    # Assemble components.
    comps: dict[str, list[str]] = {}
    for fq in fqs:
        comps.setdefault(find(fq), []).append(fq)

    # Name each component.
    obj_by_fq = {fq: o for o, fq in zip(objects, fqs)}
    result: dict[str, str] = {}
    used: dict[str, int] = {}
    for members in comps.values():
        name = _name_component(members, obj_by_fq)
        # disambiguate duplicate module names deterministically
        if name in used:
            used[name] += 1
            name = f"{name}{used[name]}"
        else:
            used[name] = 1
        for fq in members:
            result[fq] = name
    return result


def _name_component(members: list[str], obj_by_fq: dict[str, dict]) -> str:
    counts: dict[str, int] = {}
    for fq in members:
        o = obj_by_fq[fq]
        for t in (o.get("tablesWritten", []) or []) + (o.get("tablesRead", []) or []):
            counts[_display(t)] = counts.get(_display(t), 0) + 1
    if counts:
        top = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        return _sanitize(_singularize(_tail(top)))
    # fallback: shortest member's trailing name
    return _sanitize(_tail(sorted(members, key=len)[0])) or "Misc"


def _singularize(table: str) -> str:
    t = table.strip().strip("[]")
    if len(t) > 3 and t.lower().endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 2 and t.lower().endswith("s") and not t.lower().endswith("ss"):
        return t[:-1]
    return t


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", name).strip()
    if not cleaned:
        return "Misc"
    return "".join(w.capitalize() for w in cleaned.split())


# --------------------------------------------------------------------------- #
# Impact analysis + rendering
# --------------------------------------------------------------------------- #

def impact_of(graph: dict[str, Any], fq: str) -> dict[str, list[str]]:
    """Return {dependsOn, dependents} for a node id (case-insensitive match)."""
    key = _norm(fq)
    depends_on = sorted({e["to"] for e in graph["edges"] if _norm(e["from"]) == key})
    dependents = sorted({e["from"] for e in graph["edges"] if _norm(e["to"]) == key})
    return {"dependsOn": depends_on, "dependents": dependents}


def to_mermaid(graph: dict[str, Any], max_edges: int = 120) -> str:
    """Render a bounded Mermaid `graph LR`. Objects are boxes, tables cylinders."""
    def sid(nid: str) -> str:
        return "n_" + re.sub(r"[^0-9A-Za-z]+", "_", nid)

    lines = ["graph LR"]
    shown_nodes: set[str] = set()
    edges = graph["edges"][:max_edges]
    for e in edges:
        shown_nodes.add(e["from"])
        shown_nodes.add(e["to"])
    node_kind = {n["id"]: n for n in graph["nodes"]}
    for nid in sorted(shown_nodes):
        n = node_kind.get(nid, {"type": "object"})
        label = nid.replace('"', "'")
        if n.get("type") == "table":
            lines.append(f'    {sid(nid)}[("{label}")]')
        elif n.get("type") == "external":
            lines.append(f'    {sid(nid)}(["{label}"])')
        else:
            lines.append(f'    {sid(nid)}["{label}"]')
    arrow = {"reads": "-->", "writes": "==>", "calls": "-.->"}
    for e in edges:
        lines.append(f'    {sid(e["from"])} {arrow.get(e["rel"], "-->")}|{e["rel"]}| {sid(e["to"])}')
    if len(graph["edges"]) > max_edges:
        lines.append(f'    %% … {len(graph["edges"]) - max_edges} more edges elided')
    return "\n".join(lines)
