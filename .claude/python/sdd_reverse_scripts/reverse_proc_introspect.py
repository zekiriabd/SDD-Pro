"""reverse_proc_introspect.py — Phase 1 of the stored-procedure reverse flow.

Deterministic orchestrator (0 token). Connects READ-ONLY to the database whose
connection params live in stack.md, snapshots the routine bodies, clusters them
into business modules, and writes an `inventory.json` with pre-allocated
(n, Name) per module — ready for the LLM analyst (proc → US) and the
deterministic FEAT assembler (module US → FEAT).

Model (confirmed with Tech Lead):
    1 procedure = 1 User Story        (unit.procedures[])
    1 module    = 1 FEAT              (unit = U-N, pre-allocated n + Name)

Live vs offline:
    --full / --proc NAME   connect to the DB (pyodbc, extra `reverse-db`)
    --from-introspection P   replay an existing db-introspection.json (no DB) —
                             used by tests and to re-cluster without reconnecting

CLI:
    python reverse_proc_introspect.py --full   [--project DB] [--stack PATH] [--json]
    python reverse_proc_introspect.py --proc dbo.usp_X  [--project DB] [--json]
    python reverse_proc_introspect.py --from-introspection .sys/db-introspection.json --project DB

Exit codes: 0 OK · 2 DB/config error · 3 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

PY_ROOT = Path(__file__).resolve().parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse import db_introspect as dbi
from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.dialects import UnsupportedDialect, get_dialect
from sdd_reverse.proc_module_clusterer import cluster
from sdd_reverse.stack_db_config import StackConfigError, read_db_config

INVENTORY_NAME = "inventory.json"
DEFAULT_STACK = "workspace/stack/stack.md"

# verb → French capability slug fragment for the US {Name}
_VERB_SLUG = {
    "create": "Creer", "save": "Enregistrer", "update": "Modifier",
    "delete": "Supprimer", "read": "Consulter", "validate": "Valider",
    "compute": "Calculer", "process": "Traiter", "import": "Importer",
    "sync": "Synchroniser", "notify": "Notifier",
}


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", text).strip()
    return "".join(w.capitalize() for w in cleaned.split()) or "Proc"


def _us_name(verb: str | None, module: str, fq: str) -> str:
    leaf = fq.split(".")[-1]
    verb_part = _VERB_SLUG.get(verb or "", "")
    base = f"{verb_part}-{module}" if verb_part else _slug(leaf)
    return base


def _lang_cap(language_id: str) -> str:
    """Read confidence_cap for a language from language_signatures.yml (fallback high)."""
    try:
        from sdd_reverse.scan_legacy import load_signatures
        sigs = load_signatures(PY_ROOT / "sdd_reverse" / "language_signatures.yml")
        for lang in sigs.get("languages", []):
            if lang.get("id") == language_id:
                return lang.get("confidence_cap", "high")
    except Exception:
        pass
    return "high"


def _next_feat_number(feats_dir: Path) -> int:
    mx = 0
    if feats_dir.is_dir():
        for f in feats_dir.glob("*.md"):
            m = re.match(r"(\d+)-", f.name)
            if m:
                mx = max(mx, int(m.group(1)))
    return mx + 1


def _prior_proc_indices(prior: dict | None) -> dict[str, dict[str, int]]:
    """module suggestedName → {fqName: usIndex} from a prior inventory (stability)."""
    out: dict[str, dict[str, int]] = {}
    for u in (prior or {}).get("units", []):
        out[u.get("suggestedName", "")] = {
            p["fqName"]: p.get("usIndex", i + 1)
            for i, p in enumerate(u.get("procedures", []))
        }
    return out


def build_inventory(introspection: dict, *, project: str, feats_dir: Path, prior: dict | None = None) -> dict:
    """Cluster procedures into modules and (re)allocate (n, Name) per module.

    When `prior` is given (incremental run), existing modules keep their FEAT
    number, name, U-id and per-proc usIndex — only new modules/procs get fresh
    allocations. This is what lets a second proc of the same object GROW the
    existing FEAT instead of clobbering it.
    """
    procs = introspection.get("procedures", [])
    routines = [
        {"name": p["fqName"], "schema": p.get("schema"),
         "signals": {"tablesWritten": p.get("tablesWritten", []),
                     "tablesRead": p.get("tablesRead", []),
                     "calls": p.get("callsProcs", [])},
         "_proc": p}
        for p in procs
    ]
    # P0.2 opt-in: SDD_REVERSE_CLUSTER_COHESION=1 groups by dependency cohesion
    # instead of naming (robust on legacy DBs without naming conventions).
    import os
    _cohesion = os.environ.get("SDD_REVERSE_CLUSTER_COHESION", "").lower() in ("1", "true", "yes", "on")
    modules = cluster(routines, use_cohesion=_cohesion)

    prior_names: dict[str, str] = (prior or {}).get("_allocatedNames", {})       # name -> uid
    prior_alloc: dict[str, int] = (prior or {}).get("_featAllocations", {})      # uid -> n
    prior_idx = _prior_proc_indices(prior)
    prior_uid_nums = [int(u.split("-")[1]) for u in prior_alloc if u.startswith("U-")]
    next_uid = (max(prior_uid_nums) if prior_uid_nums else 0) + 1
    next_n = _next_feat_number(feats_dir)

    units = []
    feat_allocations: dict[str, int] = {}
    allocated_names: dict[str, str] = {}
    order = {"low": 0, "medium": 1, "high": 2}

    for module, members in sorted(modules.items()):
        # Reuse prior allocation for a module that already exists (stability).
        if module in prior_names:
            uid = prior_names[module]
            name = module
            n = prior_alloc.get(uid, next_n)
        else:
            name = module
            suffix = 0
            while name in allocated_names or name in prior_names or (feats_dir / f"{next_n}-{name}.md").exists():
                suffix += 1
                name = f"{module}-Legacy" if suffix == 1 else f"{module}-Legacy-{suffix}"
            uid = f"U-{next_uid}"
            next_uid += 1
            n = next_n
            next_n += 1
        feat_allocations[uid] = n
        allocated_names[name] = uid

        existing_idx = prior_idx.get(name, {})
        used = set(existing_idx.values())
        next_m = (max(used) if used else 0) + 1

        unit_procs = []
        evidence_files = []
        min_conf = "high"
        for r in members:
            p = r["_proc"]
            conf = p.get("confidenceEstimate", "high")
            if order.get(conf, 0) < order.get(min_conf, 2):
                min_conf = conf
            evidence_files.append(p.get("snapshotFile", ""))
            # Preserve usIndex for known procs; assign next for new ones.
            if p["fqName"] in existing_idx:
                m_index = existing_idx[p["fqName"]]
            else:
                m_index = next_m
                next_m += 1
            unit_procs.append({
                "spId": p["id"],
                "fqName": p["fqName"],
                "verb": r.get("verb"),
                "usIndex": m_index,
                "usName": _us_name(r.get("verb"), name, p["fqName"]),
                "evidence": p.get("evidence", ""),
                "confidence": conf,
                "encrypted": p.get("encrypted", False),
                "dynamicSql": p.get("dynamicSql", False),
                "branches": p.get("branches", 0),
                "cursors": p.get("cursors", 0),
                "tablesWritten": p.get("tablesWritten", []),
                "tablesRead": p.get("tablesRead", []),
                "raises": p.get("raises", []),
                "hasTransaction": p.get("hasTransaction", False),
            })

        units.append({
            "id": uid,
            "label": f"Module {module} ({len(members)} procédure(s))",
            "suggestedName": name,
            "language": introspection.get("languageId", "tsql"),
            "kind": "db-module",
            "source": "proc-reverse",
            "confidenceEstimate": min_conf,
            "evidenceFiles": [e for e in evidence_files if e],
            "procedures": unit_procs,
        })

    return {
        "schemaVersion": 1,
        "project": project,
        "source": "proc-reverse",
        "databaseType": introspection.get("databaseType"),
        "primaryLanguage": introspection.get("languageId", "tsql"),
        "scanDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "languagesDetected": [
            {"id": introspection.get("languageId", "tsql"), "confidence": "high"}
        ],
        "units": units,
        "_featAllocations": feat_allocations,
        "_allocatedNames": allocated_names,
        "legacyMtimeMax": int(time.time()),
        "_introspectionSummary": introspection.get("summary", {}),
    }


def _emit(args, project, inventory, introspection):
    units = inventory["units"]
    nproc = introspection.get("summary", {}).get("proceduresCount", 0)
    nenc = introspection.get("summary", {}).get("encryptedCount", 0)
    if args.json:
        print(json.dumps({
            "project": project, "modules": len(units), "procedures": nproc,
            "encrypted": nenc,
            "allocations": inventory["_featAllocations"],
        }, ensure_ascii=False, indent=2))
    else:
        enc = f", {nenc} chiffrée(s)" if nenc else ""
        print(f"[REVERSE] DB {project} → {nproc} procédure(s){enc} "
              f"regroupée(s) en {len(units)} module(s)/FEAT. (Phase 1 OK)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase 1 stored-procedure reverse (read-only).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--full", action="store_true", help="introspect all routines")
    g.add_argument("--proc", help="introspect a single routine ([schema.]name)")
    g.add_argument("--from-introspection", help="replay an existing db-introspection.json (no DB)")
    ap.add_argument("--project", help="legacy project dir name under workspace/old/ (default = DB_NAME)")
    ap.add_argument("--stack", default=DEFAULT_STACK, help="path to stack.md")
    ap.add_argument("--workspace", default="workspace", help="workspace root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    feats_dir = ws / "feats"

    def _load_json(p: Path):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    try:
        if args.from_introspection:
            introspection = json.loads(Path(args.from_introspection).read_text(encoding="utf-8"))
            project = args.project or introspection.get("database") or "Database"
            project_root = ws / "old" / project
        else:
            cfg = read_db_config(args.stack)
            cfg.require_complete()
            dialect = get_dialect(cfg.db_type)
            project = args.project or cfg.name
            project_root = ws / "old" / project
            (project_root / ".sys").mkdir(parents=True, exist_ok=True)
            # Load the PRIOR snapshot BEFORE introspect overwrites db-introspection.json,
            # so a single-proc run can MERGE (grow) instead of clobber.
            prior_introspection = _load_json(project_root / ".sys" / dbi._INTROSPECTION_NAME)
            new_model = dbi.introspect(
                cfg, project_root,
                proc=(args.proc if args.proc else None),
                lang_cap=_lang_cap(dialect.language_id),
            )
            if args.proc and prior_introspection:
                introspection = dbi.merge_introspection(prior_introspection, new_model)
                atomic_write_text(
                    project_root / ".sys" / dbi._INTROSPECTION_NAME,
                    json.dumps(introspection, indent=2, ensure_ascii=False) + "\n",
                )
            else:
                introspection = new_model
    except (StackConfigError, UnsupportedDialect, dbi.ReverseDbError) as exc:
        print("ERROR: proc-reverse Phase 1 failed", file=sys.stderr)
        print(f"CAUSE: {exc}", file=sys.stderr)
        sys.stderr.write("FIX: vérifier '## Active Database' de stack.md + accès lecture seule.\n")
        return 2

    prior_inventory = _load_json(project_root / ".sys" / INVENTORY_NAME)
    inventory = build_inventory(
        introspection, project=project, feats_dir=feats_dir, prior=prior_inventory
    )
    atomic_write_text(
        project_root / ".sys" / INVENTORY_NAME,
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
    )
    _emit(args, project, inventory, introspection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
