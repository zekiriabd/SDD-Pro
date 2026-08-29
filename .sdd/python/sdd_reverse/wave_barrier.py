"""wave_barrier — la barrière de vague du reverse base de données.

Audit 2026-08-28, P0-4. Ferme le composant orphelin le plus coûteux du module.

Le problème
-----------

`db_wave_planner` ordonne les objets SQL en vagues pour que tout appelé résolu
soit analysé strictement avant son appelant. Cet ordre n'a de valeur que par sa
BARRIÈRE : à la fin de chaque vague, les résumés des objets analysés doivent
remonter dans `db-context.json.findings`, puis les packs de la vague suivante
sont régénérés pour citer ces résumés au lieu de signaux bruts.

`db_context.record_finding()` existait, documentée « called by the orchestrator
at a wave barrier », testée — et sans aucun appelant ni point d'entrée CLI. La
commande demandait à l'orchestrateur LLM d'écrire dans le JSON « en une passe
atomique » sans lui fournir d'outil pour le faire. Résultat : le dispatch par
vagues coûtait le prix d'un tri sans en tirer le bénéfice, et un appelant
recevait de ses appelés une matrice CRUD au lieu de leur règle métier.

Ce module est cet outil, et il est déterministe : le résumé n'est pas re-généré
par un modèle, il est EXTRAIT de la User Story que l'agent vient d'écrire. Un
second appel LLM pour résumer un texte que le premier vient de produire serait
payer deux fois la même information — et introduire une divergence possible
entre l'US livrée et le résumé cité par les appelants.

Comment un objet est relié à son User Story
-------------------------------------------

Par la ligne de frontmatter `source-proc: {schema}.{objet}`, écrite par les
DEUX producteurs d'US : l'assembleur déterministe (`build_proc_us.py:114`) et
les quatre analystes spécialisés via leur template. On indexe donc les US par
`source-proc` plutôt que par nom de fichier — le nom porte un slug de
capability qui n'a aucune raison de ressembler au nom de l'objet SQL.

Ce que la barrière ne fait pas
-----------------------------

Elle n'invente rien. Une US absente n'est pas une erreur : l'objet a pu être
sauté par le cache, ou n'être pas dans `needs_llm`. Elle est rapportée comme
`skipped`, avec sa raison. Un objet dont l'US existe mais ne porte ni titre ni
Acceptance Criteria produit un finding au résumé vide plutôt qu'un finding
fabriqué — un appelant vaut mieux d'apprendre « analysé, rien d'exploitable »
que de lire une phrase inventée.

API publique
------------
    finding_from_us(text, us_path=None)      -> dict
    index_us_by_object(us_dir)               -> dict[fq_norm, Path]
    close_wave(context, wave_index, us_index) -> (context, report)
    regenerate_wave_packs(root, context, wave_index, …) -> dict
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from sdd_reverse.db_context import record_finding

__all__ = [
    "finding_from_us",
    "index_us_by_object",
    "wave_members",
    "close_wave",
    "regenerate_wave_packs",
    "SUMMARY_MAX",
    "RULES_MAX",
]

#: Longueur maximale d'un résumé cité dans un pack. Un pack porte plusieurs
#: appelés ; laisser passer un paragraphe entier ferait exploser le budget que
#: `db_context_slice` s'échine à tenir.
SUMMARY_MAX = 240

#: Nombre de règles métier remontées par appelé. `db_context_slice._callee_block`
#: n'en affiche que 4 — en stocker 40 gonflerait le JSON sans rien changer au
#: pack. On aligne sur le consommateur.
RULES_MAX = 6

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_TITLE_RE = re.compile(r"^#\s+US-[^:]*:\s*(.+?)\s*$", re.M)
_STORY_WANT_RE = re.compile(r"je veux\s+\*\*(.+?)\*\*", re.S | re.I)
_AC_RE = re.compile(r"^\s*[-*]\s*(AC-\d+)\s*:\s*(.+?)(?=^\s*[-*]\s*AC-\d+\s*:|\Z)",
                    re.M | re.S)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

def _frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip().lower()] = v.strip()
    return out


def _section(text: str, *titles: str) -> str:
    """Corps de la première section `## …` dont le titre contient l'un des mots.

    Insensible à la casse et tolérant au numéro de section, parce que les
    templates d'US ne garantissent pas un intitulé exact — seulement un thème.
    """
    matches = list(_SECTION_RE.finditer(text or ""))
    for i, m in enumerate(matches):
        head = m.group(1).lower()
        if any(t.lower() in head for t in titles):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end():end]
    return ""


def _clean(s: str) -> str:
    """Retire les commentaires HTML (evidence, confidence) et normalise l'espace.

    Les commentaires portent l'evidence `file:line` — précieuse dans l'US,
    parasite dans un résumé cité par un appelant qui n'a pas à la re-vérifier.
    """
    s = _HTML_COMMENT_RE.sub(" ", s or "")
    return re.sub(r"\s+", " ", s).strip(" .;·-–—")


def _truncate(s: str, limit: int) -> str:
    s = s.strip()
    if len(s) <= limit:
        return s
    cut = s[: limit - 1]
    # Couper sur un mot plutôt qu'au milieu : un résumé tronqué doit rester
    # lisible pour l'agent appelant, pas ressembler à une corruption.
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:") + "…"


def finding_from_us(text: str, us_path: str | None = None) -> dict[str, Any]:
    """Extrait le finding d'une User Story de reverse DB. Déterministe, 0 token.

    Le résumé est pris dans cet ordre de préférence :
      1. le titre `# US-{m}: …` — la formulation la plus dense que l'agent a
         produite, et celle qu'un humain lit en premier ;
      2. le `je veux **…**` de la section Story, si le titre est absent ;
      3. rien. Un résumé vide est un fait ; une phrase inventée est un mensonge.

    Les règles métier viennent des Acceptance Criteria, qui sont l'endroit où
    le template de reverse DB demande explicitement une AC par branche
    observable — y compris une AC négative par erreur levée. C'est donc là que
    vit la règle de gestion, pas dans une section « Business Rules » que le
    template d'objet SQL ne prévoit pas.
    """
    text = text or ""
    fm = _frontmatter(text)

    summary = ""
    m = _TITLE_RE.search(text)
    if m:
        summary = _clean(m.group(1))
    if not summary:
        story = _section(text, "story")
        m = _STORY_WANT_RE.search(story)
        if m:
            summary = _clean(m.group(1))

    rules: list[str] = []
    ac_body = _section(text, "acceptance criteria", "acceptance")
    for _, body in _AC_RE.findall(ac_body):
        rule = _clean(body)
        if rule:
            rules.append(_truncate(rule, SUMMARY_MAX))
        if len(rules) >= RULES_MAX:
            break

    effects = _section(text, "data effects", "effets")
    contract = ""
    for line in effects.splitlines():
        cl = _clean(line)
        if cl.lower().startswith(("paramètres", "parametres", "params")):
            contract = _truncate(cl, SUMMARY_MAX)
            break

    return {
        "summary": _truncate(summary, SUMMARY_MAX),
        "contract": contract,
        "businessRules": rules,
        "callees": [],
        "usPath": us_path,
        "confidence": (fm.get("confidence") or "medium").lower(),
        "sourceObject": fm.get("source-proc") or fm.get("source-object") or "",
    }


# --------------------------------------------------------------------------- #
# Index US ← objet
# --------------------------------------------------------------------------- #

def _norm(ident: str) -> str:
    """Clé de comparaison canonique — même règle que `db_context._norm`."""
    if not ident:
        return ""
    return ident.strip().strip("[]`\"").strip().lower()


def index_us_by_object(us_dir: str | Path) -> dict[str, Path]:
    """`{fq normalisé: chemin de l'US}` pour toutes les US d'un répertoire.

    Indexé sur le frontmatter `source-proc`, jamais sur le nom de fichier : le
    basename porte un slug de capability (`Reserver-Stock`) qui n'a aucune
    raison de ressembler au nom de l'objet SQL (`dbo.usp_Stock_Reserve`).

    En cas de doublon (deux US pour le même objet — anomalie), la dernière par
    ordre alphabétique gagne, de façon déterministe. Le rapport de `close_wave`
    n'a pas à trancher une anomalie d'inventaire.
    """
    d = Path(us_dir)
    out: dict[str, Path] = {}
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.md")):
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            continue
        fm = _frontmatter(head)
        fq = fm.get("source-proc") or fm.get("source-object")
        if fq:
            out[_norm(fq)] = p
    return out


# --------------------------------------------------------------------------- #
# Barrière
# --------------------------------------------------------------------------- #

def wave_members(context: dict[str, Any], wave_index: int) -> list[str]:
    """Objets de la vague `wave_index` (0-based). Liste vide hors bornes."""
    waves = (context.get("executionPlan") or {}).get("waves") or []
    if wave_index < 0 or wave_index >= len(waves):
        return []
    return [str(fq) for fq in waves[wave_index]]


def close_wave(
    context: dict[str, Any],
    wave_index: int,
    us_index: dict[str, Path],
    *,
    only: Iterable[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Enregistre les findings de tous les objets analysés d'une vague.

    Retourne `(contexte enrichi, rapport)`. Le rapport distingue trois issues,
    et cette distinction est le cœur de l'honnêteté du mécanisme :

        recorded  une US existe, son finding est inscrit
        skipped   aucune US pour cet objet — cas NORMAL (objet non routé LLM,
                  ou sauté par le cache d'extraction). Pas une erreur.
        empty     une US existe mais ne porte ni titre ni AC exploitable. Le
                  finding est inscrit avec un résumé vide, et l'objet est
                  signalé : un appelant apprendra « analysé, rien
                  d'exploitable », ce qui vaut mieux qu'une phrase inventée
                  et mieux qu'un silence.

    N'écrit rien sur disque — l'appelant décide de la persistance, ce qui rend
    cette fonction testable sans système de fichiers.
    """
    members = wave_members(context, wave_index)
    if only is not None:
        keep = {_norm(o) for o in only}
        members = [fq for fq in members if _norm(fq) in keep]

    recorded: list[str] = []
    skipped: list[dict[str, str]] = []
    empty: list[str] = []

    for fq in members:
        us_path = us_index.get(_norm(fq))
        if us_path is None:
            skipped.append({"object": fq, "reason": "aucune User Story sur disque"})
            continue
        try:
            text = us_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            skipped.append({"object": fq, "reason": f"US illisible: {exc}"})
            continue
        finding = finding_from_us(text, us_path=str(us_path))
        finding["callees"] = _callees_of(context, fq)
        context = record_finding(context, fq, finding)
        recorded.append(fq)
        if not finding["summary"] and not finding["businessRules"]:
            empty.append(fq)

    return context, {
        "wave": wave_index,
        "members": members,
        "recorded": recorded,
        "skipped": skipped,
        "empty": empty,
        "stats": {
            "members": len(members),
            "recorded": len(recorded),
            "skipped": len(skipped),
            "empty": len(empty),
        },
    }


def _callees_of(context: dict[str, Any], fq: str) -> list[str]:
    """Appelés résolus d'un objet, depuis le plan d'exécution.

    Portés par le finding pour que le pack d'un appelant sache ce que son
    appelé délègue à son tour, sans avoir à re-parcourir le graphe.
    """
    edges = (context.get("executionPlan") or {}).get("edges") or []
    key = _norm(fq)
    return sorted({str(e["to"]) for e in edges if _norm(str(e["from"])) == key})


def regenerate_wave_packs(
    project_root: str | Path,
    context: dict[str, Any],
    wave_index: int,
    *,
    depth: int,
    budget: int,
) -> dict[str, Any]:
    """Réécrit les packs de la vague `wave_index` depuis le contexte enrichi.

    Portée délibérément étroite : seuls les packs de la vague SUIVANTE citeront
    les résumés qu'on vient d'inscrire. Régénérer l'arbre entier après chaque
    vague réécrirait des centaines de fiches inchangées — sur la base réelle de
    118 objets, la différence est entre quelques fichiers et plusieurs
    centaines, à chaque barrière.
    """
    from sdd_reverse.atomic_write_local import atomic_write_text
    from sdd_reverse.db_context_slice import _safe, build_pack

    root = Path(project_root).resolve() / ".sys" / "db-context" / "packs"
    written: list[str] = []
    trimmed: list[str] = []
    for fq in wave_members(context, wave_index):
        body, report = build_pack(context, fq, depth=depth, budget=budget)
        atomic_write_text(root / f"{_safe(fq)}.md", body)
        written.append(fq)
        if report.get("trimmed"):
            trimmed.append(fq)
    return {"wave": wave_index, "written": written, "trimmedPacks": trimmed}
