#!/usr/bin/env python3
"""SDD_Pro PreToolUse.Agent hook — hard $ cost cap per run (v7.0.0 P0 §4.3).

Queries console.db `token_usage` table for the current run (matched by the
stable run_id from `sdd_lib.run_id`) and computes cumulative USD spent so far
over EVERY row of the run — sub-agents AND the orchestrator row
(`agent='orchestrator'`, written on `Stop` by `record_token_usage` from the
session transcript, audit tokens 2026-11-07). If cumulative cost reaches
`MaxCostPerRun` (layered config), blocks with exit 2 + [COST_CAP_EXCEEDED].

Pricing SSoT : `sdd_lib/pricing.py` (`estimate_cost`). A row whose model is
NULL or unknown is priced at the CONSERVATIVE tariff (most expensive known)
and reported as a WARN — it is never a reason to DENY (audit tokens
2026-11-07 : the previous `[PRICING_UNKNOWN]` DENY fired on EVERY spawn in CI
as soon as one unattributed row existed — a self-inflicted denial of
service, while the cap itself kept under-counting).

Bypass (conscient uniquement) :
  - Set MaxCostPerRun: 0 in stack.md ## Project Config (disables cap, git blame trace)
  - Set $SDD_DISABLE_COST_CAP=1 env var (one-shot, shell history audit)

Default behaviour (v7.0.0 audit P0 R1 fix 2026-05-20) :
  - 80%-100% du cap : WARN informatif (heads-up, non bloquant)
  - >= 100% du cap : **HARD BLOCK systématique** (exit 2), peu importe contexte
    interactif OU CI. Le comportement antérieur "WARN-only en interactif"
    laissait les Tech Leads dépasser silencieusement le budget.
  - console.db présent mais ILLISIBLE : **DENY [INFRA_BLOCKED]** (exit 2),
    interactif comme CI — fail-closed (audit tokens 2026-11-07 ; avant :
    WARN + ALLOW en interactif, le cap était silencieusement OFF).
    `db absent` (fresh checkout, pré-bootstrap) reste un ALLOW légitime.

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
from sdd_lib.pricing import (  # noqa: E402  # v7.0.1 SSoT (normalizes [1m] suffix — audit CR-1)
    CONSERVATIVE_MODEL_ID,
    estimate_cost,
    has_known_pricing,
)
from sdd_lib.run_id import get_or_create_run_id  # noqa: E402  # v7.0.1 stable scoping
from sdd_lib.stderr import warn  # noqa: E402


def _coerce_cap(raw: object, *, default: float, key: str) -> float:
    """Parse a configured USD cap, refusing to silently WIDEN the budget.

    Audit M9 (2026-08-29) — the pre-fix code wrapped `float()` in a bare
    ``except Exception: return <default>``. A typo (``MaxCostPerRun: 5O``,
    ``$15``, ``fifteen``) therefore replaced a deliberately *tighter* team
    value with the framework default, which is frequently **larger** — a
    defensive fallback that is weaker than the value it replaces. That is the
    one direction a safety default must never move.

    New behaviour : a malformed value is loud (ERROR on stderr, naming the
    raw text) and resolves to the *most conservative* interpretation
    available — the default, but only after the operator has been told the
    configured value was discarded. A negative value is treated as malformed
    rather than as "disabled" (only an explicit ``0`` disables).
    """
    if raw is None:
        return default
    text = str(raw).strip()
    if not text:
        return default
    try:
        value = float(text)
    except (TypeError, ValueError):
        warn(f"ERROR: preflight-cost-cap — valeur de config invalide")
        warn(f"CAUSE: [STACK_MALFORMED] {key}={text!r} n'est pas un "
             f"nombre — valeur IGNORÉE, fallback ${default:.2f}. Si votre "
             f"équipe visait un plafond PLUS SERRÉ, il vient d'être élargi "
             f"silencieusement jusqu'à ce message.")
        warn(f"FIX: corriger {key} dans ## Project Config (stack.md) ou "
             f"~/.sdd/config.team.yml — un nombre décimal en USD, ou 0 pour "
             f"désactiver explicitement le cap.")
        return default
    if value < 0:
        warn(f"ERROR: preflight-cost-cap — valeur de config invalide")
        warn(f"CAUSE: [STACK_MALFORMED] {key}={text!r} est négatif — "
             f"valeur IGNORÉE, fallback ${default:.2f} (utiliser 0 pour "
             f"désactiver le cap de façon explicite).")
        warn(f"FIX: corriger {key} dans ## Project Config (stack.md).")
        return default
    return value


def _log_cost_cap_bypass(scope: str) -> None:
    """Emit the audit line for a `SDD_DISABLE_COST_CAP=1` bypass.

    Audit M8 (2026-08-29) — the docstring above and `error-classification.md`
    both describe this bypass as "audité dans shell history", but the code
    returned `0.0` in silence: nothing on stderr, nothing in the transcript,
    nothing in console.db. A bypass nobody can see is not audited. Matches
    the house style already used by `preflight_stack_combo.py`.
    """
    warn(f"[cost-cap] {scope} : BYPASS via SDD_DISABLE_COST_CAP=1 — "
         f"le plafond de dépense est DÉSACTIVÉ pour cette invocation")


def _cost_cap_env_disabled() -> bool:
    return (os.environ.get("SDD_DISABLE_COST_CAP", "").strip().lower()
            in ("1", "true", "yes"))


def _resolve_cap() -> float:
    """Resolve MaxCostPerRun from layered config (env override possible).

    Returns 0.0 to disable. Defaults to $50.00 if config unreadable.
    """
    # Env one-shot disable
    if _cost_cap_env_disabled():
        _log_cost_cap_bypass("run-level cap (MaxCostPerRun)")
        return 0.0
    try:
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config()
        raw = cfg.get("MaxCostPerRun")
    except Exception as e:  # noqa: BLE001 — never break the pipeline
        # Audit M9 (2026-08-29) — a config layer that cannot be READ falls
        # back to the framework default. That is defensible (the value is
        # unknown, not wrong) but it must be visible, since $50 may be
        # looser than what the team intended.
        warn(f"WARN [cost-cap] layered config unreadable ({type(e).__name__}: {e}) "
             f"— fallback MaxCostPerRun=$50.00. Vérifier stack.md ## Project "
             f"Config / ~/.sdd/config.team.yml.")
        return 50.00
    return _coerce_cap(raw, default=50.00, key="MaxCostPerRun")


def _resolve_us_cap() -> float:
    """Resolve BuildLoopMaxCostUsd from layered config (audit 2026-06-06 RUPT-2).

    Caps the cumulative USD spent on build_loop iterations for ONE US.
    Distinguishes cost-pathological convergence from iter-pathological
    convergence ([BUILD_LOOP_EXHAUSTED]).

    Returns 0.0 to disable. Defaults to $15.00 if config unreadable (per
    config.base.yml line 194). Shares the env one-shot disable with the
    run-level cap.
    """
    # Env one-shot disable (same as run-level — single bypass for both).
    # The run-level resolver already logged the bypass for this invocation;
    # staying quiet here avoids a duplicated audit line (audit M8).
    if _cost_cap_env_disabled():
        return 0.0
    try:
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config()
        raw = cfg.get("BuildLoopMaxCostUsd")
    except Exception as e:  # noqa: BLE001 — never break the pipeline
        warn(f"WARN [cost-cap] layered config unreadable ({type(e).__name__}: {e}) "
             f"— fallback BuildLoopMaxCostUsd=$15.00.")
        return 15.00
    return _coerce_cap(raw, default=15.00, key="BuildLoopMaxCostUsd")


def _check_telemetry_health() -> None:
    """Emit visible WARN if record_token_usage is silently failing.

    Reads `.audit/token-telemetry-failure-count` written by record_token_usage
    hook when a DB insert raises. Emits a stderr WARN if any failures
    accumulated since last successful run, so the operator knows the cost
    cap is operating on incomplete data."""
    try:
        from sdd_lib.paths import audit_dir_path, workspace_root, repo_root
        counter_path = (
            audit_dir_path(repo_root())
            / "token-telemetry-failure-count"
        )
        if not counter_path.is_file():
            return
        n = int(counter_path.read_text(encoding="utf-8").strip() or "0")
        if n > 0:
            warn(
                f"WARN preflight-cost-cap : token telemetry has {n} failed "
                f"insert(s) accumulated. Cost cap is operating on possibly "
                f"stale data. See workspace/.sys/.audit/"
                f"token-telemetry-failures.log for details. Reset counter "
                f"after fix : echo 0 > {counter_path.as_posix()}"
            )
    except Exception:
        # Health check itself must not break the hook chain.
        pass


# --------------------------------------------------------------------------- #
# SDD agent registry — scope of the [PRICING_UNKNOWN] *report* (audit C-1,
# 2026-08-30 ; downgraded from DENY to WARN by audit tokens 2026-11-07)
# --------------------------------------------------------------------------- #
#
# Unpriced rows (NULL or unknown model) are split by ownership so the WARN
# tells the operator whether the gap is in an agent SDD routes (fixable in
# `.sdd/agents/*.md` / provider YAML) or in a Claude Code built-in (Explore,
# general-purpose, …). Both are priced at the CONSERVATIVE tariff and counted
# against the cap ; neither can DENY a spawn on its own.
_AGENT_REGISTRY_CACHE: frozenset[str] | None = None
_AGENT_REGISTRY_LOADED = False

#: Agent labels that identify nobody — `record_token_usage` falls back to the
#: hook event name (or the literal "unknown") when the payload carries no
#: `subagent_type`. Such a row COULD be an SDD agent, so it stays blocking.
_UNATTRIBUTED_PREFIXES: tuple[str, ...] = ("posttooluse", "subagentstop", "unknown")


def _sdd_agent_registry() -> frozenset[str] | None:
    """Names of the agents SDD_Pro owns, or None if the registry is unreadable.

    On-disk projection of the loader manifest : one `.sdd/agents/{name}.md`
    per declared agent (forward + reverse). Returning None makes the caller
    treat every row as in-registry — an unreadable registry must never
    *weaken* the guard, only a readable one may narrow it.
    """
    global _AGENT_REGISTRY_CACHE, _AGENT_REGISTRY_LOADED
    if not _AGENT_REGISTRY_LOADED:
        _AGENT_REGISTRY_LOADED = True
        try:
            from sdd_lib.paths import repo_root, sdd_home
            agents_dir = sdd_home(repo_root()) / "agents"
            names = {p.stem for p in agents_dir.glob("*.md")} if agents_dir.is_dir() else set()
            _AGENT_REGISTRY_CACHE = frozenset(names) or None
        except Exception:  # noqa: BLE001 — a hook never breaks the pipeline
            _AGENT_REGISTRY_CACHE = None
    return _AGENT_REGISTRY_CACHE


def _blocks_on_unknown_pricing(agent: object) -> bool:
    """True when an unpriced row from `agent` belongs to the SDD-owned bucket.

    Name kept for the audit trail (C-1) ; since audit tokens 2026-11-07 the
    bucket only drives the WARN wording — no bucket can DENY. Only an agent
    that is positively identified AND positively absent from the SDD registry
    lands in the "foreign" bucket.
    """
    registry = _sdd_agent_registry()
    if registry is None:
        return True
    name = str(agent or "").strip()
    if not name:
        return True
    if name in registry:
        return True
    if name.lower().startswith(_UNATTRIBUTED_PREFIXES):
        return True
    return False


# Module-level cache (process-local) for cost queries.
# Mitigates per-Agent-spawn SQL hit (audit finding C3 v7.0.0-alpha 2026-06-04).
# TTL 30s : cap precision is $50 default with O(0.01$) telemetry resolution,
# 30s window is fine grained enough vs Agent spawn cadence (~5-30s).
# NOTE audit 2026-06-11 (info #12) : chaque hook tourne dans un process
# `python -c` frais (durée de vie < 1 s) — ce cache module-level ne produit
# JAMAIS de hit aujourd'hui. Conservé délibérément : coût nul, et il devient
# effectif si le hook est un jour invoqué in-process (harness long-vie).
# Extended v7.0.2 (audit R2) : tuple now carries `unknown_models` list so
# fail-closed detection survives the cache hit.
# Extended 2026-08-30 (audit C-1) : a second list carries the unpriced models
# consumed by agents OUTSIDE the SDD registry — reported, never blocking.
_COST_CACHE: dict[
    str, tuple[float, float, int, str, tuple[str, ...], tuple[str, ...]]
] = {}
_COST_CACHE_TTL_SEC = 30.0


#: `session_id` du payload PreToolUse courant (posé par `main()`).
_SESSION_ID: str | None = None


def _current_run_id() -> str:
    """run_id scopé à la session Claude Code quand le payload la porte.

    Sans `session_id`, `get_or_create_run_id` retombe en mode legacy (marker
    partagé 24 h) — appel sans argument conservé pour ce cas (et pour les
    tests qui substituent la fonction par un lambda sans paramètre).
    """
    if _SESSION_ID:
        return get_or_create_run_id(session_id=_SESSION_ID)
    return get_or_create_run_id()


def _compute_run_cost() -> tuple[float, int, str, tuple[str, ...], tuple[str, ...]]:
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

    Caching (v7.0.0-alpha audit C3 fix 2026-06-04) : in-process 30s TTL on
    (cost, count, scope) keyed by run_id. PreToolUse.Agent fires before
    every Agent spawn (8-12× per /sdd-full) — without cache, each fire opens
    SQLite + queries token_usage. With index `idx_token_usage_run` the query
    itself is O(log n), but connection overhead + serialization ~5-15ms each
    accumulates. Cache invalidation = TTL expiry (next Agent spawn after 30s
    re-queries). Sufficient for cap enforcement at $0.01 precision.

    Returns (cost_usd, call_count, scope_label, unknown_models,
    unknown_models_out_of_registry). The last two split the unpriced rows by
    ownership (audit C-1, 2026-08-30) for the WARN wording — neither produces
    a HOOK_DENY (audit tokens 2026-11-07). Both are priced into `cost_usd`
    at the CONSERVATIVE tariff.

    Scope label conventions (v7.0.0-alpha telemetry-trust fix) :
      - "run={id} (no rows yet)" : DB readable, run scope empty → safe ALLOW
      - "db absent"              : console.db file missing → safe ALLOW
                                    (fresh checkout / pre-bootstrap)
      - "db error: {detail}"     : DB exists but unreadable → caller DENIES
                                    with [INFRA_BLOCKED] in every context
                                    (audit tokens 2026-11-07). Previously
                                    this state silently returned 0.0 → the
                                    cap was bypassed every time telemetry
                                    failed (root cause filed by user
                                    2026-05-21).
    """
    try:
        from sdd_lib.console_db import connect_ro, default_db_path
    except Exception as e:
        return 0.0, 0, f"db error: import failed: {e}", (), ()
    try:
        from sdd_lib.console_db import ConsoleDbUnavailable
    except Exception:  # noqa: BLE001 — API antérieure : classe absente
        ConsoleDbUnavailable = None  # type: ignore[assignment]

    # Distinguish absent (legit fresh state) from unreadable (suspect).
    try:
        if not default_db_path().exists():
            return 0.0, 0, "db absent", (), ()
    except Exception:
        # repo_root() failure is itself a problem — surface it.
        pass

    # v7.0.1 : always resolve a stable run_id (env > marker file > generate).
    # Avoids the legacy "today window" fallback which collided across parallel runs.
    run_id = _current_run_id()

    # Cache check (C3 fix) : skip SQLite if same run_id within TTL.
    import time
    now = time.monotonic()
    cached = _COST_CACHE.get(run_id)
    if cached is not None:
        (cached_ts, cached_cost, cached_count, cached_scope,
         cached_unknown, cached_foreign) = cached
        if (now - cached_ts) < _COST_CACHE_TTL_SEC:
            return (cached_cost, cached_count, cached_scope,
                    cached_unknown, cached_foreign)

    try:
        with connect_ro() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT model, input_tokens, output_tokens, "
                "       cache_creation_tokens, cache_read_tokens, agent "
                "FROM token_usage WHERE run_id = ?",
                (run_id,),
            )
            rows = cur.fetchall()
            if not rows:
                return 0.0, 0, f"run={run_id[:8]} (no rows yet)", (), ()
            scope = f"run={run_id[:8]}"
    except Exception as e:
        # `ConsoleDbUnavailable` (lot données/états, sous-classe de
        # sqlite3.OperationalError) = lecture `connect_ro` impossible sans
        # `allow_stale` : nommé explicitement, classé [INFRA_BLOCKED] → DENY.
        if ConsoleDbUnavailable is not None and isinstance(e, ConsoleDbUnavailable):
            return 0.0, 0, f"db error: ConsoleDbUnavailable: {e}", (), ()
        # SCOPE = "db error: ..." signals the caller that 0.0 is NOT a
        # legitimate "no cost yet" but a "cap unenforceable" condition.
        return 0.0, 0, f"db error: {e}", (), ()

    total = 0.0
    unknown: list[str] = []  # unpriced models consumed by SDD-registry agents (or unattributed)
    foreign: list[str] = []  # audit C-1 : same, but consumed outside the SDD registry
    for row in rows:
        model, inp, outp, cc, cr = row[:5]
        agent = row[5] if len(row) > 5 else None
        # Audit C2 (2026-08-29) — a NULL/empty model is flagged too (the
        # pre-fix guard `if model and ...` let NULL slip through unreported).
        # Audit C-1 (2026-08-30) — split by ownership for the WARN wording.
        # Audit tokens 2026-11-07 — flagged rows are REPORTED, never a DENY :
        # `estimate_cost` prices them at the most expensive known tariff, so
        # the cap can only trip early on them. (The DENY turned every CI run
        # with one unattributed row into a wall ; meanwhile the real
        # under-count — zeros from the async Agent tool — went unnoticed.)
        key = (model or "").strip()
        label = key or "<unrecorded>"
        if not key or not has_known_pricing(key):
            bucket = unknown if _blocks_on_unknown_pricing(agent) else foreign
            if label not in bucket:
                bucket.append(label)
        total += estimate_cost(
            model, input_tokens=inp or 0, output_tokens=outp or 0,
            cache_creation_tokens=cc or 0, cache_read_tokens=cr or 0,
            warn_unknown=False,  # the WARN is emitted once by main(), with context
        )

    unknown_tuple = tuple(unknown)
    foreign_tuple = tuple(foreign)
    # Cache write (C3 fix) — TTL expiry on next read past 30s.
    _COST_CACHE[run_id] = (now, total, len(rows), scope,
                           unknown_tuple, foreign_tuple)
    return total, len(rows), scope, unknown_tuple, foreign_tuple


# Module-level cache (process-local) for per-US cost queries (RUPT-2).
# Same TTL semantics as _COST_CACHE — keyed by (run_id, feat_n, us_id).
_US_COST_CACHE: dict[tuple[str, int, str], tuple[float, float, int]] = {}


def _compute_us_cost(feat_n: int, us_id: str) -> tuple[float, int, str]:
    """Aggregate USD spent so far on a specific US (audit 2026-06-06 RUPT-2).

    Scopes the cost cumulation to ``token_usage WHERE run_id=? AND feat_n=?
    AND us_id=?``. Used for ``BuildLoopMaxCostUsd`` enforcement during
    dev-backend / dev-frontend build_loop iterations.

    Returns (cost_usd, call_count, scope_label).
    Scope label: ``"us={n}-{m} run={id:.8}"`` or ``"us={n}-{m} (no rows yet)"``.

    Safe ALLOW on any I/O error (cap is best-effort, same defensive stance
    as ``_compute_run_cost``).
    """
    try:
        from sdd_lib.console_db import connect_ro, default_db_path
    except Exception:
        return 0.0, 0, "db error: import failed"

    try:
        if not default_db_path().exists():
            return 0.0, 0, "db absent"
    except Exception:
        pass

    run_id = _current_run_id()
    cache_key = (run_id, feat_n, us_id)

    import time
    now = time.monotonic()
    cached = _US_COST_CACHE.get(cache_key)
    if cached is not None:
        cached_ts, cached_cost, cached_count = cached
        if (now - cached_ts) < _COST_CACHE_TTL_SEC:
            return cached_cost, cached_count, f"us={us_id} run={run_id[:8]}"

    try:
        with connect_ro() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT model, input_tokens, output_tokens, "
                "       cache_creation_tokens, cache_read_tokens "
                "FROM token_usage "
                "WHERE run_id = ? AND feat_n = ? AND us_id = ?",
                (run_id, feat_n, us_id),
            )
            rows = cur.fetchall()
            if not rows:
                return 0.0, 0, f"us={us_id} (no rows yet)"
            scope = f"us={us_id} run={run_id[:8]}"
    except Exception as e:
        return 0.0, 0, f"db error: {e}"

    total = 0.0
    for model, inp, outp, cc, cr in rows:
        total += estimate_cost(
            model, input_tokens=inp or 0, output_tokens=outp or 0,
            cache_creation_tokens=cc or 0, cache_read_tokens=cr or 0,
            warn_unknown=False,
        )

    _US_COST_CACHE[cache_key] = (now, total, len(rows))
    return total, len(rows), scope


def _extract_feat_us_from_payload(payload: dict) -> tuple[int | None, str | None]:
    """Extract (feat_n, us_id) from a PreToolUse.Agent payload, if applicable.

    Searches the prompt-side `tool_input` for a `{n}-{m}` pattern in the
    arguments (e.g. ``Agent: dev-backend args="1-2"``). Returns
    (None, None) if no SDD-shaped anchor is found.

    Defensive : never raises. Returns (None, None) on any parse failure
    — caller treats this as "no per-US scope, skip per-US cap".
    """
    try:
        import re
        # Look in tool_input.prompt OR tool_input.arguments for a {n}-{m} anchor.
        tool_input = payload.get("tool_input", {}) or {}
        candidates = []
        if isinstance(tool_input, dict):
            for k in ("prompt", "arguments", "args", "description"):
                v = tool_input.get(k)
                if isinstance(v, str):
                    candidates.append(v)
        for haystack in candidates:
            # Match the canonical {n}-{m} SDD anchor (with optional :plan suffix
            # and optional quotes around the arg).
            m = re.search(r"\b(\d+)-(\d+)(?::plan)?\b", haystack)
            if m:
                return int(m.group(1)), f"{m.group(1)}-{m.group(2)}"
    except Exception:
        pass
    return None, None


def main() -> int:
    cap = _resolve_cap()
    if cap <= 0:
        return HOOK_ALLOW  # disabled (was bare `return 0`, normalized 2026-06-06)

    payload = read_hook_input()
    if not payload:
        return HOOK_ALLOW
    global _SESSION_ID
    sid = payload.get("session_id")
    _SESSION_ID = sid.strip() if isinstance(sid, str) and sid.strip() else None
    subagent = get_subagent_type(payload)
    if not subagent:
        return HOOK_ALLOW
    cost, calls, scope, unknown_models, foreign_unknown = _compute_run_cost()
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
    # corrupted schema, etc.).
    #
    # Audit tokens 2026-11-07 — fail-closed in EVERY context. The former
    # "interactive → WARN + ALLOW, cap OFF for the run" branch was a silent
    # bypass of a `severity: critical` invariant (cost-cap-per-run) : a Tech
    # Lead with a locked WAL file ran uncapped without having asked for it.
    # The only bypass is the explicit, audit-logged SDD_DISABLE_COST_CAP=1.
    if scope.startswith("db error:"):
        warn("ERROR: preflight-cost-cap — console.db illisible, cap inapplicable")
        warn(f"CAUSE: [INFRA_BLOCKED] telemetry unavailable "
             f"([TELEMETRY_UNAVAILABLE]) — {scope}")
        warn("FIX: diagnostiquer avec `python .sdd/python/sdd_admin/"
             "verify_telemetry_health.py` (WAL lock, permissions FS, fichier "
             "corrompu) ; bypass one-shot conscient : export SDD_DISABLE_COST_CAP=1")
        return HOOK_DENY

    # Unpriced rows (audit R2 2026-07-26 → C-1 2026-08-30 → tokens 2026-11-07).
    # A model absent from canonical PRICING and every provider YAML — NULL
    # included — is priced at the CONSERVATIVE tariff (most expensive known),
    # so the cap errs early, never late. That makes a DENY pointless and the
    # former CI-only DENY was actively harmful : one unattributed row and
    # every subsequent spawn of the run was refused. Report, count, continue.
    # `SDD_ALLOW_UNKNOWN_PRICING` is accepted for backward compatibility but
    # no longer changes anything.
    if unknown_models or foreign_unknown:
        parts = []
        if unknown_models:
            parts.append(f"agents SDD : {list(unknown_models)!r}")
        if foreign_unknown:
            parts.append(f"subagents hors registre : {list(foreign_unknown)!r}")
        warn("WARN preflight-cost-cap : [PRICING_UNKNOWN] modèle(s) sans tarif — "
             + " ; ".join(parts)
             + f" — comptés au tarif conservateur ({CONSERVATIVE_MODEL_ID}), "
             "jamais bloquant. FIX : ajouter le tarif dans sdd_lib/pricing.py "
             "ou .sdd/providers/{provider}.yaml, bumper PRICING_LAST_REVIEWED.")

    # 80%-100% : WARN (let the operator know early, do not block — head-up only)
    if cap * 0.8 <= cost < cap:
        warn(f"WARN preflight-cost-cap : ${cost:.2f} / ${cap:.2f} "
             f"({pct:.0f}% du cap) — {calls} calls scope={scope}")
        return HOOK_ALLOW
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

    # Audit 2026-06-06 RUPT-2 — per-US build_loop cost cap (BuildLoopMaxCostUsd).
    # Only applies to dev-backend / dev-frontend (the agents that iterate via
    # build_loop). Distinguishes cost-pathological convergence from
    # [BUILD_LOOP_EXHAUSTED] (iter limit). Symmetrical bypass with run-level
    # cap : SDD_DISABLE_COST_CAP=1 OR BuildLoopMaxCostUsd: 0 config.
    if subagent in ("dev-backend", "dev-frontend"):
        us_cap = _resolve_us_cap()
        if us_cap > 0:
            feat_n, us_id = _extract_feat_us_from_payload(payload)
            if feat_n is not None and us_id is not None:
                us_cost, us_calls, us_scope = _compute_us_cost(feat_n, us_id)
                if us_scope.startswith("db error:"):
                    # Same telemetry-trust policy as run-level — visible WARN,
                    # but don't double-DENY (run-level already handled it).
                    pass
                else:
                    us_pct = (us_cost / us_cap * 100) if us_cap > 0 else 0
                    if us_cost >= us_cap:
                        warn(f"ERROR: preflight-cost-cap — cap USD atteint pour cette US")
                        warn(f"CAUSE: [BUILD_LOOP_COST_EXCEEDED] ${us_cost:.2f} >= "
                             f"${us_cap:.2f} ({us_calls} calls scope={us_scope}) "
                             f"— cost-pathological convergence on us={us_id}")
                        warn(f"FIX: (a) inspecter la sortie build_loop (stderr/chat) "
                             f"pour comprendre la cause ; "
                             f"(b) augmenter BuildLoopMaxCostUsd dans Project Config "
                             f"(decision tracee) ; "
                             f"(c) bypass one-shot : export SDD_DISABLE_COST_CAP=1")
                        return HOOK_DENY
                    elif us_cap * 0.8 <= us_cost < us_cap:
                        warn(f"WARN preflight-cost-cap : ${us_cost:.2f} / ${us_cap:.2f} "
                             f"({us_pct:.0f}% du cap US) — {us_calls} calls scope={us_scope}")

    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
