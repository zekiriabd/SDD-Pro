"""synthesis.py — Deterministic system-synthesis renderers (reverse synthesis layer).

New "synthesis layer" of the reverse pipeline (Phase 3.7). It sits at an
altitude ABOVE the 3a->3b->3c ladder and is a strictly READ-ONLY consumer of
the deterministic Phase-1/2 artefacts:

    inventory.json        -> units[] (id, label, kind, classes, evidenceFiles, entities, confidenceEstimate)
    deps-graph.json       -> internalEdges[], externalDeps[], cyclesDetected[]   (source of C4)
    db-schema.merged.json -> entities[], relations[]                              (source of ERD)

It NEVER reads the legacy code, NEVER touches the FEAT contract or the ladder,
and the CLI writes ONLY under workspace/old/{P}/.sys/synthesis/ (documentation,
never workspace/feats/ — invisible to /sdd-full).

Everything here is pure (no I/O): the functions take loaded dicts and return
markdown strings. The CLI (reverse_synth.py) does the loading + atomic writes.

D4 isolation: imports ONLY stdlib + sdd_reverse. Confidence stays in the
reverse enum {high, medium, low} (no emojis) per loader.reverse invariant
`reverse-confidence-enum-strict`.

Public API:
    render_erd(db_schema)                         -> (markdown, confidence_rollup)
    build_c4(inventory, deps_graph, doc_level)    -> {context, containers, components}, confidence_rollup
    build_soul(inventory, deps_graph, db_schema)  -> (markdown, confidence_rollup)
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_CONF_ORDER = {"high": 0, "medium": 1, "low": 2}


def _norm_conf(value: str | None) -> str:
    """Coerce any confidence-ish value into the strict reverse enum."""
    v = (value or "").strip().lower()
    return v if v in _CONF_ORDER else "low"


def _new_rollup() -> dict[str, int]:
    return {"high": 0, "medium": 0, "low": 0}


def _bump(rollup: dict[str, int], conf: str) -> str:
    """Increment the rollup for `conf` and return the normalized value."""
    c = _norm_conf(conf)
    rollup[c] += 1
    return c


def _mermaid_id(name: str, prefix: str = "n") -> str:
    """Stable, render-safe Mermaid node identifier derived from a real name."""
    slug = re.sub(r"[^0-9A-Za-z]+", "_", str(name)).strip("_")
    if not slug:
        slug = "anon"
    if slug[0].isdigit():
        slug = f"{prefix}_{slug}"
    return slug


def _as_evidence_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def _framework_names(frameworks: Any) -> list[str]:
    """Normalize frameworksDetected entries (str OR {id|name|label,...}) to display names."""
    out: list[str] = []
    for f in frameworks or []:
        if isinstance(f, dict):
            name = f.get("id") or f.get("name") or f.get("label")
            if name:
                out.append(str(name))
        elif f:
            out.append(str(f))
    return out


def _top_segment(path: str) -> str:
    """First directory segment of a posix-ish relative path ('(root)' if flat)."""
    p = str(path).replace("\\", "/").lstrip("./")
    if "/" in p:
        return p.split("/", 1)[0]
    return "(root)"


# ---------------------------------------------------------------------------
# ERD  (source: db-schema.merged.json / db-schema.json)
# ---------------------------------------------------------------------------

def render_erd(db_schema: dict[str, Any] | None) -> tuple[str, dict[str, int]]:
    """Render a Mermaid erDiagram + a fields/relations reference table.

    Pure render: every entity already carries its evidence in the schema;
    `deduced` entities/relations (observed from inline SQL, not from DDL) are
    capped at confidence=medium, everything else is high.
    """
    rollup = _new_rollup()
    db_schema = db_schema or {}
    entities = db_schema.get("entities") or []
    relations = db_schema.get("relations") or []

    lines: list[str] = []
    lines.append("# ERD complet (reverse synthesis)\n")
    lines.append("> Vue déterministe rendue depuis `db-schema.merged.json` "
                 "(ou `db-schema.json`). Lecture seule, aucune interprétation.\n")
    lines.append("> Confiance : `high` = défini par le DDL source ; "
                 "`medium` = déduit du code (SQL inline), marqué `deduced`.\n")

    if not entities:
        lines.append("\n> **GAP** — aucune entité dans le schéma. "
                     "Lancer `/sdd-reverse-inventory` (et `/sdd-reverse-audit` "
                     "pour enrichir le schéma) avant la synthèse.\n")
        _bump(rollup, "low")
        return "\n".join(lines), rollup

    # --- Mermaid erDiagram ---
    lines.append("\n## Diagramme\n")
    lines.append("```mermaid")
    lines.append("erDiagram")
    id_by_name: dict[str, str] = {}
    for ent in entities:
        name = ent.get("name") or ent.get("table") or "Entity"
        eid = _mermaid_id(name, "e")
        id_by_name[name] = eid
        lines.append(f"    {eid} {{")
        for fld in ent.get("fields") or []:
            ftype = _mermaid_id(fld.get("type") or "unknown", "t")
            fname = _mermaid_id(fld.get("name") or "field", "f")
            marker = "PK" if fld.get("primaryKey") else ""
            if marker:
                lines.append(f"        {ftype} {fname} {marker}")
            else:
                lines.append(f"        {ftype} {fname}")
        lines.append("    }")

    for rel in relations:
        frm = (rel.get("from") or {}).get("entity")
        to = (rel.get("to") or {}).get("entity")
        if not frm or not to:
            continue
        fid = id_by_name.get(frm) or _mermaid_id(frm, "e")
        tid = id_by_name.get(to) or _mermaid_id(to, "e")
        label = _mermaid_id(rel.get("name") or "ref", "r")
        # Referenced entity is the "one" side, referencing holds the FK (many).
        lines.append(f"    {tid} ||--o{{ {fid} : {label}")
    lines.append("```\n")

    # --- Reference table (real names + evidence + confidence) ---
    lines.append("## Entités\n")
    lines.append("| Entité | Table | Champs | Confiance | Evidence |")
    lines.append("|---|---|---|---|---|")
    for ent in entities:
        name = ent.get("name") or ent.get("table") or "Entity"
        table = ent.get("table") or name
        nfields = len(ent.get("fields") or [])
        conf = _bump(rollup, "medium" if ent.get("deduced") else "high")
        ev = ", ".join(_as_evidence_list(ent.get("evidence"))) or "—"
        deduced = " *(deduced)*" if ent.get("deduced") else ""
        lines.append(f"| {name}{deduced} | {table} | {nfields} | {conf} | {ev} |")

    if relations:
        lines.append("\n## Relations\n")
        lines.append("| De | Champ | Vers | Confiance |")
        lines.append("|---|---|---|---|")
        for rel in relations:
            frm = (rel.get("from") or {}).get("entity") or "?"
            ffield = (rel.get("from") or {}).get("field") or "?"
            to = (rel.get("to") or {}).get("entity") or "?"
            conf = _bump(rollup, "medium" if rel.get("deduced") else "high")
            lines.append(f"| {frm} | {ffield} | {to} | {conf} |")

    return "\n".join(lines) + "\n", rollup


# ---------------------------------------------------------------------------
# C4  (source: inventory.json units[] + deps-graph.json edges)
# ---------------------------------------------------------------------------

def _container_of(file_path: str) -> str:
    return _top_segment(file_path)


def _build_file_maps(inventory: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Map evidence file -> unit id, and evidence file -> container (first owner wins)."""
    file_to_unit: dict[str, str] = {}
    file_to_container: dict[str, str] = {}
    for unit in inventory.get("units") or []:
        uid = unit.get("id") or "U-?"
        for f in unit.get("evidenceFiles") or []:
            fp = str(f).replace("\\", "/")
            file_to_unit.setdefault(fp, uid)
            file_to_container.setdefault(fp, _container_of(fp))
    return file_to_unit, file_to_container


def build_c4(
    inventory: dict[str, Any] | None,
    deps_graph: dict[str, Any] | None,
    doc_level: str = "complet",
) -> tuple[dict[str, str], dict[str, int]]:
    """Build C4 markdown documents (context always; containers+components if complet/detaille).

    Edges are aggregated from deps-graph internalEdges; every C4 relation is
    therefore evidenced by a parsed import/using/use (confidence high).
    Returns ({c4-context, [c4-containers], [c4-components]}, rollup).
    """
    rollup = _new_rollup()
    inventory = inventory or {}
    deps_graph = deps_graph or {}
    project = inventory.get("project") or "Système"
    docs: dict[str, str] = {}

    units = inventory.get("units") or []
    internal_edges = deps_graph.get("internalEdges") or []
    external = deps_graph.get("externalDeps") or []
    cycles = deps_graph.get("cyclesDetected") or []
    frameworks = inventory.get("frameworksDetected") or []
    entry_points = inventory.get("entryPoints") or []

    file_to_unit, file_to_container = _build_file_maps(inventory)

    # ---- C4 L1 : Context ----
    ctx: list[str] = []
    ctx.append(f"# C4 — Contexte : {project}\n")
    ctx.append("> Rendu déterministe depuis `inventory.json` + `deps-graph.json`. "
               "Lecture seule. Confiance `high` (parsé des manifestes/imports).\n")
    ctx.append("```mermaid")
    ctx.append("graph TB")
    sys_id = _mermaid_id(project, "sys")
    ctx.append(f'    {sys_id}["{project}<br/>(système legacy)"]')
    # External systems = top external deps (bounded), grouped by name.
    ext_names: list[str] = []
    seen_ext: set[str] = set()
    for dep in external:
        nm = dep.get("name")
        if nm and nm not in seen_ext:
            seen_ext.add(nm)
            ext_names.append(nm)
    for nm in ext_names[:15]:
        eid = _mermaid_id(nm, "ext")
        ctx.append(f'    {eid}(["{nm}"])')
        ctx.append(f"    {sys_id} --> {eid}")
        _bump(rollup, "high")
    # Actors = entry points (kind).
    for ep in entry_points[:10]:
        label = ep.get("kind") or ep.get("path") or "entrée"
        aid = _mermaid_id(f"actor_{label}", "act")
        ctx.append(f'    {aid}(("{label}"))')
        ctx.append(f"    {aid} --> {sys_id}")
    ctx.append("```\n")
    fw_names = _framework_names(frameworks)
    if fw_names:
        ctx.append("**Frameworks détectés :** " + ", ".join(fw_names) + "\n")
    _bump(rollup, "high")
    docs["c4-context"] = "\n".join(ctx) + "\n"

    if _norm_conf_doc_level(doc_level) == "essentiel":
        return docs, rollup

    # ---- C4 L2 : Containers (groupement par répertoire racine) ----
    containers: dict[str, list[str]] = {}
    for unit in units:
        for f in unit.get("evidenceFiles") or []:
            c = _container_of(str(f))
            containers.setdefault(c, [])
            if unit.get("id") and unit["id"] not in containers[c]:
                containers[c].append(unit["id"])

    cont: list[str] = []
    cont.append(f"# C4 — Conteneurs : {project}\n")
    cont.append("> Conteneurs = répertoires racine du legacy ; arêtes = "
                "dépendances internes agrégées (`deps-graph.json`).\n")
    cont.append("```mermaid")
    cont.append("graph TB")
    for c in sorted(containers):
        cid = _mermaid_id(c, "c")
        cont.append(f'    {cid}["{c}<br/>({len(containers[c])} unité(s))"]')
    # Aggregate edges container->container.
    cont_edges: set[tuple[str, str]] = set()
    for e in internal_edges:
        cf = file_to_container.get(str(e.get("from", "")).replace("\\", "/"))
        ct = file_to_container.get(str(e.get("to", "")).replace("\\", "/"))
        if cf and ct and cf != ct:
            cont_edges.add((cf, ct))
    for cf, ct in sorted(cont_edges):
        cont.append(f"    {_mermaid_id(cf, 'c')} --> {_mermaid_id(ct, 'c')}")
        _bump(rollup, "high")
    cont.append("```\n")
    if cycles:
        cont.append(f"> **Note** — {len(cycles)} cycle(s) de dépendances détecté(s) "
                    "(voir `deps-graph.json.cyclesDetected`). Confiance `medium`.\n")
        _bump(rollup, "medium")
    docs["c4-containers"] = "\n".join(cont) + "\n"

    # ---- C4 L3 : Components (unités) ----
    comp: list[str] = []
    comp.append(f"# C4 — Composants : {project}\n")
    comp.append("> Composants = unités fonctionnelles (`inventory.json.units[]`). "
                "Arêtes = dépendances internes mappées fichier→unité.\n")
    comp.append("```mermaid")
    comp.append("graph TB")
    label_by_unit: dict[str, str] = {}
    for unit in units:
        uid = unit.get("id") or "U-?"
        label = unit.get("label") or unit.get("suggestedName") or uid
        kind = unit.get("kind") or "unknown"
        label_by_unit[uid] = label
        comp.append(f'    {_mermaid_id(uid, "u")}["{uid}: {label}<br/>({kind})"]')
    unit_edges: set[tuple[str, str]] = set()
    for e in internal_edges:
        uf = file_to_unit.get(str(e.get("from", "")).replace("\\", "/"))
        ut = file_to_unit.get(str(e.get("to", "")).replace("\\", "/"))
        if uf and ut and uf != ut:
            unit_edges.add((uf, ut))
    for uf, ut in sorted(unit_edges):
        comp.append(f"    {_mermaid_id(uf, 'u')} --> {_mermaid_id(ut, 'u')}")
        _bump(rollup, "high")
    comp.append("```\n")
    # Per-unit confidence table (detaille only).
    if _norm_conf_doc_level(doc_level) == "detaille":
        comp.append("## Unités (détail)\n")
        comp.append("| Unité | Label | Kind | Confiance (estim.) | Fichiers |")
        comp.append("|---|---|---|---|---|")
        for unit in units:
            uid = unit.get("id") or "U-?"
            conf = _bump(rollup, unit.get("confidenceEstimate", "low"))
            comp.append(
                f"| {uid} | {unit.get('label', '')} | {unit.get('kind', '')} | "
                f"{conf} | {len(unit.get('evidenceFiles') or [])} |"
            )
    docs["c4-components"] = "\n".join(comp) + "\n"

    return docs, rollup


def _norm_conf_doc_level(value: str) -> str:
    v = (value or "complet").strip().lower()
    if v in ("essentiel", "essential", "essencial"):
        return "essentiel"
    if v in ("detaille", "detaillé", "détaillé", "detalhado", "detailed"):
        return "detaille"
    return "complet"


# ---------------------------------------------------------------------------
# soul.md  (executive synthesis — deterministic facts, honestly marked)
# ---------------------------------------------------------------------------

def build_soul(
    inventory: dict[str, Any] | None,
    deps_graph: dict[str, Any] | None,
    db_schema: dict[str, Any] | None,
) -> tuple[str, dict[str, int]]:
    """Build a deterministic executive synthesis (soul.md).

    No git mining, no invention: purpose is INFERRED (medium) from project
    metadata; core entities are RANKED by FK in-degree (high/medium); the
    "structuring constraints" section reports observed facts only (EOL deps,
    cycles). A narrative agent (reverse-soul) may enrich this later — out of
    scope for the deterministic core.
    """
    rollup = _new_rollup()
    inventory = inventory or {}
    deps_graph = deps_graph or {}
    db_schema = db_schema or {}

    project = inventory.get("project") or "Système"
    primary = inventory.get("primaryLanguage") or "inconnu"
    frameworks = inventory.get("frameworksDetected") or []
    units = inventory.get("units") or []
    entities = db_schema.get("entities") or []
    relations = db_schema.get("relations") or []
    external = deps_graph.get("externalDeps") or []
    cycles = deps_graph.get("cyclesDetected") or []

    lines: list[str] = []
    lines.append(f"# Soul — Synthèse exécutive : {project}\n")
    lines.append("> Synthèse déterministe (lecture seule sur les artefacts). "
                 "Chaque énoncé porte sa confiance dans l'enum reverse "
                 "`{high, medium, low}`. Aucun git-mining, aucune invention.\n")

    # --- Objectif (inféré) ---
    fw_names = _framework_names(frameworks)
    fw = (", ".join(fw_names)) if fw_names else "aucun framework détecté"
    purpose = (
        f"Système legacy `{project}` écrit principalement en **{primary}** "
        f"({fw}), composé de **{len(units)} unité(s)** fonctionnelle(s) et "
        f"**{len(entities)} entité(s)** de données."
    )
    conf = _bump(rollup, "medium")  # inferred from metadata
    lines.append("## Objectif (inféré)\n")
    lines.append(f"{purpose}\n")
    lines.append(f"<!-- confidence: {conf} ; evidence: .sys/inventory.json -->\n")

    # --- Entités centrales (rankées par in-degree FK) ---
    in_degree: dict[str, int] = {}
    for rel in relations:
        to = (rel.get("to") or {}).get("entity")
        if to:
            in_degree[to] = in_degree.get(to, 0) + 1
    # Fallback ranking by field count when no relations.
    def _rank_key(ent: dict[str, Any]) -> tuple[int, int]:
        nm = ent.get("name") or ent.get("table") or ""
        return (in_degree.get(nm, 0), len(ent.get("fields") or []))

    ranked = sorted(entities, key=_rank_key, reverse=True)
    lines.append("\n## Entités centrales\n")
    if ranked:
        lines.append("| Entité | Réf. entrantes (FK) | Champs | Confiance | Evidence |")
        lines.append("|---|---|---|---|---|")
        for ent in ranked[:10]:
            nm = ent.get("name") or ent.get("table") or "Entity"
            deg = in_degree.get(nm, 0)
            nf = len(ent.get("fields") or [])
            c = _bump(rollup, "medium" if ent.get("deduced") else "high")
            ev = ", ".join(_as_evidence_list(ent.get("evidence"))) or ".sys/db-schema.merged.json"
            lines.append(f"| {nm} | {deg} | {nf} | {c} | {ev} |")
    else:
        lines.append("> **GAP** — aucune entité dans le schéma de données.\n")
        _bump(rollup, "low")

    # --- Contraintes & décisions structurantes observées (faits, pas git) ---
    lines.append("\n## Contraintes & décisions structurantes observées\n")
    eol = [d for d in external if d.get("eol")]
    any_constraint = False
    if fw_names:
        any_constraint = True
        c = _bump(rollup, "high")
        lines.append(f"- Adhérence au(x) framework(s) : **{fw}**. "
                     f"<!-- confidence: {c} ; evidence: .sys/inventory.json -->")
    if eol:
        any_constraint = True
        c = _bump(rollup, "high")
        names = ", ".join(f"{d.get('name')} {d.get('version', '')}".strip() for d in eol[:10])
        lines.append(f"- Dépendances en fin de vie (EOL) à traiter : **{names}**. "
                     f"<!-- confidence: {c} ; evidence: .sys/deps-graph.json -->")
    if cycles:
        any_constraint = True
        c = _bump(rollup, "medium")
        lines.append(f"- **{len(cycles)} cycle(s)** de dépendances internes "
                     f"(dette structurelle). <!-- confidence: {c} ; "
                     f"evidence: .sys/deps-graph.json -->")
    if not any_constraint:
        c = _bump(rollup, "low")
        lines.append(f"- Aucune contrainte structurante déterministe détectée "
                     f"(graphe de dépendances absent ou vide). "
                     f"<!-- confidence: {c} -->")

    # --- Lacunes (pour validation humaine) ---
    lines.append("\n## Lacunes (validation humaine)\n")
    lines.append("- Les **décisions fondatrices historiques** (le *pourquoi*) ne sont "
                 "pas extraites ici : elles nécessiteraient un minage du `git log` "
                 "(hors périmètre du cœur déterministe).")
    lines.append("- L'objectif ci-dessus est **inféré** des métadonnées : à confirmer "
                 "par un humain ou par l'agent narratif optionnel `reverse-soul`.")

    return "\n".join(lines) + "\n", rollup
