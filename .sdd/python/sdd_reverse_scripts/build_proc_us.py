"""build_proc_us.py — Token-efficient routing for proc-reverse User Stories.

Confirmed model: 1 procedure = 1 US. But spending an LLM on a trivial CRUD/SELECT
proc is waste. This script classifies each procedure by complexity (from the
deterministic signals already extracted, 0 token):

  - SIMPLE  (no branches / no dynamic SQL / no raised errors / no cursors, or
            encrypted) → the US is generated DETERMINISTICALLY here, 0 token.
  - COMPLEX (real business logic) → emitted in `needs_llm` so the orchestrator
            spawns the `reverse-sql-analyst` agent only where it adds value.

This is the proc-reverse equivalent of SDD_Pro's complexity_router: ~70-80% of a
typical database's procedures (plain CRUD) cost zero LLM tokens.

CLI:
    python build_proc_us.py --project DB [--unit U-N | --all] [--workspace DIR] [--json]

Output (JSON): {"written": [...simple US paths...], "needs_llm": [{unit, proc, usName, n, m}]}
Exit codes: 0 OK · 2 inventory/IO error · 3 usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PY_ROOT = Path(__file__).resolve().parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.sql_body_analyzer import proc_complexity

_VERB_TITLE = {
    "create": "Créer", "save": "Enregistrer", "update": "Mettre à jour",
    "delete": "Supprimer", "read": "Consulter", "validate": "Valider",
    "compute": "Calculer", "process": "Traiter", "import": "Importer",
    "sync": "Synchroniser", "notify": "Notifier",
}
_VERB_LOWER = {k: v.lower() for k, v in _VERB_TITLE.items()}


def _params_map(introspection: dict) -> dict[str, list]:
    return {p["fqName"]: p.get("params", []) for p in introspection.get("procedures", [])}


def build_us(proc: dict, *, module: str, n: int, lang: str, params: list) -> str:
    verb = proc.get("verb") or ""
    title_verb = _VERB_TITLE.get(verb, "Exécuter")
    low_verb = _VERB_LOWER.get(verb, "exécuter")
    fq = proc["fqName"]
    m = proc["usIndex"]
    conf = proc.get("confidence", "high")
    ev = proc.get("evidence", "unknown:1")
    tr = proc.get("tablesRead") or []
    tw = proc.get("tablesWritten") or []
    encrypted = proc.get("encrypted", False)

    L: list[str] = []
    L.append("---")
    L.append(f"ID: {n}-{m}-{proc['usName']}")
    L.append(f"Parent FEAT: {n}-{module}")
    L.append("generated-by: sdd-reverse")
    L.append(f"source-proc: {fq}")
    L.append(f"language-detected: {lang}")
    L.append(f"Confidence: {conf}")
    L.append("Status: Draft")
    L.append("---")
    L.append("")
    obj = module
    L.append(f"# US-{m}: {title_verb} {obj}")
    L.append("")
    banner = (
        f"> ⚠️ User Story reverse-engineerée (déterministe, 0 token) depuis la "
        f"procédure `{fq}` ({lang}, lecture seule). Comportement OBSERVÉ."
    )
    if encrypted:
        banner += " **Procédure chiffrée — corps indisponible, US à compléter par revue humaine.**"
    L.append(banner)
    L.append("")

    L.append("## Story")
    L.append("")
    L.append(f"En tant que **consommateur du module {obj}**, je veux **{low_verb} {obj}**, "
             f"afin de **réaliser l'opération encapsulée par la procédure `{fq}`**.")
    L.append("")

    L.append("## Acceptance Criteria")
    L.append("")
    if encrypted:
        L.append(f"- AC-1: Given la procédure chiffrée `{fq}`, when on tente de la reverser, "
                 f"then le comportement n'est pas observable statiquement — revue humaine requise "
                 f"(rien n'est inventé). <!-- evidence: {ev} --> <!-- confidence: low -->")
    elif tw:
        L.append(f"- AC-1: Given des paramètres valides, when `{fq}` est appelée, "
                 f"then {', '.join(tw[:3])} est modifié(e) conformément au comportement legacy. "
                 f"<!-- evidence: {ev} --> <!-- confidence: {conf} -->")
        if tr:
            L.append(f"- AC-2: Given l'opération, when elle s'exécute, then elle lit également "
                     f"{', '.join(tr[:3])} pour produire le résultat. <!-- evidence: {ev} --> <!-- confidence: {conf} -->")
    else:
        src = ', '.join(tr[:3]) if tr else "la source de données"
        L.append(f"- AC-1: Given des données dans {src}, when `{fq}` est appelée, "
                 f"then un jeu de résultats issu de {src} est retourné (lecture seule). "
                 f"<!-- evidence: {ev} --> <!-- confidence: {conf} -->")
    L.append("")

    L.append("## Data Effects (plomberie démotée)")
    L.append("")
    L.append(f"- Lit : {', '.join(tr) or '(aucune table détectée)'} <!-- evidence: {ev} -->")
    L.append(f"- Écrit : {', '.join(tw) or '(aucune)'}")
    pdesc = ", ".join(f"{x.get('name','?')} {x.get('type','')}".strip()
                      + (" OUTPUT" if x.get("output") else "") for x in params) or "(aucun)"
    L.append(f"- Paramètres : {pdesc} <!-- evidence: {ev} -->")
    L.append(f"- Transaction : {'oui' if proc.get('hasTransaction') else 'non'} · "
             f"SQL dynamique : {'oui' if proc.get('dynamicSql') else 'non'} · "
             f"Branches : {proc.get('branches', 0)} · Erreurs : {', '.join(proc.get('raises', [])) or 'aucune'}")
    L.append("")

    L.append("## Covers")
    L.append("")
    L.append("<!-- back-fill par l'assembleur déterministe (rung 2). -->")
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic US generator + LLM routing for proc-reverse.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", default="workspace")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--unit", help="single unit U-N")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="report routing only, write nothing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    sysdir = ws / "old" / args.project / ".sys"
    try:
        inventory = json.loads((sysdir / "inventory.json").read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: build_proc_us\nCAUSE: [REVERSE_UNIT_NOT_FOUND] {exc}", file=sys.stderr)
        return 2
    try:
        introspection = json.loads((sysdir / "db-introspection.json").read_text(encoding="utf-8"))
    except OSError:
        introspection = {"procedures": []}

    params = _params_map(introspection)
    lang = inventory.get("primaryLanguage", "tsql")
    us_dir = ws / "us"
    us_dir.mkdir(parents=True, exist_ok=True)

    units = inventory.get("units", [])
    if args.unit:
        units = [u for u in units if u["id"] == args.unit]

    written: list[str] = []
    needs_llm: list[dict] = []
    for u in units:
        n = inventory["_featAllocations"][u["id"]]
        module = u["suggestedName"]
        for proc in u.get("procedures", []):
            if proc_complexity(proc) == "simple":
                out = us_dir / f"{n}-{proc['usIndex']}-{proc['usName']}.md"
                if not args.dry_run:
                    md = build_us(proc, module=module, n=n, lang=lang, params=params.get(proc["fqName"], []))
                    atomic_write_text(out, md)
                written.append(str(out))
            else:
                needs_llm.append({
                    "unit": u["id"], "proc": proc["fqName"],
                    "usName": proc["usName"], "n": n, "m": proc["usIndex"],
                })

    if args.json:
        print(json.dumps({"written": written, "needs_llm": needs_llm}, ensure_ascii=False, indent=2))
    else:
        print(f"[REVERSE] {len(written)} US déterministe(s) (0 token) · "
              f"{len(needs_llm)} proc(s) complexe(s) → agent LLM.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
