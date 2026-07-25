"""build_proc_feats.py — Deterministic FEAT assembler for proc-reverse (rung 2).

Confirmed model: **1 module = 1 FEAT**, composed by REMONTÉE from the module's
procedures — the assembler reads the derived inventory (and optional US files),
NEVER the raw T-SQL bodies (escalier contract: 3c never re-reads the source).
0 token, deterministic, passes validate_reverse_feat.py.

Each procedure of the module becomes one capability (SFD + FD + AC), carrying the
procedure's snapshot evidence. Confidence is min-monotone over the module's
procedures (a dynamic-SQL or encrypted proc caps the whole FEAT).

A faithful, reviewable FEAT is produced WITHOUT any LLM. The `reverse-sql-analyst`
agent enriches the per-proc User Stories separately (rung 1); when those US exist,
their titles are folded into the FD lines for readability.

CLI:
    python build_proc_feats.py --project DB [--unit U-N | --all] [--workspace DIR] [--json]

Exit codes: 0 OK · 2 inventory/IO error · 3 usage.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PY_ROOT = Path(__file__).resolve().parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.atomic_write_local import atomic_write_text

_VERB_LABEL = {
    "create": "créer", "save": "enregistrer", "update": "mettre à jour",
    "delete": "supprimer", "read": "consulter", "validate": "valider",
    "compute": "calculer", "process": "traiter", "import": "importer",
    "sync": "synchroniser", "notify": "notifier",
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ev(evidence: str, conf: str) -> str:
    e = (evidence or "unknown:1").strip().replace(" ", "_")
    if ":" not in e.rsplit("/", 1)[-1]:
        e += ":1"
    return f"<!-- evidence: {e} --> <!-- confidence: {conf} -->"


def _gate(conf: str) -> str:
    allow = "true" if conf == "high" else "false"
    reason = "" if conf == "high" else " ; reason=confidence_below_high"
    return f"<!-- REVERSE-GATE: confidence={conf} ; allow-sdd-full={allow}{reason} -->"


def build_module_feat(unit: dict, *, n: int, project: str, db_type: str) -> str:
    name = unit["suggestedName"]
    language = unit.get("language", "tsql")
    conf = unit.get("confidenceEstimate", "high")
    procs = unit.get("procedures", [])
    sources = sorted({p.get("evidence", "").split(":")[0] for p in procs if p.get("evidence")})

    L: list[str] = []
    L.append("---")
    L.append("generated-by: sdd-reverse")
    L.append(f"legacy-sources: [{', '.join(sources[:10]) or '(.sys/proc-snapshot)'}]")
    L.append(f"confidence: {conf}")
    L.append(f"extraction-date: {_now()}")
    L.append(f"language-detected: {language}")
    L.append(f"source-unit: {unit['id']}")
    L.append("---")
    L.append("")
    L.append(f"# FEAT {n} — {name} (reverse procédures stockées `{project}`)")
    L.append("")
    L.append(_gate(conf))
    L.append("")
    banner = (
        f"> ⚠️ FEAT générée par reverse engineering des procédures stockées "
        f"({db_type}). Module `{name}` = {len(procs)} procédure(s). "
        f"Chaque procédure = 1 User Story. Lecture seule de la base."
    )
    if conf != "high":
        banner += (
            f" **Confidence {conf}** — revue humaine requise avant `/sdd-full` "
            f"(SQL dynamique ou procédure chiffrée détectés)."
        )
    L.append(banner)
    L.append("")

    L.append("## Actors")
    L.append("")
    L.append("- **Utilisateur métier** — déclenche les opérations du module via l'application cible.")
    L.append("- **Équipe data / DBA** — détient les procédures legacy reversées (lecture seule).")
    L.append("")

    L.append("## Functional Needs")
    L.append("")
    L.append(
        f"- SFD-1: Le module `{name}` doit offrir les capacités encapsulées par "
        f"ses {len(procs)} procédure(s) stockée(s) legacy. {_ev(sources[0] + ':1' if sources else None, conf)}"
    )
    sfd = 2
    for p in procs:
        verb = _VERB_LABEL.get(p.get("verb") or "", "exécuter")
        L.append(
            f"- SFD-{sfd}: Permettre de **{verb}** via `{p['fqName']}` "
            f"(US {n}-{p['usIndex']}). {_ev(p.get('evidence'), p.get('confidence', conf))}"
        )
        sfd += 1
    L.append("")

    L.append("## Functional Deliverables")
    L.append("")
    for i, p in enumerate(procs, start=1):
        params_hint = ""
        tw = p.get("tablesWritten") or []
        tr = p.get("tablesRead") or []
        if tw:
            params_hint = f" — écrit {', '.join(tw[:5])}"
        elif tr:
            params_hint = f" — lit {', '.join(tr[:5])}"
        flags = []
        if p.get("hasTransaction"):
            flags.append("transactionnelle")
        if p.get("dynamicSql"):
            flags.append("SQL dynamique")
        if p.get("encrypted"):
            flags.append("chiffrée")
        fl = f" [{', '.join(flags)}]" if flags else ""
        L.append(
            f"- FD-{i}: Reproduire le comportement de `{p['fqName']}`{params_hint}{fl} "
            f"→ User Story `{n}-{p['usIndex']}-{p['usName']}`. {_ev(p.get('evidence'), p.get('confidence', conf))}"
        )
    L.append("")

    L.append("## Business Rules")
    L.append("")
    br = 1
    any_br = False
    for p in procs:
        if p.get("raises"):
            L.append(
                f"- BR-{br}: `{p['fqName']}` applique des préconditions/erreurs "
                f"({', '.join(p['raises'])}) — à préserver. {_ev(p.get('evidence'), p.get('confidence', conf))}"
            )
            br += 1
            any_br = True
        if p.get("hasTransaction"):
            L.append(
                f"- BR-{br}: `{p['fqName']}` est atomique (transaction explicite) — "
                f"tout-ou-rien à préserver. {_ev(p.get('evidence'), p.get('confidence', conf))}"
            )
            br += 1
            any_br = True
    if not any_br:
        L.append(
            f"- BR-1: Le comportement métier est porté par les procédures du module ; "
            f"aucune règle transverse explicite détectée. {_ev(sources[0] + ':1' if sources else None, conf)}"
        )
    L.append("")

    L.append("## Acceptance Criteria")
    L.append("")
    for i, p in enumerate(procs, start=1):
        verb = _VERB_LABEL.get(p.get("verb") or "", "exécuter")
        tw = p.get("tablesWritten") or []
        effect = f"les données de {', '.join(tw[:3])} reflètent l'opération" if tw else "le résultat attendu est retourné"
        L.append(
            f"- AC-{i}: Given le module `{name}` en place, when on appelle "
            f"l'équivalent de `{p['fqName']}` ({verb}), then {effect}. "
            f"{_ev(p.get('evidence'), p.get('confidence', conf))}"
        )
    L.append("")

    L.append("## Project Config")
    L.append("")
    L.append(f"<!-- à compléter par le Tech Lead : stack cible, ORM, stratégie procédures ({db_type}) -->")
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic FEAT assembler for proc-reverse.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", default="workspace")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--unit", help="single unit U-N")
    g.add_argument("--all", action="store_true", help="every module/unit")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    inv_path = ws / "old" / args.project / ".sys" / "inventory.json"
    try:
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: build_proc_feats — inventory missing\nCAUSE: [REVERSE_UNIT_NOT_FOUND] {exc}",
              file=sys.stderr)
        return 2

    feats_dir = ws / "feats"
    feats_dir.mkdir(parents=True, exist_ok=True)
    db_type = inventory.get("databaseType", "SqlServer")
    units = inventory.get("units", [])
    if args.unit:
        units = [u for u in units if u["id"] == args.unit]
        if not units:
            print(f"ERROR: build_proc_feats\nCAUSE: [REVERSE_UNIT_NOT_FOUND] {args.unit}", file=sys.stderr)
            return 2

    written = []
    for u in units:
        n = inventory["_featAllocations"][u["id"]]
        feat = build_module_feat(u, n=n, project=args.project, db_type=db_type)
        out = feats_dir / f"{n}-{u['suggestedName']}.md"
        atomic_write_text(out, feat)
        written.append(str(out))

    if args.json:
        print(json.dumps({"written": written}, ensure_ascii=False, indent=2))
    else:
        print(f"[REVERSE] {len(written)} FEAT(s) module assemblée(s) depuis l'inventaire proc.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
