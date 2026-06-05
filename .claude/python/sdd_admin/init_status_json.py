#!/usr/bin/env python3
"""SDD_Pro: idempotent bootstrap of workspace/console/status.json.

Creates an empty skeleton file if missing. The dynamic FEAT/US/plans
scan is done by the Fastify server at runtime (GET /api/tree); this
script only puts the empty file in place.

Usage:
    python init_status_json.py
    python init_status_json.py --path workspace/console/status.json --force

Migrated from .claude/scripts/init-status-json.ps1 (2026-05-13).
"""
from __future__ import annotations

from sdd_lib.exit_codes import SUCCESS  # noqa: E402

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--path", default="workspace/console/status.json")
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.path)

    if path.is_file() and not args.force:
        print(f"[skip] {args.path} existe deja (idempotent). Utiliser --force pour ecraser.")
        return SUCCESS
    path.parent.mkdir(parents=True, exist_ok=True)

    skeleton = {
        "version":   1,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "FEATs":     {},
        "gates":     {},
    }

    # UTF-8 sans BOM, conforme JSON.parse strict de Node
    path.write_text(
        json.dumps(skeleton, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    print(f"[ok] {args.path} bootstrap (squelette vide)")
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
