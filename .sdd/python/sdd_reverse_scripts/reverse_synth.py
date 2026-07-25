"""reverse_synth.py — Synthesis layer CLI (Phase 3.7, deterministic, no agent).

Read-only consumer of the deterministic reverse artefacts. Produces the
"system view" documents that the 3a->3b->3c ladder does NOT produce, WITHOUT
touching the ladder or the FEAT contract:

    .sys/synthesis/c4-context.md       (always)
    .sys/synthesis/c4-containers.md    (doc-level complet|detaille)
    .sys/synthesis/c4-components.md    (doc-level complet|detaille)
    .sys/synthesis/erd-complete.md     (if a db schema exists)
    .sys/synthesis/soul.md             (always)
    .sys/synthesis/manifest.json       (observability / synthesis "memory")

Firewall: writes ONLY under workspace/old/{P}/.sys/synthesis/ — NEVER under
workspace/feats/, so /sdd-full never mistakes a C4/ERD doc for a FEAT.

The manifest.json is a DERIVED record (regenerated each run), not a mutable
source of truth: the SSoT remains the artefacts on disk, exactly like
reverse_status.py derives state from files.

Invocation:
    python -m sdd_reverse_scripts.reverse_synth --project workspace/old/{P} \
        [--doc-level essentiel|complet|detaille] [--only c4,erd,soul] [--json]

Exit codes:
    0 OK   1 bad args / project missing   2 no usable artefacts (run inventory)   3 I/O error
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.synthesis import build_c4, build_soul, render_erd

_MANIFEST_SCHEMA = 1


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _rollup_merge(into: dict[str, int], add: dict[str, int]) -> None:
    for k in ("high", "medium", "low"):
        into[k] = into.get(k, 0) + add.get(k, 0)


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    parser = argparse.ArgumentParser(
        prog="reverse_synth",
        description="Deterministic reverse synthesis layer (C4, ERD, soul). No agent.",
    )
    parser.add_argument("--project", required=True, help="workspace/old/{P}/")
    parser.add_argument("--doc-level", default="complet",
                        choices=["essentiel", "complet", "detaille"],
                        help="Scope/verbosity knob (context-economy). Default: complet")
    parser.add_argument("--only", default=None,
                        help="Comma list among {c4,erd,soul} to restrict output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project).resolve()
    if not project_root.is_dir():
        print(f"ERROR: project root not found: {project_root}", file=sys.stderr)
        return 1

    sys_dir = project_root / ".sys"
    inventory = _load_json(sys_dir / "inventory.json")
    if not inventory:
        print("ERROR: [REVERSE_NO_SOURCE] inventory.json missing — run "
              "/sdd-reverse-inventory first.", file=sys.stderr)
        return 2
    if inventory.get("schemaVersion") != 1:
        print("ERROR: [REVERSE_INVENTORY_SCHEMA_STALE] inventory.json schemaVersion "
              "!= 1 — re-run /sdd-reverse-inventory.", file=sys.stderr)
        return 2

    deps_graph = _load_json(sys_dir / "deps-graph.json") or {}
    db_schema = (
        _load_json(sys_dir / "db-schema.merged.json")
        or _load_json(sys_dir / "db-schema.json")
        or {}
    )

    only = None
    if args.only:
        only = {s.strip().lower() for s in args.only.split(",") if s.strip()}

    def _wanted(name: str) -> bool:
        return only is None or name in only

    out_dir = sys_dir / "synthesis"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"ERROR: [INFRA_BLOCKED] cannot create {out_dir}: {e}", file=sys.stderr)
        return 3

    # Idempotence: remove stale managed outputs of each regenerated category
    # (e.g. re-running at a lower doc-level must not leave a previous run's
    # c4-containers/components behind). Categories NOT requested via --only
    # are left untouched.
    _managed = {
        "c4": ["c4-context.md", "c4-containers.md", "c4-components.md"],
        "erd": ["erd-complete.md"],
        "soul": ["soul.md"],
    }
    for category, files in _managed.items():
        if not _wanted(category):
            continue
        for fname in files:
            stale = out_dir / fname
            try:
                stale.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass  # best-effort; the write below will overwrite anyway

    written: list[dict[str, Any]] = []
    rollup_total = {"high": 0, "medium": 0, "low": 0}

    try:
        # --- C4 (context always; containers/components per doc-level) ---
        if _wanted("c4"):
            docs, rollup = build_c4(inventory, deps_graph, doc_level=args.doc_level)
            _rollup_merge(rollup_total, rollup)
            for name, content in docs.items():
                out = out_dir / f"{name}.md"
                atomic_write_text(out, content)
                written.append({"name": name, "path": str(out),
                                "source": ["inventory.json", "deps-graph.json"]})

        # --- ERD ---
        if _wanted("erd"):
            content, rollup = render_erd(db_schema)
            _rollup_merge(rollup_total, rollup)
            out = out_dir / "erd-complete.md"
            atomic_write_text(out, content)
            written.append({"name": "erd-complete", "path": str(out),
                            "source": ["db-schema.merged.json"]})

        # --- soul.md ---
        if _wanted("soul"):
            content, rollup = build_soul(inventory, deps_graph, db_schema)
            _rollup_merge(rollup_total, rollup)
            out = out_dir / "soul.md"
            atomic_write_text(out, content)
            written.append({"name": "soul", "path": str(out),
                            "source": ["inventory.json", "deps-graph.json",
                                       "db-schema.merged.json"]})

        # --- manifest.json (derived observability record) ---
        manifest = {
            "schemaVersion": _MANIFEST_SCHEMA,
            "project": inventory.get("project") or project_root.name,
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "docLevel": args.doc_level,
            "inputs": {
                "inventory": True,
                "depsGraph": bool(deps_graph),
                "dbSchema": bool(db_schema.get("entities")),
            },
            "artifacts": written,
            "confidenceRollup": rollup_total,
        }
        atomic_write_text(out_dir / "manifest.json",
                          json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"ERROR: [INFRA_BLOCKED] write failed: {e}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps({"ok": True, "written": [w["path"] for w in written],
                          "confidenceRollup": rollup_total,
                          "docLevel": args.doc_level}, ensure_ascii=False))
    else:
        names = ", ".join(Path(w["path"]).name for w in written)
        r = rollup_total
        print(f"[REVERSE] Synthèse ({args.doc_level}) : {names} "
              f"[confiance high={r['high']} medium={r['medium']} low={r['low']}]. (100%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
