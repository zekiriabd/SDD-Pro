#!/usr/bin/env python3
"""SDD_Pro Plan metadata generator — v2 frontmatter helper (v6.2).

Computes deterministic metadata fields for v2 plan frontmatter:
- `us-hash`        : SHA-256 of the US file (anti-staleness signal)
- `claude-md-hash` : SHA-256 of the project CLAUDE.md (drift detection)
- `generated-at`   : UTC ISO-8601 timestamp (second precision)
- `plan-schema-version: 2` + `strict-ready: true` (literal)
- `capabilities-triggered` : passed through from caller

Invoked by `dev-backend` / `dev-frontend` in `:plan` mode (after they've
already read the US and CLAUDE.md). The agent then appends the emitted
block to the plan's frontmatter.

Usage:
    compute_plan_metadata.py --us-path workspace/output/us/1-2-Login.md \
                             --claude-md-path workspace/output/src/Backend/CLAUDE.md \
                             [--capabilities auth-azure-ad,email] \
                             [--json]

Output (default): YAML fragment ready to inject in plan frontmatter
Output (--json): structured JSON with raw values

Exit codes:
    0 = OK, metadata emitted
    1 = US file missing/unreadable (mandatory)
    2 = CLAUDE.md missing/unreadable (mandatory if --claude-md-path given)

Conventions: Python 3.10+ stdlib only, deterministic (0 token LLM).

Related:
- `@.claude/archive/v7-design-superseded/DESIGN-FROMPLAN-STRICT.md` (design)
- `@.claude/rules/build-and-loop.md §7.4.bis` (v2 plan format)
- `validate_plan.py` (counterpart : verifies us-hash matches at consume time)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import iso_now  # noqa: E402
from sdd_lib.stderr import error_block  # noqa: E402
from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402


def sha256_of_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file's content (UTF-8 text)."""
    content = path.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Emit v2 plan frontmatter metadata block (us-hash, claude-md-hash, ...).",
    )
    p.add_argument("--us-path", required=True, help="Path to the source US file")
    p.add_argument("--claude-md-path", default=None,
                   help="Path to project CLAUDE.md (optional but recommended)")
    p.add_argument("--capabilities", default="",
                   help="Comma-separated list of capabilities-triggered (optional)")
    p.add_argument("--json", action="store_true",
                   help="Emit structured JSON on stdout instead of YAML fragment")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    us_path = Path(args.us_path).resolve()
    claude_md_path = Path(args.claude_md_path).resolve() if args.claude_md_path else None

    if not us_path.is_file():
        error_block(
            error_line=f"compute_plan_metadata --us-path {us_path}",
            cause=f"[PLAN_NOT_FOUND] US file introuvable: {us_path}",
            fix="lancer /us-generate {n} avant /dev-plan",
        )
        return FAIL_FAST
    try:
        us_hash = sha256_of_file(us_path)
    except OSError as e:
        error_block(
            error_line=f"compute_plan_metadata --us-path {us_path}",
            cause=f"[PLAN_UNREADABLE] lecture US impossible: {e}",
            fix="verifier les droits FS et l'encodage UTF-8",
        )
        return FAIL_FAST
    claude_md_hash: str | None = None
    if claude_md_path is not None:
        if not claude_md_path.is_file():
            error_block(
                error_line=f"compute_plan_metadata --claude-md-path {claude_md_path}",
                cause=f"[PLAN_NOT_FOUND] CLAUDE.md projet introuvable: {claude_md_path}",
                fix="lancer /arch-init avant /dev-plan (CLAUDE.md genere par arch Phase C)",
            )
            return CORRECTIBLE
        try:
            claude_md_hash = sha256_of_file(claude_md_path)
        except OSError as e:
            error_block(
                error_line=f"compute_plan_metadata --claude-md-path {claude_md_path}",
                cause=f"[PLAN_UNREADABLE] lecture CLAUDE.md impossible: {e}",
                fix="verifier les droits FS et l'encodage UTF-8",
            )
            return CORRECTIBLE
    caps = [c.strip() for c in args.capabilities.split(",") if c.strip()]
    timestamp = iso_now()

    if args.json:
        payload = {
            "plan_schema_version": 2,
            "us_hash": f"sha256:{us_hash}",
            "claude_md_hash": f"sha256:{claude_md_hash}" if claude_md_hash else None,
            "generated_at": timestamp,
            "capabilities_triggered": caps,
            "strict_ready": True,
        }
        print(json.dumps(payload, separators=(",", ":")))
        return SUCCESS
    # YAML fragment: lines ready to inject in frontmatter (no `---` delimiters)
    lines: list[str] = [
        "plan-schema-version: 2",
        f"generated-at: {timestamp}",
        f"us-hash: sha256:{us_hash}",
    ]
    if claude_md_hash is not None:
        lines.append(f"claude-md-hash: sha256:{claude_md_hash}")
    if caps:
        lines.append(f"capabilities-triggered: {','.join(caps)}")
    lines.append("strict-ready: true")

    print("\n".join(lines))
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
