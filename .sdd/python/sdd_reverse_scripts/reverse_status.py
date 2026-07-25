"""reverse_status.py — Diagnostic CLI for reverse engineering workflow.

Invocation:
    python -m sdd_reverse_scripts.reverse_status [--project workspace/old/{P}/] [--json]

Reports:
    - All legacy projects under workspace/old/
    - For each: phase status (init / inventory / audit / feat-extracted / ui-extracted)
    - All reverse FEATs in workspace/feats/ with [REV] / [REV⚠️] markers (ADV-6)

Exit codes:
    0  reported successfully (even if some phases incomplete — diagnostic, never blocking)
    1  no workspace/old/ directory
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.feat_structure_spec import REVERSE_GATE_RE, parse_frontmatter
from sdd_reverse.paths import workspace_root, repo_root


def _read_synthesis(sys_dir: Path) -> dict[str, Any] | None:
    """Read .sys/synthesis/manifest.json if the synthesis layer has run.

    Derived/observability record (Phase 3.7) — surfaced read-only so the
    diagnostic can report which system views exist. None when absent/corrupt.
    """
    manifest = sys_dir / "synthesis" / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {
        "docLevel": data.get("docLevel"),
        "generatedAt": data.get("generatedAt"),
        "artifacts": [a.get("name") for a in (data.get("artifacts") or []) if a.get("name")],
        "confidenceRollup": data.get("confidenceRollup") or {},
    }


def _scan_legacy_projects(workspace_old: Path) -> list[dict[str, Any]]:
    """For each subdir of workspace/old/, summarize the reverse phase state.

    P2.11 closure (2026-06-10) : JSON decode / OS errors on inventory.json
    are no longer swallowed. Each project now carries a ``warnings`` list
    that surfaces in both human + JSON output so corruption is visible
    instead of masquerading as "0 units, 0 FEATs" (which a user would read
    as "nothing to do").
    """
    projects: list[dict[str, Any]] = []
    for p in sorted(workspace_old.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        sys_dir = p / ".sys"
        warnings: list[str] = []
        proj: dict[str, Any] = {
            "name": p.name,
            "path": str(p.relative_to(workspace_old.parent.parent)),
            "phases": {
                "init": sys_dir.is_dir(),
                "inventory": (sys_dir / "inventory.json").is_file(),
                "audit": (sys_dir / "tech-audit.md").is_file(),
                "db_merged": (sys_dir / "db-schema.merged.json").is_file(),
            },
            "units_total": 0,
            "feats_extracted": 0,
            "ui_screens": 0,
            "synthesis": _read_synthesis(sys_dir),
            "warnings": warnings,
        }
        if proj["phases"]["inventory"]:
            inv_path = sys_dir / "inventory.json"
            try:
                inv = json.loads(inv_path.read_text(encoding="utf-8"))
                proj["units_total"] = len(inv.get("units") or [])
                # M9 : unit ids + allocations exposed for the caller, which
                # computes `feats_extracted` from FEAT FILES actually on disk
                # (len(_featAllocations) lied : it hits 100 % at STEP 2.5
                # pre-allocation and counts XC-* crosscut keys).
                proj["_unit_ids"] = [u["id"] for u in (inv.get("units") or [])]
                proj["_feat_numbers"] = sorted({
                    n for uid, n in (inv.get("_featAllocations") or {}).items()
                    if uid in set(proj["_unit_ids"])
                })
            except json.JSONDecodeError as e:
                warnings.append(
                    f"[REVERSE_INVENTORY_CORRUPTED] {inv_path.name} unparseable "
                    f"(line {e.lineno}, col {e.colno}): {e.msg}. "
                    "Re-run /sdd-reverse-inventory to regenerate."
                )
            except OSError as e:
                warnings.append(
                    f"[REVERSE_INVENTORY_IO_ERROR] cannot read {inv_path.name}: {e}. "
                    "Check filesystem permissions or run /sdd-reverse-inventory."
                )
        projects.append(proj)
    return projects


def _scan_reverse_feats(workspace_feats: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """List reverse-generated FEATs + collect any read warnings.

    Returns a tuple ``(feats, warnings)``. The warnings list previously
    grew silently — P2.11 closure surfaces it back to the caller for
    rendering.
    """
    feats: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not workspace_feats.is_dir():
        return feats, warnings
    for f in sorted(workspace_feats.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
        except OSError as e:
            warnings.append(
                f"[REVERSE_FEAT_UNREADABLE] {f.name} cannot be read: {e}"
            )
            continue
        fm, body = parse_frontmatter(content)
        if fm.get("generated-by") != "sdd-reverse":
            continue
        confidence = fm.get("confidence", "unknown")
        gate_match = REVERSE_GATE_RE.search(body)
        allow_full = gate_match and gate_match.group(2) == "true"
        # ASCII markers (Windows cp1252 console compat — emoji-free)
        marker = "[REV]" if confidence == "high" else "[REV-WARN]"
        feats.append({
            "file": str(f.relative_to(workspace_feats.parent.parent)),
            "name": f.stem,
            "confidence": confidence,
            "source_unit": fm.get("source-unit"),
            "language_detected": fm.get("language-detected"),
            "extraction_date": fm.get("extraction-date"),
            "allow_sdd_full": bool(allow_full),
            "marker": marker,
        })
    return feats, warnings


def _render_human(
    projects: list[dict[str, Any]],
    feats: list[dict[str, Any]],
    feat_warnings: list[str] | None = None,
) -> str:
    lines = ["=== Reverse Engineering Status ===", ""]
    if not projects:
        lines.append("Aucun projet legacy détecté sous workspace/old/")
    else:
        lines.append(f"Projets legacy : {len(projects)}")
        lines.append("")
        for p in projects:
            ph = p["phases"]
            phase_str = " -> ".join(
                f"{name}{'OK' if ok else '--'}"
                for name, ok in [
                    ("init", ph["init"]),
                    ("inventory", ph["inventory"]),
                    ("audit", ph["audit"]),
                    ("merged", ph["db_merged"]),
                ]
            )
            lines.append(f"  * {p['name']}")
            lines.append(f"      {phase_str}")
            if p["units_total"]:
                pct = (p["feats_extracted"] / p["units_total"] * 100) if p["units_total"] else 0
                lines.append(f"      FEATs : {p['feats_extracted']}/{p['units_total']} unités extraites ({pct:.0f}%)")
                if p.get("ui_screens"):
                    lines.append(f"      Mockups UI : {p['ui_screens']}")
            # Phase 3.7 : surface synthesis layer (C4 / ERD / soul) if present
            syn = p.get("synthesis")
            if syn:
                arts = ", ".join(syn.get("artifacts") or []) or "(aucun)"
                r = syn.get("confidenceRollup") or {}
                lines.append(
                    f"      Synthèse ({syn.get('docLevel', '?')}) : {arts} "
                    f"[high={r.get('high', 0)} medium={r.get('medium', 0)} low={r.get('low', 0)}]"
                )
            # P2.11 : surface project-level warnings (corruption, IO)
            for w in p.get("warnings", []):
                lines.append(f"      [!] {w}")
            lines.append("")

    lines.append("")
    lines.append(f"FEATs reverse dans workspace/feats/ : {len(feats)}")
    if feats:
        lines.append("")
        for f in feats:
            full_marker = "-> /sdd-full OK" if f["allow_sdd_full"] else "-> REVUE HUMAINE OBLIGATOIRE avant /sdd-full"
            lines.append(f"  {f['marker']} {f['name']}  (confidence={f['confidence']}, U={f['source_unit']})")
            lines.append(f"        {full_marker}")
    # P2.11 : surface FEAT-scan warnings (unreadable .md files)
    for w in (feat_warnings or []):
        lines.append(f"  [!] {w}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reverse_status",
        description="Diagnostic CLI for the reverse engineering workflow (pendant de /sdd-status).",
    )
    parser.add_argument("--project", default=None,
        help="Filter to one specific project under workspace/old/")
    parser.add_argument("--json", action="store_true",
        help="Emit report as JSON on stdout")
    args = parser.parse_args(argv)
    ensure_console_safe()

    # Anchor on the repo root, NEVER on the CWD (audit 2026-06-10 anomalie
    # env : CWD-relative paths created parasite workspace/ trees under
    # .sdd/python/ when invoked from there). Tests/CI may override via
    # SDD_REVERSE_WORKSPACE_ROOT (must exist — silently ignored otherwise).
    import os
    override = os.environ.get("SDD_REVERSE_WORKSPACE_ROOT")
    root = Path(override).resolve() if override and Path(override).is_dir() else repo_root()
    workspace_old = workspace_root(root) / "old"
    workspace_feats = workspace_root(root) / "feats"

    if not workspace_old.is_dir():
        if args.json:
            print(json.dumps({"ok": False, "error": "workspace/old/ not found", "projects": [], "feats": []}))
        else:
            print("workspace/old/ introuvable — aucun projet legacy en cours de reverse.")
        return 1

    projects = _scan_legacy_projects(workspace_old)
    if args.project:
        wanted = Path(args.project).name
        projects = [p for p in projects if p["name"] == wanted]

    feats, feat_warnings = _scan_reverse_feats(workspace_feats)

    # M9 closure : feats_extracted = FEAT files actually on disk whose
    # source-unit belongs to the project ; ui_screens = mockups whose leading
    # FEAT number is allocated to one of the project's units.
    ui_dir = workspace_root(root) / "ui"
    ui_numbers: list[int] = []
    if ui_dir.is_dir():
        for h in ui_dir.glob("*.html"):
            m = re.match(r"(\d+)-", h.name)
            if m:
                ui_numbers.append(int(m.group(1)))
    for p in projects:
        unit_ids = set(p.pop("_unit_ids", []))
        feat_numbers = set(p.pop("_feat_numbers", []))
        p["feats_extracted"] = sum(
            1 for f in feats if f.get("source_unit") in unit_ids
        )
        p["ui_screens"] = sum(1 for n in ui_numbers if n in feat_numbers)

    # P2.11 : aggregate warning counts for top-level summary
    warnings_total = sum(len(p.get("warnings", [])) for p in projects) + len(feat_warnings)

    if args.json:
        print(json.dumps({
            "ok": True,
            "projects": projects,
            "feats": feats,
            "feat_warnings": feat_warnings,
            "warnings_total": warnings_total,
        }, ensure_ascii=False))
    else:
        out = _render_human(projects, feats, feat_warnings)
        if warnings_total:
            out += (
                f"\n\n[!] {warnings_total} warning(s) detected — "
                "voir lignes [!] ci-dessus (re-run /sdd-reverse-inventory "
                "si inventory corrompu)."
            )
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
