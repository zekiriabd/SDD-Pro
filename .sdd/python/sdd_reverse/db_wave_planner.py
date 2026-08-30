"""db_wave_planner.py — dependency-aware execution planner for db-reverse.

The db-reverse orchestrator used to dispatch `needs_llm` in inventory iteration
order: a calling procedure could be analysed BEFORE the procedure it calls, so
the caller never had the meaning of what it delegates to. This module turns the
object->object call graph into an **execution plan by waves**:

    wave 0 = objects that call nothing resolvable (leaves — typically functions)
    wave k = objects whose every resolvable callee sits in a wave < k

Inside a wave, objects are independent: they can run concurrently (bounded by
MaxParallel). Between two waves there is exactly one barrier, which is where the
orchestrator writes the previous wave's summaries back into the shared context.

Recursion is real in T-SQL (self-recursive procedures, mutually recursive pairs),
so the graph is NOT assumed acyclic: strongly connected components are condensed
first (Tarjan), and a component of size > 1 is planned as ONE unit — it must be
analysed as a whole, by a single agent, with every body of the cycle in its pack.

Fully deterministic (0 token), offline, no DB access: it consumes the already
normalised introspection objects, so every engine gets the same plan.

The call graph it orders on has three sources, ranked by authority — the
engine's dependency catalog, the keyword-anchored regex extraction, and the
keyword-less invocation heuristic. See `resolve_calls` for what each is trusted
to do and, more importantly, what each is NOT trusted to do.

Public API:
    resolve_calls(objects)      -> (edges, unresolved)
    strongly_connected(nodes, adj) -> list[list[str]]
    plan_waves(objects)         -> dict (executionPlan contract)
"""
from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- #
# Identity helpers — one canonical key per object, tolerant of catalog notation
# --------------------------------------------------------------------------- #

def _norm(ident: str) -> str:
    """Canonical comparison key: unbracketed, unquoted, lowercase."""
    if not ident:
        return ""
    return ident.strip().strip("[]`\"").strip().lower()


def _tail(ident: str) -> str:
    """Bare object name, schema stripped — for lenient callee resolution."""
    n = _norm(ident)
    return n.rsplit(".", 1)[-1] if "." in n else n


def _fq(obj: dict[str, Any]) -> str:
    return str(obj.get("fqName") or obj.get("name") or "")


# --------------------------------------------------------------------------- #
# Call resolution
# --------------------------------------------------------------------------- #

def resolve_calls(
    objects: Iterable[dict[str, Any]],
) -> tuple[list[tuple[str, str]], dict[str, list[str]]]:
    """Resolve every declared callee against the known object set.

    Returns `(edges, unresolved)` where `edges` are `(caller_fq, callee_fq)`
    pairs between objects that BOTH exist in this database, and `unresolved`
    maps a caller to the callee names that could not be resolved.

    Three sources feed the graph, in decreasing authority (C2, audit 2026-08-29):

    ``catalogCalls``
        Object→object edges read from the engine's own dependency catalog
        (`sys.sql_expression_dependencies`, `all_dependencies`, `pg_depend`),
        projected per object by `db_introspect.attach_catalog_calls`. This is
        ground truth: it survives synonyms, renames and cross-schema
        qualification, and it is the ONLY reliable source on Oracle, where a
        PL/SQL call carries no keyword at all. It used to be collected and then
        dropped on the floor — merged into `dependencyGraph`, never into the
        graph `plan_waves` actually orders on.

    ``callsProcs``
        The keyword-anchored regex extraction (`EXEC` / `CALL` / `PERFORM`).
        Authoritative enough to REPORT a failure: a name written here and absent
        from the catalog is a linked server, a cross-database call, a dropped
        object or a genuinely ambiguous bare name — all honest reasons to
        downgrade the caller's confidence, because the analyst cannot read what
        that call does.

    ``callsInferred``
        Keyword-less invocations (`pkg.proc(...)`, a scalar function inside an
        expression). Heuristic by construction, so it is resolve-or-drop: it can
        only ADD a real edge, never invent an unresolved callee.

    Catalog data takes precedence where both describe the same object: when the
    regex produced a name the object set cannot resolve, but the catalog resolved
    a callee with the same bare name, the catalog's answer wins and no unresolved
    callee is reported.
    """
    objs = list(objects)
    by_fq: dict[str, str] = {}
    by_tail: dict[str, list[str]] = {}
    for o in objs:
        fq = _fq(o)
        if not fq:
            continue
        by_fq[_norm(fq)] = fq
        by_tail.setdefault(_tail(fq), []).append(fq)

    def _resolve(callee: str) -> str | None:
        target = by_fq.get(_norm(callee))
        if target is not None:
            return target
        candidates = by_tail.get(_tail(callee), [])
        # Exactly one candidate is a safe resolution; two are a guess, and a
        # guess in a dependency graph silently reorders the plan.
        return candidates[0] if len(candidates) == 1 else None

    edges: list[tuple[str, str]] = []
    unresolved: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()

    def _add(caller: str, target: str) -> None:
        key = (caller, target)
        if key not in seen:
            seen.add(key)
            edges.append(key)

    for o in objs:
        caller = _fq(o)
        if not caller:
            continue

        # 1. Catalog first — it also arbitrates the regex failures below.
        catalog_tails: set[str] = set()
        for callee in o.get("catalogCalls") or []:
            target = _resolve(callee)
            if target is None:
                continue                      # a table, or an object outside scope
            catalog_tails.add(_tail(target))
            _add(caller, target)

        # 2. Keyword-anchored regex — may report an unresolved callee.
        for callee in o.get("callsProcs") or []:
            target = _resolve(callee)
            if target is None:
                if _tail(callee) in catalog_tails:
                    continue                  # the catalog already answered this
                unresolved.setdefault(caller, [])
                if callee not in unresolved[caller]:
                    unresolved[caller].append(callee)
                continue
            _add(caller, target)

        # 3. Keyword-less invocations — resolve or drop, never reported.
        for callee in o.get("callsInferred") or []:
            target = _resolve(callee)
            if target is not None:
                _add(caller, target)

    return edges, unresolved


# --------------------------------------------------------------------------- #
# Strongly connected components (Tarjan, iterative — no recursion limit risk)
# --------------------------------------------------------------------------- #

def strongly_connected(
    nodes: list[str], adj: dict[str, list[str]]
) -> list[list[str]]:
    """Tarjan's SCC, iterative. Returns components, each sorted, order stable.

    A self-loop (`A` calls `A`) yields a component of size 1 — size alone does
    not tell you it is recursive, so callers should also check the self-edge.
    """
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    for root in nodes:
        if root in index_of:
            continue
        # work items: (node, iterator position)
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index_of[node] = counter
                low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            neighbours = adj.get(node, [])
            for i in range(pi, len(neighbours)):
                nxt = neighbours[i]
                if nxt not in index_of:
                    work[-1] = (node, i + 1)
                    work.append((nxt, 0))
                    recursed = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
            if recursed:
                continue
            if low[node] == index_of[node]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                result.append(sorted(comp))
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])

    return result


# --------------------------------------------------------------------------- #
# Wave planning
# --------------------------------------------------------------------------- #

def plan_waves(objects: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build the full execution plan from the introspected object set.

    Contract (persisted as `db-context.json.executionPlan`):
        waves            list[list[str]]  — fq names, callees strictly before callers
        components       list[{id, members, recursive, wave}]
        unresolvedCallees dict[fq, list[str]]
        metrics          dict[fq, {fanIn, fanOut, wave, sccId, recursive}]
        stats            counts, for the chat line and the audit trail
    """
    objs = [o for o in objects if _fq(o)]
    nodes = [_fq(o) for o in objs]
    edges, unresolved = resolve_calls(objs)

    adj: dict[str, list[str]] = {n: [] for n in nodes}
    rev: dict[str, list[str]] = {n: [] for n in nodes}
    self_loops: set[str] = set()
    for caller, callee in edges:
        if caller == callee:
            self_loops.add(caller)
            continue
        adj[caller].append(callee)
        rev[callee].append(caller)

    components = strongly_connected(nodes, adj)
    comp_of: dict[str, int] = {}
    for cid, members in enumerate(components):
        for m in members:
            comp_of[m] = cid

    # Condensed DAG: component -> components it depends on (its callees').
    cadj: dict[int, set[int]] = {cid: set() for cid in range(len(components))}
    for caller, callee in edges:
        a, b = comp_of[caller], comp_of[callee]
        if a != b:
            cadj[a].add(b)

    # Longest-path depth on the condensed DAG. Callees have a strictly lower
    # depth than their callers, so ascending depth == correct execution order.
    # Iterative (an object graph can chain deeper than Python's recursion limit).
    depth: dict[int, int] = {}
    for start in range(len(components)):
        if start in depth:
            continue
        stack = [(start, False)]
        while stack:
            cid, expanded = stack.pop()
            if cid in depth:
                continue
            deps = [d for d in cadj[cid] if d != cid]
            if expanded or not deps:
                depth[cid] = max((depth[d] + 1 for d in deps if d in depth), default=0)
                continue
            pending = [d for d in deps if d not in depth]
            if not pending:
                depth[cid] = max(depth[d] + 1 for d in deps)
                continue
            stack.append((cid, True))
            stack.extend((d, False) for d in pending)

    # An empty object set has ZERO waves, not one empty one — the chat line
    # would otherwise announce "1 vague" over nothing.
    if not components:
        max_depth = -1
    else:
        max_depth = max(depth.values())
    waves: list[list[str]] = [[] for _ in range(max_depth + 1)]
    for cid, members in enumerate(components):
        waves[depth[cid]].extend(members)
    waves = [sorted(w) for w in waves]

    comp_records = [
        {
            "id": f"SCC-{cid + 1}",
            "members": members,
            # A component is recursive if it holds more than one object, or if
            # its single object calls itself.
            "recursive": len(members) > 1 or members[0] in self_loops,
            "wave": depth[cid],
        }
        for cid, members in enumerate(components)
    ]
    comp_by_member = {m: c for c in comp_records for m in c["members"]}

    metrics: dict[str, dict[str, Any]] = {}
    for n in nodes:
        comp = comp_by_member[n]
        metrics[n] = {
            "fanIn": len(set(rev[n])),
            "fanOut": len(set(adj[n])),
            "wave": comp["wave"],
            "sccId": comp["id"],
            "recursive": comp["recursive"],
            "unresolvedCallees": list(unresolved.get(n, [])),
        }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "waves": waves,
        "components": comp_records,
        "edges": [{"from": a, "to": b} for a, b in edges],
        "unresolvedCallees": {k: v for k, v in sorted(unresolved.items())},
        "metrics": metrics,
        "stats": {
            "objects": len(nodes),
            "waveCount": len(waves),
            "resolvedCalls": len(edges),
            "unresolvedCalls": sum(len(v) for v in unresolved.values()),
            "recursiveComponents": sum(1 for c in comp_records if c["recursive"]),
            "widestWave": max((len(w) for w in waves), default=0),
        },
    }
