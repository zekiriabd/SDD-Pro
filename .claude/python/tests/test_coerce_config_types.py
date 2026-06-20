"""Tests for sdd_lib.project_config — opt-in type coercion (v7.0.0-alpha).

Covers `coerce_scalar`, `coerce_config_types`, and the `coerce=True` flag
on `parse_kv_block` / `read_project_config` / `read_layered_config`.

Critical invariants under test :
  - Legacy callers (`coerce=False` / default) see byte-identical v6.x output.
  - String-enum keys (mode/severity) NEVER get coerced even if the literal
    matches a bool pattern (e.g. `QAMode: off` stays "off", not False).
  - Coercion is idempotent (running it twice = no change).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.project_config import (  # noqa: E402
    STRING_ENUM_KEYS,
    coerce_config_types,
    coerce_scalar,
    parse_kv_block,
    read_project_config,
)


# ============================================================================
# coerce_scalar
# ============================================================================

class TestCoerceScalarBool(unittest.TestCase):
    """YAML 1.1 bool literals → Python bool."""

    def test_true_variants(self):
        for v in ("true", "True", "TRUE", "yes", "Yes", "on", "ON"):
            self.assertIs(coerce_scalar(v), True, f"failed on {v!r}")

    def test_false_variants(self):
        for v in ("false", "False", "FALSE", "no", "No", "off", "OFF"):
            self.assertIs(coerce_scalar(v), False, f"failed on {v!r}")

    def test_truthy_string_not_bool(self):
        # "1" is int not bool
        self.assertEqual(coerce_scalar("1"), 1)
        # "TRUEISH" doesn't match any bool literal
        self.assertEqual(coerce_scalar("TRUEISH"), "TRUEISH")


class TestCoerceScalarInt(unittest.TestCase):
    """Decimal integer literals → int (no float, no underscores)."""

    def test_positive_int(self):
        self.assertEqual(coerce_scalar("42"), 42)
        self.assertIsInstance(coerce_scalar("42"), int)

    def test_zero(self):
        self.assertEqual(coerce_scalar("0"), 0)
        self.assertIsInstance(coerce_scalar("0"), int)

    def test_negative_int(self):
        self.assertEqual(coerce_scalar("-3"), -3)

    def test_int_with_leading_zeros_stays_int(self):
        # "007" matches \d+ → coerced to 7 (matches int() behaviour)
        self.assertEqual(coerce_scalar("007"), 7)

    def test_hex_not_coerced(self):
        """No octal/hex support — too risky (could trip 0x7E parsing)."""
        self.assertEqual(coerce_scalar("0x10"), "0x10")


class TestCoerceScalarFloat(unittest.TestCase):
    """Decimal float literals → float."""

    def test_positive_float(self):
        self.assertEqual(coerce_scalar("15.00"), 15.0)
        self.assertIsInstance(coerce_scalar("15.00"), float)

    def test_negative_float(self):
        self.assertEqual(coerce_scalar("-3.14"), -3.14)

    def test_scientific_not_coerced(self):
        """`1e10` doesn't match the strict /^-?\\d+\\.\\d+$/ regex."""
        self.assertEqual(coerce_scalar("1e10"), "1e10")

    def test_dot_only_not_coerced(self):
        self.assertEqual(coerce_scalar("."), ".")
        self.assertEqual(coerce_scalar(".5"), ".5")


class TestCoerceScalarString(unittest.TestCase):
    """Everything else stays string."""

    def test_mode_literal_stays_string(self):
        # coerce_scalar coerces "off" → False but that's intentional :
        # coerce_config_types() guards mode keys via STRING_ENUM_KEYS
        self.assertIs(coerce_scalar("off"), False)  # raw coercion: YAML 1.1
        self.assertIs(coerce_scalar("manual"), False) if False else self.assertEqual(coerce_scalar("manual"), "manual")

    def test_version_string_unchanged(self):
        self.assertEqual(coerce_scalar("1.2.3"), "1.2.3")

    def test_path_unchanged(self):
        self.assertEqual(coerce_scalar("workspace/output/foo"), "workspace/output/foo")

    def test_empty_string_unchanged(self):
        self.assertEqual(coerce_scalar(""), "")

    def test_whitespace_only_stripped_to_empty(self):
        self.assertEqual(coerce_scalar("   "), "")


class TestCoerceScalarRobustness(unittest.TestCase):
    """Defensive against non-string input."""

    def test_none_passthrough(self):
        # Non-string input pass through unchanged
        self.assertIsNone(coerce_scalar(None))

    def test_int_passthrough(self):
        self.assertEqual(coerce_scalar(42), 42)

    def test_bool_passthrough(self):
        self.assertIs(coerce_scalar(True), True)


# ============================================================================
# coerce_config_types
# ============================================================================

class TestCoerceConfigTypes(unittest.TestCase):
    """Full config dict coercion with STRING_ENUM_KEYS guard."""

    def test_qamode_off_stays_string(self):
        """Mode key with `off` value MUST remain the string "off", not False."""
        result = coerce_config_types({"QAMode": "off"})
        self.assertEqual(result["QAMode"], "off")

    def test_all_modes_stay_string(self):
        modes = {
            "QAMode": "manual",
            "A11yMode": "off",
            "PerfMode": "off",
            "CodeReviewMode": "full",
            "SecurityMode": "full",
            "SpecComplianceMode": "manual",
            "ArchReviewMode": "manual",
            "ReviewMode": "scans-only",
        }
        out = coerce_config_types(modes)
        for k, v in modes.items():
            self.assertEqual(out[k], v, f"{k} should stay string")
            self.assertIsInstance(out[k], str)

    def test_failon_severity_stays_string(self):
        sevs = {
            "SecurityFailOn": "critical",
            "CodeReviewFailOn": "serious",
            "ArchReviewFailOn": "moderate",
        }
        out = coerce_config_types(sevs)
        for k, v in sevs.items():
            self.assertEqual(out[k], v)
            self.assertIsInstance(out[k], str)

    def test_numeric_keys_coerced(self):
        result = coerce_config_types({
            "CoverageMin": "0",
            "MaxParallel": "3",
            "BuildLoopMaxIter": "2",
            "MaxCostPerRun": "50.00",
        })
        self.assertEqual(result["CoverageMin"], 0)
        self.assertIsInstance(result["CoverageMin"], int)
        self.assertEqual(result["MaxParallel"], 3)
        self.assertEqual(result["MaxCostPerRun"], 50.0)
        self.assertIsInstance(result["MaxCostPerRun"], float)

    def test_bool_keys_coerced(self):
        result = coerce_config_types({
            "GatedWorkflow": "true",
            "SecurityScanEnabled": "false",
            "PlanReviewDefault": "true",
        })
        self.assertIs(result["GatedWorkflow"], True)
        self.assertIs(result["SecurityScanEnabled"], False)

    def test_appname_stays_string_even_if_numeric_shaped(self):
        """Unlikely but defensive : project named '42' must stay string."""
        result = coerce_config_types({"AppName": "42"})
        self.assertEqual(result["AppName"], "42")
        self.assertIsInstance(result["AppName"], str)

    def test_idempotent(self):
        """Running coerce twice yields the same dict."""
        once = coerce_config_types({
            "CoverageMin": "80",
            "GatedWorkflow": "true",
            "QAMode": "off",
        })
        twice = coerce_config_types(once)
        self.assertEqual(once, twice)

    def test_unknown_keys_coerced(self):
        """Unknown keys (custom user extensions) get coerced too."""
        result = coerce_config_types({"MyCustomFlag": "true"})
        self.assertIs(result["MyCustomFlag"], True)

    def test_empty_dict(self):
        self.assertEqual(coerce_config_types({}), {})


class TestStringEnumKeysCoverage(unittest.TestCase):
    """The STRING_ENUM_KEYS frozenset must cover all known mode/severity keys."""

    def test_all_modes_in_string_enum_set(self):
        for k in (
            "QAMode", "A11yMode", "PerfMode",
            "CodeReviewMode", "SecurityMode",
            "SpecComplianceMode", "ArchReviewMode", "ReviewMode",
            "MutationTestingMode", "E2EMode",
            "ElicitorGapMode", "FeatAntiGigoMode", "FeatDeepenMode",
            "CheckpointMode", "TokenUsageMode",
        ):
            self.assertIn(k, STRING_ENUM_KEYS, f"missing mode key: {k}")

    def test_all_failon_in_string_enum_set(self):
        for k in (
            "A11yFailOn", "PerfFailOn",
            "CodeReviewFailOn", "SecurityFailOn",
            "SpecComplianceFailOn", "ArchReviewFailOn", "ReviewFailOn",
        ):
            self.assertIn(k, STRING_ENUM_KEYS, f"missing severity key: {k}")

    def test_project_names_in_string_enum_set(self):
        """Names must stay strings even if user picks numeric-shaped name."""
        for k in ("AppName", "BackendName", "LibName", "FrontendName",
                  "AppNamespace", "BackendNamespace"):
            self.assertIn(k, STRING_ENUM_KEYS)


# ============================================================================
# parse_kv_block coerce flag
# ============================================================================

class TestParseKvBlockCoerce(unittest.TestCase):
    """`coerce=True` opt-in parameter on parse_kv_block."""

    BLOCK = """
CoverageMin: 80
GatedWorkflow: true
QAMode: manual
AppName: MyApp
"""

    def test_default_returns_strings_v6_compat(self):
        """Default (`coerce=False`) → all strings, byte-identical v6.x."""
        result = parse_kv_block(self.BLOCK)
        self.assertEqual(result["CoverageMin"], "80")
        self.assertEqual(result["GatedWorkflow"], "true")
        self.assertEqual(result["QAMode"], "manual")
        self.assertIsInstance(result["CoverageMin"], str)

    def test_coerce_true_returns_native_types(self):
        result = parse_kv_block(self.BLOCK, coerce=True)
        self.assertEqual(result["CoverageMin"], 80)
        self.assertIsInstance(result["CoverageMin"], int)
        self.assertIs(result["GatedWorkflow"], True)
        # Mode key stays string
        self.assertEqual(result["QAMode"], "manual")
        self.assertIsInstance(result["QAMode"], str)


# ============================================================================
# read_project_config + read_layered_config integration
# ============================================================================

class TestReadProjectConfigCoerce(unittest.TestCase):
    """End-to-end : read stack.md with coerce=True returns typed values."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        # Minimal scaffolding for repo_root detection
        (self.repo / ".claude" / "agents").mkdir(parents=True)
        (self.repo / ".claude" / "commands").mkdir(parents=True)
        (self.repo / "workspace" / "input" / "stack").mkdir(parents=True)
        (self.repo / "workspace" / "input" / "stack" / "stack.md").write_text(
            "## Project Config\n"
            "AppName: TestApp\n"
            "BackendName: TestBackend\n"
            "CoverageMin: 75\n"
            "MaxParallel: 2\n"
            "MaxCostPerRun: 20.50\n"
            "GatedWorkflow: true\n"
            "QAMode: manual\n"
            "CodeReviewFailOn: critical\n",
            encoding="utf-8",
        )
        os.environ["SDD_REPO_ROOT"] = str(self.repo)

    def tearDown(self):
        os.environ.pop("SDD_REPO_ROOT", None)
        self._tmp.cleanup()

    def test_legacy_default_returns_strings(self):
        cfg = read_project_config(root=self.repo)
        self.assertEqual(cfg["CoverageMin"], "75")
        self.assertEqual(cfg["GatedWorkflow"], "true")
        self.assertIsInstance(cfg["MaxCostPerRun"], str)

    def test_coerce_true_returns_native(self):
        cfg = read_project_config(root=self.repo, coerce=True)
        self.assertEqual(cfg["CoverageMin"], 75)
        self.assertIsInstance(cfg["CoverageMin"], int)
        self.assertEqual(cfg["MaxCostPerRun"], 20.5)
        self.assertIsInstance(cfg["MaxCostPerRun"], float)
        self.assertIs(cfg["GatedWorkflow"], True)
        # Strings preserved
        self.assertEqual(cfg["AppName"], "TestApp")
        self.assertEqual(cfg["QAMode"], "manual")
        self.assertEqual(cfg["CodeReviewFailOn"], "critical")


class TestReadLayeredConfigCoerce(unittest.TestCase):
    """End-to-end : read_layered_config(coerce=True) coerces base + project."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / ".claude" / "agents").mkdir(parents=True)
        (self.repo / ".claude" / "commands").mkdir(parents=True)
        (self.repo / "workspace" / "input" / "stack").mkdir(parents=True)
        (self.repo / ".claude" / "config.base.yml").write_text(
            "CoverageMin: 80\n"
            "MaxParallel: 3\n"
            "GatedWorkflow: true\n"
            "QAMode: manual\n",
            encoding="utf-8",
        )
        (self.repo / "workspace" / "input" / "stack" / "stack.md").write_text(
            "## Project Config\n"
            "AppName: MyApp\n"
            "CoverageMin: 90\n"     # project overrides base
            "MaxCostPerRun: 30\n",  # project-only
            encoding="utf-8",
        )
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        os.environ["SDD_TEAM_CONFIG"] = "/dev/null/missing"  # no team layer

    def tearDown(self):
        os.environ.pop("SDD_REPO_ROOT", None)
        os.environ.pop("SDD_TEAM_CONFIG", None)
        self._tmp.cleanup()

    def test_legacy_default_returns_strings(self):
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config(root=self.repo)
        self.assertEqual(cfg["CoverageMin"], "90")
        self.assertEqual(cfg["MaxParallel"], "3")
        self.assertEqual(cfg["GatedWorkflow"], "true")

    def test_coerce_returns_native_post_merge(self):
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config(root=self.repo, coerce=True)
        # Project override wins, coerced to int
        self.assertEqual(cfg["CoverageMin"], 90)
        self.assertIsInstance(cfg["CoverageMin"], int)
        # Base value coerced
        self.assertEqual(cfg["MaxParallel"], 3)
        self.assertIs(cfg["GatedWorkflow"], True)
        # Float from project layer
        self.assertEqual(cfg["MaxCostPerRun"], 30)
        # Mode preserved
        self.assertEqual(cfg["QAMode"], "manual")


if __name__ == "__main__":
    unittest.main()
