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
        self.assertEqual(p["input"], 5.00)
        self.assertEqual(p["output"], 25.00)

    def test_unknown_model_uses_conservative_tariff(self) -> None:
        """Audit tokens 2026-11-07 — plus de repli silencieux sur Sonnet 4.6 :
        tarif le plus cher connu (un cost cap doit sur-estimer l'inconnu)."""
        p = pricing.get_pricing("claude-unknown-future-model")
        self.assertEqual(p, pricing.CONSERVATIVE_PRICING)
        most = max(v["output"] for v in pricing.PRICING.values())
        self.assertEqual(p["output"], most)
        self.assertNotEqual(p, pricing.PRICING["claude-sonnet-4-6"])

    def test_unknown_model_warns_once_on_stderr(self) -> None:
        import contextlib
        import io
        pricing._WARNED_UNKNOWN.discard("'claude-warn-probe-xyz'")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            pricing.get_pricing("claude-warn-probe-xyz")
            pricing.get_pricing("claude-warn-probe-xyz")
        out = buf.getvalue()
        self.assertEqual(out.count("WARN [pricing]"), 1, out)
        self.assertIn("claude-warn-probe-xyz", out)

    def test_unknown_warning_can_be_silenced(self) -> None:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            pricing.get_pricing("claude-silent-probe-xyz", warn_unknown=False)
        self.assertEqual(buf.getvalue(), "")


class TestGeneration55(unittest.TestCase):
    """Audit tokens 2026-11-07 — tarifs exacts publiés (USD/Mtok)."""

    EXPECTED = {
        "claude-opus-5-5":   (4.00, 20.00, 0.20, 5.00),
        "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
        "claude-haiku-5-5":  (0.10, 0.50, 0.01, 0.125),
        "claude-fable-5-1":  (10.00, 50.00, 0.25, 12.50),
        "claude-opus-5":     (5.00, 25.00, 0.50, 6.25),
        "claude-sonnet-5":   (2.00, 10.00, 0.20, 2.50),
        "claude-fable-5":    (10.00, 50.00, 1.00, 12.50),
    }

    def test_exact_rates(self) -> None:
        for model, expected in self.EXPECTED.items():
            p = pricing.PRICING[model]
            got = (p["input"], p["output"], p["cache_read"], p["cache_creation"])
            self.assertEqual(got, expected, model)

    def test_provider_yaml_mirrors_canonical(self) -> None:
        import yaml
        from sdd_lib.paths import providers_dir
        data = yaml.safe_load((providers_dir() / "anthropic.yaml").read_text(encoding="utf-8"))
        for model in self.EXPECTED:
            self.assertIn(model, data["pricing"], model)
            for k in ("input", "output", "cache_read", "cache_creation"):
                self.assertAlmostEqual(float(data["pricing"][model][k]),
                                       pricing.PRICING[model][k], msg=f"{model}.{k}")

    def test_tier_map_points_to_55_with_1m_context(self) -> None:
        from sdd_lib.config_loader import load_provider
        prov = load_provider("anthropic")
        self.assertEqual(prov["tier_map"], {"deep": "claude-opus-5-5",
                                            "balanced": "claude-sonnet-5-5",
                                            "fast": "claude-haiku-5-5"})
        self.assertEqual(set(prov["context_window"].values()), {1_000_000})
        for model in prov["tier_map"].values():
            self.assertTrue(pricing.has_known_pricing(model), model)

    def test_estimate_cost(self) -> None:
        c = pricing.estimate_cost("claude-opus-5-5", input_tokens=1_000_000,
                                  output_tokens=1_000_000, cache_read_tokens=1_000_000,
                                  cache_creation_tokens=1_000_000)
        self.assertAlmostEqual(c, 4.00 + 20.00 + 0.20 + 5.00)


class TestAsTuple(unittest.TestCase):
    def test_tuple_order_input_output_cachecreation_cacheread(self) -> None:
        """Legacy report_roi.py shape: (in, out, cache_creation, cache_read)."""
        t = pricing.as_tuple("claude-opus-4-7")
        self.assertEqual(t, (5.00, 25.00, 6.25, 0.50))

    def test_tuple_unknown_model(self) -> None:
        t = pricing.as_tuple("claude-unknown")
        c = pricing.CONSERVATIVE_PRICING  # tarif conservateur (audit 2026-11-07)
        self.assertEqual(t, (c["input"], c["output"], c["cache_creation"], c["cache_read"]))


class TestMultiProviderPricing(unittest.TestCase):
    """Audit R2 (2026-07-26) — pricing.py must expose provider YAML pricing.

    Before v7.0.2 the cost-cap silently under-counted premium non-Anthropic
    models (o1, gemini-2.5-pro, kimi-k3) at Sonnet FALLBACK_PRICING rates
    → up to 5× under-estimation. Fix : load `.sdd/providers/*.yaml` lazily.
    """

    def setUp(self) -> None:
        # Force a fresh load per test — the cache is module-global and could
        # be polluted by prior tests that patched paths.
        pricing._PROVIDER_PRICING_CACHE = None

    def test_openai_o1_pricing_from_yaml(self) -> None:
        """OpenAI o1 must resolve to real openai.yaml rates, not Sonnet fallback."""
        p = pricing.get_pricing("o1")
        self.assertEqual(p["input"], 15.00)   # o1 input price
        self.assertEqual(p["output"], 60.00)  # o1 output price (not Sonnet's 75)

    def test_gemini_pro_pricing_from_yaml(self) -> None:
        """Gemini 2.5 Pro must resolve to real google.yaml rates."""
        p = pricing.get_pricing("gemini-2.5-pro")
        self.assertEqual(p["input"], 1.25)
        self.assertEqual(p["output"], 5.00)

    def test_kimi_k3_pricing_from_yaml(self) -> None:
        """Kimi K3 must resolve to real moonshot.yaml rates."""
        p = pricing.get_pricing("kimi-k3")
        self.assertEqual(p["input"], 0.60)
        self.assertEqual(p["output"], 2.50)

    def test_has_known_pricing_true_for_canonical(self) -> None:
        self.assertTrue(pricing.has_known_pricing("claude-opus-4-8"))

    def test_has_known_pricing_true_for_provider_yaml(self) -> None:
        for m in ("o1", "gpt-4o", "gemini-2.5-pro", "gemini-2.5-flash",
                  "kimi-k3", "kimi-k2.5"):
            self.assertTrue(pricing.has_known_pricing(m), f"{m} should be known")

    def test_has_known_pricing_false_for_truly_unknown(self) -> None:
        self.assertFalse(pricing.has_known_pricing("bogus-model-xyz"))
        self.assertFalse(pricing.has_known_pricing(None))
        self.assertFalse(pricing.has_known_pricing(""))

    def test_canonical_wins_on_collision(self) -> None:
        """If a provider YAML re-declares an Anthropic model, canonical wins."""
        # anthropic.yaml lists claude-opus-4-8 identically to PRICING.
        # Verify get_pricing returns the canonical entry (dict identity via ==).
        canonical = pricing.PRICING["claude-opus-4-8"]
        resolved = pricing.get_pricing("claude-opus-4-8")
        self.assertEqual(resolved, canonical)


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
