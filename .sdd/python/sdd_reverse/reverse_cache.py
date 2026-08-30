"""reverse_cache.py — Phase 3 extraction cache (L5).

The forward pipeline avoids re-doing stable work; the reverse pipeline had no
Phase 3 cache, so an orchestrator re-run re-spawned Opus on every unit even when
nothing changed. This helper lets the orchestrator skip a unit whose evidence is
byte-identical to the last successful extraction AND whose LADDER ARTEFACTS are
all still on disk (FEAT + 3a plan + at least one 3b US — audit M5, 2026-08-29;
checking the FEAT alone made a partially-cleaned workspace report a false HIT).

Cache file: workspace/old/{P}/.sys/extraction-cache.json
    { "<U-N>": { "hash": "sha256:…", "n": 3, "name": "Login" }, ... }

`hash` is a sha256 over the unit's sorted, BOM/EOL-normalised evidence files
(content), so it is stable cross-OS and invalidates automatically on any source
edit. Deterministic, 0 token.

Public API:
    compute_unit_evidence_hash(project_root, unit) -> str
    load_cache(project_root) -> dict
    save_unit(project_root, unit_id, hash_, n, name) -> None
    is_unit_cached(project_root, unit, feats_dir, plans_dir=None, us_dir=None) -> bool
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.scan_legacy import normalize_bytes

_CACHE_NAME = "extraction-cache.json"


def _cache_path(project_root: Path) -> Path:
    return project_root / ".sys" / _CACHE_NAME


def compute_unit_evidence_hash(project_root: str | Path, unit: dict[str, Any]) -> str:
    """sha256 over the unit's evidence files (sorted, normalised)."""
    root = Path(project_root).resolve()
    h = hashlib.sha256()
    for rel in sorted(unit.get("evidenceFiles", [])):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        p = root / rel
        try:
            h.update(normalize_bytes(p.read_bytes()))
        except OSError:
            h.update(b"<missing>")
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def load_cache(project_root: str | Path) -> dict[str, Any]:
    p = _cache_path(Path(project_root).resolve())
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_unit(project_root: str | Path, unit_id: str, hash_: str, n: int, name: str) -> None:
    root = Path(project_root).resolve()
    cache = load_cache(root)
    cache[unit_id] = {"hash": hash_, "n": n, "name": name}
    atomic_write_text(_cache_path(root), json.dumps(cache, indent=2, ensure_ascii=False) + "\n")


def is_unit_cached(
    project_root: str | Path,
    unit: dict[str, Any],
    feats_dir: str | Path,
    plans_dir: str | Path | None = None,
    us_dir: str | Path | None = None,
) -> bool:
    """True if the unit's evidence hash matches cache AND its artefacts still exist.

    "Its artefacts" is the whole ladder, not just the top rung (M5, audit
    2026-08-29). Checking only `feats/{n}-{name}.md` made the cache lie on a
    PARTIALLY cleaned workspace: the documented way to force US regeneration is
    to delete `workspace/us/`, and doing exactly that produced a cache HIT and
    skipped the unit — the US never came back, and the FEAT above them silently
    kept covering stories that no longer existed on disk.

    `plans_dir` / `us_dir` are optional so existing two-argument callers keep
    their behaviour; the CLI (`update_extraction_cache.py --check`) passes both.
    A `db-module` unit climbs a 2-rung ladder with no 3a analysis, so the plan
    requirement is skipped for it — same shape dispatch as
    `check_ladder_traceability`. Doubt → False → re-extract (fail-safe).
    """
    root = Path(project_root).resolve()
    cache = load_cache(root)
    entry = cache.get(unit["id"])
    if not entry:
        return False
    if entry.get("hash") != compute_unit_evidence_hash(root, unit):
        return False
    n, name = entry.get("n"), entry.get("name")
    if n is None or not name:
        return False
    if not (Path(feats_dir) / f"{n}-{name}.md").is_file():
        return False
    if plans_dir is not None and unit.get("kind") != "db-module":
        if not (Path(plans_dir) / f"{n}-{name}.analysis.md").is_file():
            return False
    if us_dir is not None:
        # US filenames carry a per-capability slug, so match on the {n}- prefix
        # only (same convention as check_ladder_traceability).
        us_path = Path(us_dir)
        if not (us_path.is_dir() and any(us_path.glob(f"{n}-*.md"))):
            return False
    return True
