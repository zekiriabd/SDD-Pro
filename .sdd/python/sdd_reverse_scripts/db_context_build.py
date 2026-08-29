#!/usr/bin/env python3
"""db_context_build.py — Phase 0.A of db-reverse: build the Database Context.

Consumes the two artefacts the read-only introspection already produced
(`db-introspection.json`, `db-schema.json`) and assembles the versioned
Database Context / SSoT plus its sliced Markdown tree:

    .sys/db-context.json          machine SSoT (facts + execution plan)
    .sys/db-context/_overview.md  orientation
    .sys/db-context/tables/…      one card per table
    .sys/db-context/{procedures,functions,views,triggers}/…
    .sys/db-context/packs/…       the per-object slice handed to each agent

Deterministic, 0 token, offline. It opens no database connection and imports no
driver: everything it needs was extracted earlier under `readonly_guard`.

Usage:
    python db_context_build.py --project workspace/old/MyDb [--json]
    python db_context_build.py --project workspace/old/MyDb --refresh
    python db_context_build.py --project workspace/old/MyDb --diff-against prev.json

Exit codes (local, D4 — the reverse module never imports sdd_lib):
    0 SUCCESS · 1 FAIL_FAST (missing/invalid input) · 3 INFRA_BLOCKED (I/O)
    4 DRIFT   (--diff-against only: the two contexts differ)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PYROOT = _HERE.parent.parent
if str(_PYROOT) not in sys.path:
    sys.path.insert(0, str(_PYROOT))

from sdd_reverse.atomic_write_local import atomic_write_text  # noqa: E402
from sdd_reverse.console_safe import ensure_console_safe  # noqa: E402
from sdd_reverse.db_context import (  # noqa: E402
    build_context, build_architect_digest, diff_contexts, merge_architect_output,
)
from sdd_reverse.db_context_slice import (  # noqa: E402
    DEFAULT_DEPTH, DEFAULT_PACK_BUDGET, write_context_tree,
)
from sdd_reverse.paths import workspace_root  # noqa: E402
from sdd_reverse.wave_barrier import (  # noqa: E402
    close_wave, index_us_by_object, regenerate_wave_packs, wave_members,
)

SUCCESS, FAIL_FAST, INFRA_BLOCKED, DRIFT = 0, 1, 3, 4


def _err(cause: str, detail: str, fix: str) -> str:
    return (f"ERROR: db-context build failed\n"
            f"CAUSE: [{cause}] {detail}\n"
            f"FIX: {fix}")


def _load(path: Path, *, required: bool) -> dict:
    if not path.exists():
        if required:
            raise FileNotFoundError(_err(
                "REVERSE_DB_CONFIG_MISSING", f"{path} absent",
                "run reverse_proc_introspect.py --full first"))
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_fq(ident: str) -> str:
    """Clé canonique d'un nom qualifié — même règle que `db_context._norm`."""
    if not ident:
        return ""
    return ident.strip().strip("[]`\"").strip().lower()


def _wave_of(context: dict, fq: str) -> int | None:
    """Index de la vague contenant `fq`, ou None si l'objet n'est pas au plan.

    Utilisé par `--record-finding` pour retrouver la vague d'un objet nommé à
    la main, afin que la régénération de packs cible la bonne vague suivante.
    """
    metrics = ((context.get("executionPlan") or {}).get("metrics") or {})
    key = _norm_fq(fq)
    for name, m in metrics.items():
        if _norm_fq(str(name)) == key and m.get("wave") is not None:
            return int(m["wave"])
    for i, wave in enumerate((context.get("executionPlan") or {}).get("waves") or []):
        if any(_norm_fq(str(o)) == key for o in wave):
            return i
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build the versioned Database Context (Phase 0.A of db-reverse).")
    ap.add_argument("--project", required=True,
                    help="db project root, e.g. workspace/old/MyDb")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the prior context (drops carried-over hypotheses)")
    ap.add_argument("--no-packs", action="store_true",
                    help="render the tree without the per-object context packs")
    ap.add_argument("--depth", type=int, default=DEFAULT_DEPTH,
                    help=f"callee depth carried into a pack (default {DEFAULT_DEPTH})")
    ap.add_argument("--budget", type=int, default=DEFAULT_PACK_BUDGET,
                    help=f"max bytes per pack (default {DEFAULT_PACK_BUDGET})")
    ap.add_argument("--diff-against", default=None,
                    help="path to a previous db-context.json; reports drift and exits 4")
    ap.add_argument("--merge-hypotheses", default=None,
                    help="path to db-context.hypotheses.json written by the "
                         "reverse-db-architect agent (Phase 0.B); merged into "
                         "the hypotheses branch only - facts are never writable")
    ap.add_argument("--close-wave", type=int, default=None, metavar="K",
                    help="BARRIÈRE DE VAGUE (audit 2026-08-28 P0-4) : inscrit "
                         "dans db-context.json.findings le résumé de chaque "
                         "objet de la vague K dont l'User Story existe, puis "
                         "régénère les packs de la vague K+1 pour qu'ils "
                         "citent ces résumés au lieu de signaux bruts. "
                         "Vagues 0-based, déterministe, idempotent.")
    ap.add_argument("--record-finding", default=None, metavar="FQ",
                    help="inscrit le finding d'UN objet (débogage / reprise "
                         "partielle d'une vague). Requiert --from-us.")
    ap.add_argument("--from-us", default=None, metavar="PATH",
                    help="chemin de l'User Story à lire pour --record-finding")
    ap.add_argument("--us-dir", default=None, metavar="PATH",
                    help="répertoire des User Stories (défaut: workspace/us)")
    ap.add_argument("--list-completed-waves", action="store_true",
                    help="affiche les vagues déjà clôturées dans le checkpoint "
                         "(db-context.waves-completed.json) et quitte 0. "
                         "Utilisé par l'orchestrateur pour reprendre un run "
                         "interrompu sans re-fermer les vagues terminées.")
    ap.add_argument("--json", action="store_true", help="machine output")
    args = ap.parse_args(argv)
    # Windows consoles default to cp1252; the chat line carries French accents
    # and an arrow. Without this, a successful run dies on its own summary.
    ensure_console_safe()

    root = Path(args.project)
    sys_dir = root / ".sys"
    ctx_path = sys_dir / "db-context.json"

    # --list-completed-waves: read-only, does not need introspection loaded.
    if args.list_completed_waves:
        cp = sys_dir / "db-context.waves-completed.json"
        try:
            state = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
        except (OSError, json.JSONDecodeError):
            state = {}
        completed = list(state.get("completedWaves") or [])
        if args.json:
            print(json.dumps({"completedWaves": completed,
                               "contextVersion": state.get("contextVersion")},
                             ensure_ascii=False))
        else:
            if completed:
                print(f"[REVERSE] Vagues déjà clôturées : {completed}. "
                      f"(contextVersion {state.get('contextVersion', 'inconnue')[:16]}…)")
            else:
                print("[REVERSE] Aucune vague clôturée (checkpoint absent ou vide).")
        return SUCCESS

    try:
        introspection = _load(sys_dir / "db-introspection.json", required=True)
        schema = _load(sys_dir / "db-schema.json", required=False)
        prior = None if args.refresh else _load(ctx_path, required=False)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return FAIL_FAST
    except (OSError, json.JSONDecodeError) as exc:
        print(_err("REVERSE_INVENTORY_CORRUPTED", str(exc),
                   "delete the artefact and re-run the introspection"), file=sys.stderr)
        return INFRA_BLOCKED

    context = build_context(
        introspection, schema or None,
        project=root.name, prior=prior or None,
    )

    # --diff-against is a read-only drift report: it never writes the context.
    if args.diff_against:
        try:
            previous = json.loads(Path(args.diff_against).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(_err("REVERSE_INVENTORY_CORRUPTED", str(exc),
                       "check the --diff-against path"), file=sys.stderr)
            return INFRA_BLOCKED
        report = diff_contexts(previous, context)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            st = report["stats"]
            print(f"[REVERSE] Drift contexte — "
                  f"tables +{st['tablesAdded']}/-{st['tablesRemoved']}/~{st['tablesChanged']}, "
                  f"objets +{st['objectsAdded']}/-{st['objectsRemoved']}/~{st['objectsChanged']}.")
            if report["reAnalysisRequired"]:
                print("  À ré-analyser : "
                      + ", ".join(report["reAnalysisRequired"][:12])
                      + (" …" if len(report["reAnalysisRequired"]) > 12 else ""))
        return SUCCESS if report["identical"] else DRIFT

    # ----------------------------------------------------------------------- #
    # Barrière de vague (audit 2026-08-28, P0-4)
    # ----------------------------------------------------------------------- #
    #
    # Placée AVANT le merge d'hypothèses et l'écriture nominale parce qu'elle a
    # une sémantique différente : elle n'a pas à reconstruire l'arbre entier,
    # seulement à enrichir `findings` et à réécrire les packs de la vague
    # suivante. Régénérer les centaines de fiches inchangées à chaque barrière
    # coûterait plus que l'analyse qu'on vient de payer.
    #
    # Pourquoi le résumé est EXTRAIT et non re-généré : l'agent vient d'écrire
    # l'User Story. Un second appel LLM pour la résumer paierait deux fois la
    # même information et ouvrirait un écart possible entre l'US livrée et le
    # résumé que ses appelants vont citer.
    if args.close_wave is not None or args.record_finding:
        if args.record_finding and not args.from_us:
            print(_err("INVALID_ARG", "--record-finding exige --from-us",
                       "python db_context_build.py --project P "
                       "--record-finding dbo.usp_X --from-us workspace/us/1-1-X.md"),
                  file=sys.stderr)
            return FAIL_FAST

        us_dir = (Path(args.us_dir) if args.us_dir
                  else workspace_root() / "us")

        if args.record_finding:
            us_path = Path(args.from_us)
            if not us_path.is_file():
                print(_err("NOT_FOUND", f"User Story introuvable: {us_path}",
                           "vérifier --from-us"), file=sys.stderr)
                return FAIL_FAST
            us_index = {_norm_fq(args.record_finding): us_path}
            targets = [args.record_finding]
            wave = _wave_of(context, args.record_finding)
        else:
            us_index = index_us_by_object(us_dir)
            targets = None
            wave = args.close_wave

        if wave is None:
            print(_err("INVALID_ARG",
                       f"objet {args.record_finding!r} absent du plan de vagues",
                       "vérifier le nom qualifié, ou relancer l'introspection"),
                  file=sys.stderr)
            return FAIL_FAST

        context, report = close_wave(context, wave, us_index, only=targets)

        try:
            atomic_write_text(
                ctx_path,
                json.dumps(context, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
            # La vague suivante est celle qui citera les résumés qu'on vient
            # d'inscrire. Si elle n'existe pas (dernière vague), il n'y a
            # simplement rien à régénérer — ce n'est pas une erreur.
            packs = regenerate_wave_packs(
                root, context, wave + 1, depth=args.depth, budget=args.budget)

            # Checkpoint de reprise : enregistrer la vague comme terminée pour
            # qu'un redémarrage après crash sache lesquelles sont déjà closes.
            # Idempotent : re-fermer une vague déjà marquée ne change rien.
            # --record-finding est une reprise partielle intra-vague — elle
            # ne marque PAS la vague complète (c'est le `--close-wave` entier
            # qui confirme la vague).
            if not args.record_finding:
                _checkpoint_path = sys_dir / "db-context.waves-completed.json"
                try:
                    existing = json.loads(_checkpoint_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    existing = {}
                completed = list(existing.get("completedWaves") or [])
                if wave not in completed:
                    completed.append(wave)
                atomic_write_text(
                    _checkpoint_path,
                    json.dumps({
                        "contextVersion": context["contextVersion"],
                        "completedWaves": sorted(completed),
                    }, ensure_ascii=False, indent=2) + "\n")
        except OSError as exc:
            print(_err("DISK", str(exc),
                       "check write rights on the project .sys/ directory"),
                  file=sys.stderr)
            return INFRA_BLOCKED

        out = {**report, "nextWavePacks": packs,
               "contextVersion": context["contextVersion"],
               "contextPath": str(ctx_path)}
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            st = report["stats"]
            print(f"[REVERSE] Barrière vague {wave} — "
                  f"{st['recorded']}/{st['members']} résumé(s) inscrit(s), "
                  f"{st['skipped']} objet(s) sans User Story, "
                  f"{len(packs['written'])} pack(s) de la vague {wave + 1} "
                  f"régénéré(s).")
            if report["empty"]:
                print("  US sans résumé exploitable (ni titre ni AC) : "
                      + ", ".join(report["empty"][:8])
                      + (" …" if len(report["empty"]) > 8 else ""))
        return SUCCESS

    # Phase 0.B lands here: the architect never edits db-context.json itself, it
    # writes a separate file that this deterministic step folds into the
    # `hypotheses` branch. Same guard as db-schema.enrichment.json (ADV-3): an
    # agent cannot clobber the fact layer, by construction rather than by rule.
    merged_hyp = 0
    if args.merge_hypotheses:
        try:
            architect = json.loads(
                Path(args.merge_hypotheses).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(_err("REVERSE_INVENTORY_CORRUPTED", str(exc),
                       "check the --merge-hypotheses path / JSON syntax"), file=sys.stderr)
            return INFRA_BLOCKED
        stated = architect.get("contextVersion")
        if stated and stated != context["contextVersion"]:
            # The architect read a database that has since changed. Merging would
            # attach a stale reading to fresh facts - worse than having none.
            print(_err("REVERSE_DB_CONTEXT_STALE",
                       f"hypotheses built on {stated} but facts are now "
                       f"{context['contextVersion']}",
                       "re-run the reverse-db-architect agent on the current context"),
                  file=sys.stderr)
            return FAIL_FAST
        context = merge_architect_output(context, architect)
        merged_hyp = sum(len(context["hypotheses"].get(k) or [])
                         for k in ("glossary", "subdomains", "objectRoles",
                                   "risks", "openQuestions"))

    try:
        atomic_write_text(
            ctx_path,
            json.dumps(context, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
        # Lightweight digest for Phase 0.B (reverse-db-architect).
        # Produced here at 0-token cost so the architect reads ~5-20 KB
        # instead of the full context (which grows with object count).
        digest = build_architect_digest(context)
        atomic_write_text(
            sys_dir / "db-context.digest.json",
            json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
        tree = write_context_tree(
            root, context,
            depth=args.depth, budget=args.budget, with_packs=not args.no_packs)
    except OSError as exc:
        print(_err("DISK", str(exc), "check write rights on the project .sys/ directory"),
              file=sys.stderr)
        return INFRA_BLOCKED

    facts, plan = context["facts"], context["executionPlan"]
    summary = {
        "contextVersion": context["contextVersion"],
        "reused": context["reuse"]["reused"],
        "tables": facts["summary"]["tables"],
        "objects": facts["summary"]["objects"],
        "waves": plan["stats"]["waveCount"],
        "widestWave": plan["stats"]["widestWave"],
        "unresolvedCalls": plan["stats"]["unresolvedCalls"],
        "recursiveComponents": plan["stats"]["recursiveComponents"],
        "tree": tree["written"],
        "trimmedPacks": tree["trimmedPacks"],
        "contextPath": str(ctx_path),
        "hypothesesMerged": merged_hyp,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"[REVERSE] Contexte DB {root.name} → "
              f"{summary['tables']} table(s), {summary['objects']} objet(s), "
              f"{summary['waves']} vague(s) (la plus large : {summary['widestWave']}), "
              f"{summary['unresolvedCalls']} appel(s) non résolu(s). "
              f"{'Contexte réutilisé.' if summary['reused'] else 'Contexte reconstruit.'}")
        if merged_hyp:
            print(f"  {merged_hyp} hypothese(s) d'architecte fusionnee(s).")
        if summary["trimmedPacks"]:
            print(f"  ⚠️ {len(summary['trimmedPacks'])} pack(s) tronqué(s) au budget : "
                  + ", ".join(summary["trimmedPacks"][:8]))
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
