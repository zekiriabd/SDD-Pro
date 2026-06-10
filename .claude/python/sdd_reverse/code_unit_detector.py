"""code_unit_detector.py — Code-driven functional units (L2).

Before L2, a functional unit could only originate from a UI page file, so a
backend-only / API-only legacy (controllers + services + repositories, no
.aspx/.cshtml) produced ZERO units and was invisible to the whole pipeline.

L2 adds two complementary unit sources, derived from the L0 code graph, that
run AFTER the UI-page units and cover what those miss:

    1. Controllers  → one unit per MVC/Web API controller (REST/API surface).
    2. Orphan modules → behavioural classes (service/repository/complex/classic
       with methods) not reachable from any page or controller unit, grouped by
       module (namespace, else top folder). Catches pure backend business
       logic, batch jobs, scheduled tasks, domain services.

Supporting-only types (DTO / entity / interface / enum / pure static helper) do
NOT form a unit on their own — they are carried in via `classes[]` enrichment.

Public API:
    detect_code_units(code_graph, existing_units, *, max_depth=3) -> list[dict]

Returns candidates in the same shape as `ui_unit_detector.detect_units`
(``{label, suggestedName, language, kind, evidenceFiles, entities,
confidenceEstimate, rationale}``) so `enrich_units` + `build_inventory` treat
them uniformly.
"""

from __future__ import annotations

import re
from typing import Any

# Roles that make a class "behavioural" enough to anchor a backend module unit.
_BEHAVIOURAL_ROLES = frozenset({"service", "repository", "controller", "complex"})


def _pascal(token: str) -> str:
    parts = re.split(r"[-_.\s]+", token)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _module_key(cls: dict[str, Any]) -> str:
    """Group key for orphan modules: namespace if present, else top folder."""
    ns = (cls.get("namespace") or "").strip()
    if ns:
        # Drop a trailing technical segment so e.g. `Acme.Billing.Services`
        # and `Acme.Billing.Repositories` group under `Acme.Billing`.
        segs = ns.split(".")
        if len(segs) >= 2 and segs[-1].lower() in (
            "services", "repositories", "repository", "data", "dal", "bll",
            "business", "logic", "core", "domain", "infrastructure",
        ):
            segs = segs[:-1]
        return ".".join(segs)
    file = cls.get("file", "")
    top = file.split("/", 1)[0] if "/" in file else ""
    return top or file


def _module_name(module_key: str) -> str:
    last = module_key.split(".")[-1].split("/")[-1] if module_key else "Module"
    return _pascal(last) or "Module"


def _closure(seed_classes: set[str], adj: dict[str, set[str]], max_depth: int) -> set[str]:
    reached = set(seed_classes)
    frontier = set(seed_classes)
    depth = 0
    while frontier and depth < max_depth:
        nxt: set[str] = set()
        for cn in frontier:
            for ref in adj.get(cn, ()):  # noqa: SIM118
                if ref not in reached:
                    nxt.add(ref)
        reached |= nxt
        frontier = nxt
        depth += 1
    return reached


def detect_code_units(
    code_graph: dict[str, Any],
    existing_units: list[dict[str, Any]],
    *,
    max_depth: int = 3,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Detect controller + orphan-module units from the code graph."""
    classes = code_graph.get("classes", [])
    if not classes:
        return []

    by_name: dict[str, dict[str, Any]] = {c["name"]: c for c in classes}
    adj: dict[str, set[str]] = {c["name"]: set(c.get("references", [])) for c in classes}
    file_to_classes: dict[str, list[str]] = {}
    for c in classes:
        file_to_classes.setdefault(c["file"], []).append(c["name"])

    lang = language or code_graph.get("language") or "unknown"

    # Classes already covered by UI-page units (their transitive closure).
    page_seed: set[str] = set()
    for u in existing_units:
        for f in (u.get("seedEvidenceFiles") or u.get("evidenceFiles", [])):
            page_seed |= set(file_to_classes.get(f, []))
    covered = _closure(page_seed, adj, max_depth)

    units: list[dict[str, Any]] = []
    used: set[str] = set(covered)

    # 1. Controllers → one unit each (API surface), unless already covered.
    controllers = sorted(
        (c for c in classes if c["role"] == "controller" and c["name"] not in covered),
        key=lambda c: c["name"],
    )
    for c in controllers:
        if c["name"] in used:
            continue
        name = c["name"]
        suggested = _pascal(re.sub(r"Controller$", "", name) or name)
        closure = _closure({name}, adj, max_depth)
        used |= closure
        units.append({
            "label": f"API {suggested}",
            "suggestedName": suggested,
            "language": lang,
            "kind": "api",
            "evidenceFiles": [c["file"]],
            "entities": [],
            "confidenceEstimate": "medium",
            "rationale": f"Controller {name} ({c['file']}) — surface API/MVC, "
                         f"{len(closure)} classe(s) atteinte(s).",
        })

    # 2. Orphan modules → group remaining behavioural classes by module key.
    orphan_behavioural = [
        c for c in classes
        if c["name"] not in used
        and (
            c["role"] in _BEHAVIOURAL_ROLES
            or (c["role"] == "classic" and c.get("methodCount", 0) >= 1)
        )
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in orphan_behavioural:
        groups.setdefault(_module_key(c), []).append(c)

    for mod_key, members in sorted(groups.items()):
        anchor = sorted(members, key=lambda c: (-c.get("methodCount", 0), c["name"]))[0]
        suggested = _module_name(mod_key)
        seed_files = sorted({m["file"] for m in members})
        member_names = {m["name"] for m in members}
        used |= member_names
        roles = sorted({m["role"] for m in members})
        units.append({
            "label": f"Module {suggested}",
            "suggestedName": suggested,
            "language": lang,
            "kind": "module",
            "evidenceFiles": seed_files,
            "entities": [],
            "confidenceEstimate": "medium",
            "rationale": f"Module backend `{mod_key}` — {len(members)} classe(s) "
                         f"métier ({', '.join(roles)}), aucune page UI rattachée. "
                         f"Ancre : {anchor['name']}.",
        })

    return units
