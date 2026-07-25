"""sync_parity_snapshots.py — Regenerate _parity_snapshots.json (P3.13).

When the Tech Lead intentionally syncs `sdd_reverse/{atomic_write_local,
file_locks_local}.py` to match a new `sdd_lib/*` mitigation (or
explicitly decides to keep a divergence), the snapshot hashes in
`sdd_reverse/_parity_snapshots.json` must be refreshed. Otherwise
`reverse_smoke.check_helper_parity_drift` keeps emitting WARN
forever (false positive after a deliberate sync).

This script is the **manual** counterpart of that decision : it
computes fresh SHA-256 hashes of the tracked upstream files and
rewrites `_parity_snapshots.json` atomically. Designed to be invoked
by the maintainer only — never auto-triggered by any pipeline.

Invocation :
    python -m sdd_reverse_scripts.sync_parity_snapshots [--dry-run] [--json]

Output (non-JSON mode) :
    Diff per tracked file (old hash → new hash) + summary.

Exit codes :
    0   snapshots regenerated successfully (or already up to date)
    1   one or more tracked files missing on disk
    2   I/O error writing the snapshots file
    3   invalid argument

Audit trail :
    The previous snapshots file is preserved as `_parity_snapshots.prev.json`
    so the maintainer can `git diff` to verify the change is intentional
    before committing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.paths import parity_snapshots_path, sdd_reverse_dir


# Files whose hashes are tracked. Relative to .claude/python/.
# Adding a new tracked file = add to this list AND document the
# rationale in design doc §12.7.bis.
# Audit 2026-06-10 : LOCAL copies added — the net was unidirectional
# (only sdd_lib/* hashed), so editing the local duplicates triggered
# nothing. Both directions now drift-detected.
_TRACKED: tuple[str, ...] = (
    "sdd_lib/atomic_write.py",
    "sdd_lib/file_locks.py",
    "sdd_reverse/atomic_write_local.py",
    "sdd_reverse/file_locks_local.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_fresh_snapshots(python_root: Path) -> dict[str, str]:
    """Compute current hashes for every tracked file. Raises FileNotFoundError
    if any tracked file is absent — caller decides how to surface this."""
    out: dict[str, str] = {}
    missing: list[str] = []
    for rel in _TRACKED:
        p = python_root / rel
        if not p.is_file():
            missing.append(rel)
            continue
        out[rel] = _sha256(p)
    if missing:
        raise FileNotFoundError(
            f"Tracked files missing on disk: {missing}. "
            "Either restore the file or update _TRACKED."
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    parser = argparse.ArgumentParser(
        prog="sync_parity_snapshots",
        description="Regenerate sdd_reverse/_parity_snapshots.json after a deliberate helper sync.",
    )
    parser.add_argument("--dry-run", action="store_true",
        help="Show what would change but don't write the snapshots file.")
    parser.add_argument("--json", action="store_true",
        help="Emit a structured JSON report on stdout.")
    args = parser.parse_args(argv)

    snap_path = parity_snapshots_path()
    python_root = snap_path.resolve().parents[1]  # .claude/python/

    # Read existing snapshots (for diff + preservation)
    try:
        existing = json.loads(snap_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        if args.json:
            print(json.dumps({"ok": False, "error": f"cannot read snapshots: {e}"}))
        else:
            print(f"ERROR: cannot read existing snapshots: {e}", file=sys.stderr)
        return 2

    try:
        fresh = compute_fresh_snapshots(python_root)
    except FileNotFoundError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    old_snapshots = existing.get("snapshots") or {}
    diff: list[dict[str, str]] = []
    for rel, new_hash in fresh.items():
        old_hash = old_snapshots.get(rel)
        if old_hash != new_hash:
            diff.append({
                "file": rel,
                "old": old_hash or "(missing)",
                "new": new_hash,
            })

    report = {
        "ok": True,
        "snapshots_path": str(snap_path.relative_to(python_root)),
        "tracked": list(_TRACKED),
        "diff": diff,
        "changed_count": len(diff),
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print("=== Parity Snapshots — Dry Run ===")
            if not diff:
                print("All tracked hashes already up to date — no changes needed.")
            else:
                for d in diff:
                    print(f"  {d['file']}")
                    print(f"    old: {d['old'][:16]}...")
                    print(f"    new: {d['new'][:16]}...")
                print(f"\nWould rewrite {len(diff)} hash(es) in {snap_path.name}.")
        return 0

    # Build new snapshots document (preserve schemaVersion + notes)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_doc = {
        "schemaVersion": existing.get("schemaVersion", 1),
        "createdAt": existing.get("createdAt", now_iso),
        "updatedAt": now_iso,
        "purpose": existing.get(
            "purpose",
            "ADV-16 parity tracking. Drift detection: if any hash here differs "
            "from current sdd_lib/* hash, reverse helpers may need a refresh sync.",
        ),
        "snapshots": fresh,
        # Audit 2026-06-11 (B3) : préserver _note (explication MA-9 de la
        # non-parité API de file_locks_local) — la régénération la perdait.
        **({"_note": existing["_note"]} if "_note" in existing else {}),
        "notes": existing.get(
            "notes",
            "Hashes computed against sdd_lib/* at the most recent deliberate sync. "
            "Regenerate via: python -m sdd_reverse_scripts.sync_parity_snapshots",
        ),
    }

    # Backup local transient du snapshot précédent (.prev.json est GITIGNORÉ —
    # ce n'est PAS un artefact d'audit git, juste un filet de sécurité local ;
    # audit 2026-06-11 B3, l'ancienne mention « git diff auditability » mentait).
    prev_path = snap_path.with_suffix(".prev.json")
    try:
        atomic_write_text(prev_path, json.dumps(existing, indent=2, ensure_ascii=False) + "\n")
        atomic_write_text(snap_path, json.dumps(new_doc, indent=2, ensure_ascii=False) + "\n")
    except OSError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": f"write failed: {e}"}))
        else:
            print(f"ERROR: write failed: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=== Parity Snapshots — Regenerated ===")
        if not diff:
            print("All hashes already up to date (file rewritten with refreshed updatedAt).")
        else:
            for d in diff:
                print(f"  {d['file']}")
                print(f"    old: {d['old'][:16]}...")
                print(f"    new: {d['new'][:16]}...")
            print(f"\n{len(diff)} hash(es) updated.")
        print(f"\nPrevious snapshots preserved at: {prev_path.name}")
        print("Run `git diff` to verify the sync is intentional before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
