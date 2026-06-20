"""Tests for sdd_scripts.match_stack_catalog — scan→stack mapping."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.match_stack_catalog import (
    AUTH_MAPPING,
    DATABASE_MAPPING,
    STACK_RULES,
    _confidence_label,
    _score_stack,
    match,
)


def _scan(
    *,
    languages: list[str] | None = None,
    frameworks: list[str] | None = None,
    ui: list[str] | None = None,
    db: list[str] | None = None,
    auth: list[str] | None = None,
) -> dict:
    return {
        "scope_dir": "/tmp/test",
        "manifests": [],
        "languages": languages or [],
        "frameworks": frameworks or [],
        "ui_indicators": ui or [],
        "database_indicators": db or [],
        "auth_indicators": auth or [],
        "warnings": [],
    }


class TestConfidenceLabel(unittest.TestCase):
    def test_high(self):
        self.assertEqual(_confidence_label(85), "high")
        self.assertEqual(_confidence_label(100), "high")
        self.assertEqual(_confidence_label(80), "high")

    def test_medium(self):
        self.assertEqual(_confidence_label(75), "medium")
        self.assertEqual(_confidence_label(50), "medium")

    def test_low(self):
        self.assertEqual(_confidence_label(49), "low")
        self.assertEqual(_confidence_label(0), "low")


class TestScoreStack(unittest.TestCase):
    def test_perfect_match_react(self):
        rules = STACK_RULES["react"]
        scan_report = _scan(
            languages=["typescript", "javascript"],
            frameworks=["react", "vite"],
        )
        info = _score_stack(rules, scan_report)
        self.assertTrue(info["required_met"])
        self.assertGreaterEqual(info["score"], 80)

    def test_required_missing(self):
        rules = STACK_RULES["dotnet-minimalapi"]
        scan_report = _scan(languages=["dotnet"])  # framework missing
        info = _score_stack(rules, scan_report)
        self.assertFalse(info["required_met"])

    def test_only_required_no_bonus(self):
        rules = STACK_RULES["dotnet-minimalapi"]
        scan_report = _scan(
            languages=["dotnet"],
            frameworks=["aspnetcore-minimal"],
        )
        info = _score_stack(rules, scan_report)
        self.assertTrue(info["required_met"])
        # 100% required (70 pts) + 0% bonus (0 pts) = 70
        self.assertEqual(info["score"], 70)


class TestMatch(unittest.TestCase):
    def test_dotnet_minimalapi_with_react(self):
        scan_report = _scan(
            languages=["dotnet", "typescript", "javascript"],
            frameworks=["aspnetcore-minimal", "react", "vite"],
            ui=["shadcn", "tailwind"],
            db=["sqlserver"],
            auth=["azure-ad"],
        )
        result = match(scan_report)
        self.assertEqual(result["candidates"]["backend"][0]["stack_id"], "dotnet-minimalapi")
        self.assertEqual(result["candidates"]["frontend"][0]["stack_id"], "react")
        self.assertEqual(result["candidates"]["ui"][0]["stack_id"], "shadcn")
        self.assertEqual(result["database"], "SqlServer")
        self.assertEqual(result["auth"], "azure-ad")

    def test_kotlin_spring(self):
        scan_report = _scan(
            languages=["kotlin"],
            frameworks=["spring-boot", "kotlin-jvm"],
            db=["postgresql"],
        )
        result = match(scan_report)
        self.assertEqual(result["candidates"]["backend"][0]["stack_id"], "kotlin-spring-boot")
        self.assertEqual(result["database"], "PostgreSql")

    def test_fastapi(self):
        scan_report = _scan(
            languages=["python"],
            frameworks=["fastapi"],
            db=["postgresql"],
        )
        result = match(scan_report)
        ids = [c["stack_id"] for c in result["candidates"]["backend"]]
        self.assertIn("python-fastapi", ids)

    def test_blazor(self):
        scan_report = _scan(
            languages=["dotnet"],
            frameworks=["blazor-webassembly"],
            ui=["radzen-blazor"],
        )
        result = match(scan_report)
        ids = [c["stack_id"] for c in result["candidates"]["frontend"]]
        self.assertIn("blazor-webassembly", ids)
        ids_ui = [c["stack_id"] for c in result["candidates"]["ui"]]
        self.assertIn("radzen-blazor", ids_ui)

    def test_no_match_warns(self):
        scan_report = _scan(languages=["rust"], frameworks=["rocket"])
        result = match(scan_report)
        self.assertEqual(result["candidates"]["backend"], [])
        self.assertEqual(result["candidates"]["frontend"], [])
        self.assertTrue(any("DISCOVER_NO_MATCH" in w for w in result["warnings"]))

    def test_partial_backend_only(self):
        scan_report = _scan(
            languages=["dotnet"],
            frameworks=["aspnetcore-minimal"],
        )
        result = match(scan_report)
        self.assertTrue(any("DISCOVER_PARTIAL" in w for w in result["warnings"]))

    def test_ambiguous_multi_backend(self):
        scan_report = _scan(
            languages=["python", "dotnet"],
            frameworks=["fastapi", "aspnetcore-minimal"],
        )
        result = match(scan_report)
        self.assertEqual(len(result["candidates"]["backend"]), 2)
        self.assertTrue(any("DISCOVER_AMBIGUOUS" in w for w in result["warnings"]))

    def test_results_sorted_by_score(self):
        scan_report = _scan(
            languages=["javascript", "typescript"],
            frameworks=["react", "vue"],  # both match their required; react gets bonus from typescript
        )
        result = match(scan_report)
        scores = [c["score"] for c in result["candidates"]["frontend"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_database_mapping_keys(self):
        # Sanity check mapping covers expected DB indicators
        for ind in ("sqlserver", "postgresql", "mysql", "sqlite", "mongodb"):
            self.assertIn(ind, DATABASE_MAPPING)

    def test_auth_mapping_keys(self):
        self.assertIn("azure-ad", AUTH_MAPPING)
        self.assertIn("oauth2-resource-server", AUTH_MAPPING)


if __name__ == "__main__":
    unittest.main()
