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

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import read_hook_input, get_subagent_type  # noqa: E402
from sdd_lib.pricing import PRICING, FALLBACK_PRICING  # noqa: E402  # v7.0.1 SSoT
from sdd_lib.run_id import get_or_create_run_id  # noqa: E402  # v7.0.1 stable scoping
from sdd_lib.stderr import warn  # noqa: E402


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

    Scope label conventions (v7.0.0-alpha telemetry-trust fix) :
      - "run={id} (no rows yet)" : DB readable, run scope empty → safe ALLOW
      - "db absent"              : console.db file missing → safe ALLOW
                                    (fresh checkout / pre-bootstrap)
      - "db error: {detail}"     : DB exists but unreadable → caller MUST
                                    treat as untrusted (block in strict CI,
                                    visible WARN in interactive). Previously
                                    this state silently returned 0.0 → the
                                    cap was bypassed every time telemetry
                                    failed (root cause filed by user
                                    2026-05-21).
    """
    try:
        from sdd_lib.console_db import connect_ro, default_db_path
    except Exception as e:
        return 0.0, 0, f"db error: import failed: {e}"

    # Distinguish absent (legit fresh state) from unreadable (suspect).
    try:
        if not default_db_path().exists():
            return 0.0, 0, "db absent"
    except Exception:
        # repo_root() failure is itself a problem — surface it.
        pass

    # v7.0.1 : always resolve a stable run_id (env > marker file > generate).
    # Avoids the legacy "today window" fallback which collided across parallel runs.
    run_id = get_or_create_run_id()
    try:
        with connect_ro() as conn:
            cur = conn.cursor()
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
    except Exception as e:
        # SCOPE = "db error: ..." signals the caller that 0.0 is NOT a
        # legitimate "no cost yet" but a "cap unenforceable" condition.
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

    # v7.0.0-alpha telemetry-trust fix (2026-05-21) — when _compute_run_cost
    # signals "db error: ...", we CANNOT trust cost=0.0 as "no cost yet".
    # Previously this branch was conflated with the legitimate empty state
    # → the cap silently became inoperative every time telemetry failed
    # (root cause filed by user 2026-05-21 : DB locked, WAL inaccessible,
    # corrupted schema, etc.). New semantics :
    #   - CI (auto strict)              → DENY [TELEMETRY_UNAVAILABLE]
    #                                     (can't enforce cap, abort the run)
    #   - Interactive (or SDD_BUDGET_MODE=warn)
    #                                   → visible ERROR on stderr + ALLOW
    #                                     (operator awareness, manual decision)
    # Bypass requires explicit SDD_DISABLE_COST_CAP=1 (no silent fallthrough).
    if scope.startswith("db error:"):
        is_ci = _detect_ci()
        warn("ERROR preflight-cost-cap : telemetry unavailable — cap cannot be enforced")
        warn(f"CAUSE: [TELEMETRY_UNAVAILABLE] {scope}")
        if is_ci:
            warn("FIX (CI strict) : investigate console.db readability "
                 "(WAL lock, FS permissions) ; bypass one-shot : "
                 "export SDD_DISABLE_COST_CAP=1")
            return HOOK_DENY
        warn("FIX (interactive) : run `python .claude/python/sdd_admin/"
             "verify_telemetry_health.py` to diagnose ; allowing this "
             "invocation but cap is OFF for the run")
        return HOOK_ALLOW

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
        return HOOK_DENY

    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
