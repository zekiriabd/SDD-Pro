"""SDD_Pro — Single source of truth for Anthropic model pricing.

Centralizes per-million-token pricing for all models used by Claude Code
agents, consumed by both `report_roi.py` (post-hoc ROI aggregation) and
`preflight_cost_cap.py` (real-time cost cap enforcement).

Before v7.0.1 the pricing was duplicated in both files with an explicit
comment "avoid import cycle". The cycle no longer exists since this
module has zero dependencies; consumers should import from here.

Rates (USD per million tokens) sourced from Anthropic API pricing page
(https://www.anthropic.com/pricing), reviewed 2026-05-21.

Freshness contract (audit m4, 2026-06-06)
-----------------------------------------
The `PRICING_LAST_REVIEWED` constant below MUST be updated each time
the pricing table is reviewed/edited. `framework_smoke.py` invokes
`check_pricing_freshness()` which compares this date against
`PricingFreshnessMaxAgeDays` (config.base.yml, default 90 days) and
emits a WARN or STOP per `PricingFreshnessMode` (off/warn/strict).
"""

from __future__ import annotations

import datetime as _dt

# ---------------------------------------------------------------------------
# Canonical pricing table (USD per million tokens)
# ---------------------------------------------------------------------------
# Schema : { model_id : { "input", "output", "cache_read", "cache_creation" } }
# Cache creation = 1.25x input, cache read = 0.10x input (Anthropic policy).
#
# Audit C2 (2026-08-29) — current-generation ids added. Before this fix the
# table stopped at the 4.x family, so a runtime model id such as
# ``claude-opus-5`` (or ``claude-opus-5[1m]``) missed every lookup and
# ``get_pricing()`` silently returned FALLBACK_PRICING (Sonnet rates),
# under-counting the run. Rates below are the published per-MTok Anthropic
# API rates for the 5-generation.
#
# KNOWN DIVERGENCE — CLOSED 2026-08-30 (follow-up to audit 2026-08-29 C2).
# The ``claude-opus-4-*`` rows carried a historical $15/$75 rate; the
# published rate for that family is $5/$25 (same as the opus-5 row). They
# were over-counting (a cost cap that trips early — conservative, never a
# safety hole), but a wrong number is still a wrong number in a cost report.
# Corrected here AND in every coordinated location that pinned the old
# figures: `providers/anthropic.yaml`, `sdd_scripts/bench_run.py` docstring,
# `tests/test_pricing.py`, `tests/test_preflight_cost_cap.py`,
# `tests/test_report_roi.py`. Deliberately NOT touched: any cost already
# recorded in a project's live `console.db` — those rows are a historical
# record of what was actually computed at the time, not a live value to
# retroactively rewrite.
PRICING: dict[str, dict[str, float]] = {
    # --- current generation (5) -------------------------------------------
    "claude-fable-5":     {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_creation": 12.50},
    "claude-mythos-5":    {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_creation": 12.50},
    "claude-opus-5":      {"input":  5.00, "output": 25.00, "cache_read": 0.50, "cache_creation":  6.25},
    "claude-sonnet-5":    {"input":  2.00, "output": 10.00, "cache_read": 0.20, "cache_creation":  2.50},
    # --- 4.x family -------------------------------------------------------
    "claude-opus-4-8":    {"input":  5.00, "output": 25.00, "cache_read": 0.50, "cache_creation":  6.25},
    "claude-opus-4-7":    {"input":  5.00, "output": 25.00, "cache_read": 0.50, "cache_creation":  6.25},
    "claude-opus-4-6":    {"input":  5.00, "output": 25.00, "cache_read": 0.50, "cache_creation":  6.25},
    "claude-sonnet-4-6":  {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-sonnet-4-5":  {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-haiku-4-5":   {"input":  1.00, "output":  5.00, "cache_read": 0.10, "cache_creation":  1.25},
}

# Conservative fallback for unknown / unmapped models : Sonnet midpoint
FALLBACK_PRICING: dict[str, float] = PRICING["claude-sonnet-4-6"]


# ---------------------------------------------------------------------------
# Multi-provider pricing (audit 2026-07-26 R2 — fail-closed under non-Anthropic)
# ---------------------------------------------------------------------------
# Provider YAMLs under `.sdd/providers/*.yaml` declare their own `pricing:`
# blocks (OpenAI, Google, Moonshot). Before v7.0.1 the cost-cap only knew
# Anthropic models and silently under-counted OpenAI o1 / Gemini Pro / Kimi
# K3 at Sonnet rates → up to 5× underestimation. Now pricing.py lazy-loads
# every provider YAML and exposes `has_known_pricing()` so callers
# (preflight_cost_cap) can fail-closed on truly-unknown models.
#
# Lazy import : hooks are short-lived subprocesses; the yaml cost (~50 ms) is
# paid once and only when the run has non-Anthropic activity.
_PROVIDER_PRICING_CACHE: dict[str, dict[str, float]] | None = None


def _load_provider_pricing() -> dict[str, dict[str, float]]:
    """Load pricing tables from every `.sdd/providers/*.yaml`, cached.

    Never raises : provider YAMLs are treated as best-effort augmentation
    of the canonical Anthropic table. Any parse error or missing key is
    silently skipped (caller falls back to `FALLBACK_PRICING`).
    """
    global _PROVIDER_PRICING_CACHE
    if _PROVIDER_PRICING_CACHE is not None:
        return _PROVIDER_PRICING_CACHE
    result: dict[str, dict[str, float]] = {}
    try:
        from .paths import providers_dir  # local import — avoid circular
        pdir = providers_dir()
    except Exception:
        _PROVIDER_PRICING_CACHE = result
        return result
    if not pdir.is_dir():
        _PROVIDER_PRICING_CACHE = result
        return result
    try:
        import yaml  # local import — hooks pay only when needed
    except Exception:
        _PROVIDER_PRICING_CACHE = result
        return result
    for ypath in sorted(pdir.glob("*.yaml")):
        try:
            data = yaml.safe_load(ypath.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        pricing = data.get("pricing")
        if not isinstance(pricing, dict):
            continue
        for model_id, tariffs in pricing.items():
            if not isinstance(tariffs, dict):
                continue
            inp = tariffs.get("input")
            outp = tariffs.get("output")
            if inp is None or outp is None:
                continue
            try:
                inp_f = float(inp)
                outp_f = float(outp)
                cr = float(tariffs.get("cache_read", inp))
                cc = float(tariffs.get("cache_creation", inp))
            except (TypeError, ValueError):
                continue
            # Canonical PRICING wins on collision (Anthropic SSoT).
            if str(model_id) in PRICING:
                continue
            result[str(model_id)] = {
                "input": inp_f,
                "output": outp_f,
                "cache_read": cr,
                "cache_creation": cc,
            }
    _PROVIDER_PRICING_CACHE = result
    return result


def has_known_pricing(model_id: str | None) -> bool:
    """Return True iff pricing for `model_id` is known (canonical OR provider YAML).

    Used by `preflight_cost_cap` to detect models that would silently fall
    back to Sonnet rates. Callers can then fail-closed with
    ``[PRICING_UNKNOWN]`` instead of continuing on stale/wrong data.
    """
    base = base_model_id(model_id)
    if not base:
        return False
    if base in PRICING:
        return True
    return base in _load_provider_pricing()


def base_model_id(model_id: str | None) -> str:
    """Strip a runtime context-window suffix like ``[1m]`` from a model id.

    Claude Code may report ``claude-opus-4-8[1m]`` at runtime while the
    pricing table is keyed on the canonical ``claude-opus-4-8``. Without
    this normalization the cost-cap would miss the table and fall back to
    Sonnet, under-counting Opus spend 5x (audit CR-1, 2026-06-11).
    """
    return (model_id or "").split("[", 1)[0].strip()


def get_pricing(model_id: str | None) -> dict[str, float]:
    """Return per-million-token pricing dict for a given model_id.

    Lookup order (audit 2026-07-26 R2) :
      1. Canonical Anthropic ``PRICING`` (SSoT).
      2. ``.sdd/providers/*.yaml`` ``pricing:`` blocks (OpenAI, Google, Moonshot).
      3. ``FALLBACK_PRICING`` (Sonnet rates — used only for truly unknown ids).

    The id is normalized (``base_model_id``) before lookup so a runtime
    ``[1m]`` suffix still resolves. Callers that need to reject unknown
    models (fail-closed cost cap) should first check
    :func:`has_known_pricing` — this function is defensive by design and
    never raises, so silent fallback would otherwise mask misconfiguration.
    """
    base = base_model_id(model_id)
    if base in PRICING:
        return PRICING[base]
    provider_pricing = _load_provider_pricing()
    if base in provider_pricing:
        return provider_pricing[base]
    return FALLBACK_PRICING


def as_tuple(model_id: str) -> tuple[float, float, float, float]:
    """Return pricing as (input, output, cache_creation, cache_read) tuple.

    Compat shim for `report_roi.py` legacy PRICING_TABLE shape.
    """
    p = get_pricing(model_id)
    return (p["input"], p["output"], p["cache_creation"], p["cache_read"])


# ---------------------------------------------------------------------------
# Freshness check (audit m4, 2026-06-06)
# ---------------------------------------------------------------------------
#: ISO date of the last manual review against https://www.anthropic.com/pricing
#: BUMP THIS each time you edit the PRICING table — `framework_smoke.py`
#: checks staleness against `PricingFreshnessMaxAgeDays` (config.base.yml).
PRICING_LAST_REVIEWED = "2026-08-30"


def check_pricing_freshness(max_age_days: int = 90, today: _dt.date | None = None
                            ) -> tuple[bool, int, str]:
    """Return (is_fresh, age_days, last_reviewed_iso).

    is_fresh : True ssi (today - PRICING_LAST_REVIEWED) <= max_age_days.
    Caller (framework_smoke.py) decides off/warn/strict per
    `PricingFreshnessMode` in layered config.
    """
    reviewed = _dt.date.fromisoformat(PRICING_LAST_REVIEWED)
    ref = today or _dt.date.today()
    age = (ref - reviewed).days
    return (age <= max_age_days, age, PRICING_LAST_REVIEWED)
