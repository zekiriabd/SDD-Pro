"""Tests for sdd_scripts.preflight_force_cumul (audit CRIT-10)."""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))

from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_scripts import preflight_force_cumul as pf  # noqa: E402


class TestEvaluate(unittest.TestCase):
    """Pure logic of the bypass cumul decision."""

    def test_no_bypass(self):
        r = pf.evaluate(force=False, no_plan_on_warn=False, no_validate=False,
                        allow_force_env=False)
        self.assertEqual(r["bypass_count"], 0)
        self.assertEqual(r["decision"], "PASS")
        self.assertEqual(r["exit_code"], SUCCESS)
        self.assertEqual(r["bypass_active"], [])

    def test_single_force(self):
        r = pf.evaluate(force=True, no_plan_on_warn=False, no_validate=False,
                        allow_force_env=False)
        self.assertEqual(r["bypass_count"], 1)
        self.assertEqual(r["decision"], "WARN")
        self.assertEqual(r["exit_code"], SUCCESS)
        self.assertEqual(r["bypass_active"], ["--force"])

    def test_single_no_validate(self):
        r = pf.evaluate(force=False, no_plan_on_warn=False, no_validate=True,
                        allow_force_env=False)
        self.assertEqual(r["bypass_count"], 1)
        self.assertEqual(r["decision"], "WARN")
        self.assertEqual(r["exit_code"], SUCCESS)

    def test_two_bypasses_rejected_when_env_false(self):
        r = pf.evaluate(force=True, no_plan_on_warn=True, no_validate=False,
                        allow_force_env=False)
        self.assertEqual(r["bypass_count"], 2)
        self.assertEqual(r["decision"], "REJECTED")
        self.assertEqual(r["exit_code"], FAIL_FAST)

    def test_three_bypasses_rejected_when_env_false(self):
        r = pf.evaluate(force=True, no_plan_on_warn=True, no_validate=True,
                        allow_force_env=False)
        self.assertEqual(r["bypass_count"], 3)
        self.assertEqual(r["decision"], "REJECTED")
        self.assertEqual(r["exit_code"], FAIL_FAST)
        self.assertEqual(set(r["bypass_active"]),
                         {"--force", "--no-plan-on-warn", "--no-validate"})

    def test_two_bypasses_allowed_when_env_true(self):
        r = pf.evaluate(force=True, no_plan_on_warn=True, no_validate=False,
                        allow_force_env=True)
        self.assertEqual(r["bypass_count"], 2)
        self.assertEqual(r["decision"], "WARN")
        self.assertEqual(r["exit_code"], SUCCESS)
        self.assertTrue(r["sdd_allow_force_env"])


class TestEnvVarParsing(unittest.TestCase):
    """Truthy/falsy detection of SDD_ALLOW_FORCE."""

    def setUp(self):
        self._saved = os.environ.pop("SDD_ALLOW_FORCE", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["SDD_ALLOW_FORCE"] = self._saved
        else:
            os.environ.pop("SDD_ALLOW_FORCE", None)

    def test_absent(self):
        self.assertFalse(pf._env_allow_force())

    def test_explicit_1(self):
        os.environ["SDD_ALLOW_FORCE"] = "1"
        self.assertTrue(pf._env_allow_force())

    def test_explicit_true(self):
        os.environ["SDD_ALLOW_FORCE"] = "true"
        self.assertTrue(pf._env_allow_force())

    def test_explicit_TRUE_uppercase(self):
        os.environ["SDD_ALLOW_FORCE"] = "TRUE"
        self.assertTrue(pf._env_allow_force())

    def test_explicit_yes(self):
        os.environ["SDD_ALLOW_FORCE"] = "yes"
        self.assertTrue(pf._env_allow_force())

    def test_explicit_0_is_false(self):
        os.environ["SDD_ALLOW_FORCE"] = "0"
        self.assertFalse(pf._env_allow_force())

    def test_explicit_false_string(self):
        os.environ["SDD_ALLOW_FORCE"] = "false"
        self.assertFalse(pf._env_allow_force())

    def test_garbage_value_is_false(self):
        os.environ["SDD_ALLOW_FORCE"] = "maybe"
        self.assertFalse(pf._env_allow_force())


class TestCliMain(unittest.TestCase):
    """End-to-end CLI invocations."""

    def setUp(self):
        self._saved = os.environ.pop("SDD_ALLOW_FORCE", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["SDD_ALLOW_FORCE"] = self._saved
        else:
            os.environ.pop("SDD_ALLOW_FORCE", None)

    def test_no_flags_exits_zero(self):
        self.assertEqual(pf.main([]), SUCCESS)

    def test_single_force_exits_zero(self):
        self.assertEqual(pf.main(["--force"]), SUCCESS)

    def test_cumul_2_rejected(self):
        # Capture stderr to keep test output clean
        with redirect_stderr(io.StringIO()) as buf:
            rc = pf.main(["--force", "--no-plan-on-warn"])
        self.assertEqual(rc, FAIL_FAST)
        # Verify the canonical ERROR block was emitted on stderr
        stderr = buf.getvalue()
        self.assertIn("[FORCE_CUMUL_REJECTED]", stderr)
        self.assertIn("--force", stderr)
        self.assertIn("--no-plan-on-warn", stderr)

    def test_cumul_3_rejected(self):
        with redirect_stderr(io.StringIO()):
            rc = pf.main(["--force", "--no-plan-on-warn", "--no-validate"])
        self.assertEqual(rc, FAIL_FAST)

    def test_cumul_allowed_via_env(self):
        os.environ["SDD_ALLOW_FORCE"] = "1"
        rc = pf.main(["--force", "--no-plan-on-warn"])
        self.assertEqual(rc, SUCCESS)

    def test_json_output_carries_decision(self):
        with redirect_stdout(io.StringIO()) as buf, redirect_stderr(io.StringIO()):
            pf.main(["--force", "--no-plan-on-warn", "--json"])
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["decision"], "REJECTED")
        self.assertEqual(payload["bypass_count"], 2)
        self.assertEqual(payload["exit_code"], FAIL_FAST)
        self.assertEqual(set(payload["bypass_active"]),
                         {"--force", "--no-plan-on-warn"})


if __name__ == "__main__":
    unittest.main()
