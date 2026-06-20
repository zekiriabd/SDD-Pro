#!/usr/bin/env python3
"""SDD_Pro preflight — force-cumul bypass gate (v7.0.0-alpha audit CRIT-10).

Détecte le cumul de bypass-flags **AVANT** que le pipeline n'engage le
moindre coût LLM ou compute. Avant CRIT-10, ce check vivait à `sdd-full.md
STEP 3.6.quart` — c-à-d après que STEP 3.5 / STEP 3.6 ait déjà déclenché
la génération de plans techniques (jusqu'à ~30-60 KB tokens Opus 4.7 par
plan × N US). Si `BYPASS_COUNT >= 2` sans `SDD_ALLOW_FORCE=1`, ces plans
étaient générés pour rien.

Le script reproduit fidèlement la logique de la gate documentée (cf.
`commands/sdd-full.md §3.6.quart`). 0 token LLM.

Usage :
    python preflight_force_cumul.py [--force] [--no-plan-on-warn]
                                    [--no-validate] [--json]

Exit codes (cf. sdd_lib/exit_codes.py) :
    0  SUCCESS       — BYPASS_COUNT in {0, 1} OU SDD_ALLOW_FORCE truthy
    1  FAIL_FAST     — BYPASS_COUNT >= 2 ET SDD_ALLOW_FORCE non défini

JSON output (--json) :
    {
      "bypass_count":  int,
      "bypass_active": ["--force", "--no-plan-on-warn", ...],
      "sdd_allow_force_env": bool,
      "decision":      "PASS" | "WARN" | "REJECTED",
      "exit_code":     0 | 1
    }

decision :
    PASS     — 0 bypass actif (cas normal)
    WARN     — 1 bypass OU cumul autorisé via SDD_ALLOW_FORCE (audit trace)
    REJECTED — >= 2 bypass sans SDD_ALLOW_FORCE → STOP

Convention env-var (cf. doc) : `SDD_ALLOW_FORCE` truthy = `1` / `true` /
`yes` (case-insensitive). Toute autre valeur (incluant `0` / `false` /
absent) compte comme non-autorisé.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.stderr import error_block  # noqa: E402


_BYPASS_FLAGS: tuple[str, ...] = ("--force", "--no-plan-on-warn", "--no-validate")
_ENV_TRUE: frozenset[str] = frozenset({"1", "true", "yes", "on"})


def _env_allow_force() -> bool:
    """Read `SDD_ALLOW_FORCE` env var and return True iff truthy."""
    return os.environ.get("SDD_ALLOW_FORCE", "").strip().lower() in _ENV_TRUE


def evaluate(*, force: bool, no_plan_on_warn: bool, no_validate: bool,
             allow_force_env: bool | None = None) -> dict:
    """Compute the bypass cumul decision.

    Args:
        force:            True iff `--force` is active.
        no_plan_on_warn:  True iff `--no-plan-on-warn` is active.
        no_validate:      True iff `--no-validate` is active.
        allow_force_env:  override the env var lookup (for tests).

    Returns a dict matching the JSON schema (see module docstring).
    """
    bypass_active: list[str] = []
    if force:
        bypass_active.append("--force")
    if no_plan_on_warn:
        bypass_active.append("--no-plan-on-warn")
    if no_validate:
        bypass_active.append("--no-validate")

    bypass_count = len(bypass_active)
    env_truthy = allow_force_env if allow_force_env is not None else _env_allow_force()

    if bypass_count == 0:
        decision = "PASS"
        exit_code = SUCCESS
    elif bypass_count == 1:
        decision = "WARN"          # legitimate single bypass — audited downstream
        exit_code = SUCCESS
    elif env_truthy:
        decision = "WARN"          # cumul allowed via env var, enriched audit trace
        exit_code = SUCCESS
    else:
        decision = "REJECTED"
        exit_code = FAIL_FAST

    return {
        "bypass_count":         bypass_count,
        "bypass_active":        bypass_active,
        "sdd_allow_force_env":  env_truthy,
        "decision":             decision,
        "exit_code":            exit_code,
    }


def _emit_error(result: dict) -> None:
    """Emit the canonical 3-line ERROR block on stderr."""
    bypass_csv = " + ".join(result["bypass_active"])
    error_block(
        "/sdd-full — cumul de bypass refusé",
        f"[FORCE_CUMUL_REJECTED] {result['bypass_count']} flags de bypass "
        f"cumulés ({bypass_csv}) sans SDD_ALLOW_FORCE",
        "retirer au moins un bypass OU exporter SDD_ALLOW_FORCE=1 "
        "(décision exceptionnelle, audit trace enrichie)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="preflight_force_cumul",
        description="Anti-cumul bypass gate for /sdd-full (audit CRIT-10).",
    )
    parser.add_argument("--force", action="store_true",
                        help="--force was passed to /sdd-full")
    parser.add_argument("--no-plan-on-warn", action="store_true",
                        help="--no-plan-on-warn was passed to /sdd-full")
    parser.add_argument("--no-validate", action="store_true",
                        help="--no-validate was passed to /sdd-full")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON result on stdout in addition to exit code")
    args = parser.parse_args(argv)

    result = evaluate(
        force=args.force,
        no_plan_on_warn=args.no_plan_on_warn,
        no_validate=args.no_validate,
    )

    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    if result["decision"] == "REJECTED":
        _emit_error(result)

    return int(result["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
