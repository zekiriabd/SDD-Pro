#!/usr/bin/env python3
"""Quick ingest of technical plans into console.db `plans` table.

Parses `workspace/output/plans/*.{back,front}.md` and upserts metadata :
us_id, family, file_path, schema_version (1|2), strict_ready, us_hash,
capabilities_json, file_count (count of entries in `## Files` section),
generated_at.

Idempotent — ON CONFLICT(plan_id) DO UPDATE. Plan ID format :
`{us_id}-{family}` (ex. `1-1-back`, `4-2-front`).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "workspace" / "output" / "db" / "console.db"
PLANS_DIR = ROOT / "workspace" / "output" / "plans"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.markdown_io import parse_frontmatter as _parse_frontmatter_pair  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402


def now_iso() -> str:
    """Alias of `sdd_lib.paths.iso_now` — kept for backward-compat with
    consumers parsing the script output (audit consolidé 2026-06-07 Sprint 2)."""
    from sdd_lib.paths import iso_now
    return iso_now()


def parse_frontmatter(text: str) -> dict:
    """Return YAML-ish frontmatter as a flat dict (string values).

    v7.0.0-alpha (audit CRIT-3) : delegates to `sdd_lib.markdown_io.parse_frontmatter`
    (SSoT). Returns the dict only (drops the body tuple element) to
    preserve the v6.x return type expected by callers in this module.
    """
    result = _parse_frontmatter_pair(text)
    return result[0] if result is not None else {}


def parse_plan(path: Path) -> dict | None:
    # Filename pattern: {n}-{m}-{Name}.{back|front}.md
    name = path.name
    m = re.match(r"^(\d+)-(\d+)-.+\.(back|front)\.md$", name)
    if not m:
        return None
    n, mm, family = m.group(1), m.group(2), m.group(3)
    us_id = f"{n}-{mm}"

    text = path.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)

    # Count file entries in `## Files` section : lines matching `- path:`
    files_section = re.search(r"^## Files\s*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    file_count = 0
    if files_section:
        file_count = len(re.findall(r"^\s*-\s*path\s*:", files_section.group(1), re.MULTILINE))

    schema_version = fm.get("plan-schema-version")
    try:
        schema_version = int(schema_version) if schema_version else 1
    except (TypeError, ValueError):
        schema_version = 1

    strict_ready = 1 if fm.get("strict-ready", "").lower() == "true" else 0

    capabilities = fm.get("capabilities-triggered", "")
    capabilities_list = [c.strip() for c in capabilities.split(",") if c.strip()] if capabilities else []

    return {
        "plan_id": f"{us_id}-{family}",
        "us_id": us_id,
        "family": family,
        "file_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "schema_version": schema_version,
        "strict_ready": strict_ready,
        "us_hash": fm.get("us-hash", ""),
        "capabilities_json": json.dumps(capabilities_list),
        "file_count": file_count,
        "generated_at": fm.get("generated-at", ""),
    }


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        return FAIL_FAST
    if not PLANS_DIR.exists():
        print(f"[OK] no plans dir — nothing to ingest")
        return SUCCESS
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    ts = now_iso()
    n_ingested = 0

    for fp in sorted(PLANS_DIR.glob("*.md")):
        data = parse_plan(fp)
        if not data:
            continue
        cur.execute(
            """INSERT INTO plans(plan_id, us_id, family, file_path, schema_version,
                  strict_ready, us_hash, capabilities_json, file_count, generated_at, ingested_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(plan_id) DO UPDATE SET
                 us_id=excluded.us_id, family=excluded.family, file_path=excluded.file_path,
                 schema_version=excluded.schema_version, strict_ready=excluded.strict_ready,
                 us_hash=excluded.us_hash, capabilities_json=excluded.capabilities_json,
                 file_count=excluded.file_count, generated_at=excluded.generated_at,
                 ingested_at=excluded.ingested_at""",
            (
                data["plan_id"], data["us_id"], data["family"], data["file_path"],
                data["schema_version"], data["strict_ready"], data["us_hash"],
                data["capabilities_json"], data["file_count"], data["generated_at"], ts,
            ),
        )
        n_ingested += 1

    conn.commit()
    print(f"[OK] ingested {n_ingested} plans into {DB_PATH.relative_to(ROOT)}")
    return SUCCESS
if __name__ == "__main__":
    raise SystemExit(main())
