"""reverse_cache.py — Phase 3 extraction cache (L5).

The forward pipeline avoids re-doing stable work; the reverse pipeline had no
Phase 3 cache, so an orchestrator re-run re-spawned Opus on every unit even when
nothing changed. This helper lets the orchestrator skip a unit whose evidence is
byte-identical to the last successful extraction AND whose FEAT still exists.

Cache file: workspace/old/{P}/.sys/extraction-cache.json
    { "<U-N>": { "hash": "sha256:…", "n": 3, "name": "Login" }, ... }

`hash` is a sha256 over the unit's sorted, BOM/EOL-normalised evidence files
(content), so it is stable cross-OS and invalidates automatically on any source
edit. Deterministic, 0 token.

Public API:
    compute_unit_evidence_hash(project_root, unit) -> str
    load_cache(project_root) -> dict
    save_unit(project_root, unit_id, hash_, n, name) -> None
    is_unit_cached(project_root, unit, feats_dir) -> bool
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
    project_root: str | Path, unit: dict[str, Any], feats_dir: str | Path
) -> bool:
    """True if the unit's evidence hash matches cache AND its FEAT file exists."""
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
    feat = Path(feats_dir) / f"{n}-{name}.md"
    return feat.is_file()
