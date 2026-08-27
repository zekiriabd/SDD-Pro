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
    build_context, diff_contexts, merge_architect_output,
)
from sdd_reverse.db_context_slice import (  # noqa: E402
    DEFAULT_DEPTH, DEFAULT_PACK_BUDGET, write_context_tree,
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
    ap.add_argument("--json", action="store_true", help="machine output")
    args = ap.parse_args(argv)
    # Windows consoles default to cp1252; the chat line carries French accents
    # and an arrow. Without this, a successful run dies on its own summary.
    ensure_console_safe()

    root = Path(args.project)
    sys_dir = root / ".sys"
    ctx_path = sys_dir / "db-context.json"

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
