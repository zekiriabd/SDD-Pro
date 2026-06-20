"""SDD_Pro Reverse Engineering — Phase 1 CLI orchestrator.

Usage:
    python -m sdd_reverse_scripts.reverse_inventory --project-path PATH [--json] [--output-dir DIR]

Scans a legacy project rooted at PATH and writes:
- {PATH}/.sys/inventory-raw.json     (raw scan + pages + entry points + modules)
- {PATH}/.sys/units-candidates.json  (functional unit candidates)

Exit codes:
  0  success
  1  preconditions failed (project not found, signatures missing)
  2  scan failed (I/O or YAML error)
  3  no language detected (legacy empty or unrecognized)

Error format: 3-line ERROR/CAUSE/FIX with [REVERSE_*] prefix per
.claude/rules/reverse-engineering.md.

Output protocol (chat): 1L per major step per
.claude/rules/output-protocol.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure parent directory is on sys.path so we can import sdd_reverse
_THIS_DIR = Path(__file__).resolve().parent
_PYTHON_DIR = _THIS_DIR.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from sdd_reverse import scan_legacy, inventory_builder, ui_unit_detector  # noqa: E402


DEFAULT_SIGNATURES_PATH = (
    _PYTHON_DIR / "sdd_reverse" / "language_signatures.yml"
)


def _print_error_3l(error_msg: str, cause: str, fix: str) -> None:
    """Print 3-line ERROR/CAUSE/FIX to stderr (rules/error-classification.md format)."""
    print(f"ERROR: {error_msg}", file=sys.stderr)
    print(f"CAUSE: {cause}", file=sys.stderr)
    print(f"FIX: {fix}", file=sys.stderr)


_CHAT_QUIET = False  # set to True when --json is passed (machine-readable mode)


def _print_chat_update(message: str, progress: int) -> None:
    """Emit 1-line chat update per rules/output-protocol.md.

    Suppressed when --json mode is active (stdout reserved for the JSON document).
    """
    if _CHAT_QUIET:
        return
    print(f"[REVERSE] {message} ({progress}%)", flush=True)


def _write_atomic_json(target: Path, data: dict) -> None:
    """Write JSON atomically (.sddtmp + rename)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".sddtmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )
    tmp.replace(target)


def run_inventory(
    project_path: Path,
    signatures_path: Path,
    output_dir: Path | None = None,
    verbose_json: bool = False,
) -> int:
    """Execute Phase 1 pipeline. Returns exit code."""
    global _CHAT_QUIET
    _CHAT_QUIET = bool(verbose_json)
    project_path = project_path.resolve()
    if not project_path.is_dir():
        _print_error_3l(
            f"reverse-inventory: project path not found",
            f"[REVERSE_PRECONDITION] {project_path} is not a directory",
            "Create the directory and place legacy code inside, or correct --project-path",
        )
        return 1

    if not signatures_path.is_file():
        _print_error_3l(
            "reverse-inventory: signatures file missing",
            f"[REVERSE_SCAN_FAILED] language_signatures.yml not found at {signatures_path}",
            "Reinstall SDD_Pro reverse module or pass --signatures explicitly",
        )
        return 2

    # Phase 1a — Scan déterministe
    _print_chat_update(f"Scan legacy {project_path.name}...", 10)
    try:
        signatures = scan_legacy.load_signatures(signatures_path)
        scan_result = scan_legacy.scan_project(project_path, signatures)
    except (FileNotFoundError, ValueError, OSError) as exc:
        _print_error_3l(
            "reverse-inventory: scan failed",
            f"[REVERSE_SCAN_FAILED] {exc}",
            "Inspect language_signatures.yml + workspace/old/{P}/ permissions",
        )
        return 2

    stats = scan_result["stats"]
    _print_chat_update(
        f"{stats['files_analyzed']}/{stats['files_total']} fichiers analyses, "
        f"{stats['files_excluded']} exclus.",
        25,
    )

    if not scan_result["languages"]:
        _print_error_3l(
            "reverse-inventory: no language detected",
            "[REVERSE_NO_LANGUAGE] zero recognized files in project",
            "Verify workspace/old/{P}/ contains source code OR extend language_signatures.yml",
        )
        return 3

    langs_summary = ", ".join(
        f"{l['id']} ({l['confidence_hint']})" for l in scan_result["languages"][:3]
    )
    _print_chat_update(f"Detection langages : {langs_summary}.", 40)

    # Phase 1a+ — Pages + entry points + modules
    inventory = inventory_builder.build_inventory(scan_result, project_path)
    _print_chat_update(
        f"{len(inventory['pages'])} pages, {len(inventory['modules_suggested'])} modules suggeres.",
        60,
    )

    # Phase 1b — Functional units (pre-detection, LLM agent will arbitrate)
    units = ui_unit_detector.detect_all_units(inventory["pages"], project_path)
    _print_chat_update(
        f"{len(units['units'])} unites fonctionnelles candidates identifiees.",
        80,
    )

    # Write outputs
    out_dir = output_dir if output_dir else (project_path / ".sys")
    out_inventory = out_dir / "inventory-raw.json"
    out_units = out_dir / "units-candidates.json"
    _write_atomic_json(out_inventory, inventory)
    _write_atomic_json(out_units, units)
    _print_chat_update(f"Inventaire ecrit dans {out_dir.relative_to(project_path)}/", 95)

    # Final verdict (chat mode only — JSON mode produces only the JSON document)
    if not verbose_json:
        print(
            f"[DONE] Inventory {project_path.name} — {len(units['units'])} unites candidates "
            f"(confidence globale : {_summarize_global_confidence(scan_result, units)}). (100%)"
        )
    else:
        print(json.dumps({
            "ok": True,
            "project": scan_result["project"],
            "outputs": {
                "inventory_raw": str(out_inventory),
                "units_candidates": str(out_units),
            },
            "summary": {
                "files_analyzed": stats["files_analyzed"],
                "files_excluded": stats["files_excluded"],
                "languages_detected": [l["id"] for l in scan_result["languages"]],
                "pages_count": len(inventory["pages"]),
                "units_count": len(units["units"]),
                "modules_count": len(inventory["modules_suggested"]),
                "global_confidence": _summarize_global_confidence(scan_result, units),
            },
        }, indent=2, ensure_ascii=False))

    return 0


def _summarize_global_confidence(scan_result: dict, units: dict) -> str:
    """Roll-up the global confidence indicator."""
    if not scan_result["languages"]:
        return "low"
    # Use highest LOC language as proxy
    primary = scan_result["languages"][0]
    return primary.get("confidence_hint", "low")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reverse-inventory",
        description=(
            "SDD_Pro Reverse Engineering — Phase 1 scan + inventory builder. "
            "Produces inventory-raw.json + units-candidates.json under {PATH}/.sys/."
        ),
    )
    parser.add_argument(
        "--project-path",
        type=Path,
        required=True,
        help="Path to legacy project root (e.g. workspace/old/AcmeCRM/)",
    )
    parser.add_argument(
        "--signatures",
        type=Path,
        default=DEFAULT_SIGNATURES_PATH,
        help=f"Path to language_signatures.yml (default: {DEFAULT_SIGNATURES_PATH})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: {project-path}/.sys/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit verbose JSON summary on stdout after success",
    )
    args = parser.parse_args(argv)

    return run_inventory(
        project_path=args.project_path,
        signatures_path=args.signatures,
        output_dir=args.output_dir,
        verbose_json=args.json,
    )


if __name__ == "__main__":
    sys.exit(main())
