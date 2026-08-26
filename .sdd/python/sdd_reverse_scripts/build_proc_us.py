"""build_proc_us.py — Token-efficient routing for db-reverse User Stories.

Confirmed model: 1 SQL object = 1 US. But spending an LLM on a trivial
CRUD/SELECT proc is waste. This script classifies each object by complexity
(from the deterministic signals already extracted, 0 token):

  - SIMPLE  → statically trivial AND small: the US is generated
              DETERMINISTICALLY here, 0 token, and marked `extraction: templated`.
  - COMPLEX → real business logic → emitted in `needs_llm` so the orchestrator
              spawns the `reverse-sql-analyst` agent only where it adds value.
              Those US are marked `extraction: analyzed` by the agent.

This is the db-reverse equivalent of SDD_Pro's complexity_router.

Audit 2026-08-25 closes three defects here:
  - M2: the rubric now weighs volume, multi-table writes, transactional
    invariants and contract width, not just control flow — a 500-line branchless
    ETL is no longer "simple". Its routing REASONS travel into the US so a
    reviewer can see why an LLM was or was not spent.
  - D4: the US carries `Parent FEAT hash: sha256:COMPUTE_REQUIRED`, resolved by
    the assembler. Without it, DB-reverse US sat forever on preflight's
    pre-v7.0.0 compatibility path and FEAT drift was never detected.
  - D3: an OBJECT-level cache (was: module-level, so one changed procedure
    re-analysed its 19 siblings). Fail-safe: any doubt → re-extract.

CLI:
    python build_proc_us.py --project DB [--unit U-N | --all] [--workspace DIR]
                            [--no-cache] [--dry-run] [--json]

Output (JSON): {"written": [...], "needs_llm": [...], "cached": [...]}
Exit codes: 0 OK · 2 inventory/IO error · 3 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PY_ROOT = Path(__file__).resolve().parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.sql_body_analyzer import complexity_reasons, proc_complexity

# Same sentinel the forward pipeline resolves (sdd_scripts/resolve_us_hash_sentinel.py).
HASH_SENTINEL = "sha256:COMPUTE_REQUIRED"
CACHE_NAME = "proc-extraction-cache.json"

_VERB_TITLE = {
    "create": "Créer", "save": "Enregistrer", "update": "Mettre à jour",
    "delete": "Supprimer", "read": "Consulter", "validate": "Valider",
    "compute": "Calculer", "process": "Traiter", "import": "Importer",
    "sync": "Synchroniser", "notify": "Notifier",
}
_VERB_LOWER = {k: v.lower() for k, v in _VERB_TITLE.items()}

# Business angle per SQL object kind (P0.1 covers more than procedures).
_KIND_ANGLE = {
    "VIEW": ("vue", "projection métier exposée par la vue"),
    "SQL_TRIGGER": ("trigger", "règle déclenchée automatiquement par un événement"),
    "TRIGGER": ("trigger", "règle déclenchée automatiquement par un événement"),
    "SQL_SCALAR_FUNCTION": ("fonction", "calcul encapsulé par la fonction"),
    "SQL_INLINE_TABLE_VALUED_FUNCTION": ("fonction table", "jeu de données produit par la fonction"),
    "SQL_TABLE_VALUED_FUNCTION": ("fonction table", "jeu de données produit par la fonction"),
}
_DEFAULT_ANGLE = ("procédure stockée", "opération encapsulée par la procédure")


def _params_map(introspection: dict) -> dict[str, list]:
    return {p["fqName"]: p.get("params", []) for p in introspection.get("procedures", [])}


def _object_kind(proc: dict) -> tuple[str, str]:
    return _KIND_ANGLE.get(str(proc.get("routineType") or "").upper(), _DEFAULT_ANGLE)


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
    kind_label, kind_goal = _object_kind(proc)

    L: list[str] = []
    L.append("---")
    L.append(f"ID: {n}-{m}-{proc['usName']}")
    L.append(f"Parent FEAT: {n}-{module}")
    # D4 — resolved by build_proc_feats once the FEAT exists on disk.
    L.append(f"Parent FEAT hash: {HASH_SENTINEL}")
    L.append("generated-by: sdd-reverse")
    L.append(f"source-proc: {fq}")
    L.append(f"source-object-type: {proc.get('routineType') or 'SQL_STORED_PROCEDURE'}")
    L.append(f"language-detected: {lang}")
    L.append(f"Confidence: {conf}")
    # M2 — `confidence` says how readable the BODY was; `extraction` says how the
    # US was produced. Conflating them is what let a tautological template US
    # inherit confidence=high and sail through the REVERSE-GATE.
    L.append("extraction: templated")
    L.append("Status: Draft")
    L.append("---")
    L.append("")
    obj = module
    L.append(f"# US-{m}: {title_verb} {obj}")
    L.append("")
    banner = (
        f"> ⚠️ User Story reverse-engineerée **déterministe (0 token)** depuis la "
        f"{kind_label} `{fq}` ({lang}, lecture seule). Comportement OBSERVÉ."
    )
    if encrypted:
        banner += (" **Objet chiffré — corps indisponible, US à compléter par "
                   "revue humaine.**")
    else:
        banner += (" L'objet a été jugé statiquement trivial (aucune branche, "
                   "écriture unique, contrat court) : le texte ci-dessous est un "
                   "gabarit fidèle mais **non analysé** — à relire si l'objet "
                   "porte une intention métier implicite.")
    L.append(banner)
    L.append("")

    L.append("## Story")
    L.append("")
    L.append(f"En tant que **consommateur du module {obj}**, je veux **{low_verb} {obj}**, "
             f"afin de **réaliser l'{kind_goal} `{fq}`**.")
    L.append("")

    L.append("## Acceptance Criteria")
    L.append("")
    if encrypted:
        L.append(f"- AC-1: Given l'objet chiffré `{fq}`, when on tente de le reverser, "
                 f"then le comportement n'est pas observable statiquement — revue humaine "
                 f"requise (rien n'est inventé). <!-- evidence: {ev} --> <!-- confidence: low -->")
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
    L.append(f"- Lignes de corps : {proc.get('lineCount', 0)} · "
             f"Routage : déterministe (aucun signal de complexité détecté)")
    L.append("")

    L.append("## Covers")
    L.append("")
    L.append("<!-- back-fill par l'assembleur déterministe (rung 2). -->")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Object-level extraction cache (D3)
# --------------------------------------------------------------------------- #

def _snapshot_hash(project_root: Path, proc: dict) -> str:
    """sha256 of the object's own snapshot body. '' when it cannot be read.

    Returning '' is what makes the cache fail-safe: an unreadable snapshot yields
    a hash that never matches, so the object is re-extracted rather than skipped.
    """
    rel = (proc.get("evidence") or "").split(":")[0] or proc.get("snapshotFile") or ""
    if not rel:
        return ""
    path = project_root / rel
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def load_cache(sysdir: Path) -> dict:
    try:
        data = json.loads((sysdir / CACHE_NAME).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(sysdir: Path, cache: dict) -> None:
    atomic_write_text(sysdir / CACHE_NAME,
                      json.dumps(cache, indent=2, ensure_ascii=False) + "\n")


def is_cached(cache: dict, proc: dict, body_hash: str, us_path: Path) -> bool:
    """True iff this exact object body already produced this exact US file."""
    if not body_hash:
        return False
    entry = cache.get(proc["fqName"]) or {}
    return (entry.get("bodyHash") == body_hash
            and entry.get("usFile") == us_path.name
            and us_path.is_file())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic US generator + LLM routing for db-reverse.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", default="workspace")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--unit", help="single unit U-N")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="report routing only, write nothing")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore the object cache and re-extract everything")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    project_root = ws / "old" / args.project
    sysdir = project_root / ".sys"
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

    cache = {} if args.no_cache else load_cache(sysdir)
    written: list[str] = []
    needs_llm: list[dict] = []
    cached: list[str] = []
    for u in units:
        n = inventory["_featAllocations"][u["id"]]
        module = u["suggestedName"]
        for proc in u.get("procedures", []):
            out = us_dir / f"{n}-{proc['usIndex']}-{proc['usName']}.md"
            body_hash = _snapshot_hash(project_root, proc)
            # The inventory already carries the routing verdict; recompute only
            # if an older inventory predates it (backward compatible).
            verdict = proc.get("complexity") or proc_complexity(proc)
            if is_cached(cache, proc, body_hash, out):
                cached.append(str(out))
                continue
            if verdict == "simple":
                if not args.dry_run:
                    md = build_us(proc, module=module, n=n, lang=lang,
                                  params=params.get(proc["fqName"], []))
                    atomic_write_text(out, md)
                    cache[proc["fqName"]] = {
                        "bodyHash": body_hash, "usFile": out.name,
                        "extraction": "templated",
                    }
                written.append(str(out))
            else:
                needs_llm.append({
                    "unit": u["id"], "proc": proc["fqName"],
                    "usName": proc["usName"], "n": n, "m": proc["usIndex"],
                    "reasons": proc.get("complexityReasons") or complexity_reasons(proc),
                })

    if not args.dry_run and not args.no_cache:
        save_cache(sysdir, cache)

    if args.json:
        print(json.dumps({"written": written, "needs_llm": needs_llm,
                          "cached": cached}, ensure_ascii=False, indent=2))
    else:
        skip = f" · {len(cached)} inchangée(s) (cache)" if cached else ""
        print(f"[REVERSE] {len(written)} US déterministe(s) (0 token) · "
              f"{len(needs_llm)} objet(s) complexe(s) → agent LLM{skip}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
