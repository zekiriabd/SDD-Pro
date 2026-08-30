"""Tests for sdd_lib.pricing freshness check (audit m4, 2026-06-06).

Validates that:
1. PRICING_LAST_REVIEWED is a parseable ISO date.
2. check_pricing_freshness() correctly flags stale data per max_age_days.
3. The PRICING table contains all model IDs documented in CLAUDE.md /
   .sdd/docs/ (Opus 4.7, Sonnet 4.6, Haiku 4.5).
"""
from __future__ import annotations

import datetime as dt

from sdd_lib import pricing


def test_pricing_last_reviewed_is_iso_date():
    """PRICING_LAST_REVIEWED must be parseable — no typos."""
    reviewed = dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
    assert reviewed.year >= 2024  # sanity floor


#: Fixed reference "today" for the arithmetic tests below.
#:
#: Audit C3 (2026-08-29) — this constant deliberately does NOT derive from
#: `pricing.PRICING_LAST_REVIEWED`. The pre-fix test set
#: `today = PRICING_LAST_REVIEWED` and asserted `age == 0`, which is a
#: tautology: it holds for every possible value of PRICING_LAST_REVIEWED and
#: could therefore never fail, no matter how stale the table got. With a
#: hardcoded date the function's arithmetic is genuinely checked, and
#: `test_pricing_is_not_stale_against_real_clock` below is what actually
#: catches rot.
_REF_TODAY = dt.date(2026, 9, 1)


def test_check_pricing_freshness_computes_age_against_fixed_today():
    """Age is (today - PRICING_LAST_REVIEWED), computed, not assumed."""
    reviewed = dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
    expected_age = (_REF_TODAY - reviewed).days
    is_fresh, age, last = pricing.check_pricing_freshness(
        max_age_days=90, today=_REF_TODAY
    )
    assert age == expected_age
    assert last == pricing.PRICING_LAST_REVIEWED
    assert is_fresh is (expected_age <= 90)


def test_check_pricing_freshness_within_window():
    """A table reviewed 10d before the reference date is fresh at a 90d cap."""
    with_reviewed = _REF_TODAY - dt.timedelta(days=10)
    is_fresh, age, _ = pricing.check_pricing_freshness(
        max_age_days=90,
        today=dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED) + dt.timedelta(days=10),
    )
    assert is_fresh is True
    assert age == 10
    assert with_reviewed <= _REF_TODAY  # sanity on the fixture itself


def test_pricing_is_not_stale_against_real_clock():
    """The check that can actually fail when the pricing table rots.

    Uses the REAL current date (same call shape as `framework_smoke.py`'s
    `_check_pricing_freshness`). A generous 365d cap keeps this from
    flapping in CI on a normal quarterly cadence while still failing loudly
    when the table has been abandoned for a year.
    """
    is_fresh, age, reviewed = pricing.check_pricing_freshness(max_age_days=365)
    assert is_fresh, (
        f"PRICING table last reviewed {reviewed} ({age}d ago) — re-check "
        f"https://www.anthropic.com/pricing, update sdd_lib/pricing.py and "
        f"bump PRICING_LAST_REVIEWED. A stale table silently mis-prices the "
        f"cost cap."
    )


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
    required = ["claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]
    for model in required:
        p = pricing.get_pricing(model)
        # Schema invariant: every entry has the 4 canonical keys.
        for key in ("input", "output", "cache_read", "cache_creation"):
            assert key in p, f"{model}: missing key {key}"
            assert p[key] > 0, f"{model}.{key}: must be positive USD/M"


def test_every_agent_frontmatter_model_is_priced():
    """Root-cause guard (audit CR-1, 2026-06-11).

    The cost-cap hook (`preflight_cost_cap.py`) under-counts spend by 5x
    whenever an agent declares a model absent from PRICING, because
    get_pricing() silently falls back to Sonnet ($3/$15 vs Opus $15/$75).
    This is exactly how `claude-opus-4-8` slipped through after the
    frontmatter bump while pricing still knew only `-4-7`.

    Therefore: every `model:` declared in any `.claude/agents/*.md`
    frontmatter MUST have an EXACT key in PRICING (no fallback allowed).
    """
    import pathlib
    import re

    agents_dir = pathlib.Path(__file__).resolve().parents[2] / "agents"
    if not agents_dir.is_dir():
        return  # tolerate layout changes — covered by other suites

    model_re = re.compile(r"^model:\s*([^\s#]+)\s*$", re.MULTILINE)
    offenders: list[str] = []
    for agent_md in sorted(agents_dir.glob("*.md")):
        text = agent_md.read_text(encoding="utf-8")
        for m in model_re.finditer(text):
            model_id = m.group(1).strip().strip("'\"")
            # strip a runtime context-window suffix like "[1m]" if present
            base = model_id.split("[", 1)[0]
            if base not in pricing.PRICING:
                offenders.append(f"{agent_md.name}: model '{model_id}' not in PRICING")

    assert not offenders, (
        "Agent frontmatter declares model(s) with no exact pricing entry "
        "(cost-cap would silently fall back to Sonnet and under-count Opus 5x):\n  "
        + "\n  ".join(offenders)
    )


def test_pricing_fallback_for_unknown_model():
    """Unknown model → Sonnet midpoint, never crash."""
    p = pricing.get_pricing("claude-unknown-99")
    sonnet = pricing.get_pricing("claude-sonnet-4-6")
    assert p == sonnet
