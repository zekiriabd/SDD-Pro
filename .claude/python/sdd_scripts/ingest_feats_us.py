#!/usr/bin/env python3
"""Quick ingest of FEATs + US markdown into console.db.

Populates `feats` table with name, ac_count, sfd_count, br_count, fd_count,
actors_json, status, file_path. Populates `us` table with us_id, n, m, name,
file_path, status, covers_json, ac_count.

Idempotent — uses INSERT OR REPLACE on (feat_n) and (us_id) primary keys.
"""

from __future__ import annotations

import functools
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "workspace" / "output" / "db" / "console.db"
FEATS_DIR = ROOT / "workspace" / "input" / "feats"
US_DIR = ROOT / "workspace" / "output" / "us"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.markdown_io import section_body_stripped  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402


@functools.lru_cache(maxsize=8)
def _count_ids_pattern(prefix: str) -> re.Pattern[str]:
    """Compile-once regex for counting `{prefix}-N` IDs (SFD/BR/AC/FD).

    Audit mineur #2 v7.0.0-alpha 2026-06-05 — was rebuilt inside count_ids
    on every call (rare hot path but easy fix).
    """
    return re.compile(rf"^\s*[-*]?\s*{re.escape(prefix)}-\d+", re.MULTILINE)


def now_iso() -> str:
    """Alias of `sdd_lib.paths.iso_now` — kept for backward-compat with
    consumers parsing the script output (audit consolidé 2026-06-07 Sprint 2)."""
    from sdd_lib.paths import iso_now
    return iso_now()


def parse_feat(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")

    # FEAT-N from filename
    m = re.match(r"^(\d+)-(.+)$", path.stem)
    if not m:
        return {}
    feat_n = int(m.group(1))
    feat_name = m.group(2)

    # v7.0.0-alpha (audit CRIT-3) : section extraction delegated to
    # sdd_lib.markdown_io (SSoT). Inner closure removed.
    def section(name: str) -> str:
        return section_body_stripped(text, name) or ""

    # Counts by counting ID prefixes (regex precompiled per prefix — audit
    # mineur #2 v7.0.0-alpha 2026-06-05, was recompiled on every call).
    def count_ids(prefix: str, body: str) -> int:
        return len(_count_ids_pattern(prefix).findall(body))

    sfd_body = section("Functional Needs")
    br_body = section("Business Rules")
    ac_body = section("Acceptance Criteria")
    fd_body = section("Functional Deliverables")
    actors_body = section("Actors")

    actors = [
        re.sub(r"^\s*[-*]\s*", "", line).split(":")[0].strip()
        for line in actors_body.splitlines()
        if line.strip().startswith(("-", "*"))
    ]
    actors = [a for a in actors if a]

    return {
        "feat_n": feat_n,
        "name": feat_name,
        "file_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "status": "active",
        "actors_json": json.dumps(actors, ensure_ascii=False),
        "sfd_count": count_ids("SFD", sfd_body),
        "br_count": count_ids("BR", br_body),
        "ac_count": count_ids("AC", ac_body),
        "fd_count": count_ids("FD", fd_body),
    }


def parse_us(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # us_id from filename : {n}-{m}-{Name}
    m = re.match(r"^(\d+)-(\d+)-(.+)$", path.stem)
    if not m:
        return {}
    n, mm, name = int(m.group(1)), int(m.group(2)), m.group(3)
    us_id = f"{n}-{mm}"

    # Status from frontmatter
    status_match = re.search(r"^Status:\s*(\w+)", text, re.MULTILINE)
    status = status_match.group(1) if status_match else "Draft"

    # ACs count
    ac_count = len(re.findall(r"^\s*[-*]?\s*AC-\d+", text, re.MULTILINE))

    # Covers section
    covers_block = re.search(r"^Covers:\s*\n(.*?)(?=^[A-Z][a-z]|\Z)", text, re.DOTALL | re.MULTILINE)
    covers = []
    if covers_block:
        covers = re.findall(r"\b(?:SFD|BR|AC|FD)-\d+", covers_block.group(1))

    return {
        "us_id": us_id,
        "feat_n": n,
        "n": n,
        "m": mm,
        "name": name,
        "file_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "status": status,
        "covers_json": json.dumps(sorted(set(covers))),
        "ac_count": ac_count,
    }


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        return FAIL_FAST
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    ts = now_iso()
    n_feats, n_us = 0, 0

    for fp in sorted(FEATS_DIR.glob("*.md")):
        data = parse_feat(fp)
        if not data:
            continue
        cur.execute(
            """INSERT INTO feats(feat_n, name, file_path, status, actors_json,
                  sfd_count, br_count, ac_count, fd_count, created_at, updated_at, ingested_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM feats WHERE feat_n=?), ?), ?, ?)
               ON CONFLICT(feat_n) DO UPDATE SET
                 name=excluded.name, file_path=excluded.file_path, status=excluded.status,
                 actors_json=excluded.actors_json,
                 sfd_count=excluded.sfd_count, br_count=excluded.br_count,
                 ac_count=excluded.ac_count, fd_count=excluded.fd_count,
                 updated_at=excluded.updated_at, ingested_at=excluded.ingested_at""",
            (
                data["feat_n"], data["name"], data["file_path"], data["status"], data["actors_json"],
                data["sfd_count"], data["br_count"], data["ac_count"], data["fd_count"],
                data["feat_n"], ts, ts, ts,
            ),
        )
        n_feats += 1

    for fp in sorted(US_DIR.glob("*.md")):
        data = parse_us(fp)
        if not data:
            continue
        cur.execute(
            """INSERT INTO us(us_id, feat_n, n, m, name, file_path, status, complexity,
                  effort_estimate, covers_json, deps_json, ac_count, created_at, updated_at, ingested_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, '[]', ?,
                      COALESCE((SELECT created_at FROM us WHERE us_id=?), ?), ?, ?)
               ON CONFLICT(us_id) DO UPDATE SET
                 feat_n=excluded.feat_n, n=excluded.n, m=excluded.m,
                 name=excluded.name, file_path=excluded.file_path, status=excluded.status,
                 covers_json=excluded.covers_json, ac_count=excluded.ac_count,
                 updated_at=excluded.updated_at, ingested_at=excluded.ingested_at""",
            (
                data["us_id"], data["feat_n"], data["n"], data["m"], data["name"],
                data["file_path"], data["status"], data["covers_json"], data["ac_count"],
                data["us_id"], ts, ts, ts,
            ),
        )
        n_us += 1

    conn.commit()
    print(f"[OK] ingested {n_feats} FEATs + {n_us} US into {DB_PATH.relative_to(ROOT)}")
    return SUCCESS
if __name__ == "__main__":
    raise SystemExit(main())
