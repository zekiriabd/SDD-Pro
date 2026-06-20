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
PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-7":    {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_creation": 18.75},
    "claude-opus-4-6":    {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_creation": 18.75},
    "claude-sonnet-4-6":  {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-sonnet-4-5":  {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-haiku-4-5":   {"input":  1.00, "output":  5.00, "cache_read": 0.10, "cache_creation":  1.25},
}

# Conservative fallback for unknown / unmapped models : Sonnet midpoint
FALLBACK_PRICING: dict[str, float] = PRICING["claude-sonnet-4-6"]


def get_pricing(model_id: str) -> dict[str, float]:
    """Return per-million-token pricing dict for a given model_id.

    Falls back to Sonnet pricing if the model is unknown (defensive —
    callers never break on a new model_id).
    """
    return PRICING.get(model_id, FALLBACK_PRICING)


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
PRICING_LAST_REVIEWED = "2026-05-21"


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
