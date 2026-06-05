"""SSoT loader for `.claude/templates/combos.json` — validated combos + per-component levels.

v7.0.0-alpha (audit CRIT-6, 2026-06-04) : consolidates the previously
duplicated `VALIDATED_COMBOS`/`COMPONENT_LEVELS` from `validate_stack_combo.py`
and the hardcoded `"validation": "🟢"` field per entry in
`match_stack_catalog.STACK_RULES`. Single load path with mtime-keyed
cache (same pattern as `read_stack_md_text` in `project_config.py`).

The per-stack `Validation:` markdown header in
`.claude/stacks/{cat}/{stack-id}.md` remains the **human-readable
source of truth** — this loader exposes the **machine** mirror.
Cross-check enforced by `tests/test_combos_cross_check.py`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sdd_lib.paths import repo_root


def combos_json_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".claude" / "templates" / "combos.json"


@lru_cache(maxsize=2)
def _load_json_cached(path_str: str, mtime_ns: int) -> dict[str, Any]:
    """Cached load keyed on (resolved path, mtime_ns). DO NOT call directly."""
    del mtime_ns  # part of the cache key only
    with open(path_str, encoding="utf-8") as f:
        return json.load(f)


def load_combos(root: Path | None = None) -> dict[str, Any]:
    """Load `combos.json` from the framework templates dir.

    Returns the full payload dict (combos + componentLevels + levelPriority +
    schemaVersion metadata). Cache invalidates automatically when the file's
    mtime changes (Tech Lead edit, framework upgrade, git checkout).

    Raises FileNotFoundError if the SSoT file is missing — that's a
    framework-integrity error (a fresh checkout would always include it).
    """
    path = combos_json_path(root)
    if not path.is_file():
        raise FileNotFoundError(
            f"combos.json not found at {path} — framework integrity error. "
            f"Restore from git or reinstall .claude/templates/."
        )
    mtime_ns = path.stat().st_mtime_ns
    return _load_json_cached(str(path.resolve()), mtime_ns)


def get_validated_combos(root: Path | None = None) -> list[dict[str, Any]]:
    """Return the list of validated combos (C1, C2, …).

    Each combo's `qa` field is a list (JSON-native) — callers comparing
    sets should `set(combo["qa"])` themselves.
    """
    return load_combos(root).get("combos", [])


def get_component_levels(root: Path | None = None) -> dict[str, dict[str, str]]:
    """Return the per-category {stack_id: level} mapping.

    Strips the embedded `_doc` metadata key for callers iterating
    categories.
    """
    raw = load_combos(root).get("componentLevels", {})
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}


def get_component_level(
    category: str, stack_id: str | None, *, root: Path | None = None
) -> str:
    """Return validation level for a (category, stack_id) pair.

    Convention:
      - `stack_id is None`              → "missing"
      - stack_id not in componentLevels → "untested"
      - else                             → declared level
    """
    if stack_id is None:
        return "missing"
    return get_component_levels(root).get(category, {}).get(stack_id, "untested")


def get_level_priority(root: Path | None = None) -> dict[str, int]:
    """Return severity ordering used to compute the overall combo verdict."""
    raw = load_combos(root).get("levelPriority", {})
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, int)}


def clear_combos_cache() -> None:
    """Drop the cached payload (forces a re-read on the next call)."""
    _load_json_cached.cache_clear()
