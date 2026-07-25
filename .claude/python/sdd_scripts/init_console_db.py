#!/usr/bin/env python3
"""SDD_Pro v7.0.0+ — Bootstrap workspace/db/console.db (SQLite, WAL).

DB centralisée pour toute la télémétrie SDD_Pro. Schéma split en sub-modules
depuis v7.0.0 (audit Sprint 2 2026-06-07) : `sdd_lib/console_db/{core,runs,qa}.py`
définissent les CREATE TABLE par domaine. Ce script orchestre l'init :
  - Métadonnées FEAT/US/plans/ADRs (frontmatter, pas le contenu MD)
  - Résultats QA (coverage, quality, api-tests, a11y, code-review, security, perf, spec-compliance)
  - Runs, gates, events, token_usage, context_budget, validation_reports

Remplace les outputs HTML générés (dashboard/README.html, qa dashboards retirés v7.0.0).

Idempotent : ré-exécution = no-op si la DB est déjà au bon schema_version.
Migrations forward-only (audit CTO 2026-06-09 Bug #15 closure) : scripts
`sdd_lib/migrations/NNNN_slug.sql` appliqués automatiquement par
`apply_pending_migrations` si `previous < SCHEMA_VERSION`. Pour les changements
de schéma backward-incompatibles non-couverts par migration : `--force-recreate`
(destructif, toutes données perdues).

Usage :
    python -m sdd_scripts.init_console_db
    python -m sdd_scripts.init_console_db --db-path some/path.db
    python -m sdd_scripts.init_console_db --force-recreate     # drop & recreate (DESTRUCTIVE)
    python -m sdd_scripts.init_console_db --json               # output machine-readable

Exit codes :
    0 = OK (created or already up-to-date)
    1 = error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Permettre l'exécution directe (python init_console_db.py)
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from sdd_lib.console_db import (  # noqa: E402
    SCHEMA_VERSION,
    connect,
    current_schema_version,
    default_db_path,
    load_schema_sql,
)
from sdd_lib.console_db.core import apply_pending_migrations  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402


def _utc_now_iso() -> str:
    """Alias of `sdd_lib.paths.iso_now` — kept as `_utc_now_iso` for
    backward-compat with internal callers (audit consolidé 2026-06-07 Sprint 2)."""
    from sdd_lib.paths import iso_now
    return iso_now()


def init_db(db_path: Path, force_recreate: bool = False) -> dict:
    """Create the DB and apply schema. Returns a result dict.

    Result schema:
        {"status": "created"|"up_to_date"|"recreated"|"migrated",
         "db_path": str, "schema_version": int,
         "previous_version": int|None, "applied_migrations": list[int]?}
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if force_recreate and db_path.exists():
        # WAL leftovers
        for suffix in ("", "-wal", "-shm", "-journal"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        action = "recreated"
    elif db_path.exists():
        action = None
    else:
        action = "created"

    schema_sql = load_schema_sql()

    with connect(db_path) as conn:
        previous = current_schema_version(conn)

        if previous is not None and not force_recreate:
            if previous == SCHEMA_VERSION:
                return {
                    "status": "up_to_date",
                    "db_path": str(db_path),
                    "schema_version": SCHEMA_VERSION,
                    "previous_version": previous,
                }
            if previous < SCHEMA_VERSION:
                # Audit CTO 2026-06-09 Bug #15 closure : appliquer les migrations
                # forward-only depuis `sdd_lib/migrations/NNNN_slug.sql`
                # (mécanisme déjà présent dans le module mais non câblé ici).
                # Plus de RuntimeError "no migration available" trompeur.
                applied = apply_pending_migrations(conn)
                new_version = current_schema_version(conn) or previous
                if new_version == SCHEMA_VERSION:
                    return {
                        "status": "migrated",
                        "db_path": str(db_path),
                        "schema_version": SCHEMA_VERSION,
                        "previous_version": previous,
                        "applied_migrations": applied,
                    }
                # Migration partielle : aucune migration disponible OU gap
                # entre `previous` et `SCHEMA_VERSION` non couvert.
                raise RuntimeError(
                    f"[CONSOLE_DB_MIGRATION_GAP] DB at v{previous}, framework "
                    f"expects v{SCHEMA_VERSION}, but applied migrations only "
                    f"reached v{new_version}. Missing migration scripts in "
                    f"`sdd_lib/migrations/`. Use --force-recreate (destructive) "
                    f"OR add the missing migration."
                )
            # previous > SCHEMA_VERSION → DB plus récente qu'attendu, on log et on tolère
            return {
                "status": "up_to_date",
                "db_path": str(db_path),
                "schema_version": previous,
                "previous_version": previous,
                "warning": f"DB at v{previous} > expected v{SCHEMA_VERSION}",
            }

        # Fresh install ou recreate
        conn.executescript(schema_sql)
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
            (SCHEMA_VERSION, _utc_now_iso()),
        )

    return {
        "status": action or "created",
        "db_path": str(db_path),
        "schema_version": SCHEMA_VERSION,
        "previous_version": previous,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="init_console_db",
        description="Bootstrap workspace/db/console.db (SQLite, WAL).",
    )
    default_path = default_db_path()
    parser.add_argument(
        "--db-path",
        default=str(default_path),
        help=f"Path to console.db (default: <repo-root>/workspace/db/console.db)",
    )
    parser.add_argument(
        "--force-recreate",
        action="store_true",
        help="Drop & recreate the DB (DESTRUCTIVE — all data lost).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON for machine consumption.",
    )
    args = parser.parse_args(argv)

    try:
        result = init_db(Path(args.db_path), force_recreate=args.force_recreate)
    except Exception as exc:  # pragma: no cover
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}))
        else:
            print(f"ERROR: init_console_db failed", file=sys.stderr)
            print(f"CAUSE: {exc}", file=sys.stderr)
            print("FIX: see traceback above; --force-recreate is destructive", file=sys.stderr)
        return FAIL_FAST
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result["status"]
        path = result["db_path"]
        v = result["schema_version"]
        prev = result.get("previous_version")
        if status == "created":
            print(f"OK init_console_db: created {path} (schema v{v})")
        elif status == "recreated":
            print(f"OK init_console_db: recreated {path} (schema v{v}, previous v{prev})")
        elif status == "migrated":
            applied = result.get("applied_migrations") or []
            print(f"OK init_console_db: migrated {path} v{prev} -> v{v} "
                  f"(applied: {applied})")
        else:  # up_to_date
            print(f"OK init_console_db: {path} already at v{v}")
        if "warning" in result:
            print(f"WARN: {result['warning']}")

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
