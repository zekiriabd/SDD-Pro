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
from sdd_reverse.conn_string import ConnStringError, parse_connection_string
from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.dialects import UnsupportedDialect, get_dialect
from sdd_reverse.object_filter import ObjectFilter
from sdd_reverse.proc_module_clusterer import cluster_with_report
from sdd_reverse.sql_body_analyzer import complexity_reasons
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


# Qualifier tokens dropped from the MODULE name but kept in the US name so two
# User Stories of one FEAT never share a {Name} (M4, audit 2026-08-25).
_NOISE_SLUG = {
    "byid": "Par-Id", "by": "Par", "id": "Par-Id", "ids": "Par-Ids",
    "list": "Liste", "all": "Tous", "details": "Detail", "detail": "Detail",
    "info": "Info", "data": "Donnees", "rows": "Lignes", "row": "Ligne",
    "result": "Resultat", "results": "Resultats", "page": "Page",
    "paged": "Pagine", "full": "Complet", "single": "Unitaire",
}


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", text).strip()
    return "".join(w.capitalize() for w in cleaned.split()) or "Proc"


def _us_name(
    verb: str | None, module: str, fq: str, noise: list[str] | None = None,
) -> str:
    """Distinctive capability slug for ONE SQL object.

    Audit 2026-08-25 (M4): the name used to be `{Verb}-{Module}`, which collided
    for every module with more than one routine of the same verb —
    `usp_GetContactById` and `usp_GetContactList` both became
    `Consulter-Contact`. CLAUDE.md §1 is explicit that two US of one FEAT never
    share a {Name}, precisely so the disk tree stays readable without opening
    files. The qualifier tokens the module name discards are appended here.
    """
    leaf = fq.split(".")[-1]
    verb_part = _VERB_SLUG.get(verb or "", "")
    base = f"{verb_part}-{module}" if verb_part else _slug(leaf)
    qualifier = "-".join(
        _NOISE_SLUG.get(tok.lower(), _slug(tok)) for tok in (noise or [])
    )
    return f"{base}-{qualifier}" if qualifier else base


def _unique_us_name(candidate: str, taken: set[str], fq: str) -> str:
    """Guarantee uniqueness within a module, falling back to the routine name.

    The qualifier tokens close the common case; this closes the rest (e.g.
    `usp_Contact_Insert` and `usp_Contact_Add`, both verb=create with no noise
    token to tell them apart). Last resort keeps a numeric suffix so a name is
    never silently duplicated.
    """
    if candidate not in taken:
        return candidate
    with_leaf = f"{candidate}-{_slug(fq.split('.')[-1])}"
    if with_leaf not in taken:
        return with_leaf
    i = 2
    while f"{with_leaf}-{i}" in taken:
        i += 1
    return f"{with_leaf}-{i}"


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


def _prior_us_names(prior: dict | None, module: str) -> dict[str, str]:
    """`{fqName: usName}` already allocated for a module, for idempotent re-runs."""
    for u in (prior or {}).get("units", []):
        if u.get("suggestedName") == module:
            return {p["fqName"]: p.get("usName", "")
                    for p in u.get("procedures", []) if p.get("usName")}
    return {}


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
    # Clustering strategy (audit 2026-08-25). Default is AUTO: try the naming
    # heuristic, measure whether it actually groups anything, and fall back to
    # dependency cohesion when the database has no parseable convention. Two
    # escape hatches remain for a Tech Lead who knows better than the heuristic:
    #   SDD_REVERSE_CLUSTER_COHESION=1 → always cohesion
    #   SDD_REVERSE_CLUSTER_NAMING=1   → always naming (disables the fallback)
    import os

    def _flag(name: str) -> bool:
        return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")

    if _flag("SDD_REVERSE_CLUSTER_COHESION"):
        strategy: bool | None = True
    elif _flag("SDD_REVERSE_CLUSTER_NAMING"):
        strategy = False
    else:
        strategy = None                      # AUTO
    modules, cluster_report = cluster_with_report(routines, use_cohesion=strategy)

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
        prior_us_names = _prior_us_names(prior, name)

        unit_procs = []
        evidence_files = []
        min_conf = "high"
        taken_names: set[str] = set()
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
            # Idempotence beats prettiness: a proc already reversed keeps the
            # exact US name it was written under, so re-running never orphans a
            # file on disk. Only new procs get a freshly computed name.
            if p["fqName"] in prior_us_names:
                us_name = prior_us_names[p["fqName"]]
            else:
                # The routine's OWN business object, not the module it landed
                # in: after a sub-object fold (`ClientAdresse` → FEAT `Client`)
                # the two would otherwise collapse onto the same slug, and
                # CLAUDE.md §1 forbids two US of one FEAT sharing a {Name}.
                us_object = r.get("object") or name
                us_name = _unique_us_name(
                    _us_name(r.get("verb"), us_object, p["fqName"], r.get("noise")),
                    taken_names | set(prior_us_names.values()),
                    p["fqName"],
                )
            taken_names.add(us_name)
            record = {
                "spId": p["id"],
                "fqName": p["fqName"],
                "routineType": p.get("routineType", ""),
                "verb": r.get("verb"),
                "usIndex": m_index,
                "usName": us_name,
                "evidence": p.get("evidence", ""),
                "confidence": conf,
                "encrypted": p.get("encrypted", False),
                "dynamicSql": p.get("dynamicSql", False),
                "branches": p.get("branches", 0),
                "cursors": p.get("cursors", 0),
                # M2 — the complexity rubric now weighs volume and contract
                # width, so they must travel with the unit record.
                "lineCount": p.get("lineCount", 0),
                "params": p.get("params", []),
                "tablesWritten": p.get("tablesWritten", []),
                "tablesRead": p.get("tablesRead", []),
                "raises": p.get("raises", []),
                "hasTransaction": p.get("hasTransaction", False),
            }
            # Carry the routing decision AND its justification into the
            # inventory, so build_proc_us, the US banner and the audit trail all
            # agree on why an LLM was (or was not) spent on this object.
            reasons = complexity_reasons(record)
            record["complexity"] = "simple" if p.get("encrypted") else (
                "complex" if reasons else "simple")
            record["complexityReasons"] = reasons
            unit_procs.append(record)

        units.append({
            "id": uid,
            "label": f"Module {module} ({len(members)} procédure(s))",
            "suggestedName": name,
            "language": introspection.get("languageId", "tsql"),
            "kind": "db-module",
            "source": "db-reverse",
            "confidenceEstimate": min_conf,
            "evidenceFiles": [e for e in evidence_files if e],
            "procedures": unit_procs,
        })

    return {
        "schemaVersion": 1,
        "project": project,
        "source": "db-reverse",
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
        # How the modules were decided — naming vs dependency cohesion,
        # with the measured fragmentation that drove the choice.
        "_clusteringReport": cluster_report,
    }


def _clustering_summary(report: dict) -> str:
    """One-clause French summary of HOW the modules were decided.

    Audit 2026-08-25: the strategy, the fragmentation that drove it and the
    sub-object folds were written to `_clusteringReport` in the inventory JSON
    and nowhere else. A Tech Lead reading the chat had no way to know that his
    FEATs came from the dependency graph rather than from the object names —
    the single most consequential decision of the whole DB reverse, since it
    determines the FEAT découpage. `rules/output-protocol.md §6` allows exactly
    this: a business-level result clause on the existing 1-line update.
    """
    strategy = (report or {}).get("strategy", "")
    frag = (report or {}).get("fragmentation")
    merges = len((report or {}).get("subObjectMerges") or {})
    fold = f", {merges} sous-objet(s) rattaché(s)" if merges else ""
    if strategy == "cohesion":
        detail = (f" (fragmentation {frag:.2f})"
                  if isinstance(frag, (int, float)) else "")
        return f"regroupement par cohésion — nommage inexploitable{detail}"
    if (report or {}).get("degraded"):
        detail = (f" {frag:.2f}" if isinstance(frag, (int, float)) else "")
        return (f"regroupement par nommage — dégradé, fragmentation{detail} "
                f"et la cohésion ne fait pas mieux{fold}")
    return f"regroupement par nommage{fold}"


def _emit(args, project, inventory, introspection):
    units = inventory["units"]
    nproc = introspection.get("summary", {}).get("proceduresCount", 0)
    nenc = introspection.get("summary", {}).get("encryptedCount", 0)
    report = inventory.get("_clusteringReport", {}) or {}
    if args.json:
        print(json.dumps({
            "project": project, "modules": len(units), "procedures": nproc,
            "encrypted": nenc,
            "allocations": inventory["_featAllocations"],
            "clustering": report,
        }, ensure_ascii=False, indent=2))
    else:
        # N2 (audit 2026-08-25): "procédure(s)" undercounts what actually ran —
        # the same pass introspects functions, views, triggers and Oracle
        # packages. The count was already all of them; only the word was wrong.
        enc = f", {nenc} chiffré(s)" if nenc else ""
        print(f"[REVERSE] DB {project} → {nproc} objet(s) SQL{enc} "
              f"regroupé(s) en {len(units)} module(s)/FEAT — "
              f"{_clustering_summary(report)}. (Phase 1 OK)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase 1 stored-procedure reverse (read-only).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--full", action="store_true", help="introspect all routines")
    g.add_argument("--proc", help="introspect a single routine ([schema.]name)")
    g.add_argument("--from-introspection", help="replay an existing db-introspection.json (no DB)")
    ap.add_argument("--project", help="legacy project dir name under workspace/old/ (default = DB_NAME)")
    ap.add_argument("--stack", default=DEFAULT_STACK, help="path to stack.md")
    ap.add_argument("--workspace", default="workspace", help="workspace root")
    # M6 — accept the form the Tech Lead actually has, instead of forcing a
    # manual decomposition into stack.md keys before anything can run.
    ap.add_argument("--conn-str", dest="conn_str", default=None,
                    help="full connection string (ADO.NET/ODBC, JDBC, URI, libpq "
                         "DSN or Oracle easy-connect) — overrides stack.md")
    ap.add_argument("--db-type", default=None,
                    help="DatabaseType override / hint when --conn-str omits the engine")
    # M6 — scope control, so a 3000-object database is runnable at all.
    ap.add_argument("--schema", action="append", default=[],
                    help="restrict to these schemas (repeatable or comma-separated)")
    ap.add_argument("--include", action="append", default=[],
                    help="only objects matching these globs (e.g. 'usp_Invoice*')")
    ap.add_argument("--exclude", action="append", default=[],
                    help="skip objects matching these globs (e.g. 'usp_Debug*')")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap the number of objects (reports what it dropped)")
    ap.add_argument("--no-schema", action="store_true",
                    help="skip the live structure read (tables/columns/keys/jobs)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    # Audit 2026-08-25: `_emit` prints `→`, which raised UnicodeEncodeError on a
    # cp1252 Windows console (the default on the machines this framework targets).
    # It never surfaced in tests because pytest captures stdout as UTF-8 — only a
    # real terminal hit it. Every other reverse script already guards this way.
    ensure_console_safe()

    ws = Path(args.workspace)
    feats_dir = ws / "feats"

    def _load_json(p: Path):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    obj_filter = ObjectFilter(schemas=args.schema, include=args.include,
                              exclude=args.exclude, limit=args.limit)
    try:
        if args.from_introspection:
            introspection = json.loads(Path(args.from_introspection).read_text(encoding="utf-8"))
            project = args.project or introspection.get("database") or "Database"
            project_root = ws / "old" / project
        else:
            if args.conn_str:
                # M6 — a connection string is the primary input, no manual
                # decomposition into stack.md required. Never logged.
                cfg = parse_connection_string(
                    args.conn_str, db_type_hint=(args.db_type or "")).to_db_config()
            else:
                cfg = read_db_config(args.stack)
                if args.db_type:
                    cfg.db_type = args.db_type
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
                with_schema=not args.no_schema,
                obj_filter=obj_filter,
            )
            if args.proc and prior_introspection:
                introspection = dbi.merge_introspection(prior_introspection, new_model)
                atomic_write_text(
                    project_root / ".sys" / dbi._INTROSPECTION_NAME,
                    json.dumps(introspection, indent=2, ensure_ascii=False) + "\n",
                )
            else:
                introspection = new_model
    except (StackConfigError, UnsupportedDialect, ConnStringError,
            dbi.ReverseDbError) as exc:
        print("ERROR: db-reverse Phase 1 failed", file=sys.stderr)
        print(f"CAUSE: {exc}", file=sys.stderr)
        sys.stderr.write("FIX: vérifier '## Active Database' de stack.md (ou "
                         "--conn-str) + accès lecture seule.\n")
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
