#!/usr/bin/env python3
"""SDD_Pro: build_context_pack — construit le pack de contexte d'un agent (0 token).

Audit 2026-08-28, correction #4 (Context Engineering généralisé).

Résout les sources déclarées par un agent dans `loader.yml` (y compris les
placeholders `{cat}/{active}` résolus depuis `stack.md`), applique le slicing
par rôle de `sdd_lib.context_pack`, et écrit un pack borné et auto-descriptif
sous `workspace/.sys/.context/packs/{agent}.md`.

Pourquoi un fichier sur disque et pas un pipe
---------------------------------------------

Parce que le consommateur n'est pas ce script. Trois lecteurs distincts ont
besoin du MÊME artefact : l'agent (qui le lit à la place des stacks entiers),
`context_budget.py` (qui doit mesurer ce que l'agent lit réellement, pas une
hypothèse), et le Tech Lead (qui doit pouvoir vérifier ce qui a été retiré).
Un pack éphémère ne servirait qu'au premier.

Usage
-----
    python -m sdd_scripts.build_context_pack --agent arch
    python -m sdd_scripts.build_context_pack --agent dev-backend --us-id 1-2
    python -m sdd_scripts.build_context_pack --all --json
    python -m sdd_scripts.build_context_pack --agent arch --dry-run

Exit codes (sdd_lib.exit_codes)
    0 SUCCESS       pack(s) écrit(s)
    1 FAIL_FAST     agent inconnu / loader.yml illisible
    2 CORRECTIBLE   aucune source résolue (stack.md absent ou vide)
    3 INFRA_BLOCKED échec d'écriture disque
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.atomic_write import atomic_write_text  # noqa: E402
from sdd_lib.console_safe import ensure_console_safe  # noqa: E402
from sdd_lib.context_pack import (  # noqa: E402
    PackSource, build_pack, fingerprint_of, role_for_agent,
)
from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.loader_yml import parse_agent_section  # noqa: E402
from sdd_lib.paths import normalize, repo_root, workspace_root  # noqa: E402

INFRA_BLOCKED = 3

#: Repertoire des packs. Reconnu pour exclure un pack de ses propres
#: sources (cf. `resolve_sources`).
PACK_DIR_MARKER = "/.sys/.context/packs/"

#: Agents pour lesquels un pack a du sens : ceux qui lisent des stacks.
#: Les agents reverse ont leur propre chaîne de packs (`db_context_slice`) et
#: ne sont pas concernés.
PACKABLE_AGENTS: tuple[str, ...] = (
    "arch", "dev-backend", "dev-frontend", "qa", "constitutioner",
    "code-reviewer", "security-reviewer", "arch-reviewer",
    "spec-compliance-reviewer", "adversarial-reviewer",
)

#: Budgets d'octets par agent — miroir de `context_budget.DEFAULT_BUDGETS`.
#: Importé dynamiquement pour éviter la duplication : une seule table de
#: budgets, sinon le pack et la gate divergent et l'un dit vert quand l'autre
#: dit rouge.
def _budget_for(agent: str) -> int | None:
    try:
        from sdd_scripts.context_budget import DEFAULT_BUDGETS
        return DEFAULT_BUDGETS.get(agent)
    except Exception:  # noqa: BLE001
        return None


#: Classement d'une source par stabilité, d'après son chemin. Pilote l'ordre
#: d'émission dans le pack (levier de cache de préfixe).
def _stability_for(path: str) -> str:
    p = normalize(path)
    if "/rules/" in p or "/digests/" in p or "/templates/" in p:
        return "rule"
    if "/stacks/" in p:
        return "stack"
    if "/.sys/.context/" in p or p.endswith("CLAUDE.md") or "/db/schema" in p:
        return "project"
    if "/us/" in p or "/feats/" in p or "/ui/" in p or "/plans/" in p:
        return "artifact"
    return "project"


#: Une source non sliceable est celle dont le contenu EST le sujet de la tâche.
#: Trancher dans une US ou un plan n'est pas du packing, c'est de la
#: mutilation : l'agent doit voir son artefact en entier.
def _sliceable(path: str) -> bool:
    p = normalize(path)
    if "/stacks/" in p or "/rules/" in p or "/digests/" in p:
        return True
    return False


# --------------------------------------------------------------------------- #
# Résolution des placeholders de loader.yml
# --------------------------------------------------------------------------- #

_ACTIVE_SECTIONS = (
    "## Active Architecture Pattern", "## Active Tech Specs",
    "## Active UI Specs", "## Active QA Specs", "## Active Auth Specs",
)


def active_stack_paths(root: Path) -> list[str]:
    """Chemins de stacks déclarés actifs dans `workspace/stack/stack.md`.

    Délègue le parsing à `sdd_lib.project_config.parse_active_stack_ids`, SSoT
    bi-racine. Ne PAS recompiler le motif ici : l'audit 2026-08-25 a montré que
    `phase_planner` voyait 0 stack actif là où `sdd_full_planner` en voyait 8,
    parce que chacun avait réimplémenté la regex en y figeant une racine —
    l'ancienne façade pour l'un, le foyer neutre pour l'autre. Le test
    `test_stack_path_parity.py::test_no_regex_hardcodes_stack_root` refuse
    toute copie locale du motif, et il a refusé la première version de cette
    fonction.
    """
    stack_md = workspace_root(root) / "stack" / "stack.md"
    if not stack_md.is_file():
        return []
    from sdd_lib.project_config import normalize_stack_path, parse_active_stack_ids
    text = stack_md.read_text(encoding="utf-8", errors="replace")
    out: list[str] = []
    for category, ids in parse_active_stack_ids(text).items():
        for stack_id in ids:
            out.append(normalize(normalize_stack_path(
                f".sdd/stacks/{category}/{stack_id}.md")))
    # dédoublonnage en préservant l'ordre de découverte (stable, donc cachable
    # — cf. STABILITY_ORDER)
    seen: set[str] = set()
    return [p for p in out if not (p in seen or seen.add(p))]


_PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")


def resolve_sources(agent: str, root: Path, *, us_id: str | None = None,
                    feat_n: int | None = None) -> tuple[list[PackSource], list[str]]:
    """Transforme les `reads:` de `loader.yml` en sources concrètes.

    Retourne ``(sources, unresolved)``. `unresolved` liste les patterns qu'on
    n'a pas su résoudre — remonté au manifeste plutôt que jeté, parce qu'un
    pattern silencieusement ignoré est une source de contexte manquante que
    personne ne verra.
    """
    # `pack_sources:` prime sur `reads:` quand il est declare.
    #
    # Un agent qui a bascule voit son pack dans `reads:` ; ses sources ne
    # peuvent donc plus etre lues la sans circularite. `pack_sources:` est la
    # declaration explicite de ce qui entre dans le pack, et conserve le
    # cadrage par dimension que `reads:` assurait avant la bascule.
    #
    # Repli sur `reads:` pour les agents non bascules : leur pack reste
    # calculable (projection informationnelle) sans exiger un second bloc.
    declared = (parse_agent_section(agent, section='pack_sources')
                or parse_agent_section(agent) or [])
    sources: list[PackSource] = []
    unresolved: list[str] = []
    stacks = active_stack_paths(root)
    added: set[str] = set()

    def _add(path: str) -> None:
        p = normalize(path)
        if p in added:
            return
        added.add(p)
        sources.append(PackSource(path=p, stability=_stability_for(p),
                                  sliceable=_sliceable(p)))

    for raw in declared:
        pat = raw if isinstance(raw, str) else str(raw)
        pat = normalize(pat)

        # Un pack ne peut pas etre sa propre source.
        #
        # Des que l'agent a bascule, `loader.yml` declare son pack parmi
        # ses `reads:`. L'inclure dans l'empreinte des sources la ferait
        # changer a chaque reconstruction du pack, donc invalider le pack
        # en permanence : la gate crierait [PACK_UNUSABLE] a chaque spawn
        # sur un pack pourtant fraichement ecrit.
        if PACK_DIR_MARKER in pat:
            continue

        # Placeholders de stack → jeu des stacks actifs, filtré par dimension
        # quand le pattern la nomme (`.sdd/stacks/backend/{active}.md`).
        if pat.startswith(".sdd/stacks/") and _PLACEHOLDER_RE.search(pat):
            dim = pat.split("/")[2]
            for s in stacks:
                if dim in ("{cat}", "*") or s.split("/")[2] == dim:
                    _add(s)
            continue

        if _PLACEHOLDER_RE.search(pat):
            concrete = pat
            if us_id:
                m = re.match(r"^(\d+)-(\d+)$", us_id)
                if m:
                    concrete = concrete.replace("{n}", m.group(1)).replace("{m}", m.group(2))
            if feat_n is not None:
                concrete = concrete.replace("{n}", str(feat_n))
            if _PLACEHOLDER_RE.search(concrete):
                unresolved.append(pat)
                continue
            pat = concrete

        matches = [normalize(p) for p in glob.glob(str(root / pat), recursive=True)
                   if Path(p).is_file()]
        if matches:
            for mfile in sorted(matches):
                try:
                    _add(normalize(str(Path(mfile).relative_to(root))))
                except ValueError:
                    _add(mfile)
        elif "*" in pat:
            unresolved.append(pat)
        else:
            # Chemin littéral absent : conservé comme source, `build_pack` le
            # déclarera dans `missing_sources` (l'agent doit savoir qu'un
            # fichier annoncé n'existait pas).
            _add(pat)

    return sources, unresolved


# --------------------------------------------------------------------------- #
# Écriture
# --------------------------------------------------------------------------- #

def pack_path(agent: str, root: Path) -> Path:
    return workspace_root(root) / ".sys" / ".context" / "packs" / f"{agent}.md"


def manifest_path(agent: str, root: Path) -> Path:
    """Sidecar machine du pack.

    Le pack `.md` est pour l'agent, ce JSON est pour l'outillage : la gate de
    budget doit pouvoir verifier la fraicheur sans parser du Markdown.
    """
    return pack_path(agent, root).with_suffix('.pack.json')


def pack_is_fresh(agent: str, root: Path) -> tuple[bool, str]:
    """`(frais, raison)` : le pack sur disque correspond-il a ses sources ?

    Load-bearing des lors que le pack REMPLACE les stacks dans `loader.yml`.
    Un pack perime nourrirait l'agent d'un stack d'hier sans que rien ne le
    signale. On recompare l'empreinte des sources declarees (quelques
    millisecondes) au sidecar ; reconstruire le pack pour comparer couterait
    le slicing complet.

    Toute incertitude retourne « pas frais » : un doute doit provoquer une
    reconstruction, jamais une consommation optimiste.
    """
    if not pack_path(agent, root).is_file():
        return False, 'pack absent'
    mf = manifest_path(agent, root)
    if not mf.is_file():
        return False, 'manifeste du pack absent'
    try:
        stored = json.loads(mf.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f'manifeste illisible: {exc}'
    sources, _ = resolve_sources(agent, root)
    if not sources:
        return False, 'aucune source resolue'
    if stored.get('sourcesFingerprint') != fingerprint_of(sources, root=root):
        return False, 'sources modifiees depuis la construction du pack'
    return True, 'a jour'


def build_for_agent(agent: str, root: Path, *, us_id: str | None = None,
                    feat_n: int | None = None, budget: int | None = None,
                    write: bool = True) -> dict[str, Any]:
    role = role_for_agent(agent)
    sources, unresolved = resolve_sources(agent, root, us_id=us_id, feat_n=feat_n)
    if not sources:
        return {"agent": agent, "role": role, "error": "no source resolved",
                "unresolved": unresolved}
    text, manifest = build_pack(
        role, sources,
        budget_bytes=budget if budget is not None else _budget_for(agent),
        root=root, agent=agent,
    )
    manifest["unresolved_patterns"] = unresolved
    dest = pack_path(agent, root)
    if write:
        atomic_write_text(dest, text, newline="\n")
        manifest["pack_path"] = normalize(str(dest.relative_to(root)))
        # Sidecar ecrit APRES le pack : si le processus meurt entre les deux,
        # on obtient un pack sans manifeste, donc juge non frais et
        # reconstruit. L'ordre inverse laisserait un manifeste valide decrire
        # un pack absent — un faux « a jour ».
        atomic_write_text(
            manifest_path(agent, root),
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str)
            + "\n",
            newline="\n")
    else:
        manifest["pack_path"] = None
    return manifest


def render_md(manifests: list[dict[str, Any]]) -> str:
    out = ["# Context packs", ""]
    out.append("| agent | rôle | avant | après | gain | sections retirées | budget |")
    out.append("|---|---|--:|--:|--:|--:|---|")
    for m in manifests:
        if m.get("error"):
            out.append(f"| `{m['agent']}` | {m['role']} | — | — | — | — | {m['error']} |")
            continue
        dropped = sum(len(s["sections_dropped"]) for s in m["sources"])
        state = "hors budget" if m["over_budget"] else "OK"
        pct = m["reduction_pct"]
        # Un pack sans section retirée grossit de l'overhead du manifeste.
        # L'afficher avec son signe évite de présenter une perte comme un gain.
        gain = f"-{pct}%" if pct > 0 else (f"+{abs(pct)}%" if pct < 0 else "0%")
        out.append(f"| `{m['agent']}` | {m['role']} | {m['bytes_before']:,} "
                   f"| {m['bytes_after']:,} | {gain} | {dropped} "
                   f"| {state} |".replace(",", " "))
    out.append("")
    out.append("Un gain `+x%` signale un pack plus GROS que ses sources : rien "
               "n'a pu être retiré pour ce rôle, et le manifeste coûte quelques "
               "centaines d'octets. C'est un signal utile — il dit que le "
               "`loader.yml` avait déjà correctement borné cet agent.")
    out.append("")
    for m in manifests:
        if m.get("error") or not m.get("unresolved_patterns"):
            continue
        out.append(f"`{m['agent']}` — patterns non résolus (contexte potentiellement "
                   f"manquant, pas ignoré silencieusement) :")
        for p in m["unresolved_patterns"]:
            out.append(f"- `{p}`")
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    p = argparse.ArgumentParser(
        prog="build_context_pack",
        description="Construit le pack de contexte d'un agent (slicing par rôle, 0 token)",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--agent", choices=PACKABLE_AGENTS)
    g.add_argument("--all", action="store_true", help="tous les agents packables")
    p.add_argument("--us-id", default=None, help="{n}-{m} pour résoudre les artefacts")
    p.add_argument("--feat-number", type=int, default=None)
    p.add_argument("--budget", type=int, default=None, help="override du budget en octets")
    p.add_argument("--dry-run", action="store_true", help="ne rien écrire")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    root = repo_root()
    agents = list(PACKABLE_AGENTS) if args.all else [args.agent]

    manifests: list[dict[str, Any]] = []
    try:
        for a in agents:
            manifests.append(build_for_agent(
                a, root, us_id=args.us_id, feat_n=args.feat_number,
                budget=args.budget, write=not args.dry_run,
            ))
    except OSError as exc:
        print(f"ERROR: build_context_pack failed\n"
              f"CAUSE: [DISK] écriture du pack impossible: {exc}\n"
              f"FIX: vérifier workspace/.sys/.context/packs/", file=sys.stderr)
        return INFRA_BLOCKED

    if args.json:
        print(json.dumps(manifests if len(manifests) > 1 else manifests[0],
                         ensure_ascii=False, indent=2, default=str))
    else:
        print(render_md(manifests))

    if all(m.get("error") for m in manifests):
        print("ERROR: build_context_pack failed\n"
              "CAUSE: [STACK_MALFORMED] aucune source résolue — "
              "workspace/stack/stack.md absent ou sans section `## Active *`\n"
              "FIX: renseigner stack.md, ou lancer /sdd-bootstrap", file=sys.stderr)
        return CORRECTIBLE
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
