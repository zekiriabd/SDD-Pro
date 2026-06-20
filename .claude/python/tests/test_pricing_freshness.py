"""Tests for sdd_lib.pricing freshness check (audit m4, 2026-06-06).

Validates that:
1. PRICING_LAST_REVIEWED is a parseable ISO date.
2. check_pricing_freshness() correctly flags stale data per max_age_days.
3. The PRICING table contains all model IDs documented in CLAUDE.md /
   .claude/docs/ (Opus 4.7, Sonnet 4.6, Haiku 4.5).
"""
from __future__ import annotations

import datetime as dt

from sdd_lib import pricing


def test_pricing_last_reviewed_is_iso_date():
    """PRICING_LAST_REVIEWED must be parseable — no typos."""
    reviewed = dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
    assert reviewed.year >= 2024  # sanity floor


def test_check_pricing_freshness_within_window():
    """Reviewed today → fresh."""
    today = dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
    is_fresh, age, _ = pricing.check_pricing_freshness(max_age_days=90, today=today)
    assert is_fresh is True
    assert age == 0


def test_check_pricing_freshness_stale():
    """Reviewed 120d ago with 90d cap → stale."""
    reviewed = dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
    future = reviewed + dt.timedelta(days=120)
    is_fresh, age, last = pricing.check_pricing_freshness(max_age_days=90, today=future)
    assert is_fresh is False
    assert age == 120
    assert last == pricing.PRICING_LAST_REVIEWED


def test_check_pricing_freshness_edge_exact_max_age():
    """Exactly at max_age_days → still fresh (inclusive boundary)."""
    reviewed = dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
    boundary = reviewed + dt.timedelta(days=90)
    is_fresh, age, _ = pricing.check_pricing_freshness(max_age_days=90, today=boundary)
    assert is_fresh is True
    assert age == 90


def test_pricing_table_covers_active_models():
    """All models referenced by CLAUDE.md / loader.yml must price."""
    required = ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]
    for model in required:
        p = pricing.get_pricing(model)
        # Schema invariant: every entry has the 4 canonical keys.
        for key in ("input", "output", "cache_read", "cache_creation"):
            assert key in p, f"{model}: missing key {key}"
            assert p[key] > 0, f"{model}.{key}: must be positive USD/M"


def test_pricing_fallback_for_unknown_model():
    """Unknown model → Sonnet midpoint, never crash."""
    p = pricing.get_pricing("claude-unknown-99")
    sonnet = pricing.get_pricing("claude-sonnet-4-6")
    assert p == sonnet
