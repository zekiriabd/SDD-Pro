"""db_context_slice.py — context slicing for the db-reverse agents.

No agent reads the whole database context. This module renders the SSoT
(`db-context.json`) into a navigable tree of small Markdown files, and assembles,
for each SQL object, a **context pack**: its own body reference, the structure of
the tables it actually touches, the summaries of what it calls, who calls it, and
the glossary terms of its subdomain — and nothing else.

    db-context/
        _overview.md                  whole-database orientation
        tables/{schema}.{table}.md    one card per table
        procedures/…  functions/…  views/…  triggers/…
        packs/{schema}.{object}.md    the slice handed to the analysing agent

The pack is what makes nested stored procedures analysable. The isolation rule
that forbids an analyst from reading outside its own module is not relaxed — it
is redirected: the agent still reads exactly one thing, and that one thing now
carries the transitive context, computed rather than left to its judgement.

Every pack is budget-bounded and **declares what was trimmed**, so an agent that
received a truncated view can lower its confidence knowingly instead of guessing
confidently.

Deterministic (0 token), offline, read-only on its inputs.

Public API:
    render_overview(context)                  -> str
    render_table_card(context, qualified)     -> str
    render_object_card(context, fq)           -> str
    build_pack(context, fq, depth=2, budget=…) -> (str, dict)
    write_context_tree(root, context, …)      -> dict
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sdd_reverse.atomic_write_local import atomic_write_text

SCHEMA_VERSION = 1

# A pack beyond this size stops being a slice and becomes a dump. Overridable
# per run (`ContextPackBudget`) — the value is a policy, not a law of nature.
DEFAULT_PACK_BUDGET = 14_000
DEFAULT_DEPTH = 2

_FAMILIES = {
    "procedures": ("PROCEDURE",),
    "functions": ("FUNCTION",),
    "views": ("VIEW",),
    "triggers": ("TRIGGER",),
}


def _norm(ident: str) -> str:
    if not ident:
        return ""
    return ident.strip().strip("[]`\"").strip().lower()


def family_of(routine_type: str) -> str:
    """Map a catalog routine type onto the tree folder that owns it."""
    rt = (routine_type or "").upper()
    for family, markers in _FAMILIES.items():
        if any(m in rt for m in markers):
            return family
    return "procedures"


def _safe(fq: str) -> str:
    """Filename for an object, keeping schema qualification readable."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in (fq or "unknown"))


def _index(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_norm(str(o.get("fqName"))): o for o in context.get("facts", {}).get("objects", [])}


def _tables_index(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_norm(str(t["qualifiedName"])): t
            for t in context.get("facts", {}).get("tables", [])}


def _resolve_table(context: dict[str, Any], raw: str) -> dict[str, Any] | None:
    tables = _tables_index(context)
    hit = tables.get(_norm(raw))
    if hit:
        return hit
    tail = _norm(raw).rsplit(".", 1)[-1]
    cands = [t for k, t in tables.items() if k.rsplit(".", 1)[-1] == tail]
    return cands[0] if len(cands) == 1 else None


# --------------------------------------------------------------------------- #
# Cards
# --------------------------------------------------------------------------- #

def render_overview(context: dict[str, Any]) -> str:
    """Whole-database orientation — the file an agent reads to situate itself."""
    facts = context.get("facts", {})
    db = facts.get("database", {})
    s = facts.get("summary", {})
    plan = context.get("executionPlan", {})
    hyp = context.get("hypotheses", {})

    lines = [
        f"# Contexte base de données — {db.get('name') or 'inconnue'}",
        "",
        f"> Moteur `{db.get('type')}` · dialecte `{db.get('language')}` · "
        f"contexte `{context.get('contextVersion', '')[:19]}…`",
        "> Structure uniquement — aucune donnée métier n'est lue ni stockée ici.",
        "",
        "## Volumétrie",
        "",
        f"- {s.get('tables', 0)} table(s), {s.get('columns', 0)} colonne(s), "
        f"{s.get('relations', 0)} clé(s) étrangère(s)",
        f"- {s.get('objects', 0)} objet(s) exécutable(s) "
        f"({s.get('encrypted', 0)} chiffré(s), {s.get('dynamicSql', 0)} avec SQL dynamique)",
        f"- Structure lue en mode `{s.get('schemaCompleteness')}`",
        "",
        "## Plan d'exécution (vagues de dépendance)",
        "",
        f"- {plan.get('stats', {}).get('waveCount', 0)} vague(s), "
        f"la plus large contient {plan.get('stats', {}).get('widestWave', 0)} objet(s)",
        f"- {plan.get('stats', {}).get('resolvedCalls', 0)} appel(s) résolu(s), "
        f"{plan.get('stats', {}).get('unresolvedCalls', 0)} non résolu(s)",
        f"- {plan.get('stats', {}).get('recursiveComponents', 0)} composante(s) récursive(s)",
        "",
    ]

    metrics = facts.get("tableMetrics", {})
    if metrics:
        top = sorted(metrics.items(), key=lambda kv: -kv[1]["objects"])[:15]
        lines += [
            "## Tables les plus sollicitées",
            "",
            "| Table | Objets | Lecteurs | Écrivains |",
            "|---|--:|--:|--:|",
        ]
        lines += [
            f"| `{name}` | {m['objects']} | {m['readers']} | {m['writers']} |"
            for name, m in top
        ]
        lines.append("")

    unresolved = plan.get("unresolvedCallees") or {}
    if unresolved:
        lines += [
            "## Appels non résolus (zones aveugles)",
            "",
            "> Ces appels pointent hors du catalogue lu (serveur lié, autre base, "
            "objet supprimé) ou sont ambigus. Tout objet listé ici voit sa "
            "confidence dégradée.",
            "",
        ]
        for caller, callees in list(unresolved.items())[:30]:
            lines.append(f"- `{caller}` → {', '.join(f'`{c}`' for c in callees)}")
        lines.append("")

    glossary = hyp.get("glossary") or []
    if glossary:
        lines += ["## Glossaire métier <!-- kind: hypothesis -->", ""]
        for g in glossary[:60]:
            term = g.get("term") if isinstance(g, dict) else str(g)
            meaning = g.get("meaning", "") if isinstance(g, dict) else ""
            lines.append(f"- **{term}** — {meaning}")
        lines.append("")
    else:
        lines += [
            "## Glossaire métier",
            "",
            "_Non renseigné : l'agent architecte (Phase 0.B) n'a pas encore tourné._",
            "",
        ]

    return "\n".join(lines)


def render_table_card(context: dict[str, Any], qualified: str) -> str:
    """One table: columns, keys, constraints, and who touches it."""
    table = _resolve_table(context, qualified)
    if table is None:
        return f"# Table `{qualified}`\n\n_Absente du catalogue lu._\n"

    facts = context.get("facts", {})
    usage = facts.get("tableUsage", {}).get(table["qualifiedName"], {})
    rels = [r for r in facts.get("relations", [])
            if _norm(str(r.get("from", {}).get("entity"))) == _norm(table["qualifiedName"])
            or _norm(str(r.get("to", {}).get("entity"))) == _norm(table["qualifiedName"])]

    lines = [
        f"# Table `{table['qualifiedName']}`",
        "",
        "| Colonne | Type | PK | Null | Défaut |",
        "|---|---|:-:|:-:|---|",
    ]
    for c in table["columns"]:
        lines.append(
            f"| `{c['name']}` | `{c['type']}` | {'✓' if c['primaryKey'] else ''} | "
            f"{'✓' if c['nullable'] else ''} | "
            f"{('`' + str(c['default']) + '`') if c['default'] else ''} |"
        )
    lines.append("")

    if table["checks"]:
        lines += ["## Contraintes CHECK", "",
                  "> Règles de gestion portées par la base, souvent invisibles "
                  "aux applications.", ""]
        lines += [f"- `{c['name']}` — `{c['definition']}`" for c in table["checks"]]
        lines.append("")

    if rels:
        lines += ["## Relations", ""]
        for r in rels:
            f_, t_ = r.get("from", {}), r.get("to", {})
            lines.append(
                f"- `{f_.get('entity')}.{f_.get('field')}` → "
                f"`{t_.get('entity')}.{t_.get('field')}` (`{r.get('name')}`)")
        lines.append("")

    if table["indexes"]:
        lines += ["## Index", ""]
        for i in table["indexes"]:
            flags = " ".join(f for f, on in (("unique", i["unique"]), ("pk", i["primary"])) if on)
            lines.append(f"- `{i['name']}` ({', '.join(i['columns'])}) {flags}".rstrip())
        lines.append("")

    if usage:
        lines += ["## Objets qui la touchent", "", "| Objet | CRUD |", "|---|---|"]
        lines += [f"| `{fq}` | `{letters}` |" for fq, letters in sorted(usage.items())]
        lines.append("")

    return "\n".join(lines)


def render_object_card(context: dict[str, Any], fq: str) -> str:
    """One SQL object: contract, data effects, calls — facts only."""
    obj = _index(context).get(_norm(fq))
    if obj is None:
        return f"# `{fq}`\n\n_Absent de l'introspection._\n"

    plan_metrics = context.get("executionPlan", {}).get("metrics", {}).get(obj["fqName"], {})
    crud = context.get("facts", {}).get("crud", {}).get(obj["fqName"], {})

    lines = [
        f"# `{obj['fqName']}`",
        "",
        f"> `{obj.get('routineType')}` · {obj.get('lineCount', 0)} ligne(s) · "
        f"vague {plan_metrics.get('wave', '?')} · "
        f"appelé par {plan_metrics.get('fanIn', 0)} objet(s)",
        f"> Evidence : `{obj.get('evidence') or 'inconnue'}`",
        "",
    ]
    if obj.get("encrypted"):
        lines += ["> ⚠️ Objet chiffré : le corps est illisible. "
                  "Ne rien inventer — confidence plafonnée à `low`.", ""]

    if obj.get("params"):
        lines += ["## Contrat", ""]
        lines += [f"- `{p}`" for p in obj["params"]]
        lines.append("")

    if crud:
        lines += ["## Effets données (CRUD déterministe)", "",
                  "| Table | CRUD |", "|---|---|"]
        lines += [f"| `{t}` | `{v}` |" for t, v in sorted(crud.items())]
        lines.append("")

    signals = []
    if obj.get("hasTransaction"):
        signals.append("transaction explicite")
    if obj.get("hasTryCatch"):
        signals.append("TRY/CATCH")
    if obj.get("dynamicSql"):
        signals.append("**SQL dynamique** (comportement non lisible statiquement)")
    if obj.get("cursors"):
        signals.append(f"{obj['cursors']} curseur(s)")
    if obj.get("branches"):
        signals.append(f"{obj['branches']} branche(s)")
    if obj.get("raises"):
        signals.append("erreurs levées : " + ", ".join(f"`{r}`" for r in obj["raises"]))
    if signals:
        lines += ["## Signaux", ""] + [f"- {s}" for s in signals] + [""]

    if obj.get("callsProcs"):
        lines += ["## Appelle", ""]
        unresolved = set(plan_metrics.get("unresolvedCallees") or [])
        for c in obj["callsProcs"]:
            mark = " — ⚠️ non résolu" if c in unresolved else ""
            lines.append(f"- `{c}`{mark}")
        lines.append("")

    if plan_metrics.get("recursive"):
        lines += ["## Récursivité", "",
                  f"Membre de la composante `{plan_metrics.get('sccId')}` — "
                  "le cycle doit être analysé d'un bloc.", ""]

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Packs
# --------------------------------------------------------------------------- #

def _callee_block(context: dict[str, Any], fq: str, depth: int) -> list[str]:
    """Callees up to `depth`, with their already-written summary when available."""
    objects = _index(context)
    findings = context.get("findings", {})
    plan = context.get("executionPlan", {})
    edges = plan.get("edges", [])
    out_by: dict[str, list[str]] = {}
    for e in edges:
        out_by.setdefault(_norm(str(e["from"])), []).append(str(e["to"]))

    lines: list[str] = []
    seen: set[str] = {_norm(fq)}
    frontier = [fq]
    for level in range(1, depth + 1):
        nxt: list[str] = []
        for caller in frontier:
            for callee in out_by.get(_norm(caller), []):
                if _norm(callee) in seen:
                    continue
                seen.add(_norm(callee))
                nxt.append(callee)
        if not nxt:
            break
        lines.append(f"### Profondeur {level}")
        lines.append("")
        for callee in sorted(nxt):
            found = findings.get(callee)
            obj = objects.get(_norm(callee), {})
            if found and found.get("summary"):
                lines.append(
                    f"- `{callee}` — {found['summary']} "
                    f"<!-- confidence: {found.get('confidence', 'medium')} -->")
                for rule in (found.get("businessRules") or [])[:4]:
                    lines.append(f"    - {rule}")
            else:
                crud = context.get("facts", {}).get("crud", {}).get(callee, {})
                effect = ", ".join(f"`{t}`={v}" for t, v in sorted(crud.items())[:4])
                lines.append(
                    f"- `{callee}` — _pas encore analysé_ · "
                    f"{obj.get('routineType', 'objet')} · {effect or 'aucun effet détecté'}")
        lines.append("")
        frontier = nxt
    return lines


def build_pack(
    context: dict[str, Any],
    fq: str,
    *,
    depth: int = DEFAULT_DEPTH,
    budget: int = DEFAULT_PACK_BUDGET,
) -> tuple[str, dict[str, Any]]:
    """Assemble the context slice handed to the agent analysing `fq`.

    Returns `(markdown, report)`. `report.trimmed` names every section dropped to
    fit the budget — a pack never shrinks silently, because a silently shrunk
    pack produces a confidently wrong User Story.
    """
    objects = _index(context)
    obj = objects.get(_norm(fq))
    if obj is None:
        return (f"# Pack `{fq}`\n\n_Objet absent de l'introspection._\n",
                {"object": fq, "found": False, "trimmed": ["all"]})

    plan_metrics = context.get("executionPlan", {}).get("metrics", {}).get(obj["fqName"], {})
    scc = next((c for c in context.get("executionPlan", {}).get("components", [])
                if c["id"] == plan_metrics.get("sccId")), None)

    head = [
        f"# Contexte d'analyse — `{obj['fqName']}`",
        "",
        f"> Slice déterministe du contexte base de données "
        f"(`{context.get('contextVersion', '')[:19]}…`).",
        "> Tout ce qui suit est un **fait** vérifiable dans le catalogue ou dans "
        "un snapshot de corps, sauf les blocs explicitement marqués "
        "`kind: hypothesis`.",
        "",
        "---",
        "",
        render_object_card(context, obj["fqName"]).split("\n", 1)[1].lstrip("\n"),
    ]

    sections: list[tuple[str, list[str]]] = []

    if scc and scc.get("recursive") and len(scc["members"]) > 1:
        sections.append(("cycle", [
            "## Cycle à analyser d'un bloc",
            "",
            f"Composante `{scc['id']}` — ces objets s'appellent mutuellement et "
            "ne peuvent pas être compris séparément :",
            "",
            *[f"- `{m}`" for m in scc["members"]],
            "",
        ]))

    touched = sorted({*(obj.get("tablesRead") or []), *(obj.get("tablesWritten") or [])})
    table_lines: list[str] = []
    if touched:
        table_lines = ["## Structure des tables touchées", ""]
        for raw in touched:
            table = _resolve_table(context, raw)
            if table is None:
                table_lines.append(f"### `{raw}`\n\n_Absente du catalogue lu._\n")
                continue
            card = render_table_card(context, table["qualifiedName"])
            body = card.split("\n", 1)[1] if "\n" in card else ""
            # Drop the "objects that touch it" section: in a pack it is noise.
            body = body.split("## Objets qui la touchent")[0]
            table_lines.append(f"### `{table['qualifiedName']}`")
            table_lines.append(body.rstrip())
            table_lines.append("")
        sections.append(("tables", table_lines))

    callee_lines = _callee_block(context, obj["fqName"], depth)
    if callee_lines:
        sections.append(("callees", ["## Ce que cet objet appelle", "",
                                     "> Résumé déjà écrit par la vague précédente "
                                     "quand il existe ; sinon, effets déterministes.",
                                     "", *callee_lines]))

    plan = context.get("executionPlan", {})
    callers = sorted({str(e["from"]) for e in plan.get("edges", [])
                      if _norm(str(e["to"])) == _norm(obj["fqName"])})
    if callers:
        sections.append(("callers", ["## Ce qui appelle cet objet", "",
                                     *[f"- `{c}`" for c in callers], ""]))

    hyp = context.get("hypotheses", {})
    roles = {(_norm(str(r.get("object"))) if isinstance(r, dict) else ""): r
             for r in hyp.get("objectRoles") or []}
    role = roles.get(_norm(obj["fqName"]))
    open_q = [q for q in hyp.get("openQuestions") or []
              if isinstance(q, dict) and _norm(str(q.get("about", ""))) == _norm(obj["fqName"])]
    if role or open_q:
        hyp_lines = ["## Hypothèses de l'architecte <!-- kind: hypothesis -->", "",
                     "> Interprétations non prouvées par le code. Ne peuvent pas "
                     "devenir des Acceptance Criteria.", ""]
        if role:
            hyp_lines.append(f"- Rôle supposé : **{role.get('role')}** — {role.get('rationale', '')}")
        for q in open_q:
            hyp_lines.append(f"- Question ouverte : {q.get('question')}")
        hyp_lines.append("")
        sections.append(("hypotheses", hyp_lines))

    # Assemble, then trim in a declared order until the budget is met.
    trim_order = ["callers", "hypotheses", "tables", "callees"]
    trimmed: list[str] = []
    while True:
        body = "\n".join(head + [l for _, block in sections for l in block])
        if len(body) <= budget or not sections:
            break
        for candidate in trim_order:
            idx = next((i for i, (k, _) in enumerate(sections) if k == candidate), None)
            if idx is not None:
                trimmed.append(candidate)
                sections.pop(idx)
                break
        else:
            break

    if trimmed:
        body += (
            "\n\n---\n\n> ⚠️ **Pack tronqué** pour tenir le budget de contexte. "
            f"Sections retirées : {', '.join(f'`{t}`' for t in trimmed)}. "
            "Baisser la confidence en conséquence.\n")

    return body, {
        "object": obj["fqName"],
        "found": True,
        "bytes": len(body),
        "depth": depth,
        "trimmed": trimmed,
        "wave": plan_metrics.get("wave"),
    }


# --------------------------------------------------------------------------- #
# Tree writing
# --------------------------------------------------------------------------- #

def write_context_tree(
    project_root: str | Path,
    context: dict[str, Any],
    *,
    depth: int = DEFAULT_DEPTH,
    budget: int = DEFAULT_PACK_BUDGET,
    with_packs: bool = True,
) -> dict[str, Any]:
    """Render the whole `db-context/` tree under `{project_root}/.sys/`."""
    root = Path(project_root).resolve() / ".sys" / "db-context"
    facts = context.get("facts", {})

    atomic_write_text(root / "_overview.md", render_overview(context))
    written = {"overview": 1, "tables": 0, "objects": 0, "packs": 0}

    for table in facts.get("tables", []):
        atomic_write_text(
            root / "tables" / f"{_safe(table['qualifiedName'])}.md",
            render_table_card(context, table["qualifiedName"]))
        written["tables"] += 1

    pack_reports: list[dict[str, Any]] = []
    for obj in facts.get("objects", []):
        fq = str(obj["fqName"])
        atomic_write_text(
            root / family_of(str(obj.get("routineType"))) / f"{_safe(fq)}.md",
            render_object_card(context, fq))
        written["objects"] += 1
        if with_packs:
            body, report = build_pack(context, fq, depth=depth, budget=budget)
            atomic_write_text(root / "packs" / f"{_safe(fq)}.md", body)
            pack_reports.append(report)
            written["packs"] += 1

    return {
        "root": str(root),
        "written": written,
        "packs": pack_reports,
        "trimmedPacks": [p["object"] for p in pack_reports if p.get("trimmed")],
    }
