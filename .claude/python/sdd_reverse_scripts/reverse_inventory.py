"""reverse_inventory.py — Phase 1 orchestrator CLI.

Invocation:
    python -m sdd_reverse_scripts.reverse_inventory --project workspace/old/{P}/

Outputs (under workspace/old/{P}/.sys/) :
    inventory.json      (machine, design doc §5.1)
    inventory.md        (FR, lecture humaine — squelette ; agent enrichit)
    db-schema.json      (basic, D7, §5.2)
    db-schema.md        (FR squelette)
    language-detected.json (§5.3)

Exit codes :
    0  OK
    1  invalid arguments / project root missing
    2  no source files detected (empty legacy)
    3  I/O error
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.code_graph_builder import build_code_graph, enrich_units
from sdd_reverse.code_unit_detector import detect_code_units
from sdd_reverse.config_extractor import extract_config
from sdd_reverse.data_access_extractor import extract_data_access
from sdd_reverse.db_schema_extractor import extract_db_schema
from sdd_reverse.dependency_inventory import extract_dependencies
from sdd_reverse.inventory_builder import build_inventory, validate_inventory_schema
from sdd_reverse.scan_legacy import load_signatures, scan_project
from sdd_reverse.ui_unit_detector import detect_units


# Bug #2 fix: entry-point detection heuristics
ENTRY_POINT_PATTERNS = {
    # filename (lowercase) → (type, description)
    "global.asax": ("lifecycle", "ASP.NET application events (Application_Start, Session_Start)"),
    "global.asax.cs": ("lifecycle", "ASP.NET application code-behind"),
    "startup.cs": ("lifecycle", ".NET Core/Framework Startup configuration"),
    "program.cs": ("lifecycle", ".NET entry point (Main method)"),
    "webapiconfig.cs": ("router", "Web API route configuration"),
    "routeconfig.cs": ("router", "MVC route configuration"),
    "default.aspx": ("landing", "ASP.NET default landing page"),
    "home.aspx": ("landing", "Home landing page"),
    "index.aspx": ("landing", "Index landing page"),
    "index.php": ("landing", "PHP default entry"),
    "index.jsp": ("landing", "JSP default entry"),
    "main.java": ("lifecycle", "Java Main class"),
    "application.java": ("lifecycle", "Spring Boot Application"),
    "web.xml": ("config", "Java EE servlet configuration"),
    "web.config": ("config", ".NET application configuration"),
    "application.properties": ("config", "Spring Boot properties"),
    "application.yml": ("config", "Spring Boot YAML config"),
    "pom.xml": ("manifest", "Maven build manifest"),
    "package.json": ("manifest", "Node.js package manifest"),
    "composer.json": ("manifest", "PHP Composer manifest"),
    "requirements.txt": ("manifest", "Python pip requirements"),
}


def _detect_entry_points(scan_result, project_root: Path) -> list[dict[str, Any]]:
    """Detect entry points (Bug #2 fix). Scans for well-known filenames."""
    entry_points: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lm in scan_result.languages:
        for f in lm.files:
            key = f.name.lower()
            if key in ENTRY_POINT_PATTERNS and key not in seen:
                etype, edesc = ENTRY_POINT_PATTERNS[key]
                rel = str(f.relative_to(project_root).as_posix())
                entry_points.append({"path": rel, "type": etype, "description": edesc})
                seen.add(key)
    # Also scan files NOT matched by any language (manifest files like Web.config
    # which might not be in any file_extensions). Use rglob direct.
    for known_name in ENTRY_POINT_PATTERNS:
        if known_name in seen:
            continue
        for p in project_root.rglob(known_name):
            if not p.is_file():
                continue
            if any(part in {".git", "bin", "obj", "packages", "node_modules", "vendor"} for part in p.parts):
                continue
            etype, edesc = ENTRY_POINT_PATTERNS[known_name]
            entry_points.append({
                "path": str(p.relative_to(project_root).as_posix()),
                "type": etype,
                "description": edesc,
            })
            seen.add(known_name)
            break  # one per filename
    return entry_points


def _build_pages_list(scan_result, project_root: Path) -> list[dict[str, Any]]:
    """Extract pages from detected UI-style files (aspx, cshtml, jsp, php, blade, xaml).

    `.xaml` added 2026-06-10 — WPF Window/Page/UserControl files. Code-behind
    discovery looks for the canonical `.xaml.cs` companion.
    """
    pages: list[dict[str, Any]] = []
    page_id = 1
    ui_extensions = {
        ".aspx", ".cshtml", ".vbhtml", ".jsp", ".jspx", ".xhtml",
        ".php", ".blade.php", ".twig", ".pas",
        ".xaml",  # WPF (2026-06-10)
    }
    for lm in scan_result.languages:
        for f in lm.files:
            ext = f.suffix.lower()
            if ext not in ui_extensions:
                continue
            rel = str(f.relative_to(project_root).as_posix())
            # Find code-behind (e.g. .aspx → .aspx.cs, .xaml → .xaml.cs)
            cb_candidates = [
                f.with_suffix(f.suffix + ".cs"),
                f.with_suffix(".aspx.cs") if ext == ".aspx" else None,
                f.with_suffix(".xaml.cs") if ext == ".xaml" else None,
                f.with_suffix(".xaml.vb") if ext == ".xaml" else None,
            ]
            code_behind = None
            for cb in cb_candidates:
                if cb and cb.is_file():
                    code_behind = str(cb.relative_to(project_root).as_posix())
                    break
            try:
                loc_total = sum(1 for line in f.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
            except OSError:
                loc_total = 0
            pages.append({
                "id": f"P-{page_id}",
                "path": rel,
                "codeBehindPath": code_behind,
                "locTotal": loc_total,
                "linkedUnits": [],
            })
            page_id += 1
    return pages


def _render_inventory_md(inventory: dict[str, Any], project_name: str) -> str:
    """Skeleton FR inventory.md — the agent enriches it."""
    lines = [
        f"# Inventaire — {project_name}",
        "",
        f"**Date scan** : {inventory['scanDate']}",
        f"**Durée scan** : {inventory['scanDurationMs']} ms",
        f"**Langage principal** : `{inventory.get('primaryLanguage') or 'inconnu'}`",
        "",
        "## Langages détectés",
        "",
        "| ID | Label | Confiance | Fichiers | LOC |",
        "|---|---|---|---:|---:|",
    ]
    for lang in inventory["languagesDetected"]:
        lines.append(
            f"| `{lang['id']}` | {lang['label']} | {lang['confidence']} | "
            f"{lang['filesCount']} | {lang['locTotal']} |"
        )
    lines.extend(["", "## Frameworks détectés", ""])
    if inventory["frameworksDetected"]:
        for fw in inventory["frameworksDetected"]:
            ver = fw.get("version") or "n/a"
            lines.append(f"- `{fw['id']}` (version : {ver}) — evidence : `{fw['evidence']}`")
    else:
        lines.append("_Aucun framework signé._")
    lines.extend(["", f"## Pages ({len(inventory['pages'])})", ""])
    for p in inventory["pages"][:30]:
        cb = f" / code-behind `{p['codeBehindPath']}`" if p.get("codeBehindPath") else ""
        lines.append(f"- `{p['path']}`{cb} — {p['locTotal']} LOC, lié à {p.get('linkedUnits', [])}")
    if len(inventory["pages"]) > 30:
        lines.append(f"- _… ({len(inventory['pages']) - 30} autres pages)_")
    lines.extend(["", f"## Unités fonctionnelles candidates ({len(inventory['units'])})", ""])
    for u in inventory["units"]:
        lines.append(
            f"- **{u['id']}** — {u['label']} _(suggéré: `{u['suggestedName']}`)_ "
            f"— kind: {u['kind']}, confiance: {u['confidenceEstimate']}"
        )
        seed = u.get("seedEvidenceFiles") or u["evidenceFiles"]
        lines.append(f"  - Seed : {', '.join(f'`{e}`' for e in seed[:5])}")
        deep = [e for e in u["evidenceFiles"] if e not in seed]
        if deep:
            lines.append(
                f"  - Evidence profonde (graphe) : "
                f"{', '.join(f'`{e}`' for e in deep[:10])}"
                + (f" _… (+{len(deep) - 10})_" if len(deep) > 10 else "")
            )
        classes = u.get("classes") or []
        if classes:
            by_role: dict[str, list[str]] = {}
            for c in classes:
                by_role.setdefault(c["role"], []).append(c["name"])
            role_str = "; ".join(
                f"{role}: {', '.join(sorted(names))}"
                for role, names in sorted(by_role.items())
            )
            lines.append(f"  - Classes ({len(classes)}) — {role_str}")
        if u.get("entities"):
            lines.append(f"  - Entités : {', '.join(u['entities'])}")
        da = u.get("dataAccess") or {}
        if da.get("queries") or da.get("storedProcedureCalls"):
            q = len(da.get("queries", []))
            sp = len(da.get("storedProcedureCalls", []))
            lines.append(f"  - Accès données : {q} requête(s) SQL, {sp} appel(s) de procédure")
            for query in da.get("queries", [])[:3]:
                lines.append(
                    f"    - `{query['verb']}` sur {query.get('tables') or '?'} "
                    f"(`{query['file']}:{query['line']}`)"
                )
        lines.append(f"  - Rationale : {u['rationale']}")
    lines.append("")
    return "\n".join(lines)


def _render_tech_summary_md(
    code_graph: dict[str, Any],
    data_access: dict[str, Any],
    config: dict[str, Any],
    dependencies: dict[str, Any],
) -> str:
    """Project-level technical synthesis (L1) appended to inventory.md."""
    lines = ["", "## Synthèse technique (L1)", ""]
    roles = code_graph.get("rolesSummary", {})
    if roles:
        lines.append("**Classes par rôle** : " + ", ".join(
            f"{role}: {n}" for role, n in sorted(roles.items())
        ))
    da = data_access.get("summary", {})
    lines.append(
        f"**Accès données** : {da.get('queriesCount', 0)} requête(s) SQL inline, "
        f"{da.get('procCallsCount', 0)} appel(s) de procédure, "
        f"{da.get('procDefsCount', 0)} procédure(s) stockée(s) définie(s)."
    )
    procs = data_access.get("storedProcedureDefs", [])
    if procs:
        lines.append("")
        lines.append("**Procédures stockées** :")
        for p in procs[:20]:
            params = ", ".join(
                f"{x['name']} {x['type']}{' OUT' if x.get('output') else ''}"
                for x in p.get("params", [])
            )
            lines.append(f"- `{p['name']}` ({params}) — `{p['file']}:{p['line']}`")
    cs = config.get("connectionStrings", [])
    if cs:
        lines.append("")
        lines.append(f"**Connection strings ({len(cs)})** :")
        for c in cs[:10]:
            lines.append(
                f"- `{c['name']}` → provider `{c.get('provider') or '?'}`, "
                f"server `{c.get('server') or '?'}`, db `{c.get('database') or '?'}` "
                f"(`{c['file']}:{c['line']}`)"
            )
    deps = dependencies.get("packages", [])
    if deps:
        lines.append("")
        lines.append(f"**Librairies à installer ({len(deps)})** :")
        for p in deps[:40]:
            ver = p.get("version") or "?"
            lines.append(f"- `{p['name']}` {ver} ({p['ecosystem']}) — `{p.get('evidence', '?')}`")
    refs = dependencies.get("assemblyReferences", [])
    if refs:
        lines.append("")
        lines.append(f"**Références d'assembly ({len(refs)})** :")
        for r in refs[:20]:
            hp = f" → `{r['hintPath']}`" if r.get("hintPath") else " (GAC/SDK)"
            lines.append(f"- `{r['name']}`{hp}")
    lines.append("")
    return "\n".join(lines)


def _render_db_schema_md(schema: dict[str, Any]) -> str:
    lines = [
        f"# Schéma DB — {schema['project']}",
        "",
        f"**Date extraction** : {schema['extractDate']}",
        f"**Type DB** : {schema['databaseType']}",
        f"**Complétude** : {schema['completeness']}",
        f"**Sources** : {schema['source']}",
        "",
    ]
    if schema.get("missingPartsHint"):
        lines.append("> ⚠️ " + "\n> ".join(schema["missingPartsHint"]))
        lines.append("")
    lines.extend([f"## Entités ({len(schema['entities'])})", ""])
    for e in schema["entities"]:
        lines.append(f"### {e['name']} (table `{e['table']}`)")
        lines.append("")
        if e.get("fields"):
            lines.extend(["| Champ | Type | PK | Nullable | Default |", "|---|---|:---:|:---:|---|"])
            for f in e["fields"]:
                pk = "✓" if f.get("primaryKey") else ""
                nullable = "✓" if f.get("nullable") else ""
                default = f.get("default") or ""
                lines.append(f"| `{f['name']}` | `{f['type']}` | {pk} | {nullable} | {default} |")
        lines.extend(["", f"Evidence : {', '.join(e.get('evidence', []))}", ""])
    if schema.get("relations"):
        lines.extend([f"## Relations ({len(schema['relations'])})", ""])
        for r in schema["relations"]:
            lines.append(
                f"- `{r['name']}` : {r['from']['entity']}.{r['from']['field']} → "
                f"{r['to']['entity']}.{r['to']['field']} ({r['type']})"
            )
            lines.append(f"  - Evidence : {r.get('evidence', 'n/a')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reverse_inventory",
        description="Phase 1 reverse engineering: scan + inventory + DB schema basic.",
    )
    parser.add_argument("--project", required=True,
        help="Path to workspace/old/{P}/ (project legacy root)")
    parser.add_argument("--use-cache", action="store_true",
        help="Skip scan if inventory.json exists AND passes schema gate (ADV-23)")
    parser.add_argument("--json", action="store_true",
        help="Emit progress as JSON lines on stdout")
    parser.add_argument("--structured-log", action="store_true",
        help="Emit structured JSON events on stderr (P3.14 observability).")
    args = parser.parse_args(argv)

    # P3.14 — structured logging opt-in (CLI flag OR env var SDD_REVERSE_LOG)
    if args.structured_log:
        from sdd_reverse.structured_log import install_default_handler, get_logger, log_event
        install_default_handler()
        _log = get_logger("reverse_inventory")
        log_event(_log, "phase1.start", project=str(Path(args.project).resolve()))
    else:
        _log = None

    project_root = Path(args.project).resolve()
    if not project_root.is_dir():
        if _log is not None:
            from sdd_reverse.structured_log import log_event
            log_event(_log, "phase1.error", level="ERROR",
                      reason="project_root_missing", path=str(project_root))
        print(f"ERROR: project root not found: {project_root}", file=sys.stderr)
        return 1

    project_name = project_root.name
    sys_dir = project_root / ".sys"
    sys_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = sys_dir / "inventory.json"
    existing_inventory: dict[str, Any] | None = None
    if args.use_cache and inventory_path.is_file():
        try:
            existing_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing_inventory = None
        if existing_inventory:
            ok, reason = validate_inventory_schema(existing_inventory)
            if not ok:
                print(
                    f"INFO: [REVERSE_INVENTORY_SCHEMA_STALE] cache rejected ({reason}); "
                    f"forcing refresh.",
                    file=sys.stderr,
                )
                existing_inventory = None

    # Load signatures
    # P1.7 closure — use paths helper instead of fragile __file__ walk
    from sdd_reverse.paths import language_signatures_path
    signatures = load_signatures(language_signatures_path())

    # Scan
    scan_result = scan_project(project_root, signatures)
    if scan_result.files_scanned == 0:
        print(
            f"ERROR: no source files matched any language. "
            f"workspace/old/{project_name}/ may be empty or all binary.",
            file=sys.stderr,
        )
        return 2

    # DB schema (extracted early so entity names can inform L0 class-role
    # classification — a class matching a DB table is tagged `entity`).
    db_schema = extract_db_schema(project_root, scan_result)
    known_entity_names = frozenset(
        e.get("name", "") for e in db_schema.get("entities", []) if e.get("name")
    )

    # Pages + units
    pages = _build_pages_list(scan_result, project_root)
    units = detect_units(pages, project_root, signatures)
    # Link pages → units (heuristic: same path in seed evidenceFiles). Done
    # before enrichment so links stay anchored to the page, not deep classes.
    for u in units:
        for p in pages:
            if p["path"] in u["evidenceFiles"]:
                p.setdefault("linkedUnits", [])
                # We'll patch linkedUnits after build_inventory assigns U-N
                p["linkedUnits"].append(u["label"])  # placeholder

    # L0 — symbol-level code graph + transitive evidence enrichment. Follows the
    # class reference chain page→code-behind→service→repository→… so the deep
    # business layer becomes visible (classes + role) and readable (evidence).
    code_graph = build_code_graph(
        project_root, scan_result, known_entity_names=known_entity_names
    )
    # L2 — code-driven units (controllers + orphan backend modules) so that
    # backend/API-only legacies (no UI page) still produce functional units.
    code_units = detect_code_units(
        code_graph, units, language=scan_result.primary_language
    )
    units = units + code_units
    enrich_units(units, code_graph)
    for u in units:
        # Pin the U-N fingerprint to the seed (page + code-behind), not the
        # enriched set — graph-walk changes must never destabilise U-N IDs.
        u["fingerprintSeed"] = u.get("seedEvidenceFiles") or u["evidenceFiles"]

    # L1 — deep technical extraction (project-wide artefacts).
    data_access = extract_data_access(project_root, scan_result)
    config = extract_config(project_root, scan_result)
    dependencies = extract_dependencies(project_root, scan_result)

    # Attach per-unit data-access summary: queries / proc-calls whose source
    # file is part of the unit's (enriched) evidence.
    for u in units:
        files = set(u.get("evidenceFiles", []))
        u["dataAccess"] = {
            "queries": [q for q in data_access["queries"] if q["file"] in files],
            "storedProcedureCalls": [
                c for c in data_access["storedProcedureCalls"] if c["file"] in files
            ],
        }

    # Bug #2 fix: detect entry points
    entry_points = _detect_entry_points(scan_result, project_root)

    # Build inventory (assigns U-N)
    inventory = build_inventory(
        project_name, project_root, scan_result, pages, units,
        signatures, existing_inventory, entry_points=entry_points,
    )

    # Patch pages.linkedUnits to actual U-N ids
    label_to_uid = {u["label"]: u["id"] for u in inventory["units"]}
    for p in inventory["pages"]:
        p["linkedUnits"] = sorted({
            label_to_uid.get(lbl, lbl) for lbl in p.get("linkedUnits", [])
        })

    # language-detected.json (§5.3)
    caps_applied = {
        lm.id: lm.confidence_cap for lm in scan_result.languages
    }
    lang_detected = {
        "schemaVersion": 1,
        "primary": scan_result.primary_language,
        "secondary": [lm.id for lm in scan_result.languages[1:]],
        "confidence_caps_applied": caps_applied,
        "_caps_source": ".claude/python/sdd_reverse/language_signatures.yml",
    }

    # Write all artefacts
    atomic_write_text(inventory_path, json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
    atomic_write_text(sys_dir / "code-graph.json", json.dumps(code_graph, indent=2, ensure_ascii=False) + "\n")
    atomic_write_text(sys_dir / "data-access.json", json.dumps(data_access, indent=2, ensure_ascii=False) + "\n")
    atomic_write_text(sys_dir / "config.json", json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    atomic_write_text(sys_dir / "dependencies.json", json.dumps(dependencies, indent=2, ensure_ascii=False) + "\n")
    inventory_md = (
        _render_inventory_md(inventory, project_name)
        + _render_tech_summary_md(code_graph, data_access, config, dependencies)
    )
    atomic_write_text(sys_dir / "inventory.md", inventory_md + "\n")
    atomic_write_text(sys_dir / "db-schema.json", json.dumps(db_schema, indent=2, ensure_ascii=False) + "\n")
    atomic_write_text(sys_dir / "db-schema.md", _render_db_schema_md(db_schema) + "\n")
    atomic_write_text(sys_dir / "language-detected.json", json.dumps(lang_detected, indent=2, ensure_ascii=False) + "\n")

    # P3.14 — structured completion event
    if _log is not None:
        from sdd_reverse.structured_log import log_event
        log_event(_log, "phase1.complete",
                  project=project_name,
                  primary_language=inventory["primaryLanguage"],
                  units_detected=len(inventory["units"]),
                  entities_detected=len(db_schema["entities"]),
                  files_scanned=scan_result.files_scanned,
                  files_skipped=scan_result.files_skipped,
                  duration_ms=scan_result.duration_ms)

    if args.json:
        print(json.dumps({
            "ok": True,
            "project": project_name,
            "primaryLanguage": inventory["primaryLanguage"],
            "unitsDetected": len(inventory["units"]),
            "entitiesDetected": len(db_schema["entities"]),
            "classesAnalyzed": len(code_graph.get("classes", [])),
            "sqlQueries": data_access["summary"]["queriesCount"],
            "storedProcs": data_access["summary"]["procDefsCount"] + data_access["summary"]["procCallsCount"],
            "connectionStrings": config["summary"]["connectionStringsCount"],
            "dependencies": dependencies["summary"]["packagesCount"],
            "filesScanned": scan_result.files_scanned,
            "rolesSummary": code_graph.get("rolesSummary", {}),
            "outputs": {
                "inventory_json": str(inventory_path.relative_to(project_root.parent.parent.parent)),
                "db_schema_json": str((sys_dir / "db-schema.json").relative_to(project_root.parent.parent.parent)),
                "code_graph_json": str((sys_dir / "code-graph.json").relative_to(project_root.parent.parent.parent)),
                "data_access_json": str((sys_dir / "data-access.json").relative_to(project_root.parent.parent.parent)),
                "config_json": str((sys_dir / "config.json").relative_to(project_root.parent.parent.parent)),
                "dependencies_json": str((sys_dir / "dependencies.json").relative_to(project_root.parent.parent.parent)),
            },
        }))
    else:
        print(f"[REVERSE] Inventory: {len(inventory['units'])} units, "
              f"{len(code_graph.get('classes', []))} classes, "
              f"{len(db_schema['entities'])} entities, "
              f"primary language: {inventory['primaryLanguage']} ({scan_result.files_scanned} files). (100%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
