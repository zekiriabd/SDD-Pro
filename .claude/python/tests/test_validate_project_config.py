"""Tests for sdd_scripts.validate_project_config — JSON-Schema validator.

Targets the pure validation function (in-process, no DB / no subprocess).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.validate_project_config import (  # noqa: E402
    _load_schema,
    validate_config,
)


def _schema() -> dict:
    """Load the actual project-config.schema.json from the repo."""
    repo = Path(__file__).resolve().parents[3]
    return _load_schema(repo)


class TestSchemaIntegrity(unittest.TestCase):
    """The schema file itself must be well-formed and cover the framework keys."""

    def test_schema_is_valid_json(self):
        schema = _schema()
        self.assertEqual(schema["title"], "SDD_Pro Project Config")

    def test_schema_covers_key_modes(self):
        """All *Mode keys consumed by agents are documented."""
        schema = _schema()
        props = schema["properties"]
        for key in (
            "QAMode", "CodeReviewMode", "SecurityMode", "SpecComplianceMode",
            "ArchReviewMode", "ReviewMode", "MutationTestingMode", "E2EMode",
            "ElicitorGapMode", "FeatAntiGigoMode", "FeatDeepenMode",
            "CheckpointMode", "TokenUsageMode",
        ):
            self.assertIn(key, props, f"Schema missing {key}")

    def test_schema_covers_failon_keys(self):
        """All *FailOn keys are documented with FailOnSeverity definition."""
        schema = _schema()
        props = schema["properties"]
        for key in (
            "CoverageMin",
            "CodeReviewFailOn", "SecurityFailOn", "SpecComplianceFailOn",
            "ArchReviewFailOn", "ReviewFailOn", "A11yFailOn", "PerfFailOn",
        ):
            self.assertIn(key, props, f"Schema missing {key}")

    def test_schema_covers_cost_caps(self):
        schema = _schema()
        props = schema["properties"]
        for key in ("MaxCostPerRun", "BuildLoopMaxCostUsd", "BuildLoopMaxIter", "MaxParallel"):
            self.assertIn(key, props)

    def test_schema_explicitly_marks_deprecated_keys(self):
        """Deprecated/experimental keys must carry a marker in _meta."""
        schema = _schema()
        depr = schema["_meta"]["experimental_or_noop"]
        self.assertIn("PlanCacheStrict", depr)
        self.assertIn("SecurityThreatModelEnabled", depr)


class TestValidateConfigBasics(unittest.TestCase):
    """Pure validate_config() : valid config → empty findings."""

    def test_empty_config_no_errors(self):
        self.assertEqual(validate_config({}, _schema()), [])

    def test_valid_default_config_no_errors(self):
        """Mirror of config.base.yml defaults should validate clean."""
        config = {
            "QAMode": "manual",
            "CoverageMin": 80,
            "MaxParallel": 3,
            "BuildLoopMaxIter": 3,
            "BuildLoopMaxCostUsd": 15.00,
            "MaxCostPerRun": 50.00,
            "CodeReviewMode": "full",
            "CodeReviewFailOn": "critical",
            "SecurityMode": "full",
            "SecurityScanEnabled": True,
            "PlanCacheStrict": False,
            "GatedWorkflow": True,
            "CiTemplatesGeneration": True,
        }
        self.assertEqual(validate_config(config, _schema()), [])


class TestValidateConfigEnumViolations(unittest.TestCase):
    """ENUM_VIOLATION when value is outside the declared enum."""

    def test_qamode_typo_caught(self):
        findings = validate_config({"QAMode": "of"}, _schema())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "ENUM_VIOLATION")
        self.assertEqual(findings[0]["key"], "QAMode")

    def test_failon_out_of_enum_caught(self):
        findings = validate_config({"SecurityFailOn": "BLOCKER"}, _schema())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "ENUM_VIOLATION")

    def test_valid_enum_passes(self):
        findings = validate_config({"QAMode": "tests-only"}, _schema())
        self.assertEqual(findings, [])

    def test_review_mode_full_set(self):
        """ReviewMode has more options than the standard ModeOnOffManualFull."""
        for v in ("off", "manual", "scans-only", "read-only", "full"):
            self.assertEqual(validate_config({"ReviewMode": v}, _schema()), [])
        self.assertEqual(
            validate_config({"ReviewMode": "partial"}, _schema())[0]["code"],
            "ENUM_VIOLATION",
        )


class TestValidateConfigRangeViolations(unittest.TestCase):
    """BELOW_MINIMUM / ABOVE_MAXIMUM on integer + number."""

    def test_coverage_min_negative_caught(self):
        findings = validate_config({"CoverageMin": -10}, _schema())
        self.assertEqual(findings[0]["code"], "BELOW_MINIMUM")

    def test_coverage_min_above_100_caught(self):
        findings = validate_config({"CoverageMin": 150}, _schema())
        self.assertEqual(findings[0]["code"], "ABOVE_MAXIMUM")

    def test_max_parallel_too_high_caught(self):
        findings = validate_config({"MaxParallel": 20}, _schema())
        self.assertEqual(findings[0]["code"], "ABOVE_MAXIMUM")

    def test_max_parallel_zero_caught(self):
        findings = validate_config({"MaxParallel": 0}, _schema())
        self.assertEqual(findings[0]["code"], "BELOW_MINIMUM")

    def test_max_cost_per_run_zero_accepted(self):
        """$0 = disabled = valid (NonNegativeNumber)."""
        self.assertEqual(validate_config({"MaxCostPerRun": 0.0}, _schema()), [])

    def test_max_cost_per_run_negative_caught(self):
        findings = validate_config({"MaxCostPerRun": -5.0}, _schema())
        self.assertEqual(findings[0]["code"], "BELOW_MINIMUM")


class TestValidateConfigTypeMismatch(unittest.TestCase):
    """TYPE_MISMATCH when value type differs from schema type."""

    def test_max_parallel_string_caught(self):
        findings = validate_config({"MaxParallel": "three"}, _schema())
        self.assertEqual(findings[0]["code"], "TYPE_MISMATCH")

    def test_gated_workflow_string_caught(self):
        """Boolean expected — string 'true' rejected (must be true literal)."""
        findings = validate_config({"GatedWorkflow": "true"}, _schema())
        self.assertEqual(findings[0]["code"], "TYPE_MISMATCH")

    def test_coverage_min_string_caught(self):
        findings = validate_config({"CoverageMin": "80"}, _schema())
        self.assertEqual(findings[0]["code"], "TYPE_MISMATCH")

    def test_boolean_int_rejected_for_int_field(self):
        """bool is a subclass of int in Python — schema must distinguish."""
        # True == 1, but schema expects integer not bool for MaxParallel
        findings = validate_config({"MaxParallel": True}, _schema())
        self.assertEqual(findings[0]["code"], "TYPE_MISMATCH")


class TestValidateConfigStrictUnknown(unittest.TestCase):
    """When --strict-unknown : unknown keys → UNKNOWN_KEY findings."""

    def test_unknown_key_lenient_by_default(self):
        findings = validate_config({"MyCustomKey": "x"}, _schema(), strict_unknown=False)
        self.assertEqual(findings, [])

    def test_unknown_key_strict_caught(self):
        findings = validate_config({"MyCustomKey": "x"}, _schema(), strict_unknown=True)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "UNKNOWN_KEY")
        self.assertEqual(findings[0]["key"], "MyCustomKey")

    def test_known_keys_pass_in_strict_mode(self):
        findings = validate_config({"QAMode": "manual", "CoverageMin": 70},
                                   _schema(), strict_unknown=True)
        self.assertEqual(findings, [])


class TestValidateConfigMultipleErrors(unittest.TestCase):
    """All issues should be collected, not just the first one."""

    def test_collects_multiple_findings(self):
        bad = {
            "QAMode": "of",            # ENUM_VIOLATION
            "CoverageMin": 150,        # ABOVE_MAXIMUM
            "MaxParallel": "three",    # TYPE_MISMATCH
            "SecurityFailOn": "BLOCK", # ENUM_VIOLATION
        }
        findings = validate_config(bad, _schema())
        codes = {f["code"] for f in findings}
        keys = {f["key"] for f in findings}
        self.assertEqual(len(findings), 4)
        self.assertEqual(codes, {"ENUM_VIOLATION", "ABOVE_MAXIMUM", "TYPE_MISMATCH"})
        self.assertEqual(keys, {"QAMode", "CoverageMin", "MaxParallel", "SecurityFailOn"})


if __name__ == "__main__":
    unittest.main()
