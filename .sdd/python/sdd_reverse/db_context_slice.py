"""db_context_slice.py — context slicing for the db-reverse agents.

No agent reads the whole database context. This module renders the SSoT
(`db-context.json`) into a navigable tree of small Markdown files, and assembles,
for each SQL object, a **context pack**: its own body reference, the structure of
the tables it actually touches, the summaries of what it calls, who calls it, and
the glossary terms of its subdomain — and nothing else.

    db-context/
        _overview.md                  whole-database orientation
        tables/{schema}.{table}.md    one card per table
        procedures/…  functions/…  views/…  triggers/…  packages/…
        packs/{schema}.{object}.md    the slice handed to the analysing agent

The pack is what makes nested stored procedures analysable. The isolation rule
that forbids an analyst from reading outside its own module is not relaxed — it
is redirected: the agent still reads exactly one thing, and that one thing now
carries the transitive context, computed rather than left to its judgement.

Every pack is budget-bounded and **declares what was trimmed**, so an agent that
received a truncated view can lower its confidence knowingly instead of guessing
confidently.

What a pack gives up when it overflows is itself a design decision (audit
2026-08-28). Relational structure is the LAST thing to go, and it goes by
degrees, never as a block:

    callers → hypotheses → callees
        → tables at `no-index` (indexes + column defaults dropped)
        → tables at `keys-only` (columns / PK / FK / CHECK — the load-bearing set)
        → tables removed one at a time, read-only ones before written ones

The reasoning: an unread callee still leaves a name, a routine type and a CRUD
matrix, so the analyst can work around it and lower its confidence knowingly. An
unknown column, foreign key or CHECK leaves nothing to work with — it makes the
Acceptance Criteria factually wrong. The pre-2026-08-28 order dropped table
structure BEFORE callee summaries, i.e. exactly on the fat procedures that need
it most.

Deterministic (0 token), offline, read-only on its inputs.

Public API:
    render_overview(context)                        -> str
    render_table_card(context, qualified, detail=…) -> str
    render_object_card(context, fq)                 -> str
    build_pack(context, fq, depth=2, budget=…,
               project_root=…)                      -> (str, dict)
    write_context_tree(root, context, …)            -> dict
    pack_relpath(fq)                                -> str
    TABLE_DETAIL_LADDER                             -> tuple[str, ...]
    CYCLE_BODY_LADDER                               -> tuple[int | None, ...]
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

# Échelle de dégradation des corps de co-membres d'un cycle (D-M3, 2026-08-30).
# Un cycle « doit être analysé d'un bloc » : le pack de chaque membre embarque
# donc les corps des autres membres. Quand le budget mord, ces corps sont les
# PREMIERS à rétrécir — par paliers d'octets par corps, puis noms seuls (None =
# corps complet, 0 = noms seuls). Chaque palier est déclaré dans `trimmed`.
CYCLE_BODY_LADDER: tuple[int | None, ...] = (None, 4_000, 1_200, 0)

_FAMILIES = {
    "procedures": ("PROCEDURE",),
    "functions": ("FUNCTION",),
    "views": ("VIEW",),
    "triggers": ("TRIGGER",),
    # Packages Oracle (spec + body). Famille explicite depuis 2026-08-30 :
    # avant, `PACKAGE` retombait sur le défaut "procedures" par accident, et le
    # proc-analyst pouvait le refuser via sa garde de type. La famille est
    # possédée par `reverse-sql-analyst` (1 package = 1 US), qui accepte
    # explicitement ces objets.
    "packages": ("PACKAGE",),
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


def pack_relpath(fq: str) -> str:
    """Chemin (relatif au projet) du pack d'un objet — même règle de nommage
    que `write_context_tree`. C'est ce que `needs_llm.pack` doit porter : le
    fqName brut d'un objet aux caractères exotiques ne correspond à aucun
    fichier sur disque (audit 2026-08-29, mineur 2)."""
    return f".sys/db-context/packs/{_safe(fq)}.md"


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


# Degradation ladder for a table card inside a pack. A pack that no longer
# fits its budget loses table DETAIL before it loses the table itself: an
# unread callee can be inferred from its name and CRUD matrix, an unknown
# column or foreign key makes the Acceptance Criteria plainly wrong.
#   full      everything
#   no-index  indexes and column defaults dropped
#   keys-only columns / primary key / foreign keys / CHECK — the load-bearing set
TABLE_DETAIL_LADDER = ("full", "no-index", "keys-only")

_TABLE_DETAIL_NOTE = {
    "no-index": "Fiche dégradée : index et valeurs par défaut retirés pour "
                "tenir le budget de contexte.",
    "keys-only": "Fiche dégradée : colonnes, clé primaire, clés étrangères et "
                 "contraintes CHECK uniquement.",
}


def render_table_card(
    context: dict[str, Any], qualified: str, *, detail: str = "full"
) -> str:
    """One table: columns, keys, constraints, and who touches it.

    `detail` walks `TABLE_DETAIL_LADDER`. Whatever the level, the columns, the
    primary key, the foreign keys and the CHECK constraints stay — they are the
    facts an Acceptance Criteria is written against.
    """
    table = _resolve_table(context, qualified)
    if table is None:
        return f"# Table `{qualified}`\n\n_Absente du catalogue lu._\n"

    if detail not in TABLE_DETAIL_LADDER:
        detail = "full"
    with_defaults = detail == "full"
    with_nullable = detail in ("full", "no-index")
    with_indexes = detail == "full"

    facts = context.get("facts", {})
    usage = facts.get("tableUsage", {}).get(table["qualifiedName"], {})
    rels = [r for r in facts.get("relations", [])
            if _norm(str(r.get("from", {}).get("entity"))) == _norm(table["qualifiedName"])
            or _norm(str(r.get("to", {}).get("entity"))) == _norm(table["qualifiedName"])]

    header = ["Colonne", "Type", "PK"]
    align = ["---", "---", ":-:"]
    if with_nullable:
        header.append("Null")
        align.append(":-:")
    if with_defaults:
        header.append("Défaut")
        align.append("---")

    lines = [f"# Table `{table['qualifiedName']}`", ""]
    if detail in _TABLE_DETAIL_NOTE:
        lines += [f"> {_TABLE_DETAIL_NOTE[detail]}", ""]
    lines += ["| " + " | ".join(header) + " |", "|" + "|".join(align) + "|"]

    for c in table["columns"]:
        cells = [f"`{c['name']}`", f"`{c['type']}`", "✓" if c["primaryKey"] else ""]
        if with_nullable:
            cells.append("✓" if c["nullable"] else "")
        if with_defaults:
            cells.append(("`" + str(c["default"]) + "`") if c["default"] else "")
        lines.append("| " + " | ".join(cells) + " |")
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

    if with_indexes and table["indexes"]:
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


def _table_section(
    context: dict[str, Any], touched: list[str], detail: str
) -> list[str]:
    """The `## Structure des tables touchées` block, at one detail level."""
    lines = ["## Structure des tables touchées", ""]
    for raw in touched:
        table = _resolve_table(context, raw)
        if table is None:
            lines.append(f"### `{raw}`\n\n_Absente du catalogue lu._\n")
            continue
        card = render_table_card(context, table["qualifiedName"], detail=detail)
        body = card.split("\n", 1)[1] if "\n" in card else ""
        # Drop the "objects that touch it" section: in a pack it is noise.
        body = body.split("## Objets qui la touchent")[0]
        lines.append(f"### `{table['qualifiedName']}`")
        lines.append(body.rstrip())
        lines.append("")
    return lines


def _cycle_section(
    fq: str,
    scc: dict[str, Any],
    co_bodies: list[tuple[str, str]],
    body_cap: int | None,
) -> list[str]:
    """Le bloc `## Cycle à analyser d'un bloc`, à un palier de dégradation donné.

    `co_bodies` = [(fqName, corps)] des AUTRES membres du cycle. `body_cap`
    marche `CYCLE_BODY_LADDER` : None = corps complets, N = tronqués à N
    octets (troncature déclarée dans le bloc), 0 = noms seuls (comportement
    d'avant 2026-08-30, désormais réservé au dernier palier).
    """
    lines = [
        "## Cycle à analyser d'un bloc",
        "",
        f"Composante `{scc['id']}` — ces objets s'appellent mutuellement et "
        "ne peuvent pas être compris séparément :",
        "",
        *[f"- `{m}`" for m in scc["members"]],
        "",
    ]
    if body_cap == 0 and co_bodies:
        lines += [
            "> ⚠️ Corps des co-membres retirés pour tenir le budget de contexte "
            "— lire les snapshots `.sys/proc-snapshot/` si nécessaire, et "
            "plafonner la confidence à `medium`.",
            "",
        ]
        return lines
    for member_fq, body in co_bodies:
        lines += [f"### Corps de `{member_fq}` (co-membre du cycle)", ""]
        shown = body
        if body_cap is not None and len(body) > body_cap:
            shown = body[:body_cap]
            lines += [
                f"> ⚠️ Corps tronqué à {body_cap} caractère(s) sur {len(body)} "
                "pour tenir le budget de contexte — la fin n'a PAS été lue.",
                "",
            ]
        lines += ["```sql", shown.rstrip("\n"), "```", ""]
    return lines


def build_pack(
    context: dict[str, Any],
    fq: str,
    *,
    depth: int = DEFAULT_DEPTH,
    budget: int = DEFAULT_PACK_BUDGET,
    project_root: str | Path | None = None,
) -> tuple[str, dict[str, Any]]:
    """Assemble the context slice handed to the agent analysing `fq`.

    Returns `(markdown, report)`. `report.trimmed` names every section dropped to
    fit the budget — a pack never shrinks silently, because a silently shrunk
    pack produces a confidently wrong User Story.

    `project_root` (D-M3, 2026-08-30) : racine du projet reverse
    (`workspace/old/{DB}`). Quand elle est fournie et que l'objet appartient à
    une composante récursive, les CORPS des autres membres du cycle (snapshots
    `.sys/proc-snapshot/`) sont embarqués dans le pack — c'est ce qui rend la
    promesse « tous les corps du cycle dans son pack » vraie. Sans elle
    (rétro-compat), seuls les noms des membres sont listés.
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

    # D-M3 — corps des co-membres du cycle, lus depuis les snapshots.
    co_bodies: list[tuple[str, str]] = []
    cycle_cap_step = 0  # index dans CYCLE_BODY_LADDER
    if scc and scc.get("recursive") and len(scc["members"]) > 1:
        if project_root is not None:
            for member in scc["members"]:
                if _norm(str(member)) == _norm(obj["fqName"]):
                    continue
                m_obj = objects.get(_norm(str(member))) or {}
                rel = m_obj.get("snapshotFile") or ""
                if not rel:
                    continue
                try:
                    body_txt = (Path(project_root) / rel).read_text(
                        encoding="utf-8", errors="replace")
                except OSError:
                    continue
                co_bodies.append((str(member), body_txt))
        sections.append(("cycle", _cycle_section(
            obj["fqName"], scc, co_bodies, CYCLE_BODY_LADDER[cycle_cap_step])))

    touched = sorted({*(obj.get("tablesRead") or []), *(obj.get("tablesWritten") or [])})
    if touched:
        sections.append(("tables", _table_section(context, touched, "full")))

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

    # Assemble, then reduce in a declared order until the budget is met.
    #
    # `tables` now comes LAST, after `callees` — and it degrades by steps before
    # it is dropped at all. Rationale (audit 2026-08-28): an unread callee still
    # leaves a name, a routine type and a CRUD matrix in the pack, so the analyst
    # can reason around it and lower its confidence knowingly. An unknown column,
    # foreign key or CHECK leaves nothing to reason with — it makes the
    # Acceptance Criteria factually wrong. The previous order removed the
    # structure of a fat procedure's tables first, i.e. exactly on the objects
    # that need it most.
    trim_order = ["callers", "hypotheses", "callees"]
    trimmed: list[str] = []
    table_detail = "full"
    kept_tables = list(touched)

    # Once the detail ladder is exhausted, tables go one at a time rather than
    # all at once — dropping the whole block to save the last hundred bytes
    # would repeat, in miniature, the very pathology this ordering fixes.
    # Read-only tables go first: the tables the object WRITES are where its
    # Acceptance Criteria live.
    _written = {_norm(t) for t in (obj.get("tablesWritten") or [])}
    drop_order = ([t for t in reversed(touched) if _norm(t) not in _written]
                  + [t for t in reversed(touched) if _norm(t) in _written])

    def _assemble() -> str:
        return "\n".join(head + [l for _, block in sections for l in block])

    def _index_of(key: str) -> int | None:
        return next((i for i, (k, _) in enumerate(sections) if k == key), None)

    while sections:
        body = _assemble()
        if len(body) <= budget:
            break

        # Les corps des co-membres d'un cycle rétrécissent EN PREMIER (D-M3) :
        # ils sont volumineux par nature et l'analyste garde, même dégradés,
        # les noms + la consigne d'analyser le cycle d'un bloc.
        ci = _index_of("cycle")
        if (ci is not None and co_bodies
                and cycle_cap_step < len(CYCLE_BODY_LADDER) - 1):
            cycle_cap_step += 1
            cap = CYCLE_BODY_LADDER[cycle_cap_step]
            sections[ci] = ("cycle", _cycle_section(
                obj["fqName"], scc, co_bodies, cap))
            trimmed.append("cycle:names-only" if cap == 0
                           else f"cycle:bodies-{cap}")
            continue

        idx = next((i for i in (_index_of(k) for k in trim_order) if i is not None), None)
        if idx is not None:
            trimmed.append(sections[idx][0])
            sections.pop(idx)
            continue

        ti = _index_of("tables")
        if ti is None:
            break

        step = TABLE_DETAIL_LADDER.index(table_detail) + 1
        if step < len(TABLE_DETAIL_LADDER):
            table_detail = TABLE_DETAIL_LADDER[step]
            sections[ti] = ("tables", _table_section(context, kept_tables, table_detail))
            trimmed.append(f"tables:{table_detail}")
            continue

        victim = next((t for t in drop_order if t in kept_tables), None)
        if victim is None:
            trimmed.append("tables")
            sections.pop(ti)
            continue
        kept_tables.remove(victim)
        trimmed.append(f"tables:-{victim}")
        if kept_tables:
            sections[ti] = ("tables", _table_section(context, kept_tables, table_detail))
        else:
            sections.pop(ti)

    body = _assemble()

    if trimmed:
        removed = [t for t in trimmed
                   if not t.startswith("tables:") and not t.startswith("cycle:")]
        cycle_steps = [t.split(":", 1)[1] for t in trimmed if t.startswith("cycle:")]
        degraded = [t.split(":", 1)[1] for t in trimmed
                    if t.startswith("tables:") and not t.startswith("tables:-")]
        dropped_tables = [t.split(":-", 1)[1] for t in trimmed if t.startswith("tables:-")]
        notice = ["\n\n---\n\n> ⚠️ **Pack tronqué** pour tenir le budget de contexte."]
        if cycle_steps:
            notice.append(
                " Corps des co-membres du cycle dégradés jusqu'à "
                f"`{cycle_steps[-1]}`.")
        if removed:
            notice.append(
                " Sections retirées : " + ", ".join(f"`{t}`" for t in removed) + ".")
        if degraded:
            notice.append(
                " Fiches de tables dégradées jusqu'à "
                f"`{degraded[-1]}` (colonnes, clé primaire, clés étrangères et "
                "CHECK conservés).")
        if dropped_tables:
            notice.append(
                " Tables retirées faute de place : "
                + ", ".join(f"`{t}`" for t in dropped_tables)
                + " — leur structure n'a PAS été lue.")
        notice.append(" Baisser la confidence en conséquence.\n")
        body += "".join(notice)

    return body, {
        "object": obj["fqName"],
        "found": True,
        "bytes": len(body),
        "depth": depth,
        "trimmed": trimmed,
        "tableDetail": table_detail,
        "cycleBodies": len(co_bodies),
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

    # Import here (not at module level) to preserve D4 isolation: this module is
    # imported by tests that do NOT have the full sdd_reverse package in sys.path,
    # and tier routing is only needed for the pack-skip optimisation.
    try:
        from sdd_reverse.db_tier_router import tier_for as _tier_for
        _has_router = True
    except ImportError:
        _has_router = False

    pack_reports: list[dict[str, Any]] = []
    for obj in facts.get("objects", []):
        fq = str(obj["fqName"])
        atomic_write_text(
            root / family_of(str(obj.get("routineType"))) / f"{_safe(fq)}.md",
            render_object_card(context, fq))
        written["objects"] += 1
        if with_packs:
            # 🟡 Efficiency: tier=none objects are handled by the deterministic
            # template path (build_proc_us.py) and their pack is never consumed by
            # any LLM agent. Generating it wastes I/O and context budget.
            obj_tier = "none"
            if _has_router:
                try:
                    obj_tier, _ = _tier_for(obj)
                except Exception:
                    obj_tier = "fast"  # fail-safe: when in doubt, generate the pack
            if obj_tier == "none":
                written["packs"] += 0  # counted but not written
                continue
            body, report = build_pack(context, fq, depth=depth, budget=budget,
                                      project_root=project_root)
            atomic_write_text(root / "packs" / f"{_safe(fq)}.md", body)
            pack_reports.append(report)
            written["packs"] += 1

    return {
        "root": str(root),
        "written": written,
        "packs": pack_reports,
        "trimmedPacks": [p["object"] for p in pack_reports if p.get("trimmed")],
    }
