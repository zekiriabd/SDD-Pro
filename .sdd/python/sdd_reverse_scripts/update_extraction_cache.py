"""update_extraction_cache.py — CLI wiring for the L5 extraction cache (C4).

Audit 2026-06-10 C4 : `reverse_cache.save_unit` had ZERO production caller —
`is_unit_cached` always returned False, so STEP 3a of /sdd-reverse-full and
`--no-cache` were dead and every resume re-paid all Opus extractions.

Two modes (deterministic, 0 token) :

    --save   (agent reverse-feat-composer, barreau 3c STEP 5) :
        python .sdd/python/sdd_reverse_scripts/update_extraction_cache.py \
            --project workspace/old/{P} --unit U-3 --n 3 --name Login --save
        Computes the unit evidence hash and persists the cache entry.

    --check  (orchestrator /sdd-reverse-full, STEP 3a) :
        python .sdd/python/sdd_reverse_scripts/update_extraction_cache.py \
            --project workspace/old/{P} --unit U-3 --check \
            [--feats-dir DIR] [--plans-dir DIR] [--us-dir DIR]
        Exit 0 = cached (skip extraction) ; exit 1 = not cached (extract).
        A HIT requires the FEAT **and** the 3a plan **and** ≥ 1 3b US on disk
        (M5, audit 2026-08-29) — the plan is not required for `db-module` units,
        whose ladder has no 3a rung.

Exit codes:
    0  saved OK / cache hit (--check)
    1  cache miss (--check only)
    2  bad args / unit not found / inventory missing
    3  I/O error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.reverse_cache import (
    compute_unit_evidence_hash,
    is_unit_cached,
    save_unit,
)


def _load_unit(project_root: Path, unit_id: str) -> dict | None:
    inv_path = project_root / ".sys" / "inventory.json"
    try:
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for u in inv.get("units", []):
        if u.get("id") == unit_id:
            return u
    return None


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    parser = argparse.ArgumentParser(prog="update_extraction_cache")
    parser.add_argument("--project", required=True, help="workspace/old/{P}/")
    parser.add_argument("--unit", required=True, help="U-N")
    parser.add_argument("--save", action="store_true", help="Persist cache entry (post-extraction)")
    parser.add_argument("--check", action="store_true", help="Exit 0 if unit is cached, 1 otherwise")
    parser.add_argument("--n", type=int, default=None, help="FEAT number (required with --save)")
    parser.add_argument("--name", default=None, help="FEAT Name (required with --save)")
    parser.add_argument("--feats-dir", default=None,
        help="FEATs directory (default: workspace/feats relative to repo)")
    parser.add_argument("--plans-dir", default=None,
        help="Plans directory (default: sibling workspace/plans). A cache HIT "
             "requires {n}-{name}.analysis.md there, except for db-module units.")
    parser.add_argument("--us-dir", default=None,
        help="User-stories directory (default: sibling workspace/us). A cache HIT "
             "requires at least one {n}-*.md there.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.save == args.check:
        print("ERROR: exactly one of --save / --check required.", file=sys.stderr)
        return 2

    project_root = Path(args.project).resolve()
    unit = _load_unit(project_root, args.unit)
    if unit is None:
        print(f"ERROR: [REVERSE_UNIT_NOT_FOUND] {args.unit} absent de "
              f"{project_root / '.sys' / 'inventory.json'}", file=sys.stderr)
        return 2

    feats_dir = Path(args.feats_dir).resolve() if args.feats_dir else (
        project_root.parent.parent / "feats"
    )
    # M5 (audit 2026-08-29): a HIT must mean "the whole ladder is still on disk",
    # not just the FEAT — deleting workspace/us/ to force US regeneration used to
    # be swallowed as a cache hit. Siblings of workspace/feats/ by default.
    workspace = feats_dir.parent
    plans_dir = Path(args.plans_dir).resolve() if args.plans_dir else workspace / "plans"
    us_dir = Path(args.us_dir).resolve() if args.us_dir else workspace / "us"

    if args.check:
        cached = is_unit_cached(project_root, unit, feats_dir, plans_dir, us_dir)
        if args.json:
            print(json.dumps({"ok": True, "unit": args.unit, "cached": cached}))
        else:
            print(f"[REVERSE] Cache {args.unit}: {'HIT (skip extraction)' if cached else 'MISS (extract)'}. (100%)")
        return 0 if cached else 1

    # --save
    if args.n is None or not args.name:
        print("ERROR: --save requires --n and --name.", file=sys.stderr)
        return 2
    try:
        h = compute_unit_evidence_hash(project_root, unit)
        save_unit(project_root, args.unit, h, args.n, args.name)
    except OSError as e:
        print(f"ERROR: [INFRA_BLOCKED] cannot write extraction-cache.json: {e}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps({"ok": True, "unit": args.unit, "saved": True, "hash": h}))
    else:
        print(f"[REVERSE] Cache {args.unit} -> {args.n}-{args.name} enregistre. (100%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
