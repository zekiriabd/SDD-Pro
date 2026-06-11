"""preallocate_feats.py — Deterministic FEAT name/number pre-allocation (L5).

The Phase 3 extractor used to allocate `(n, Name)` per unit *at extraction time*,
behind the `.alloc.lock`, which forced strict sequential execution (ADV-2) — a
40-unit legacy meant 40 serial Opus invocations.

This script pre-allocates `(n, Name)` for EVERY unit up-front, once, under a
single lock, writing the result into inventory.json `_featAllocations` +
`_allocatedNames`. After that, each unit's `(n, Name)` is fixed, so Phase 3
extraction can run in BOUNDED PARALLEL: each agent reads its pre-allocated
identity and writes a disjoint `{n}-{Name}.md` — no shared allocation, no lock
contention (ADV-2 relaxed to parallel-safe, see rules/reverse-engineering.md §8).

Allocation is deterministic + idempotent: same inventory → same mapping; re-run
preserves existing allocations and only fills new units. Collision handling
mirrors the extractor agent (suffix `-Legacy`, then `-Legacy-{U-N}`).

Invocation:
    python -m sdd_reverse_scripts.preallocate_feats --project workspace/old/{P} [--feats-dir DIR] [--json]

Exit: 0 OK | 1 bad args / inventory missing | 3 lock/IO error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.file_locks_local import acquire_lock, release_lock


def _sanitize_name(raw: str) -> str:
    """PascalCase, no accents/spaces — defensive (suggestedName is usually clean)."""
    cleaned = re.sub(r"[^0-9A-Za-z]+", "-", raw).strip("-")
    parts = [p for p in cleaned.split("-") if p]
    name = "".join(p[:1].upper() + p[1:] for p in parts) or "Unit"
    return name


def _existing_feat_numbers(feats_dir: Path) -> set[int]:
    nums: set[int] = set()
    if feats_dir.is_dir():
        for f in feats_dir.glob("*.md"):
            m = re.match(r"(\d+)-", f.name)
            if m:
                nums.add(int(m.group(1)))
    return nums


def _existing_feat_names(feats_dir: Path) -> set[str]:
    names: set[str] = set()
    if feats_dir.is_dir():
        for f in feats_dir.glob("*.md"):
            m = re.match(r"\d+-(.+)\.md$", f.name)
            if m:
                names.add(m.group(1))
    return names


def preallocate(
    inventory: dict[str, Any], feats_dir: Path
) -> tuple[dict[str, int], dict[str, str], dict[str, str]]:
    """Compute (featAllocations, allocatedNames, unit->Name) deterministically.

    Returns updated `_featAllocations`, `_allocatedNames`, and a per-unit
    resolved Name map. Pure — does not write anything.
    """
    feat_allocs: dict[str, int] = dict(inventory.get("_featAllocations") or {})
    allocated_names: dict[str, str] = dict(inventory.get("_allocatedNames") or {})
    units = inventory.get("units", [])

    used_numbers = _existing_feat_numbers(feats_dir) | set(feat_allocs.values())
    used_names = _existing_feat_names(feats_dir) | set(allocated_names.keys())

    def _next_free_number() -> int:
        n = 1
        while n in used_numbers:
            n += 1
        return n

    def _resolve_name(base: str, unit_id: str) -> str:
        # Already allocated to THIS unit → reuse (idempotent).
        for nm, uid in allocated_names.items():
            if uid == unit_id:
                return nm
        if base not in used_names:
            return base
        cand = f"{base}-Legacy"
        if cand not in used_names:
            return cand
        return f"{base}-Legacy-{unit_id}"

    unit_name: dict[str, str] = {}
    for u in units:
        uid = u["id"]
        base = _sanitize_name(u.get("suggestedName") or uid)
        name = _resolve_name(base, uid)
        unit_name[uid] = name
        used_names.add(name)
        allocated_names[name] = uid
        if uid not in feat_allocs:
            n = _next_free_number()
            used_numbers.add(n)
            feat_allocs[uid] = n

    return feat_allocs, allocated_names, unit_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="preallocate_feats")
    parser.add_argument("--project", required=True, help="workspace/old/{P}/")
    parser.add_argument("--feats-dir", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    ensure_console_safe()

    project_root = Path(args.project).resolve()
    inventory_path = project_root / ".sys" / "inventory.json"
    if not inventory_path.is_file():
        print(f"ERROR: [REVERSE_NO_SOURCE] inventory.json missing at {inventory_path}",
              file=sys.stderr)
        return 1
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: [INFRA_BLOCKED] cannot read inventory.json: {e}", file=sys.stderr)
        return 3

    feats_dir = Path(args.feats_dir).resolve() if args.feats_dir else (
        project_root.parent.parent / "input" / "feats"
    )
    feats_dir.mkdir(parents=True, exist_ok=True)

    lock_path = str(feats_dir / ".alloc.lock")
    code = acquire_lock(lock_path, "preallocate-feats", ttl=60)
    if code in (1, 3):
        print("ERROR: [REVERSE_LOCK_HELD] .alloc.lock unavailable.", file=sys.stderr)
        return 3
    try:
        feat_allocs, allocated_names, unit_name = preallocate(inventory, feats_dir)
        inventory["_featAllocations"] = feat_allocs
        inventory["_allocatedNames"] = allocated_names
        atomic_write_text(inventory_path,
                          json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
    finally:
        release_lock(lock_path, "preallocate-feats")

    mapping = {uid: {"n": feat_allocs[uid], "name": unit_name[uid]}
               for uid in unit_name}
    if args.json:
        print(json.dumps({"ok": True, "allocations": mapping}))
    else:
        preview = ", ".join(
            f"{v['n']}-{v['name']}" for _, v in sorted(mapping.items())
        )[:200]
        # ASCII only (M10 — this is the NOMINAL STEP 2.5 path on Windows)
        print(f"[REVERSE] Pre-allocation : {len(mapping)} unite(s) -> {preview}. (100%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
