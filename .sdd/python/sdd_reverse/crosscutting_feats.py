"""crosscutting_feats.py — Deterministic cross-cutting reverse FEATs (L3).

Two transversal FEATs the Tech Lead explicitly needs for a faithful migration,
generated 100% deterministically from the L1 artefacts (no LLM, 0 token):

    1. "Librairies à installer" — from dependencies.json: every NuGet/npm/…
       package + assembly reference the legacy used, so the target stack can be
       provisioned with equivalents.
    2. "Base de données" — from db-schema(.merged).json + data-access.json +
       config.json: entities, stored procedures (name + typed params), and
       connection strings (provider/server/db, secrets masked).

Both are emitted as standard reverse FEATs (frontmatter + REVERSE-GATE + the six
ordered sections + per-item evidence/confidence + Given/When/Then ACs) so they
pass `validate_reverse_feat.py` and are first-class inputs to `/sdd-full`.

Stable-ID bullet format (audit F-04, 2026-08-25) — every SFD/FD/BR/AC item MUST
be written as::

    - SFD-1: texte

This is the convention of `templates/feat.template.md` and of the LLM composer
`reverse-feat-composer`, and the one `sdd_scripts/validate_readiness.py` counts
(`- SFD-N:` at line start). This generator used to emit `**SFD-1** — texte`,
which the readiness gate scored as *zero* IDs: the reverse→forward handoff
(`/sdd-reverse-full` → `/sdd-full`) then ran every FD/SFD-keyed coverage check
against an empty set and passed trivially, so the advertised traceability was
structurally absent on the cross-cutting FEATs. Do not reintroduce bold IDs.

Public API:
    build_libraries_feat(dependencies, *, n, name, project, language) -> str
    build_database_feat(db_schema, data_access, config, *, n, name, project, language) -> str
"""

from __future__ import annotations

import time
from typing import Any

_MAX_ITEMS = 80  # cap per list to keep the FEAT reviewable; truncation is noted


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fileline(d: dict[str, Any]) -> str:
    """`{file: x, line: n}` → `x:n` (avoids nested-quote f-strings)."""
    return f"{d.get('file', 'unknown')}:{d.get('line', 1)}"


def _ev(evidence: str | None) -> str:
    """Normalise an evidence pointer to the `<!-- evidence: path:line -->` shape.

    The validator requires `path:NN` (no spaces). Append `:1` when a manifest
    evidence carries no line, and replace spaces defensively.
    """
    e = (evidence or "unknown:1").strip().replace(" ", "_")
    if ":" not in e.rsplit("/", 1)[-1]:
        e = e + ":1"
    return f"<!-- evidence: {e} --> <!-- confidence: high -->"


def _frontmatter(n: int, name: str, project: str, language: str, sources: list[str]) -> str:
    src = ", ".join(sorted(set(sources))[:10]) or "(.sys artefacts)"
    return (
        "---\n"
        "generated-by: sdd-reverse\n"
        f"legacy-sources: [{src}]\n"
        "confidence: high\n"
        f"extraction-date: {_now()}\n"
        f"language-detected: {language}\n"
        f"source-unit: XC-{name}\n"
        "---\n"
    )


def _gate() -> str:
    # Cross-cutting FEATs are deterministic (no hallucination risk) → high + allow.
    return "<!-- REVERSE-GATE: confidence=high ; allow-sdd-full=true ; reason=deterministic_crosscutting -->"


# --------------------------------------------------------------------------- #
# Libraries FEAT
# --------------------------------------------------------------------------- #

def build_libraries_feat(
    dependencies: dict[str, Any], *, n: int, name: str, project: str, language: str
) -> str:
    packages = dependencies.get("packages", [])
    asm_refs = dependencies.get("assemblyReferences", [])
    binaries = dependencies.get("binaries", [])
    sources = [p.get("evidence", "").split(":")[0] for p in packages if p.get("evidence")]

    lines: list[str] = []
    lines.append(_frontmatter(n, name, project, language, sources))
    lines.append(f"# FEAT {n} — Librairies à installer (migration legacy `{project}`)")
    lines.append("")
    lines.append(_gate())
    lines.append("")
    lines.append(
        "> ⚠️ FEAT transversale générée par reverse engineering (déterministe). "
        "Inventaire des dépendances du legacy à reproduire (équivalents) dans le "
        "stack cible. Revue Tech Lead : mapper chaque dépendance vers son "
        "équivalent cible dans `stack.md` avant `/sdd-full`."
    )
    lines.append("")

    lines.append("## Actors")
    lines.append("")
    lines.append("- **Équipe d'intégration / build** — provisionne le stack cible.")
    lines.append("")

    lines.append("## Functional Needs")
    lines.append("")
    lines.append(
        f"- SFD-1: Le stack cible doit fournir un équivalent fonctionnel de "
        f"chaque dépendance externe du legacy ({len(packages)} paquet(s), "
        f"{len(asm_refs)} référence(s) d'assembly, {len(binaries)} binaire(s) bin/). "
        + _ev(sources[0] if sources else None)
    )
    lines.append("")

    lines.append("## Functional Deliverables")
    lines.append("")
    fd = 1
    truncated = packages[:_MAX_ITEMS]
    for p in truncated:
        ver = p.get("version") or "version non figée"
        lines.append(
            f"- FD-{fd}: Dépendance `{p['name']}` ({ver}, {p['ecosystem']}, "
            f"source: {p.get('source', '?')}). {_ev(p.get('evidence'))}"
        )
        fd += 1
    for r in asm_refs[:_MAX_ITEMS]:
        hp = r.get("hintPath")
        loc = f"DLL locale `{hp}`" if hp else "GAC/SDK"
        lines.append(
            f"- FD-{fd}: Référence d'assembly `{r['name']}` ({loc}). "
            f"{_ev(r.get('evidence'))}"
        )
        fd += 1
    if len(packages) > _MAX_ITEMS:
        lines.append(
            f"> _… {len(packages) - _MAX_ITEMS} paquet(s) supplémentaire(s) — "
            f"voir `.sys/dependencies.json`._"
        )
    lines.append("")

    lines.append("## Business Rules")
    lines.append("")
    lines.append(
        f"- BR-1: Les versions exactes du legacy sont documentées comme point "
        f"de départ ; le stack cible peut imposer des versions LTS plus récentes "
        f"(cf. politique runtime SDD_Pro). {_ev(sources[0] if sources else None)}"
    )
    eol = [p for p in packages if p.get("name", "").lower() in ("log4net",)]
    if eol:
        lines.append(
            f"- BR-2: Dépendances potentiellement obsolètes à auditer (CVE/EOL) "
            f"avant reprise : {', '.join(p['name'] for p in eol)}. "
            + _ev(eol[0].get("evidence"))
        )
    lines.append("")

    lines.append("## Acceptance Criteria")
    lines.append("")
    lines.append(
        f"- AC-1: Given le stack cible provisionné, when le projet est buildé, "
        f"then chaque capacité couverte par les {len(packages)} dépendance(s) "
        f"legacy a un équivalent résolu (ou une décision de retrait tracée). "
        + _ev(sources[0] if sources else None)
    )
    lines.append("")

    lines.append("## Project Config")
    lines.append("")
    lines.append("<!-- à compléter par le Tech Lead : mapping legacy→cible -->")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Database FEAT
# --------------------------------------------------------------------------- #

def build_database_feat(
    db_schema: dict[str, Any],
    data_access: dict[str, Any],
    config: dict[str, Any],
    *,
    n: int,
    name: str,
    project: str,
    language: str,
) -> str:
    entities = db_schema.get("entities", [])
    relations = db_schema.get("relations", [])
    procs = data_access.get("storedProcedureDefs", [])
    conn = config.get("connectionStrings", [])
    db_type = db_schema.get("databaseType", "Unknown")

    # Audit C3 2026-06-10 : les procédures APPELÉES par le code dont le DDL
    # n'est pas dans les sources (cas EDI : 21 SP appelées, 1 définie) sont un
    # contrat d'interface DB de premier ordre — sans elles la migration casse
    # au premier batch. Idem pour les tables touchées par les requêtes inline
    # mais absentes du schéma extrait.
    defs_names = {p["name"].lower() for p in procs}
    called_only: dict[str, dict] = {}
    for c in data_access.get("storedProcedureCalls", []):
        nm = (c.get("name") or "").strip()
        if nm and nm.lower() not in defs_names and nm.lower() not in called_only:
            called_only[nm.lower()] = c
    called_procs = sorted(called_only.values(), key=lambda c: c["name"].lower())

    entity_names = {e["name"].lower() for e in entities}
    inline_tables: dict[str, dict] = {}
    for q in data_access.get("queries", []):
        for t in q.get("tables", []):
            if t.lower() not in entity_names and t.lower() not in inline_tables:
                inline_tables[t.lower()] = {"name": t, "file": q.get("file", "?"),
                                            "line": q.get("line", 1)}
    inline_table_list = sorted(inline_tables.values(), key=lambda d: d["name"].lower())

    sources: list[str] = []
    for e in entities:
        sources.extend(e.get("evidence", []))
    for p in procs:
        sources.append(f"{p['file']}:{p['line']}")

    lines: list[str] = []
    lines.append(_frontmatter(n, name, project, language, [s.split(":")[0] for s in sources]))
    lines.append(f"# FEAT {n} — Base de données & accès données (migration legacy `{project}`)")
    lines.append("")
    lines.append(_gate())
    lines.append("")
    lines.append(
        f"> ⚠️ FEAT transversale générée par reverse engineering (déterministe). "
        f"Modèle de données du legacy à reproduire : {len(entities)} entité(s), "
        f"{len(relations)} relation(s), {len(procs)} procédure(s) stockée(s) définie(s), "
        f"{len(called_procs)} procédure(s) appelée(s) sans DDL source, "
        f"{len(inline_table_list)} table(s) référencée(s) hors schéma, "
        f"{len(conn)} connection string(s). Type DB source : `{db_type}`."
    )
    lines.append("")

    lines.append("## Actors")
    lines.append("")
    lines.append("- **Équipe data / DBA** — recrée le schéma et les procédures sur la cible.")
    lines.append("")

    lines.append("## Functional Needs")
    lines.append("")
    lines.append(
        f"- SFD-1: La cible doit persister les mêmes entités métier que le "
        f"legacy ({len(entities)} table(s)) avec des contraintes équivalentes. "
        + _ev(sources[0] if sources else None)
    )
    sfd = 2
    if procs:
        lines.append(
            f"- SFD-{sfd}: La logique encapsulée dans {len(procs)} procédure(s) "
            f"stockée(s) doit être reproduite (procédure cible OU service applicatif "
            f"équivalent). {_ev(_fileline(procs[0]))}"
        )
        sfd += 1
    if called_procs:
        lines.append(
            f"- SFD-{sfd}: {len(called_procs)} procédure(s) stockée(s) sont "
            f"APPELÉES par le code sans DDL dans les sources : récupérer leur "
            f"définition en base (scripting) AVANT migration — contrat d'interface "
            f"DB obligatoire. {_ev(_fileline(called_procs[0]))}"
        )
        sfd += 1
    lines.append("")

    lines.append("## Functional Deliverables")
    lines.append("")
    fd = 1
    for e in entities[:_MAX_ITEMS]:
        cols = ", ".join(f"{f['name']}:{f['type']}" for f in e.get("fields", [])[:12]) or "(colonnes non extraites)"
        ev = (e.get("evidence") or ["unknown:1"])[0]
        lines.append(
            f"- FD-{fd}: Entité `{e['name']}` (table `{e.get('table', e['name'])}`) "
            f"— champs : {cols}. {_ev(ev)}"
        )
        fd += 1
    for p in procs[:_MAX_ITEMS]:
        params = ", ".join(
            f"{x['name']} {x['type']}{' OUTPUT' if x.get('output') else ''}"
            for x in p.get("params", [])
        ) or "(aucun paramètre)"
        lines.append(
            f"- FD-{fd}: Procédure stockée `{p['name']}`({params}). "
            f"{_ev(_fileline(p))}"
        )
        fd += 1
    for c in called_procs[:_MAX_ITEMS]:
        params = ", ".join(c.get("params", [])) or "(paramètres au call-site)"
        lines.append(
            f"- FD-{fd}: Procédure stockée APPELÉE `{c['name']}` ({params}) "
            f"— DDL absent des sources, à scripter depuis la base. "
            f"{_ev(_fileline(c))}"
        )
        fd += 1
    for t in inline_table_list[:_MAX_ITEMS]:
        t_ev = "{}:{}".format(t["file"], t["line"])
        lines.append(
            f"- FD-{fd}: Table `{t['name']}` référencée par les requêtes SQL "
            f"inline mais absente du schéma extrait — récupérer son DDL. "
            f"{_ev(t_ev)}"
        )
        fd += 1
    for c in conn[:_MAX_ITEMS]:
        lines.append(
            f"- FD-{fd}: Connection string `{c['name']}` → provider "
            f"`{c.get('provider') or '?'}`, server `{c.get('server') or '?'}`, "
            f"db `{c.get('database') or '?'}` (secrets masqués). "
            f"{_ev(_fileline(c))}"
        )
        fd += 1
    lines.append("")

    lines.append("## Business Rules")
    lines.append("")
    br = 1
    for r in relations[:_MAX_ITEMS]:
        lines.append(
            f"- BR-{br}: Relation `{r.get('name', 'FK')}` : "
            f"{r['from']['entity']}.{r['from']['field']} → "
            f"{r['to']['entity']}.{r['to']['field']} ({r.get('type', 'fk')}). "
            f"{_ev(r.get('evidence'))}"
        )
        br += 1
    if not relations:
        lines.append(
            f"- BR-1: Aucune relation FK explicite extraite ; vérifier "
            f"l'intégrité référentielle à la reprise. "
            + _ev(sources[0] if sources else None)
        )
    lines.append("")

    lines.append("## Acceptance Criteria")
    lines.append("")
    ac = 1
    if entities:
        e0 = entities[0]
        lines.append(
            f"- AC-{ac}: Given le schéma cible migré, when on inspecte la table "
            f"`{e0.get('table', e0['name'])}`, then ses colonnes correspondent à "
            f"celles du legacy. {_ev((e0.get('evidence') or ['unknown:1'])[0])}"
        )
        ac += 1
    if procs:
        p0 = procs[0]
        lines.append(
            f"- AC-{ac}: Given la cible, when on appelle l'équivalent de "
            f"`{p0['name']}` avec ses paramètres, then le comportement legacy est "
            f"reproduit. {_ev(_fileline(p0))}"
        )
        ac += 1
    if ac == 1:  # no entities, no procs → still need ≥1 AC
        lines.append(
            f"- AC-1: Given la cible, when la couche données est en place, then "
            f"elle expose les mêmes capacités d'accès que le legacy. "
            + _ev(sources[0] if sources else None)
        )
    lines.append("")

    lines.append("## Project Config")
    lines.append("")
    lines.append("<!-- à compléter par le Tech Lead : SGBD cible, ORM, stratégie procs -->")
    lines.append("")
    return "\n".join(lines)
