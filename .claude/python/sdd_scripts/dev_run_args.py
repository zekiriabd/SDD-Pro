#!/usr/bin/env python3
"""SDD_Pro /dev-run args wrapper — parse CLI flags deterministically.

Audit P3 C (2026-06-08) — `/dev-run.md` declares CLI flags (`--unsequenced`,
`--legacy-auditor-parallel`, `--rebuild-arch`, `--resume`, `--force`,
`--max-parallel N`) but the slash command is LLM-interpreted, meaning the
LLM parses these from the user's natural-language invocation. When the LLM
misses a flag (or mis-orders them), the documented bypass doesn't work.

This wrapper script :
  1. Receives the raw user input string (via stdin or `--input`)
  2. Parses CLI flags deterministically via argparse
  3. Writes a structured args file to
     `workspace/output/.sys/.state/dev-run-{n}.args.json`
  4. Returns the parsed flags as JSON on stdout

Slash command behavior in `.md` :
  STEP 1.bis (new) — invoke this wrapper, read the resulting JSON for
  flag values. The LLM no longer has to parse `--xxx` from raw text.

Bypass : if this script isn't invoked, the .md falls back to LLM
interpretation (backward-compat).

Usage:
    python -m sdd_scripts.dev_run_args --input "1 --unsequenced --max-parallel 4"
    python -m sdd_scripts.dev_run_args --input "1 --legacy-auditor-parallel"

Exit codes :
    0 SUCCESS       : args parsed, JSON file written
    1 FAIL_FAST     : no FEAT number found
    2 CORRECTIBLE   : invalid arg combination (e.g. mutually exclusive flags)
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


def _build_parser() -> argparse.ArgumentParser:
    """The canonical argparse for /dev-run.

    Mirrors the flags documented in `.claude/commands/dev-run.md`. Every
    flag declared in the .md must appear here OR be annotated `@llm-only-flag`
    (smoke test enforces — cf. test_cli_flags_declared.py).
    """
    p = argparse.ArgumentParser(
        prog="/dev-run",
        description="Args parser for /dev-run slash command (v7.0.0+).",
    )
    p.add_argument("feat_number", type=int, nargs="?", default=None,
                   help="FEAT number (positional, required)")
    p.add_argument("--force", action="store_true",
                   help="Bypass readiness NO-GO gate")
    p.add_argument("--max-parallel", type=int, default=None,
                   help="Max US in parallel (1-12, default MaxParallel config)")
    p.add_argument("--rebuild-arch", action="store_true",
                   help="Force arch invocation even if shortcircuit detects stable bootstrap")
    p.add_argument("--resume", action="store_true",
                   help="Resume from last checkpoint (CheckpointMode=resume)")
    p.add_argument("--unsequenced", action="store_true",
                   help="Disable gated API back/front pipeline (legacy v6.x parallel)")
    p.add_argument("--legacy-auditor-parallel", action="store_true",
                   help="Disable two-stage auditor pattern (force 4-reviewer parallel batch)")
    return p


def parse_input_string(input_str: str) -> dict:
    """Parse a /dev-run input string into a structured args dict.

    Input format examples :
        "1"
        "1 --unsequenced"
        "1 --legacy-auditor-parallel --max-parallel 4"
        "--force 1"  (positional order tolerant)

    Returns dict with keys :
        feat_number, force, max_parallel, rebuild_arch, resume,
        unsequenced, legacy_auditor_parallel, _raw, _parsed_at
    """
    # Tokenize honoring quotes
    tokens = shlex.split(input_str)
    parser = _build_parser()
    try:
        args = parser.parse_args(tokens)
    except SystemExit as exc:
        # argparse calls sys.exit on parse error — re-raise as ValueError
        raise ValueError(f"argparse error (code {exc.code}) on input: {input_str!r}") from exc

    # Mutual exclusion check (load-bearing : --unsequenced and
    # --legacy-auditor-parallel are orthogonal, but using both together
    # is suspicious — document but don't block)
    if args.unsequenced and args.legacy_auditor_parallel:
        sys.stderr.write(
            "INFO [DEV_RUN_DUAL_BYPASS] both --unsequenced AND "
            "--legacy-auditor-parallel set. Both apply, but combination is "
            "unusual (full v6.x behavior).\n"
        )

    # Range check max-parallel
    if args.max_parallel is not None and not (1 <= args.max_parallel <= 12):
        raise ValueError(f"--max-parallel must be 1-12, got {args.max_parallel}")

    return {
        "feat_number":             args.feat_number,
        "force":                   args.force,
        "max_parallel":            args.max_parallel,
        "rebuild_arch":            args.rebuild_arch,
        "resume":                  args.resume,
        "unsequenced":             args.unsequenced,
        "legacy_auditor_parallel": args.legacy_auditor_parallel,
        "_raw":                    input_str,
        "_parsed_at":              datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_args_state(parsed: dict, root: Path) -> Path:
    """Persist parsed args to workspace/output/.sys/.state/dev-run-{n}.args.json."""
    n = parsed["feat_number"]
    if n is None:
        raise ValueError("feat_number is None — cannot write state file")
    state_dir = root / "workspace" / "output" / ".sys" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / f"dev-run-{n}.args.json"
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
        prog="dev_run_args",
        description="Deterministic args parser for /dev-run (v7.0.0+ audit P3 C).",
    )
    cli.add_argument("--input", "-i", type=str, default=None,
                     help="Raw /dev-run input string (default: read from stdin)")
    cli.add_argument("--dry-run", action="store_true",
                     help="Parse and print JSON, do not persist state file")
    args = cli.parse_args(argv)

    raw = args.input
    if raw is None:
        raw = sys.stdin.read().strip()

    if not raw:
        sys.stderr.write("ERROR: no input provided (use --input or stdin)\n")
        return CORRECTIBLE

    try:
        parsed = parse_input_string(raw)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: [INVALID_ARG] {exc}\n")
        return CORRECTIBLE

    if parsed["feat_number"] is None:
        sys.stderr.write("ERROR: [INVALID_ARG] FEAT number required (positional)\n")
        sys.stderr.write("Example: python -m sdd_scripts.dev_run_args --input '1 --unsequenced'\n")
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
    sys.stderr.write(f"[DEV_RUN_ARGS] state written → {out_path.relative_to(_repo_root()).as_posix()}\n")
    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
