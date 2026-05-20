#!/usr/bin/env python3
"""SDD_Pro context registry compiler — v6.10.5 audit 2026-05-19.

Generates ``workspace/output/.sys/.cache/context-registry.json``, a
manifest that lets agents perform **hash-based cache invalidation** on
the 4 compiled digests:

    - rules.digest.md           (compiled from .claude/rules/*.md)
    - stack.digest.md           (compiled from stack.md + active stacks)
    - architecture.digest.md    (compiled from constitution + ADRs)
    - qa.digest.md              (compiled from QA modes + classes)

Agents consume the registry as follows (v7 design):

    1. Read context-registry.json (~1 KB).
    2. For each digest needed, compare ``hash`` against last-seen value
       in agent's local context (stored in conversation memory).
    3. Only Read the digest file if hash changed (cache miss). Otherwise,
       skip the Read entirely — Anthropic prompt cache hit serves the
       previously-loaded content (5min TTL).

Cache key allocation is deterministic and stable across regenerations:
the same digest name always maps to the same cache_key (cache_001 to
cache_004). Adding new digests appends new keys (cache_005, ...).

Exit codes:
    0 = registry written successfully (or unchanged if --check-only)
    1 = cache directory missing or unreadable
    2 = at least one digest is missing (run digest compilers first)
    3 = --check-only and registry needs update (drift detected)

Usage:
    python compile_context_registry.py                # write registry
    python compile_context_registry.py --check-only   # CI / pre-commit
    python compile_context_registry.py --verbose

Idempotent: re-running on unchanged digests produces a bit-identical
registry (timestamps are not regenerated when content hashes match).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402


# Stable digest -> cache_key mapping. Order matters for cache_key
# allocation but NOT for registry consumption (agents query by digest
# name, not by index).
#
# Niveaux 2-3 (cache_001..004) : stable cross-FEAT.
# Niveau 5    (cache_005)      : dynamic per run, but registry hash only
#                                changes when phases transition. The
#                                file is optional — absent on cold start.
DIGEST_REGISTRY: tuple[tuple[str, str, str], ...] = (
    # (digest_name, source_filename, cache_key)
    ("rules_digest",        "rules.digest.md",        "cache_001"),
    ("stack_digest",        "stack.digest.md",        "cache_002"),
    ("architecture_digest", "architecture.digest.md", "cache_003"),
    ("qa_digest",           "qa.digest.md",           "cache_004"),
    ("session_digest",      "session.digest.md",      "cache_005"),
)

# Optional digests : registry skips them silently if the file is absent
# (e.g., session digest before first /sdd-full run).
OPTIONAL_DIGESTS: frozenset[str] = frozenset({"session.digest.md"})

REGISTRY_VERSION = 1


def cache_dir(root: Path) -> Path:
    return root / "workspace" / "output" / ".sys" / ".cache"


def registry_path(root: Path) -> Path:
    return cache_dir(root) / "context-registry.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def build_registry(root: Path) -> tuple[dict, list[str]]:
    """Returns (registry_dict, list_of_missing_digest_filenames)."""
    cdir = cache_dir(root)
    if not cdir.is_dir():
        raise FileNotFoundError(
            f"Cache directory not found : {cdir}. "
            f"Create the digests first (rules.digest.md, stack.digest.md, "
            f"architecture.digest.md, qa.digest.md)."
        )

    # Spec utilisateur (audit 2026-05-19) : digests EN RACINE, hash
    # prefixe "sha256_" (underscore), pas de sous-objet wrapper. Metadata
    # operationnel groupe sous "_meta" (cles prefixees underscore =
    # convention "private/internal" en JSON, ignorees par les
    # consommateurs simples qui font registry[digest_name]["hash"]).
    digests: dict[str, dict] = {}
    missing: list[str] = []

    for digest_name, filename, cache_key in DIGEST_REGISTRY:
        digest_path = cdir / filename
        if not digest_path.is_file():
            # Optional digests (e.g., session.digest.md before first run)
            # are silently skipped — not considered "missing".
            if filename not in OPTIONAL_DIGESTS:
                missing.append(filename)
            continue
        digests[digest_name] = {
            "hash": f"sha256_{sha256_file(digest_path)}",
            "cache_key": cache_key,
            "path": f"workspace/output/.sys/.cache/{filename}",
            "size_bytes": digest_path.stat().st_size,
        }

    # Build flat registry : digests at top level (matches user spec).
    registry: dict = dict(digests)
    registry["_meta"] = {
        "$schema": "https://sdd-pro.local/schemas/context-registry-v1.json",
        "registry_version": REGISTRY_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rationale": (
            "Shared cache registry — hash-based invalidation for the 4 "
            "compiled context digests. Agents check 'hash' against "
            "last-seen value before Reading the digest body, enabling "
            "Anthropic prompt cache hits on stable content. v6.10.5 "
            "audit 2026-05-19."
        ),
        "consumption_protocol": [
            "1. Read context-registry.json (~1 KB).",
            "2. For each digest needed: compare hash against last-seen value.",
            "3. If hash unchanged: skip Read of digest body (cache hit).",
            "4. If hash changed or first invocation: Read digest body, store hash.",
        ],
    }
    return registry, missing


def write_registry(root: Path, verbose: bool = False) -> int:
    try:
        registry, missing = build_registry(root)
    except FileNotFoundError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    if missing:
        sys.stderr.write(
            f"ERROR: {len(missing)} digest(s) missing : {', '.join(missing)}\n"
            f"FIX: regenerate the digests via the future `compile_digests.py` "
            f"or manually update them in workspace/output/.sys/.cache/.\n"
        )
        return 2

    target = registry_path(root)
    # Idempotent: if registry content (minus timestamp) is identical, do
    # not bump generated_at — keep the file bit-stable across reruns.
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            # Compare on digest entries only (drop "_meta" which has
            # generated_at + rationale that should not trigger drift).
            existing_no_ts = {k: v for k, v in existing.items() if k != "_meta"}
            new_no_ts = {k: v for k, v in registry.items() if k != "_meta"}
            if existing_no_ts == new_no_ts:
                if verbose:
                    sys.stdout.write(
                        f"context-registry.json unchanged (digests stable). "
                        f"Path: {target}\n"
                    )
                return 0
        except (json.JSONDecodeError, OSError):
            pass  # Corrupted or unreadable -> overwrite

    target.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if verbose:
        sys.stdout.write(
            f"context-registry.json written : {target}\n"
            f"  {len([k for k in registry if k != '_meta'])} digests registered\n"
        )
    return 0


def check_only(root: Path) -> int:
    """Returns 3 if registry needs regeneration (drift detected)."""
    try:
        registry, missing = build_registry(root)
    except FileNotFoundError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    if missing:
        sys.stderr.write(
            f"ERROR: {len(missing)} digest(s) missing : {', '.join(missing)}\n"
        )
        return 2

    target = registry_path(root)
    if not target.is_file():
        sys.stderr.write(
            f"DRIFT: registry missing at {target}. Run without --check-only.\n"
        )
        return 3

    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"DRIFT: registry corrupted: {exc}\n")
        return 3

    existing_no_ts = {k: v for k, v in existing.items() if k != "generated_at"}
    new_no_ts = {k: v for k, v in registry.items() if k != "generated_at"}
    if existing_no_ts != new_no_ts:
        sys.stderr.write(
            f"DRIFT: registry stale. Regenerate via "
            f"`python compile_context_registry.py`.\n"
        )
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compile_context_registry")
    parser.add_argument("--check-only", action="store_true",
                        help="exit 3 if registry needs regen (CI / pre-commit)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    root = repo_root()
    if args.check_only:
        return check_only(root)
    return write_registry(root, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
