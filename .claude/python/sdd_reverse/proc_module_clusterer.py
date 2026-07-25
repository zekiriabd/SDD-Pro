"""proc_module_clusterer.py — Group stored procedures into business modules.

User model (confirmed): **1 proc = 1 User Story**, **1 module = 1 FEAT**. A
module is the set of procedures that act on the same business object:

    usp_Contact_Insert / usp_Contact_Delete / usp_Contact_List   → module "Contact"
    usp_Order_Create   / usp_GetOrders      / usp_UpdateOrder     → module "Order"

Heuristic (deterministic, 0 token):
  1. strip a known routine prefix (usp_, sp_, proc_, p_, fn_, ufn_, tvf_, f_…)
  2. tokenise on `_`, `-`, or CamelCase boundaries
  3. drop VERB tokens (insert/get/update/delete/...) and NOISE tokens
     (list/all/byid/by/details/...) → the remaining nouns = the module/object
  4. fall back to a shared-table footprint, then to the schema, when no object
     can be derived (so nothing is ever dropped — traceability over tidiness)

The module name becomes the FEAT `{Name}` (PascalCase, no accents). Two procs
of the same module never get separate FEATs; a proc with no derivable object is
parked in a `Misc` module rather than discarded.

Public API:
    parse_routine_name(raw) -> {prefix, verb, object, tokens}
    cluster(routines) -> {module_name: [routine, ...]}   # routines annotated in place
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = 1

_PREFIXES = ("usp_", "sp_", "proc_", "prc_", "p_", "ufn_", "fn_", "tvf_", "udf_", "f_")

# Canonical verb → normalised label (drives the US title later).
_VERBS = {
    "insert": "create", "ins": "create", "add": "create", "create": "create",
    "new": "create", "save": "save", "upsert": "save", "merge": "save",
    "update": "update", "upd": "update", "edit": "update", "modify": "update", "set": "update",
    "delete": "delete", "del": "delete", "remove": "delete", "rmv": "delete", "drop": "delete",
    "get": "read", "list": "read", "select": "read", "sel": "read", "read": "read",
    "fetch": "read", "find": "read", "search": "read", "load": "read", "lookup": "read",
    "count": "read", "exists": "read", "check": "read", "report": "read", "export": "read",
    "validate": "validate", "calc": "compute", "compute": "compute", "process": "process",
    "import": "import", "sync": "sync", "send": "notify", "notify": "notify",
}
# Tokens that are neither verb nor object — noise to strip from the object name.
_NOISE = frozenset({
    "list", "all", "byid", "by", "id", "ids", "details", "detail", "info",
    "data", "rows", "row", "result", "results", "page", "paged", "full", "single",
    "sp", "proc", "tbl", "tmp", "temp", "v", "vw",
})


def _split_tokens(core: str) -> list[str]:
    # split on separators, then on CamelCase humps
    parts: list[str] = []
    for chunk in re.split(r"[_\-\s]+", core):
        if not chunk:
            continue
        parts.extend(re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", chunk) or [chunk])
    return [p for p in parts if p]


def parse_routine_name(raw: str) -> dict[str, Any]:
    name = raw.split(".")[-1].strip().strip("[]")
    core = name
    low = name.lower()
    for pre in _PREFIXES:
        if low.startswith(pre):
            core = name[len(pre):]
            break
    tokens = _split_tokens(core)
    verb = None
    object_tokens: list[str] = []
    for tok in tokens:
        tl = tok.lower()
        if verb is None and tl in _VERBS:
            verb = _VERBS[tl]
            continue
        if tl in _NOISE:
            continue
        object_tokens.append(tok)
    obj = "".join(t.capitalize() for t in object_tokens) if object_tokens else ""
    return {"prefix_stripped": core, "verb": verb, "object": obj, "tokens": tokens}


def _sanitize_module(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", name).strip()
    if not cleaned:
        return "Misc"
    return "".join(w.capitalize() for w in cleaned.split())


def cluster(
    routines: list[dict[str, Any]], *, use_cohesion: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Group routines into modules. Annotates each routine with `verb`/`module`.

    `routines` items use at least {"name": str}. Optional {"schema", "signals"}
    refine the fallback (shared-table footprint, schema grouping).

    `use_cohesion` (P0.2, opt-in — default keeps the naming behaviour and every
    existing test green): group by the dependency-cohesion graph instead of the
    name heuristic (objects sharing tables / calling each other land in one
    module). Far more robust on legacy DBs with no naming convention (audit DB4).
    """
    if use_cohesion:
        return _cluster_by_cohesion(routines)
    modules: dict[str, list[dict[str, Any]]] = {}
    for r in routines:
        parsed = parse_routine_name(r["name"])
        r["verb"] = parsed["verb"]
        module = parsed["object"]
        if not module:
            # Fallback 1: dominant written table; Fallback 2: schema; else Misc.
            sig = r.get("signals") or {}
            written = sig.get("tablesWritten") or []
            read = sig.get("tablesRead") or []
            if written:
                module = _singularize(written[0])
            elif read:
                module = _singularize(read[0])
            elif r.get("schema"):
                module = str(r["schema"])
        module = _sanitize_module(module or "Misc")
        modules.setdefault(module, []).append(r)
    return modules


def _cluster_by_cohesion(routines: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """P0.2 cohesion grouping: use the dependency graph, keep verb annotation."""
    from sdd_reverse.sql_dependency_graph import cohesion_modules

    objects = []
    for r in routines:
        sig = r.get("signals") or {}
        objects.append({
            "fqName": r["name"],
            "tablesRead": sig.get("tablesRead") or [],
            "tablesWritten": sig.get("tablesWritten") or [],
            "callsProcs": sig.get("calls") or [],
        })
    assignment = cohesion_modules(objects)
    modules: dict[str, list[dict[str, Any]]] = {}
    for r in routines:
        r["verb"] = parse_routine_name(r["name"])["verb"]
        module = _sanitize_module(assignment.get(r["name"], "") or "Misc")
        modules.setdefault(module, []).append(r)
    return modules


def _singularize(table: str) -> str:
    t = table.strip().strip("[]")
    if len(t) > 3 and t.lower().endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 2 and t.lower().endswith("s") and not t.lower().endswith("ss"):
        return t[:-1]
    return t
