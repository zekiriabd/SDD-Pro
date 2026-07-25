#!/usr/bin/env python3
"""Validate ADR filenames against the v7.0.0 canonical pattern.

Audit CTO 2026-06-09 (item #18 closure) — gate anti-régression sur le
nommage des ADRs. Émet une erreur si un fichier `.claude/docs/adrs/ADR-*.md`
ne matche pas le pattern documenté en `ownership.md §3` + `sdd_lib/adr_id.py`.

Canonical pattern (v7.0.0+) :
    ADR-{YYYYMMDDTHHmmss}-{rand4}-{slug}.md
        - {YYYYMMDDTHHmmss} : UTC seconde compacte ISO 8601
        - {rand4} : 4 hex chars lowercase (secrets.token_hex(2))
        - {slug} : kebab-case strict — start/end alphanum, 1-40 chars
                   refuse `---`, `-foo`, `foo-`, slug all-dashes

Compat tolérance pre-2026-06-08 (cf. ownership.md Partie A §3) :
    ADR-{YYYYMMDDTHHmmss}-{slug}.md  (sans rand4 — accepté en lecture)

Usage :
    python -m sdd_admin.validate_adr_naming                  # framework ADRs only
    python -m sdd_admin.validate_adr_naming --include-projects  # + workspace/.sys/.context/adrs/
    python -m sdd_admin.validate_adr_naming --strict         # rand4 obligatoire (rejette legacy)
    python -m sdd_admin.validate_adr_naming --json           # output machine-readable

Exit codes :
    0 = all ADRs match the canonical pattern (+ legacy in non-strict)
    1 = at least 1 ADR has a malformed name
    2 = ADRs directory not found (only when explicit --adrs-dir is set;
        absence of project ADRs dir with --include-projects is non-fatal)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ADRS_DIR = ROOT / ".claude" / "docs" / "adrs"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.exit_codes import SUCCESS, FAIL_FAST, INFRA_BLOCKED  # noqa: E402
from sdd_lib.paths import workspace_root  # noqa: E402

PROJECT_ADRS_DIR = workspace_root(ROOT) / ".sys" / ".context" / "adrs"


def _rel(p: Path) -> str:
    """Display path relative to the repo root; falls back to the project root
    (parent of the workspace) for artifacts under an external/sibling workspace
    (split layout where the framework lives in a sub-folder), else absolute."""
    for base in (ROOT, workspace_root(ROOT).parent):
        try:
            return str(p.relative_to(base)).replace("\\", "/")
        except ValueError:
            continue
    return str(p).replace("\\", "/")

# Slug kebab-case strict : start/end alphanum, 1-40 chars total.
# Refuse "---", "-foo", "foo-" (audit CTO 2026-06-09 Major #2 closure).
# Single-char slug `a` accepté (longueur 1 alphanum).
_SLUG = r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?"

# Canonical v7.0.0+ : timestamp + rand4 + slug
_RE_CANONICAL = re.compile(
    rf"^ADR-(\d{{8}}T\d{{6}})-([0-9a-f]{{4}})-({_SLUG})\.md$"
)
# Legacy pre-2026-06-08 : timestamp + slug (no rand4)
_RE_LEGACY = re.compile(
    rf"^ADR-(\d{{8}}T\d{{6}})-({_SLUG})\.md$"
)


def classify(name: str) -> str:
    """Return 'canonical' | 'legacy' | 'invalid'."""
    if _RE_CANONICAL.match(name):
        return "canonical"
    if _RE_LEGACY.match(name):
        return "legacy"
    return "invalid"


def scan(adrs_dir: Path) -> dict:
    """Walk `adrs_dir` and classify each ADR file."""
    if not adrs_dir.is_dir():
        return {"error": f"ADRs directory not found: {adrs_dir}", "found": False}

    canonical, legacy, invalid = [], [], []
    for fp in sorted(adrs_dir.glob("ADR-*.md")):
        verdict = classify(fp.name)
        rel = _rel(fp)
        {"canonical": canonical, "legacy": legacy, "invalid": invalid}[verdict].append(rel)

    return {
        "found": True,
        "adrs_dir": _rel(adrs_dir),
        "counts": {
            "canonical": len(canonical),
            "legacy": len(legacy),
            "invalid": len(invalid),
            "total": len(canonical) + len(legacy) + len(invalid),
        },
        "canonical": canonical,
        "legacy": legacy,
        "invalid": invalid,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate ADR filename pattern v7.0.0")
    ap.add_argument("--adrs-dir", type=Path, default=DEFAULT_ADRS_DIR,
                    help=f"Override ADRs dir (default: {_rel(DEFAULT_ADRS_DIR)})")
    ap.add_argument("--include-projects", action="store_true",
                    help=f"Also scan project ADRs under "
                         f"{_rel(PROJECT_ADRS_DIR)} (absence non-fatal)")
    ap.add_argument("--strict", action="store_true",
                    help="Reject legacy filenames (rand4 mandatory)")
    ap.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = ap.parse_args()

    # Framework ADRs (canonical scan, fatal if dir missing only when explicit)
    report = scan(args.adrs_dir)
    if not report.get("found"):
        if args.json:
            print(json.dumps(report))
        else:
            print(f"ERROR: {report['error']}", file=sys.stderr)
        return INFRA_BLOCKED

    # Optionnel : merge project ADRs (audit CTO 2026-06-09 #22 closure).
    # Absence du dossier projet = non-fatal (les projets vides en sont sans).
    project_report = None
    if args.include_projects and PROJECT_ADRS_DIR.is_dir():
        project_report = scan(PROJECT_ADRS_DIR)
        if project_report.get("found"):
            # Merge counts + lists
            for k in ("canonical", "legacy", "invalid"):
                report["counts"][k] += project_report["counts"][k]
                report[k].extend(project_report[k])
            report["counts"]["total"] = (
                report["counts"]["canonical"]
                + report["counts"]["legacy"]
                + report["counts"]["invalid"]
            )
            report["project_adrs_dir"] = project_report["adrs_dir"]

    invalid_count = report["counts"]["invalid"]
    legacy_count = report["counts"]["legacy"]
    blocking_count = invalid_count + (legacy_count if args.strict else 0)

    if args.json:
        report["strict"] = args.strict
        report["include_projects"] = args.include_projects
        report["blocking_count"] = blocking_count
        print(json.dumps(report, indent=2))
    else:
        c = report["counts"]
        print(f"ADRs scanned: {c['total']} (canonical={c['canonical']}, "
              f"legacy={c['legacy']}, invalid={c['invalid']})")
        # ASCII-only markers — Windows console defaults to cp1252 which
        # cannot encode `✗`/`⚠` (audit CTO 2026-06-09 Major closure).
        if report["invalid"]:
            print("\nInvalid ADR filenames (do not match pattern):")
            for p in report["invalid"]:
                print(f"  [INVALID] {p}")
            print("\n  Expected: ADR-{YYYYMMDDTHHmmss}-{rand4}-{slug}.md")
            print("  Helper:   python -c 'from sdd_lib.adr_id import mint_adr_filename;"
                  " print(mint_adr_filename(\"my-slug\"))'")
        if args.strict and report["legacy"]:
            print("\nLegacy ADR filenames (missing rand4, --strict rejected):")
            for p in report["legacy"]:
                print(f"  [LEGACY] {p}")
        if blocking_count == 0:
            print("\n[OK] all ADR filenames valid")

    return SUCCESS if blocking_count == 0 else FAIL_FAST


if __name__ == "__main__":
    raise SystemExit(main())
