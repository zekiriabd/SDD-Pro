#!/usr/bin/env python3
"""SDD_Pro session digest compiler — Niveau 5 (Persistent Sessions).

Materializes ``workspace/output/.sys/.cache/session.digest.md`` from the
latest run captured in ``console.db`` (or a specific ``--run-id``).

This is the **5th digest** of the cache hierarchy (cache_001 to
cache_004 are stable cross-FEAT; cache_005 is **dynamic per run**, but
its hash only changes when a phase transitions or new events are logged).

Usage :
    python compile_session_digest.py                       # latest run
    python compile_session_digest.py --feat-number 1       # latest run on FEAT 1
    python compile_session_digest.py --run-id <id>         # specific run
    python compile_session_digest.py --json                # JSON output (debug)
    python compile_session_digest.py --skip-registry-update  # only the .md

Exit codes :
    0 = digest written (or unchanged when idempotent)
    1 = no run found in console.db (digest still produced with `available: false`)
    2 = console.db unreachable
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.session_context import (  # noqa: E402
    build_session_digest,
    render_session_digest_md,
)


def cache_dir(root: Path) -> Path:
    return root / "workspace" / "output" / ".sys" / ".cache"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="compile_session_digest")
    p.add_argument("--run-id", default=None,
                   help="explicit run_id (default: latest)")
    p.add_argument("--feat-number", type=int, default=None,
                   help="restrict to latest run of FEAT N")
    p.add_argument("--json", action="store_true",
                   help="emit the raw digest dict to stdout")
    p.add_argument("--skip-registry-update", action="store_true",
                   help="do not refresh context-registry.json after writing")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main(argv: list[str] | None = None) -> int:
    args = parse_args() if argv is None else (
        argparse.ArgumentParser().parse_args(argv)
    )
    root = repo_root()
    cdir = cache_dir(root)
    cdir.mkdir(parents=True, exist_ok=True)

    digest = build_session_digest(
        run_id=args.run_id, feat_n=args.feat_number, events_limit=20,
    )

    if args.json:
        print(json.dumps(digest, indent=2, ensure_ascii=False, default=str))
        return 0 if digest.get("available") else 1

    md = render_session_digest_md(digest)
    target = cdir / "session.digest.md"

    # Idempotent : only rewrite if content differs (avoid rewriting on
    # every call when nothing changed).
    write = True
    if target.is_file():
        try:
            if target.read_text(encoding="utf-8") == md:
                write = False
        except OSError:
            pass

    if write:
        target.write_text(md, encoding="utf-8")
        if args.verbose:
            sys.stdout.write(
                f"session.digest.md written : {target} "
                f"({len(md):,} bytes, "
                f"{'available' if digest.get('available') else 'no-run'})\n"
            )
    else:
        if args.verbose:
            sys.stdout.write(
                f"session.digest.md unchanged : {target}\n"
            )

    # Refresh registry to capture new hash unless caller disabled it.
    if not args.skip_registry_update:
        from compile_context_registry import write_registry  # type: ignore
        write_registry(root, verbose=args.verbose)

    return 0 if digest.get("available") else 1


if __name__ == "__main__":
    sys.exit(main())
