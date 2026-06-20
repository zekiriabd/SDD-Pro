#!/usr/bin/env python3
"""SDD_Pro: migrate User Stories from v1 (pre-6.8) to v2 schema.

v2 additions (cf. templates/us.template.md):
    - `## Metadata` section with empty JSON block `{}`
    - `Status:` line backward-compatible (Draft|Ready|InProgress|Review|Done|Deferred|Cancelled)

Migration is **idempotent**: re-running on a v2 US is a no-op (skipped).
**Safe**: only appends what is missing, never rewrites existing content.

Usage:
    python migrate_us_v1_to_v2.py --all                  # migrate every US
    python migrate_us_v1_to_v2.py --us 1-2               # migrate one US
    python migrate_us_v1_to_v2.py --all --dry-run        # preview without writing
    python migrate_us_v1_to_v2.py --all --json           # machine-readable report

Exit codes:
    0  Success (all targets processed)
    1  No US found ([US_NOT_FOUND])
    2  Invalid args ([INVALID_ARG])
    5  I/O error on at least one file
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.stderr import error_block, warn  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST  # noqa: E402


US_ID_RE = re.compile(r"^\d+-\d+$")
STATUS_LINE_RE = re.compile(r"(?m)^Status:[ \t]*([A-Za-z]+)[ \t]*$")
METADATA_HEADER_RE = re.compile(r"(?m)^## Metadata\s*$")

METADATA_SECTION_TEMPLATE = """

## Metadata
<!-- Bloc JSON optionnel AI-safe (v6.8+). Survit aux re-runs et permet aux
     agents/Tech Lead d'attacher du contexte arbitraire à l'US sans casser
     le schéma. Agents lisent en optional (ignore si absent ou invalide). -->
```json
{}
```
"""


def resolve_us_path(us_id: str) -> Path | None:
    if not US_ID_RE.match(us_id):
        return None
    us_dir = repo_root() / "workspace" / "output" / "us"
    matches = sorted(us_dir.glob(f"{us_id}-*.md"))
    if len(matches) != 1:
        return None
    return matches[0]


def discover_all_us() -> list[Path]:
    us_dir = repo_root() / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    return sorted(p for p in us_dir.glob("*-*-*.md") if p.is_file())


def migrate_content(content: str) -> tuple[str, list[str]]:
    """Return (new_content, changes_list). changes_list empty = no-op."""
    changes: list[str] = []
    new_content = content

    # 1. Ensure Status: line exists (default Draft if absent)
    if not STATUS_LINE_RE.search(new_content):
        # Inject right after "Parent FEAT:" line if present, else after H1.
        if "Parent FEAT:" in new_content:
            new_content = re.sub(
                r"(?m)(^Parent FEAT:.*$)",
                r"\1\nStatus: Draft",
                new_content,
                count=1,
            )
        else:
            new_content = re.sub(
                r"(?m)(^# .+$)",
                r"\1\n\nStatus: Draft",
                new_content,
                count=1,
            )
        changes.append("added Status: Draft (defaulted)")

    # 2. Ensure ## Metadata section exists
    if not METADATA_HEADER_RE.search(new_content):
        # Append at end, separated by single newline (template already starts with \n\n)
        if not new_content.endswith("\n"):
            new_content += "\n"
        new_content = new_content.rstrip() + METADATA_SECTION_TEMPLATE
        changes.append("added ## Metadata section")

    return new_content, changes


def write_atomic(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def process_one(path: Path, *, dry_run: bool) -> dict:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return {"path": path.name, "status": "error", "error": str(e), "changes": []}

    new_content, changes = migrate_content(content)
    if not changes:
        return {"path": path.name, "status": "skipped", "changes": []}

    if dry_run:
        return {"path": path.name, "status": "would-migrate", "changes": changes}

    try:
        write_atomic(path, new_content)
    except OSError as e:
        return {"path": path.name, "status": "error", "error": str(e), "changes": changes}

    return {"path": path.name, "status": "migrated", "changes": changes}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Migrate User Stories from v1 to v2 schema (idempotent).",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--us", help="US short id (e.g. 1-2) to migrate")
    g.add_argument("--all", action="store_true",
                   help="Migrate every US under workspace/output/us/")
    p.add_argument("--dry-run", action="store_true",
                   help="Print would-be changes without writing")
    p.add_argument("--json", action="store_true",
                   help="Print machine-readable JSON report")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    targets: list[Path]
    if args.all:
        targets = discover_all_us()
        if not targets:
            error_block(
                "migrate_us_v1_to_v2 — no US to migrate",
                "[US_NOT_FOUND] workspace/output/us/ empty or absent",
                "run /us-generate {n} first",
            )
            return FAIL_FAST
    else:
        path = resolve_us_path(args.us)
        if path is None:
            error_block(
                f"migrate_us_v1_to_v2 — US {args.us} not found",
                f"[US_NOT_FOUND] no unique match for workspace/output/us/{args.us}-*.md",
                "verify --us format ({n}-{m})",
            )
            return FAIL_FAST
        targets = [path]

    results = [process_one(p, dry_run=args.dry_run) for p in targets]

    summary = {
        "total": len(results),
        "migrated": sum(1 for r in results if r["status"] == "migrated"),
        "would-migrate": sum(1 for r in results if r["status"] == "would-migrate"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "dry_run": args.dry_run,
    }

    if args.json:
        print(json.dumps({"summary": summary, "results": results},
                         indent=2, ensure_ascii=False))
    else:
        for r in results:
            tag = {
                "migrated": "[OK]",
                "would-migrate": "[DRY]",
                "skipped": "[SKIP]",
                "error": "[ERR]",
            }[r["status"]]
            detail = ", ".join(r["changes"]) if r["changes"] else "no changes needed"
            print(f"{tag} {r['path']}: {detail}")
            if r["status"] == "error":
                warn(f"      {r.get('error', '?')}")
        print(
            f"\nSummary: {summary['total']} US — "
            f"{summary['migrated']} migrated, "
            f"{summary['would-migrate']} would-migrate, "
            f"{summary['skipped']} already v2, "
            f"{summary['errors']} errors"
            + (" (DRY-RUN)" if args.dry_run else "")
        )

    return 5 if summary["errors"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
