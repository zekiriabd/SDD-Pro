"""Remove orphan artifacts from workspace/output/ (with .trash/ backup).

v7.0.0 (audit 2026-06-05) — implémentation effective des scripts
spec'd dans `docs/orphan-cleanup-policy.md §4.2`.

Workflow :
1. Run `audit_orphans.find_orphans()` pour identifier les cibles
2. Affiche le plan
3. Si `--yes` (et stdin tty), demande confirmation
4. Pour chaque fichier orphan :
   - cp vers `workspace/output/.sys/.trash/{ts}/{relative-path}`
   - rm du fichier original
   - log dans `console.db.events` (best-effort, non-bloquant)

Usage :
    python cleanup_orphans.py [--feat N] [--dry-run] [--yes] [--root PATH]

Exit codes :
    0 = SUCCESS (clean OR removals completed)
    1 = FAIL_FAST (user declined OR safety check failed)
    3 = INFRA_BLOCKED (workspace inaccessible)

Périmètre PROTÉGÉ — never delete (cf. policy §5) :
    - workspace/input/ (sources Tech Lead)
    - workspace/output/.sys/.context/constitution.md
    - workspace/output/.sys/.context/adrs/*
    - workspace/output/db/console.db*
    - workspace/console/
    - workspace/output/.sys/.trash/ (lui-même)
    - tout fichier hors workspace/output/
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_admin.audit_orphans import find_orphans  # noqa: E402


# Périmètres absolument protégés (substring match sur paths relatifs au root).
_PROTECTED_PATHS = (
    "workspace/input/",
    "workspace/output/.sys/.context/constitution.md",
    "workspace/output/.sys/.context/adrs/",
    "workspace/output/db/",
    "workspace/console/",
    "workspace/output/.sys/.trash/",
)


def _is_protected(rel_path: str) -> bool:
    """Check whether a given relative path is in the protected zone."""
    norm = rel_path.replace("\\", "/")
    if not norm.startswith("workspace/output/"):
        return True  # paranoid : never touch outside workspace/output
    return any(norm.startswith(p) for p in _PROTECTED_PATHS)


def _collect_target_paths(orphans: dict[str, list[dict]]) -> list[str]:
    """Flatten all path entries from audit_orphans output."""
    targets: list[str] = []
    for category, items in orphans.items():
        for entry in items:
            path = entry.get("path")
            if path:
                targets.append(path)
    return targets


def _trash_one(root: Path, rel_path: str, trash_dir: Path, dry_run: bool) -> bool:
    """Move `rel_path` to trash_dir (preserve sub-structure)."""
    src = root / rel_path
    if not src.exists():
        return False
    dst = trash_dir / rel_path
    if dry_run:
        return True
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.move(str(src), str(dst))
        else:
            shutil.move(str(src), str(dst))
        return True
    except OSError as e:
        print(f"  ⚠ failed to move {rel_path}: {e}", file=sys.stderr)
        return False


def _record_event(root: Path, action: str, paths: list[str]) -> None:
    """Best-effort log to console.db `events` table (non-blocking)."""
    db_path = root / "workspace" / "output" / "db" / "console.db"
    if not db_path.exists():
        return
    try:
        import sqlite3
        con = sqlite3.connect(str(db_path), timeout=2.0)
        try:
            con.execute(
                """INSERT INTO events (run_id, ts, agent, phase, payload_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    "cleanup-orphans",
                    _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "cleanup_orphans",
                    action,
                    '{"paths_count": ' + str(len(paths)) + '}',
                ),
            )
            con.commit()
        finally:
            con.close()
    except Exception:
        # Telemetry is best-effort — never abort cleanup
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove orphan artifacts (with .trash/ backup, 7-day recovery)"
    )
    parser.add_argument("--feat", type=int, default=None,
                        help="Restrict to FEAT N (default: scan all)")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Repository root (default: cwd)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be moved; do not modify FS (default if --yes absent)")
    parser.add_argument("--yes", action="store_true",
                        help="Actually perform removals (requires tty for interactive confirmation)")
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    if not root.exists() or not (root / ".claude").is_dir():
        print(f"ERROR: {root} is not a SDD_Pro project root (.claude/ missing)",
              file=sys.stderr)
        return INFRA_BLOCKED

    # Default to dry-run unless --yes
    dry_run = args.dry_run or not args.yes

    try:
        orphans = find_orphans(root, feat_filter=args.feat)
    except OSError as e:
        print(f"ERROR: filesystem error during scan: {e}", file=sys.stderr)
        return INFRA_BLOCKED

    targets = _collect_target_paths(orphans)
    if not targets:
        print("✅ No orphan to clean — workspace is consistent.")
        return SUCCESS

    # Filter out protected paths (defense-in-depth)
    safe_targets = []
    skipped_protected = []
    for t in targets:
        if _is_protected(t):
            skipped_protected.append(t)
        else:
            safe_targets.append(t)

    print(f"=== cleanup_orphans plan ===")
    print(f"  - {len(safe_targets)} orphan(s) would be moved to .trash/")
    if skipped_protected:
        print(f"  - {len(skipped_protected)} protected path(s) SKIPPED")
    for t in safe_targets:
        print(f"    • {t}")

    if dry_run:
        print(f"\n[DRY-RUN] No filesystem change. Run with --yes to apply.")
        return SUCCESS

    # Interactive confirmation
    if sys.stdin.isatty():
        answer = input(f"\nProceed with moving {len(safe_targets)} item(s) to .trash/? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return FAIL_FAST
    else:
        print("ERROR: --yes requires a tty for confirmation (refused in non-interactive context)",
              file=sys.stderr)
        return FAIL_FAST

    # Move to trash
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    trash_dir = root / "workspace" / "output" / ".sys" / ".trash" / ts
    moved: list[str] = []
    for t in safe_targets:
        if _trash_one(root, t, trash_dir, dry_run=False):
            moved.append(t)

    print(f"\n✅ {len(moved)}/{len(safe_targets)} item(s) moved to {trash_dir.relative_to(root)}")
    _record_event(root, "orphan.deleted", moved)
    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
