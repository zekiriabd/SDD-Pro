#!/usr/bin/env python3
"""correlate_db_app.py — join db-introspection.json × data-access.json (P0.3).

Answers "which application consumes which DB object". Reads the DB reverse
artefact (`db-introspection.json`, from db-reverse) and the application reverse
artefact (`data-access.json`, from the code reverse), and writes a consumption
map + a Mermaid diagram under the DB project's `.sys/`.

Usage:
    python correlate_db_app.py --introspection <path> --data-access <path> [--out <dir>] [--json]

Deterministic, 0 token, read-only on both inputs. Exit codes (local, D4):
0 SUCCESS · 1 FAIL_FAST (missing/invalid input) · 3 INFRA_BLOCKED (I/O).
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

from sdd_reverse.sql_app_correlation import correlate, to_mermaid  # noqa: E402

# Local exit codes (D4 — reverse module never imports sdd_lib).
SUCCESS, FAIL_FAST, INFRA_BLOCKED = 0, 1, 3


def _load(path: Path, label: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"ERROR: {label} not found\n"
            f"CAUSE: [REVERSE_DB_CONFIG_MISSING] {path} absent\n"
            f"FIX: run the {'db-reverse' if 'introspect' in label else 'code reverse'} phase first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Correlate DB objects with consuming applications.")
    ap.add_argument("--introspection", required=True, help="path to db-introspection.json")
    ap.add_argument("--data-access", required=True, help="path to data-access.json")
    ap.add_argument("--out", default=None, help="output dir (default: introspection's dir)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    intro_path = Path(args.introspection)
    da_path = Path(args.data_access)
    try:
        introspection = _load(intro_path, "db-introspection.json")
        data_access = _load(da_path, "data-access.json")
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return FAIL_FAST
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read input\nCAUSE: [REVERSE_INVENTORY_CORRUPTED] {exc}\nFIX: re-run reverse", file=sys.stderr)
        return FAIL_FAST

    corr = correlate(introspection, data_access)

    out_dir = Path(args.out) if args.out else intro_path.parent
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "db-app-correlation.json"
        md_path = out_dir / "db-app-correlation.md"
        json_path.write_text(json.dumps(corr, ensure_ascii=False, indent=2), encoding="utf-8")
        md = _render_md(corr)
        md_path.write_text(md, encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: write failed\nCAUSE: [DISK] {exc}\nFIX: check {out_dir} writable", file=sys.stderr)
        return INFRA_BLOCKED

    s = corr["summary"]
    if args.json:
        print(json.dumps(s, ensure_ascii=False))
    else:
        print(
            f"OK correlate_db_app — {s['consumedObjects']}/{s['dbObjects']} objets consommés, "
            f"{s['orphanObjects']} orphelin(s), {s['consumedTables']} table(s) consommée(s), "
            f"{s['missingProcedures']} appel(s) vers proc absente → {json_path}"
        )
    return SUCCESS


def _render_md(corr: dict) -> str:
    lines = [
        f"# Corrélation DB ↔ Applications — {corr.get('dbProject')} × {corr.get('appProject')}",
        "",
        "> Quelle application consomme quel objet de la base. Généré (0 token) par "
        "`correlate_db_app.py` (jointure db-introspection.json × data-access.json).",
        "",
        "## Objets DB consommés par le code applicatif",
        "",
        "| Objet DB | Appelé par (fichiers) | # appels |",
        "|---|---|---:|",
    ]
    for fq, e in corr.get("objectConsumers", {}).items():
        files = ", ".join(e["calledByFiles"]) or "—"
        lines.append(f"| `{fq}` | {files} | {e['callCount']} |")
    lines += ["", "## Tables consommées (SQL inline dans le code)", "",
              "| Table | Accédée par | # requêtes |", "|---|---|---:|"]
    for tbl, e in corr.get("tableConsumers", {}).items():
        files = ", ".join(e["accessedByFiles"]) or "—"
        lines.append(f"| `{tbl}` | {files} | {e['queryCount']} |")
    orphans = corr.get("orphanDbProcedures", [])
    if orphans:
        lines += ["", "## Procédures DB jamais appelées par le code scanné (orphelines / externes)", ""]
        lines += [f"- `{o}`" for o in orphans]
    missing = corr.get("missingProcedures", {})
    if missing:
        lines += ["", "## Appels applicatifs vers des procédures absentes de la base (drift)", ""]
        for name, files in missing.items():
            lines.append(f"- `{name}` ← {', '.join(files)}")
    lines += ["", "## Diagramme (Mermaid)", "", "```mermaid", to_mermaid(corr), "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
