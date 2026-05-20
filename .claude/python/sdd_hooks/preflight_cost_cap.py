#!/usr/bin/env python3
"""SDD_Pro PreToolUse.Agent hook — hard $ cost cap per run (v7.0.0 P0 §4.3).

Queries console.db `token_usage` table for the current run (matched by RunId
emitted via env $SDD_RUN_ID, or fallback to "all-time-today" window) and
computes cumulative USD spent so far. If the next Agent spawn would push
the run past `MaxCostPerRun` (layered config), blocks with exit 2 +
[COST_CAP_EXCEEDED].

Pricing table mirrors sdd_scripts/report_roi.py (single source of truth would
be ideal, but the script imports cycle is intentionally avoided here for
hook startup speed — keep these in sync).

Bypass (conscient uniquement) :
  - Set MaxCostPerRun: 0 in stack.md ## Project Config (disables cap, git blame trace)
  - Set $SDD_DISABLE_COST_CAP=1 env var (one-shot, shell history audit)

Default behaviour (v7.0.0 audit P0 R1 fix 2026-05-20) :
  - 80%-100% du cap : WARN informatif (heads-up, non bloquant)
  - >= 100% du cap : **HARD BLOCK systématique** (exit 2), peu importe contexte
    interactif OU CI. Le comportement antérieur "WARN-only en interactif"
    laissait les Tech Leads dépasser silencieusement le budget.

This hook is INTENTIONALLY decoupled from preflight_agent_budget.py because:
  - context_budget = per-invocation estimated input tokens (predictive)
  - cost_cap     = per-run cumulative billed USD (factual, post-recorded)
The two are orthogonal — both can fail independently.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.hook_input import read_hook_input, get_subagent_type  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402

# Pricing per million tokens (must mirror report_roi.py)
PRICING = {
    "claude-opus-4-7":    {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_creation": 18.75},
    "claude-sonnet-4-6":  {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-haiku-4-5":   {"input":  1.00, "output":  5.00, "cache_read": 0.10, "cache_creation":  1.25},
}
# Fallback for unknown models — apply Sonnet pricing (conservative midpoint)
FALLBACK_PRICING = PRICING["claude-sonnet-4-6"]


def _detect_ci() -> bool:
    ci_signals = (
        "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
        "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
        "BITBUCKET_BUILD_NUMBER",
    )
    return any(
        (os.environ.get(v, "").strip().lower() not in ("", "0", "false", "no"))
        for v in ci_signals
    )


def _resolve_cap() -> float:
    """Resolve MaxCostPerRun from layered config (env override possible).

    Returns 0.0 to disable. Defaults to $50.00 if config unreadable.
    """
    # Env one-shot disable
    if (os.environ.get("SDD_DISABLE_COST_CAP", "").strip().lower()
            in ("1", "true", "yes")):
        return 0.0
    try:
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config()
        raw = cfg.get("MaxCostPerRun")
        if raw is None:
            return 50.00
        return float(str(raw).strip())
    except Exception:
        return 50.00  # defensive default — never break the pipeline


def _check_telemetry_health() -> None:
    """Emit visible WARN if record_token_usage is silently failing.

    Reads `.audit/token-telemetry-failure-count` written by record_token_usage
    hook when a DB insert raises. Emits a stderr WARN if any failures
    accumulated since last successful run, so the operator knows the cost
    cap is operating on incomplete data."""
    try:
        from sdd_lib.paths import repo_root
        counter_path = (
            repo_root() / "workspace" / "output" / ".sys" / ".audit"
            / "token-telemetry-failure-count"
        )
        if not counter_path.is_file():
            return
        n = int(counter_path.read_text(encoding="utf-8").strip() or "0")
        if n > 0:
            warn(
                f"WARN preflight-cost-cap : token telemetry has {n} failed "
                f"insert(s) accumulated. Cost cap is operating on possibly "
                f"stale data. See workspace/output/.sys/.audit/"
                f"token-telemetry-failures.log for details. Reset counter "
                f"after fix : echo 0 > {counter_path.as_posix()}"
            )
    except Exception:
        # Health check itself must not break the hook chain.
        pass


def _compute_run_cost() -> tuple[float, int, str]:
    """Aggregate USD spent so far in the current run.

    Run scoping (precedence v7.0.0 audit fix 2026-05-20) :
      1. $SDD_RUN_ID env var + filter by `token_usage.run_id` column (exact match).
         Robust under concurrency : 2 parallel /sdd-full → 2 distinct run_ids
         → no cost crosstalk. Requires record_token_usage.py to set run_id at
         insert (done in same fix). Old rows pre-fix have run_id IS NULL and
         are excluded from this scope (clean separation).
      2. fallback A : $SDD_RUN_ID set but no row matches → return early
         (run just started, no telemetry yet).
      3. fallback B : no $SDD_RUN_ID at all → all rows from today (UTC date
         prefix). Coarse, but safe : Tech Lead in interactive without
         /sdd-full state.

    Returns (cost_usd, call_count, scope_label).
    """
    try:
        from sdd_lib.console_db import connect_ro
    except Exception:
        return 0.0, 0, "console.db unavailable"

    run_id = os.environ.get("SDD_RUN_ID", "").strip()
    try:
        with connect_ro() as conn:
            cur = conn.cursor()
            if run_id:
                # v7.0.0 — exact match on run_id column (no more time window).
                cur.execute(
                    "SELECT model, input_tokens, output_tokens, "
                    "       cache_creation_tokens, cache_read_tokens "
                    "FROM token_usage WHERE run_id = ?",
                    (run_id,),
                )
                rows = cur.fetchall()
                if not rows:
                    return 0.0, 0, f"run={run_id[:8]} (no rows yet)"
                scope = f"run={run_id[:8]}"
            else:
                # Fallback : today UTC window (no run_id context available)
                from datetime import datetime, timezone
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                cur.execute(
                    "SELECT model, input_tokens, output_tokens, "
                    "       cache_creation_tokens, cache_read_tokens "
                    "FROM token_usage WHERE ts LIKE ?",
                    (f"{today}%",),
                )
                rows = cur.fetchall()
                scope = f"today={today}"
    except Exception as e:
        return 0.0, 0, f"db error: {e}"

    total = 0.0
    for model, inp, outp, cc, cr in rows:
        p = PRICING.get(model or "", FALLBACK_PRICING)
        total += (inp or 0) * p["input"] / 1_000_000
        total += (outp or 0) * p["output"] / 1_000_000
        total += (cc or 0) * p["cache_creation"] / 1_000_000
        total += (cr or 0) * p["cache_read"] / 1_000_000

    return total, len(rows), scope


def main() -> int:
    cap = _resolve_cap()
    if cap <= 0:
        return 0  # disabled

    payload = read_hook_input()
    if not payload:
        return 0
    subagent = get_subagent_type(payload)
    if not subagent:
        return 0

    cost, calls, scope = _compute_run_cost()
    pct = (cost / cap * 100) if cap > 0 else 0

    # v7.0.0 audit fix — emit visible alert if record_token_usage.py is
    # silently failing (DB locked, schema mismatch, disk full...).
    # Without this, the cap is operating on stale/incomplete data and the
    # operator is unaware.
    _check_telemetry_health()

    # 80%-100% : WARN (let the operator know early, do not block — head-up only)
    if cap * 0.8 <= cost < cap:
        warn(f"WARN preflight-cost-cap : ${cost:.2f} / ${cap:.2f} "
             f"({pct:.0f}% du cap) — {calls} calls scope={scope}")
        return 0

    # >= 100% : HARD BLOCK in ALL contexts (v7.0.0 audit P0 R1 fix 2026-05-20).
    # Previous behavior `return 2 if is_ci else 0` made the cap purely
    # informational in interactive sessions — Tech Lead lancant /sdd-full
    # avec $40 déjà consommé voyait juste un WARN et finissait à $90.
    # Désormais : bloquant systématique. Bypass conscient via env var ONLY :
    #   - SDD_DISABLE_COST_CAP=1  (one-shot, audité dans shell history)
    #   - MaxCostPerRun: 0        (désactivation projet, tracée git blame)
    if cost >= cap:
        warn(f"ERROR: preflight-cost-cap — cap USD atteint pour ce run")
        warn(f"CAUSE: [COST_CAP_EXCEEDED] ${cost:.2f} >= ${cap:.2f} "
             f"({calls} calls scope={scope})")
        warn(f"FIX: (a) attendre la fin du run en cours et relancer ; "
             f"(b) augmenter MaxCostPerRun dans Project Config (decision tracee) ; "
             f"(c) bypass one-shot : export SDD_DISABLE_COST_CAP=1 puis relancer")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
