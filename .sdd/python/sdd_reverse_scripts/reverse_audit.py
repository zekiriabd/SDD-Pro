"""reverse_audit.py — Phase 2 orchestrator CLI (audit + enrichment).

Invocation:
    python -m sdd_reverse_scripts.reverse_audit --project workspace/old/{P}/

Outputs under workspace/old/{P}/.sys/ :
    deps-graph.json              (internal edges + external EOL hints + cycles + dead code)
    db-schema.enrichment.json    (skeleton — agent fills with addedRelations/addedFields)
    db-schema.merged.json        (computed: base + enrichment via merge_db_schema)

Note: this script produces machine artifacts. The tech-auditor AGENT
(.claude/agents/reverse-tech-auditor.md) enriches tech-audit.md (FR
narrative). The agent does NOT write JSON outputs.

Exit codes:
    0  OK
    1  invalid arguments / project root missing
    2  Phase 1 inventory.json absent
    3  I/O error
    4  merge conflicts ADV-3 hard-fail
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.deps_graph_builder import build_deps_graph
from sdd_reverse.merge_db_schema import merge_schemas
from sdd_reverse.scan_legacy import load_signatures, scan_project


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    parser = argparse.ArgumentParser(
        prog="reverse_audit",
        description="Phase 2 reverse engineering: tech audit + deps graph + db-schema enrichment merge.",
    )
    parser.add_argument("--project", required=True,
        help="Path to workspace/old/{P}/ (project legacy root)")
    parser.add_argument("--force-enrichment-on", action="append", default=[],
        metavar="Entity.field",
        help="ADV-12: allow enrichment to override base on this field (repeatable)")
    parser.add_argument("--json", action="store_true",
        help="Emit summary as JSON on stdout")
    args = parser.parse_args(argv)

    project_root = Path(args.project).resolve()
    if not project_root.is_dir():
        print(f"ERROR: project root not found: {project_root}", file=sys.stderr)
        return 1

    sys_dir = project_root / ".sys"
    inventory_path = sys_dir / "inventory.json"
    if not inventory_path.is_file():
        print(f"ERROR: [REVERSE_NO_SOURCE] Phase 1 inventory.json missing — run /sdd-reverse-inventory first",
              file=sys.stderr)
        return 2

    # Load Phase 1 outputs
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: inventory.json unreadable: {e}", file=sys.stderr)
        return 3

    # Re-scan to get scan_result (needed for deps_graph_builder)
    # P1.7 closure — use paths helper instead of fragile __file__ walk
    from sdd_reverse.paths import language_signatures_path
    signatures = load_signatures(language_signatures_path())
    scan_result = scan_project(project_root, signatures)

    # Phase 1 code-graph.json — the strong (type-usage) edge resolver. Consumed
    # instead of re-deriving internal edges from the weaker namespace+using
    # heuristic, which resolved nothing at all on namespace-less legacy such as
    # WebForms App_Code/ and therefore reported the whole app as dead code
    # (audit F-03). Absent/corrupt file → rebuild in-memory from scan_result
    # rather than silently degrading to the weak heuristic.
    code_graph: dict | None = None
    code_graph_path = sys_dir / "code-graph.json"
    if code_graph_path.is_file():
        try:
            loaded = json.loads(code_graph_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                code_graph = loaded
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARN: [REVERSE_NO_SOURCE] code-graph.json unreadable ({e}) — rebuilding in memory",
                  file=sys.stderr)
    if code_graph is None:
        from sdd_reverse.code_graph_builder import build_code_graph
        code_graph = build_code_graph(project_root, scan_result)

    # Build deps graph
    deps_graph = build_deps_graph(project_root, scan_result, code_graph=code_graph)
    atomic_write_text(sys_dir / "deps-graph.json",
                       json.dumps(deps_graph, indent=2, ensure_ascii=False) + "\n")

    # Skeleton enrichment file (the agent fills it, but we create the file
    # so the agent has a known target path)
    enrichment_path = sys_dir / "db-schema.enrichment.json"
    if not enrichment_path.is_file():
        atomic_write_text(enrichment_path, json.dumps({
            "schemaVersion": 1,
            "enrichmentDate": None,
            "addedRelations": [],
            "addedIndexes": [],
            "addedConstraints": [],
            "addedFields": [],
        }, indent=2) + "\n")

    # Merge base + enrichment (idempotent — if enrichment is empty, merged ≈ base)
    base_path = sys_dir / "db-schema.json"
    if base_path.is_file() and enrichment_path.is_file():
        try:
            base = json.loads(base_path.read_text(encoding="utf-8"))
            enrichment = json.loads(enrichment_path.read_text(encoding="utf-8"))
            merged, conflicts = merge_schemas(base, enrichment, set(args.force_enrichment_on))
            merged_path = sys_dir / "db-schema.merged.json"
            atomic_write_text(merged_path,
                               json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
        except ValueError as e:
            print(f"ERROR: [REVERSE_ENRICHMENT_INVALID] {e}", file=sys.stderr)
            return 4
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: I/O during merge: {e}", file=sys.stderr)
            return 3
    else:
        conflicts = []

    if args.json:
        print(json.dumps({
            "ok": True,
            "project": inventory.get("project"),
            "internalEdges": deps_graph["internalEdgesTotal"],
            "externalDeps": len(deps_graph["externalDeps"]),
            "eolDeps": sum(1 for d in deps_graph["externalDeps"] if d.get("eol")),
            "cyclesDetected": len(deps_graph["cyclesDetected"]),
            "deadCodeHints": len(deps_graph["deadCodeHint"]),
            "mergeConflicts": len(conflicts),
        }, ensure_ascii=False))
    else:
        eol_count = sum(1 for d in deps_graph["externalDeps"] if d.get("eol"))
        print(f"[REVERSE] Audit: {deps_graph['internalEdgesTotal']} internal edges, "
              f"{len(deps_graph['externalDeps'])} external deps "
              f"({eol_count} EOL), {len(deps_graph['cyclesDetected'])} cycles, "
              f"{len(deps_graph['deadCodeHint'])} dead code hints. (25%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
