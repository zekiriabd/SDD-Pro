"""Tests for sdd_scripts.validate_spec_compliance — schema + verdict consistency."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.validate_spec_compliance import (
    _expected_verdict,
    validate_report,
)


def _make_valid_report(
    *,
    verdict: str = "🟢 GREEN",
    total: int = 2,
    verified: int = 2,
    critical: int = 0,
    serious: int = 0,
    moderate: int = 0,
    minor: int = 0,
    fail_on: str = "serious",
    us_acs: list[dict] | None = None,
) -> dict:
    if us_acs is None:
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "POST /auth/login returns 200",
                "class": "testable_strict",
                "status": "verified",
                "evidence": {
                    "file": "workspace/output/src/Backend/Endpoints/AuthEndpoints.cs",
                    "lines": "42-58",
                    "snippet": "app.MapPost...",
                },
            },
            {
                "ac_id": "AC-2",
                "ac_text": "Session valid 8h",
                "class": "testable_strict",
                "status": "verified",
                "evidence": {
                    "file": "workspace/output/src/Backend/Services/AuthService.cs",
                    "lines": "100-110",
                    "snippet": "TimeSpan.FromHours(8)",
                },
            },
        ]
    return {
        "feat": 1,
        "generated_at": "2026-05-15T18:30:00Z",
        "config": {"mode": "full", "fail_on": fail_on},
        "summary": {
            "verdict": verdict,
            "total_acs": total,
            "verified": verified,
            "issues": {
                "critical": critical,
                "serious": serious,
                "moderate": moderate,
                "minor": minor,
            },
        },
        "us": [{"us_id": "1-1", "acs": us_acs}],
    }


class TestValidateReportGreen(unittest.TestCase):
    def test_all_verified_green(self):
        report = _make_valid_report()
        rc, info = validate_report(report)
        self.assertEqual(rc, 0)
        self.assertEqual(info["verdict"], "🟢 GREEN")
        self.assertEqual(info["verified"], 2)


class TestValidateReportWarn(unittest.TestCase):
    def test_minor_only_warn(self):
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "Vague AC",
                "class": "ambiguous",
                "status": "ambiguous",
            },
        ]
        report = _make_valid_report(
            verdict="🟡 WARN", total=1, verified=0, minor=1, us_acs=us_acs,
        )
        rc, info = validate_report(report)
        self.assertEqual(rc, 1)
        self.assertEqual(info["verdict"], "🟡 WARN")


class TestValidateReportRed(unittest.TestCase):
    def test_serious_with_fail_on_serious_red(self):
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "POST /auth/login returns 200",
                "class": "testable_strict",
                "status": "verified",
                "evidence": {
                    "file": "workspace/output/src/Backend/Endpoints/AuthEndpoints.cs",
                    "lines": "42-58",
                },
            },
            {
                "ac_id": "AC-2",
                "ac_text": "Refresh JWT endpoint",
                "class": "testable_soft",
                "status": "not_verified",
                "severity": "serious",
                "reason": "no /refresh endpoint found",
            },
        ]
        report = _make_valid_report(
            verdict="🔴 RED", total=2, verified=1, serious=1, us_acs=us_acs,
        )
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)
        self.assertEqual(info["verdict"], "🔴 RED")

    def test_critical_always_red_even_low_threshold(self):
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "POST /auth/login returns 200",
                "class": "testable_strict",
                "status": "not_verified",
                "severity": "critical",
                "reason": "endpoint missing",
            },
        ]
        report = _make_valid_report(
            verdict="🔴 RED", total=1, verified=0, critical=1, fail_on="minor",
            us_acs=us_acs,
        )
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)


class TestInconsistencies(unittest.TestCase):
    def test_summary_total_mismatch_with_us(self):
        report = _make_valid_report(total=99)
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)
        self.assertIn("error_block", info)
        self.assertIn("total_acs", info["error_block"])

    def test_summary_verified_mismatch(self):
        report = _make_valid_report(verified=99)
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)
        self.assertIn("verified", info["error_block"])

    def test_verdict_inconsistent_with_issues(self):
        # GREEN claimed but there's a serious issue and fail_on=serious -> should be RED
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "test",
                "class": "testable_strict",
                "status": "not_verified",
                "severity": "serious",
                "reason": "missing",
            },
        ]
        report = _make_valid_report(
            verdict="🟢 GREEN", total=1, verified=0, serious=1, fail_on="serious",
            us_acs=us_acs,
        )
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)
        self.assertIn("incoh", info["error_block"].lower())

    def test_verified_without_evidence_file(self):
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "test",
                "class": "testable_strict",
                "status": "verified",
                "evidence": {"lines": "1-10"},  # missing file
            },
        ]
        report = _make_valid_report(total=1, verified=1, us_acs=us_acs)
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)
        self.assertIn("evidence.file", info["error_block"])

    def test_not_verified_without_severity(self):
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "test",
                "class": "testable_soft",
                "status": "not_verified",
                # missing severity
            },
        ]
        report = _make_valid_report(total=1, verified=0, us_acs=us_acs)
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)
        self.assertIn("severity", info["error_block"])

    def test_invalid_class_value(self):
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "test",
                "class": "garbage",
                "status": "verified",
                "evidence": {"file": "x"},
            },
        ]
        report = _make_valid_report(total=1, verified=1, us_acs=us_acs)
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)

    def test_invalid_status_value(self):
        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "test",
                "class": "testable_strict",
                "status": "garbage",
            },
        ]
        report = _make_valid_report(total=1, verified=1, us_acs=us_acs)
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)

    def test_missing_top_level_key(self):
        report = _make_valid_report()
        del report["summary"]
        rc, info = validate_report(report)
        self.assertEqual(rc, 2)
        self.assertIn("summary", info["error_block"])


class TestExpectedVerdict(unittest.TestCase):
    def test_green_when_no_issues(self):
        issues = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
        self.assertEqual(_expected_verdict(issues, "serious", has_any_issue=False), "🟢 GREEN")

    def test_red_when_critical_with_threshold_critical(self):
        issues = {"critical": 1, "serious": 0, "moderate": 0, "minor": 0}
        self.assertEqual(_expected_verdict(issues, "critical", has_any_issue=True), "🔴 RED")

    def test_warn_when_minor_with_threshold_serious(self):
        issues = {"critical": 0, "serious": 0, "moderate": 0, "minor": 1}
        self.assertEqual(_expected_verdict(issues, "serious", has_any_issue=True), "🟡 WARN")

    def test_red_when_moderate_with_threshold_moderate(self):
        issues = {"critical": 0, "serious": 0, "moderate": 1, "minor": 0}
        self.assertEqual(_expected_verdict(issues, "moderate", has_any_issue=True), "🔴 RED")


class TestCli(unittest.TestCase):
    def test_main_report_path_green(self):
        from sdd_scripts.validate_spec_compliance import main

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "1-spec-compliance.json"
            path.write_text(json.dumps(_make_valid_report()), encoding="utf-8")
            from io import StringIO
            old = sys.stdout
            sys.stdout = StringIO()
            try:
                rc = main(["--report-path", str(path)])
                out = sys.stdout.getvalue()
            finally:
                sys.stdout = old
            self.assertEqual(rc, 0)
            self.assertIn("GREEN", out)

    def test_main_report_path_red_returns_2(self):
        from sdd_scripts.validate_spec_compliance import main

        us_acs = [
            {
                "ac_id": "AC-1",
                "ac_text": "test",
                "class": "testable_strict",
                "status": "not_verified",
                "severity": "critical",
                "reason": "missing",
            },
        ]
        report = _make_valid_report(
            verdict="🔴 RED", total=1, verified=0, critical=1, us_acs=us_acs,
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "1-spec-compliance.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            from io import StringIO
            old_err = sys.stderr
            sys.stderr = StringIO()
            old_out = sys.stdout
            sys.stdout = StringIO()
            try:
                rc = main(["--report-path", str(path), "--fail-on", "critical"])
            finally:
                sys.stdout = old_out
                sys.stderr = old_err
            self.assertEqual(rc, 2)

    def test_main_missing_report_returns_2(self):
        from sdd_scripts.validate_spec_compliance import main

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "absent.json"
            from io import StringIO
            old_err = sys.stderr
            sys.stderr = StringIO()
            try:
                rc = main(["--report-path", str(path)])
            finally:
                sys.stderr = old_err
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
