#!/usr/bin/env python3
"""SDD_Pro per-US schema slice generator (Levier 4, audit 2026-06-08).

Reads `workspace/output/db/schema.json` and a target US, extracts the
tables mentioned in the US (+ FK transitive closure), and writes
`workspace/output/db/schema-slice-{n}-{m}.json`. The dev-backend and
qa agents prefer the slice over the full schema when both exist.

Invoked by orchestrating commands (`/dev-run`, `/qa-generate`) before
spawning the dev-backend / qa agent. Idempotent: re-runs overwrite the
slice deterministically.

Usage::

    python -m sdd_scripts.generate_schema_slice \\
        --us-path workspace/output/us/1-2-Login.md \\
        [--schema-path workspace/output/db/schema.json] \\
        [--out workspace/output/db/schema-slice-1-2.json] \\
        [--json]

Exit codes (aligned with sdd_lib.exit_codes):
    0 = SUCCESS — slice file written
    1 = FAIL_FAST — invalid arg / US not found / schema malformed / cannot derive path
    2 = CORRECTIBLE — schema missing OR no entity matched (caller fallback to full)
    3 = INFRA_BLOCKED — disk write failure

The slice file omits tables not referenced by the US. Agents must
still fallback to the full `schema.json` if the slice file is absent
(deterministic via loader.yml ordering).

Anti-pattern: never modify `schema.json` itself. The slice is a
side-output per-US, derived freshly each run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.atomic_write import atomic_write_text  # noqa: E402
from sdd_lib.exit_codes import (  # noqa: E402
    CORRECTIBLE,
    FAIL_FAST,
    INFRA_BLOCKED,
    SUCCESS,
)
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.schema_slice import slice_for_us  # noqa: E402


_US_BASENAME_RE = re.compile(r"^(?P<n>\d+)-(?P<m>\d+)(?:-.*)?(?:\.md)?$")


def _derive_slice_path(us_path: Path, schema_dir: Path) -> Path | None:
    """Compute workspace/output/db/schema-slice-{n}-{m}.json from US filename."""
    m = _US_BASENAME_RE.match(us_path.stem)
    if not m:
        return None
    return schema_dir / f"schema-slice-{m['n']}-{m['m']}.json"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Generate per-US schema slice (Levier 4)"
    )
    p.add_argument("--us-path", required=True, help="Path to the US markdown file")
    p.add_argument("--schema-path", help="Override schema.json location")
    p.add_argument("--out", help="Override output slice path")
    p.add_argument("--no-fk-closure", action="store_true",
                   help="Do not include FK-referenced tables transitively")
    p.add_argument("--json", action="store_true", help="JSON stdout report")
    args = p.parse_args()

    repo = repo_root()
    us_path = Path(args.us_path)
    if not us_path.is_absolute():
        us_path = repo / us_path

    schema_path = Path(args.schema_path) if args.schema_path else repo / "workspace" / "output" / "db" / "schema.json"
    if not schema_path.is_absolute():
        schema_path = repo / schema_path

    if not schema_path.is_file():
        print(f"INFO: schema.json not found at {schema_path} — no slice to produce.",
              file=sys.stderr)
        return CORRECTIBLE

    if not us_path.is_file():
        print(f"FAIL: US not found at {us_path}", file=sys.stderr)
        return FAIL_FAST

    out_path = Path(args.out) if args.out else _derive_slice_path(us_path, schema_path.parent)
    if out_path is None:
        print(f"FAIL: cannot derive slice path from US filename {us_path.name} "
              f"(expected 'N-M-Name.md')", file=sys.stderr)
        return FAIL_FAST
    if not out_path.is_absolute():
        out_path = repo / out_path

    try:
        sliced, matched = slice_for_us(
            schema_path, us_path,
            include_referenced=not args.no_fk_closure,
        )
    except ValueError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return FAIL_FAST

    if not matched:
        print(
            f"INFO: no entity from schema referenced by {us_path.name}. "
            f"Agents will fallback to full schema.json.",
            file=sys.stderr,
        )
        return CORRECTIBLE

    try:
        atomic_write_text(
            out_path,
            json.dumps(sliced, indent=2, ensure_ascii=False),
        )
    except OSError as e:
        print(f"FAIL: disk write failed for {out_path}: {e}", file=sys.stderr)
        return INFRA_BLOCKED

    meta = sliced.get("_slice_metadata", {})
    report = {
        "slice_path": str(out_path),
        "seed_entities": meta.get("seed_entities", []),
        "transitive_entities": meta.get("transitive_entities", []),
        "tables_in_slice": meta.get("total_tables_in_slice", 0),
        "tables_in_source": meta.get("total_tables_in_source", 0),
    }
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        ratio = (
            report["tables_in_slice"] / report["tables_in_source"] * 100
            if report["tables_in_source"] else 0
        )
        print(
            f"OK: slice {report['tables_in_slice']}/{report['tables_in_source']} "
            f"tables ({ratio:.0f}%) -> {out_path}"
        )
        print(f"     seed: {', '.join(report['seed_entities']) or '(none)'}")
        if report["transitive_entities"]:
            print(f"     via FK: {', '.join(report['transitive_entities'])}")

    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
