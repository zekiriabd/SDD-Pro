"""Unit tests for sdd_lib/pricing.py — Anthropic model pricing SSoT."""
from __future__ import annotations

import datetime as _dt
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib import pricing  # noqa: E402


class TestPricingTable(unittest.TestCase):
    def test_known_models_listed(self) -> None:
        """All currently-used Claude 4.x models are in the table."""
        for model in ("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"):
            self.assertIn(model, pricing.PRICING)

    def test_pricing_schema_complete(self) -> None:
        """Each model exposes the 4 required pricing fields."""
        required = {"input", "output", "cache_read", "cache_creation"}
        for model, prices in pricing.PRICING.items():
            self.assertEqual(set(prices.keys()), required, f"model={model}")
            # All values are positive floats
            for k, v in prices.items():
                self.assertIsInstance(v, (int, float))
                self.assertGreater(v, 0, f"{model}.{k}")

    def test_output_costlier_than_input(self) -> None:
        """Anthropic policy : output ≈ 5× input (sanity check)."""
        for model, prices in pricing.PRICING.items():
            self.assertGreater(
                prices["output"], prices["input"],
                f"{model} output should cost more than input",
            )

    def test_cache_read_cheaper_than_input(self) -> None:
        """Cache read = 0.10× input per Anthropic policy."""
        for model, prices in pricing.PRICING.items():
            self.assertLess(
                prices["cache_read"], prices["input"],
                f"{model} cache_read should be cheaper than input",
            )

    def test_cache_creation_premium(self) -> None:
        """Cache creation = 1.25× input per Anthropic policy."""
        for model, prices in pricing.PRICING.items():
            self.assertGreater(
                prices["cache_creation"], prices["input"],
                f"{model} cache_creation should be more expensive than input",
            )


class TestGetPricing(unittest.TestCase):
    def test_known_model_returns_correct_dict(self) -> None:
        p = pricing.get_pricing("claude-opus-4-7")
        self.assertEqual(p["input"], 15.00)
        self.assertEqual(p["output"], 75.00)

    def test_unknown_model_falls_back_to_sonnet(self) -> None:
        p = pricing.get_pricing("claude-unknown-future-model")
        # Fallback = sonnet pricing
        self.assertEqual(p, pricing.PRICING["claude-sonnet-4-6"])


class TestAsTuple(unittest.TestCase):
    def test_tuple_order_input_output_cachecreation_cacheread(self) -> None:
        """Legacy report_roi.py shape: (in, out, cache_creation, cache_read)."""
        t = pricing.as_tuple("claude-opus-4-7")
        self.assertEqual(t, (15.00, 75.00, 18.75, 1.50))

    def test_tuple_unknown_model(self) -> None:
        t = pricing.as_tuple("claude-unknown")
        # Sonnet fallback as tuple
        self.assertEqual(t, (3.00, 15.00, 3.75, 0.30))


class TestCheckPricingFreshness(unittest.TestCase):
    def test_fresh_returns_true(self) -> None:
        """Within max_age_days → is_fresh=True."""
        # Use the reviewed date + 30 days = fresh under default 90d
        reviewed = _dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
        today = reviewed + _dt.timedelta(days=30)
        is_fresh, age, last = pricing.check_pricing_freshness(max_age_days=90, today=today)
        self.assertTrue(is_fresh)
        self.assertEqual(age, 30)
        self.assertEqual(last, pricing.PRICING_LAST_REVIEWED)

    def test_stale_returns_false(self) -> None:
        """Beyond max_age_days → is_fresh=False."""
        reviewed = _dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
        today = reviewed + _dt.timedelta(days=120)
        is_fresh, age, _ = pricing.check_pricing_freshness(max_age_days=90, today=today)
        self.assertFalse(is_fresh)
        self.assertEqual(age, 120)

    def test_exactly_at_max_age_is_fresh(self) -> None:
        """Boundary: age == max_age_days is still fresh."""
        reviewed = _dt.date.fromisoformat(pricing.PRICING_LAST_REVIEWED)
        today = reviewed + _dt.timedelta(days=90)
        is_fresh, _, _ = pricing.check_pricing_freshness(max_age_days=90, today=today)
        self.assertTrue(is_fresh)


if __name__ == "__main__":
    unittest.main()
