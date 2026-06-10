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
from sdd_reverse.db_schema_extractor import extract_db_schema
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
    """Extract pages from detected UI-style files (aspx, cshtml, jsp, php, blade)."""
    pages: list[dict[str, Any]] = []
    page_id = 1
    ui_extensions = {
        ".aspx", ".cshtml", ".vbhtml", ".jsp", ".jspx", ".xhtml",
        ".php", ".blade.php", ".twig", ".pas",
    }
    for lm in scan_result.languages:
        for f in lm.files:
            ext = f.suffix.lower()
            if ext not in ui_extensions:
                continue
            rel = str(f.relative_to(project_root).as_posix())
            # Find code-behind (e.g. .aspx → .aspx.cs)
            cb_candidates = [
                f.with_suffix(f.suffix + ".cs"),
                f.with_suffix(".aspx.cs") if ext == ".aspx" else None,
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
        lines.append(f"  - Evidence : {', '.join(f'`{e}`' for e in u['evidenceFiles'][:5])}")
        lines.append(f"  - Rationale : {u['rationale']}")
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
    args = parser.parse_args(argv)

    project_root = Path(args.project).resolve()
    if not project_root.is_dir():
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
    sig_path = Path(__file__).parent.parent / "sdd_reverse" / "language_signatures.yml"
    signatures = load_signatures(sig_path)

    # Scan
    scan_result = scan_project(project_root, signatures)
    if scan_result.files_scanned == 0:
        print(
            f"ERROR: no source files matched any language. "
            f"workspace/old/{project_name}/ may be empty or all binary.",
            file=sys.stderr,
        )
        return 2

    # Pages + units
    pages = _build_pages_list(scan_result, project_root)
    units = detect_units(pages, project_root, signatures)
    # Link pages → units (heuristic: same path in evidenceFiles)
    for u in units:
        for p in pages:
            if p["path"] in u["evidenceFiles"]:
                p.setdefault("linkedUnits", [])
                # We'll patch linkedUnits after build_inventory assigns U-N
                p["linkedUnits"].append(u["label"])  # placeholder

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

    # DB schema
    db_schema = extract_db_schema(project_root, scan_result)

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
    atomic_write_text(sys_dir / "inventory.md", _render_inventory_md(inventory, project_name) + "\n")
    atomic_write_text(sys_dir / "db-schema.json", json.dumps(db_schema, indent=2, ensure_ascii=False) + "\n")
    atomic_write_text(sys_dir / "db-schema.md", _render_db_schema_md(db_schema) + "\n")
    atomic_write_text(sys_dir / "language-detected.json", json.dumps(lang_detected, indent=2, ensure_ascii=False) + "\n")

    if args.json:
        print(json.dumps({
            "ok": True,
            "project": project_name,
            "primaryLanguage": inventory["primaryLanguage"],
            "unitsDetected": len(inventory["units"]),
            "entitiesDetected": len(db_schema["entities"]),
            "filesScanned": scan_result.files_scanned,
            "outputs": {
                "inventory_json": str(inventory_path.relative_to(project_root.parent.parent.parent)),
                "db_schema_json": str((sys_dir / "db-schema.json").relative_to(project_root.parent.parent.parent)),
            },
        }))
    else:
        print(f"[REVERSE] Inventory: {len(inventory['units'])} units, "
              f"{len(db_schema['entities'])} entities, "
              f"primary language: {inventory['primaryLanguage']} ({scan_result.files_scanned} files). (100%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
