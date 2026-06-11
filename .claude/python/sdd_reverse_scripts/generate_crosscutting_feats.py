"""generate_crosscutting_feats.py — Emit the L3 cross-cutting reverse FEATs.

Reads the deterministic Phase-1 artefacts of a legacy project and writes two
standard reverse FEATs into workspace/input/feats/ :

    {n}-Libraries.md   — libraries / DLLs to install on the target stack
    {n}-Database.md    — schema + stored procedures + connection strings

Allocation of `n` is idempotent: recorded under synthetic keys
`XC-Libraries` / `XC-Database` in inventory.json `_featAllocations` (+ Names in
`_allocatedNames`), so re-running overwrites the same files. Writes happen under
the shared `.alloc.lock` (same as Phase 3) to stay race-free.

Invocation:
    python -m sdd_reverse_scripts.generate_crosscutting_feats --project workspace/old/{P} [--feats-dir DIR] [--json]

Exit codes:
    0 OK   1 bad args / project missing   2 no usable artefacts   3 I/O error
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
from sdd_reverse.crosscutting_feats import build_database_feat, build_libraries_feat
from sdd_reverse.file_locks_local import acquire_lock, release_lock


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _existing_feat_numbers(feats_dir: Path) -> set[int]:
    nums: set[int] = set()
    if not feats_dir.is_dir():
        return nums
    for f in feats_dir.glob("*.md"):
        m = re.match(r"(\d+)-", f.name)
        if m:
            nums.add(int(m.group(1)))
    return nums


def _next_free(used: set[int]) -> int:
    n = 1
    while n in used:
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    parser = argparse.ArgumentParser(prog="generate_crosscutting_feats")
    parser.add_argument("--project", required=True, help="workspace/old/{P}/")
    parser.add_argument("--feats-dir", default=None,
                        help="Override feats output dir (default workspace/input/feats)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project).resolve()
    if not project_root.is_dir():
        print(f"ERROR: project root not found: {project_root}", file=sys.stderr)
        return 1

    sys_dir = project_root / ".sys"
    inventory_path = sys_dir / "inventory.json"
    inventory = _load_json(inventory_path) or {}
    dependencies = _load_json(sys_dir / "dependencies.json") or {}
    data_access = _load_json(sys_dir / "data-access.json") or {}
    config = _load_json(sys_dir / "config.json") or {}
    db_schema = (
        _load_json(sys_dir / "db-schema.merged.json")
        or _load_json(sys_dir / "db-schema.json")
        or {}
    )

    if not (dependencies or db_schema or data_access or config):
        print("ERROR: no Phase-1 technical artefacts found (run /sdd-reverse-inventory first).",
              file=sys.stderr)
        return 2

    if args.feats_dir:
        feats_dir = Path(args.feats_dir).resolve()
    else:
        # workspace/old/{P} → workspace/input/feats
        feats_dir = project_root.parent.parent / "input" / "feats"
    feats_dir.mkdir(parents=True, exist_ok=True)

    project_name = inventory.get("project") or project_root.name
    language = inventory.get("primaryLanguage") or "unknown"

    feat_allocs: dict[str, int] = dict(inventory.get("_featAllocations") or {})
    allocated_names: dict[str, str] = dict(inventory.get("_allocatedNames") or {})

    lock_path = str(feats_dir / ".alloc.lock")
    code = acquire_lock(lock_path, "crosscutting-feats", ttl=30)
    if code == 1:
        print("ERROR: [REVERSE_LOCK_HELD] .alloc.lock held by another agent.", file=sys.stderr)
        return 3
    if code == 3:
        print("ERROR: [INFRA_BLOCKED] cannot acquire .alloc.lock.", file=sys.stderr)
        return 3

    written: list[str] = []
    try:
        used = _existing_feat_numbers(feats_dir) | set(feat_allocs.values())

        plan = [
            ("XC-Libraries", "Libraries",
             lambda n: build_libraries_feat(dependencies, n=n, name="Libraries",
                                            project=project_name, language=language)),
            ("XC-Database", "Database",
             lambda n: build_database_feat(db_schema, data_access, config, n=n,
                                           name="Database", project=project_name, language=language)),
        ]

        for key, name, builder in plan:
            n = feat_allocs.get(key)
            if n is None:
                n = _next_free(used)
                used.add(n)
                feat_allocs[key] = n
                allocated_names[name] = key
            content = builder(n)
            out = feats_dir / f"{n}-{name}.md"
            atomic_write_text(out, content + "\n")
            written.append(str(out))

        # Persist allocations back into inventory.json (atomic).
        if inventory:
            inventory["_featAllocations"] = feat_allocs
            inventory["_allocatedNames"] = allocated_names
            atomic_write_text(inventory_path,
                              json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
    finally:
        release_lock(lock_path, "crosscutting-feats")

    if args.json:
        print(json.dumps({"ok": True, "written": written,
                          "allocations": {k: feat_allocs[k] for k in ("XC-Libraries", "XC-Database")}}))
    else:
        print(f"[REVERSE] Cross-cutting FEATs: {', '.join(Path(w).name for w in written)}. (100%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
