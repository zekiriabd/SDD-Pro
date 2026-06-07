"""Tests for sdd_lib.cache_control — Anthropic prompt-caching manifest parser.

Audit CTO 2026-06-07 — P0 performance fix: this module preps the manifest
for prompt caching activation (v7.1 harness wiring).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.cache_control import (  # noqa: E402
    AgentCacheManifest,
    CachedRead,
    cache_breakpoints_for,
    parse_loader_annotations,
    report,
)

pytestmark = pytest.mark.smoke


class TestCacheControlParser(unittest.TestCase):
    def test_parse_loader_returns_all_12_agents(self):
        manifests = parse_loader_annotations()
        # 12 agents expected after v7.0.1 cache_layer rollout
        expected_agents = {
            "po", "arch", "dev-backend", "dev-frontend", "qa",
            "elicitor", "constitutioner", "code-reviewer",
            "security-reviewer", "spec-compliance-reviewer",
            "arch-reviewer", "adversarial-reviewer",
        }
        actual_agents = set(manifests.keys())
        missing = expected_agents - actual_agents
        self.assertFalse(
            missing,
            f"Missing agents in loader.yml cache_layer annotations: {missing}",
        )

    def test_each_agent_has_at_least_one_read_annotated(self):
        manifests = parse_loader_annotations()
        for agent_name, manifest in manifests.items():
            if agent_name not in {
                "po", "arch", "dev-backend", "dev-frontend", "qa",
                "elicitor", "constitutioner", "code-reviewer",
                "security-reviewer", "spec-compliance-reviewer",
                "arch-reviewer", "adversarial-reviewer",
            }:
                continue
            stats = manifest.stats()
            self.assertGreater(
                stats["total"], 0,
                f"Agent '{agent_name}' has 0 cache_layer-annotated reads "
                f"in loader.yml — annotate to enable prompt caching.",
            )

    def test_stable_reads_dominate_globally(self):
        """Globally, stable should be the largest bucket (cache-friendly)."""
        manifests = parse_loader_annotations()
        totals = {"stable": 0, "semi": 0, "volatile": 0}
        for m in manifests.values():
            stats = m.stats()
            totals["stable"] += stats["stable"]
            totals["semi"] += stats["semi"]
            totals["volatile"] += stats["volatile"]
        grand = sum(totals.values())
        self.assertGreater(grand, 50, "Expected >50 annotated reads total")
        # Stable + semi should dominate (cache-friendly > 50%)
        cacheable = totals["stable"] + totals["semi"]
        self.assertGreater(
            cacheable, totals["volatile"],
            f"Cacheable reads ({cacheable}) should exceed volatile "
            f"({totals['volatile']}) for net cache benefit.",
        )

    def test_cache_breakpoints_ordering(self):
        """Cache breakpoints must be in cache-friendly order: stable → semi → volatile."""
        for agent in ("dev-backend", "arch", "code-reviewer"):
            breakpoints = cache_breakpoints_for(agent)
            if not breakpoints:
                continue  # agent missing — covered by previous test
            layers = [layer for layer, _ in breakpoints]
            expected_order = ["stable", "semi", "volatile"]
            actual_order = [l for l in expected_order if l in layers]
            # Ensure stable appears before semi before volatile
            for i in range(len(actual_order) - 1):
                idx_a = layers.index(actual_order[i])
                idx_b = layers.index(actual_order[i + 1])
                self.assertLess(
                    idx_a, idx_b,
                    f"Agent '{agent}' breakpoints not in stable→semi→volatile "
                    f"order: {layers}",
                )

    def test_max_4_breakpoints_per_agent(self):
        """Anthropic supports max 4 cache_control markers per request."""
        manifests = parse_loader_annotations()
        for agent_name, manifest in manifests.items():
            breakpoints = manifest.cache_breakpoints()
            self.assertLessEqual(
                len(breakpoints), 4,
                f"Agent '{agent_name}' has {len(breakpoints)} cache breakpoints "
                f"— Anthropic supports max 4 per request.",
            )

    def test_report_contains_total_line(self):
        text = report()
        self.assertIn("TOTAL", text)
        self.assertIn("stable=", text)
        self.assertIn("semi=", text)
        self.assertIn("volatile=", text)


class TestManifestDataclass(unittest.TestCase):
    def test_all_reads_orders_stable_first(self):
        m = AgentCacheManifest(agent="test")
        m.volatile.append(CachedRead(path="v.md", layer="volatile"))
        m.stable.append(CachedRead(path="s.md", layer="stable"))
        m.semi.append(CachedRead(path="m.md", layer="semi"))
        ordered = m.all_reads()
        self.assertEqual([r.path for r in ordered], ["s.md", "m.md", "v.md"])

    def test_stats_dict(self):
        m = AgentCacheManifest(agent="test")
        m.stable.append(CachedRead(path="s.md", layer="stable"))
        m.stable.append(CachedRead(path="s2.md", layer="stable"))
        m.semi.append(CachedRead(path="m.md", layer="semi"))
        stats = m.stats()
        self.assertEqual(stats, {"stable": 2, "semi": 1, "volatile": 0, "total": 3})


if __name__ == "__main__":
    unittest.main()
