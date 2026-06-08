#!/usr/bin/env python3
"""SDD_Pro /feat-deepen + elicitor args wrapper — parse CLI flags deterministically.

Audit P3 D (2026-06-08) — sibling of `dev_run_args.py`. The elicitor agent
.md declares `--quick`, `--legacy-5`, `--techniques nom1,nom2[,...]` flags
but they're LLM-interpreted. This wrapper makes them deterministic.

Outputs structured args + the resolved technique list to
`workspace/output/.sys/.state/elicitor-{n}.args.json` so the elicitor
agent can read instead of parsing.

The wrapper validates `--techniques` against the canonical 15 names from
`brainstorming-techniques.md` §0. Invalid names → exit 2 with clear error.

Usage:
    python -m sdd_scripts.elicitor_args --input "1 --quick"
    python -m sdd_scripts.elicitor_args --input "1 --legacy-5"
    python -m sdd_scripts.elicitor_args --input "1 --techniques pre-mortem,red-team"

Exit codes :
    0 SUCCESS       : args parsed, JSON file written
    1 FAIL_FAST     : missing FEAT or invalid technique name
    2 CORRECTIBLE   : mutually exclusive flags (--legacy-5 + --techniques)
    3 INFRA_BLOCKED : disk write failure
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402

INFRA_BLOCKED = 3


#: Canonical 15 technique names from brainstorming-techniques.md §0 Quick Reference.
#: kebab-case slugs (case-insensitive on input).
CANONICAL_TECHNIQUES = frozenset({
    "pre-mortem",
    "first-principles",
    "red-team",
    "stakeholder-mapping",
    "stakeholder-raci",   # alias
    "inversion",
    "scamper",
    "reverse-brainstorming",
    "5-whys",
    "five-whys",          # alias
    "customer-journey",
    "customer-journey-mapping",  # alias
    "empathy-map",
    "crazy-8s",
    "crazy8s",            # alias
    "six-thinking-hats",
    "six-hats",           # alias
    "cynefin",
    "okr-decomposition",
    "okr",                # alias
    "lotus-blossom",
})

#: Legacy v6.x default — 5 historical techniques applied in this order
LEGACY_5_TECHNIQUES = (
    "pre-mortem",
    "first-principles",
    "red-team",
    "stakeholder-mapping",
    "inversion",
)

#: Default 3 techniques in --quick mode (audit P2 M1)
QUICK_DEFAULT_TECHNIQUES = (
    "pre-mortem",
    "red-team",
    "inversion",
)


def _normalize_technique(name: str) -> str:
    """Normalize a technique name to canonical kebab-case lowercase."""
    return name.strip().lower().replace("_", "-").replace(" ", "-")


def _validate_techniques(raw_list: list[str]) -> list[str]:
    """Validate and normalize a list of technique names.

    Returns the canonical names. Raises ValueError on unknown name.
    Deduplicates while preserving order.
    """
    seen: set[str] = set()
    out: list[str] = []
    for name in raw_list:
        norm = _normalize_technique(name)
        if not norm:
            continue
        if norm not in CANONICAL_TECHNIQUES:
            raise ValueError(
                f"unknown technique '{name}' (normalized: '{norm}'). "
                f"Valid names: {', '.join(sorted(CANONICAL_TECHNIQUES))}"
            )
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    if not out:
        raise ValueError("--techniques requires at least 1 valid name")
    if len(out) > 5:
        raise ValueError(f"--techniques limited to 5 max (got {len(out)}). Cognitive fatigue beyond.")
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="/feat-deepen",
        description="Args parser for /feat-deepen slash command + elicitor agent (v7.0.0+).",
    )
    p.add_argument("feat_number", type=int, nargs="?", default=None,
                   help="FEAT number (positional, required)")
    p.add_argument("--quick", action="store_true",
                   help="One-shot mode (no Q/R), 3 default techniques inferred from context")
    p.add_argument("--legacy-5", action="store_true",
                   help="Apply the 5 historical v6.x techniques (Pre-mortem, First Principles, Red Team, Stakeholder RACI, Inversion)")
    p.add_argument("--techniques", type=str, default=None,
                   help="Comma-separated technique names from the 15-lib (mutually exclusive with --legacy-5)")
    return p


def parse_input_string(input_str: str) -> dict:
    """Parse /feat-deepen input into structured args + resolved technique list."""
    tokens = shlex.split(input_str)
    parser = _build_parser()
    try:
        args = parser.parse_args(tokens)
    except SystemExit as exc:
        raise ValueError(f"argparse error (code {exc.code}) on input: {input_str!r}") from exc

    # Mutual exclusion
    if args.legacy_5 and args.techniques:
        raise ValueError(
            "--legacy-5 and --techniques are mutually exclusive "
            "(one bypasses the contextual detection, the other forces an explicit list)"
        )

    # Resolve final technique list
    if args.legacy_5:
        techniques = list(LEGACY_5_TECHNIQUES)
        mode = "legacy-5"
    elif args.techniques:
        raw = [t for t in args.techniques.split(",") if t.strip()]
        techniques = _validate_techniques(raw)
        mode = "explicit"
    elif args.quick:
        techniques = list(QUICK_DEFAULT_TECHNIQUES)
        mode = "quick-default"
    else:
        # Interactive mode — techniques resolved at runtime by elicitor agent
        # via context detection. Wrapper leaves empty list to signal "agent decides".
        techniques = []
        mode = "interactive-context-detected"

    return {
        "feat_number":  args.feat_number,
        "quick":        args.quick,
        "legacy_5":     args.legacy_5,
        "techniques":   techniques,
        "mode":         mode,
        "_raw":         input_str,
        "_parsed_at":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_args_state(parsed: dict, root: Path) -> Path:
    n = parsed["feat_number"]
    if n is None:
        raise ValueError("feat_number is None — cannot write state file")
    state_dir = root / "workspace" / "output" / ".sys" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / f"elicitor-{n}.args.json"
    out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def _repo_root() -> Path:
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root and Path(env_root).is_dir():
        return Path(env_root)
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / ".claude").is_dir():
            return p
    return cwd


def main(argv: list[str] | None = None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    cli = argparse.ArgumentParser(
        prog="elicitor_args",
        description="Deterministic args parser for /feat-deepen + elicitor (v7.0.0+ audit P3 D).",
    )
    cli.add_argument("--input", "-i", type=str, default=None,
                     help="Raw /feat-deepen input string (default: read from stdin)")
    cli.add_argument("--dry-run", action="store_true",
                     help="Parse and print JSON, do not persist state file")
    args = cli.parse_args(argv)

    raw = args.input
    if raw is None:
        raw = sys.stdin.read().strip()

    if not raw:
        sys.stderr.write("ERROR: no input provided\n")
        return CORRECTIBLE

    try:
        parsed = parse_input_string(raw)
    except ValueError as exc:
        msg = str(exc)
        if "mutually exclusive" in msg:
            sys.stderr.write(f"ERROR: [INVALID_ARG] {msg}\n")
            return CORRECTIBLE
        sys.stderr.write(f"ERROR: [INVALID_ARG] {msg}\n")
        return FAIL_FAST

    if parsed["feat_number"] is None:
        sys.stderr.write("ERROR: [INVALID_ARG] FEAT number required (positional)\n")
        return FAIL_FAST

    sys.stdout.write(json.dumps(parsed, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")

    if args.dry_run:
        return SUCCESS

    try:
        out_path = write_args_state(parsed, _repo_root())
    except OSError as exc:
        sys.stderr.write(f"ERROR: [INFRA_BLOCKED] cannot write state file: {exc}\n")
        return INFRA_BLOCKED
    sys.stderr.write(
        f"[ELICITOR_ARGS] state written → "
        f"{out_path.relative_to(_repo_root()).as_posix()} "
        f"(mode={parsed['mode']}, {len(parsed['techniques'])} techniques)\n"
    )
    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
