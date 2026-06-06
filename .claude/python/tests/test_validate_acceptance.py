"""Unit tests for sdd_scripts/validate_acceptance.py + sdd_hooks/validate_acceptance_gate.py.

Coverage:
- Script: mode off/warn/strict, no src dir, no projects, bypass envvar
- Hook: missing report → ALLOW, pass verdict → ALLOW, fail strict → DENY,
  fail warn → ALLOW, corrupted JSON → ALLOW (graceful)
- Round-trip: script writes JSON → hook reads it correctly.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))

from sdd_scripts import validate_acceptance as va  # noqa: E402
from sdd_hooks import validate_acceptance_gate as vag  # noqa: E402


class TestValidateAcceptanceScript(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        (self.root / "workspace" / "input" / "stack").mkdir(parents=True)
        (self.root / "workspace" / "output" / "src").mkdir(parents=True)
        self.env_patch = patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.tmp.cleanup()

    def _write_stack(self, mode: str = "strict"):
        (self.root / "workspace" / "input" / "stack" / "stack.md").write_text(
            f"# Stack\n\n## Project Config\nAcceptanceGate: {mode}\n", encoding="utf-8"
        )

    def _report_path(self) -> Path:
        return self.root / "workspace" / "output" / ".sys" / ".acceptance" / "acceptance.json"

    def test_no_stack_md_skipped(self):
        # No stack.md → mode=off → skipped, exit 0
        with patch.object(sys, "argv", ["validate_acceptance.py"]):
            rc = va.main()
        self.assertEqual(rc, 0)
        report = json.loads(self._report_path().read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "skipped")

    def test_mode_off_skipped(self):
        self._write_stack("off")
        with patch.object(sys, "argv", ["validate_acceptance.py"]):
            rc = va.main()
        self.assertEqual(rc, 0)
        report = json.loads(self._report_path().read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "skipped")
        self.assertEqual(report["mode"], "off")

    def test_no_projects_skipped(self):
        self._write_stack("strict")
        with patch.object(sys, "argv", ["validate_acceptance.py"]):
            rc = va.main()
        self.assertEqual(rc, 0)
        report = json.loads(self._report_path().read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "skipped")

    def test_bypass_envvar(self):
        self._write_stack("strict")
        # Make a dummy node project that would fail otherwise
        proj = self.root / "workspace" / "output" / "src" / "demo"
        proj.mkdir()
        (proj / "package.json").write_text('{"scripts":{}}', encoding="utf-8")  # missing test
        with patch.dict(os.environ, {"SDD_ALLOW_ACCEPTANCE_BYPASS": "1"}):
            with patch.object(sys, "argv", ["validate_acceptance.py"]):
                rc = va.main()
        self.assertEqual(rc, 0)
        report = json.loads(self._report_path().read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "bypass")

    def test_project_detection(self):
        proj_node = self.root / "workspace" / "output" / "src" / "MyApp"
        proj_node.mkdir()
        (proj_node / "package.json").write_text('{"scripts":{"test":"jest"}}', encoding="utf-8")
        self.assertEqual(va._detect_project_type(proj_node), "node")

        proj_py = self.root / "workspace" / "output" / "src" / "PyApp"
        proj_py.mkdir()
        (proj_py / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
        self.assertEqual(va._detect_project_type(proj_py), "python")

        proj_unknown = self.root / "workspace" / "output" / "src" / "Mystery"
        proj_unknown.mkdir()
        self.assertIsNone(va._detect_project_type(proj_unknown))


class TestAcceptanceGateHook(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        self.report_dir = self.root / "workspace" / "output" / ".sys" / ".acceptance"
        self.report_dir.mkdir(parents=True)
        self.env_patch = patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.tmp.cleanup()

    def _write_report(self, payload: dict):
        (self.report_dir / "acceptance.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_missing_report_allows(self):
        rc = vag.main()
        self.assertEqual(rc, 0)  # HOOK_ALLOW

    def test_pass_verdict_allows(self):
        self._write_report({"verdict": "pass", "mode": "strict", "failures": []})
        rc = vag.main()
        self.assertEqual(rc, 0)

    def test_skipped_verdict_allows(self):
        self._write_report({"verdict": "skipped", "mode": "off", "failures": []})
        rc = vag.main()
        self.assertEqual(rc, 0)

    def test_bypass_verdict_allows(self):
        self._write_report({"verdict": "bypass", "mode": "bypass", "failures": []})
        rc = vag.main()
        self.assertEqual(rc, 0)

    def test_warn_verdict_allows(self):
        self._write_report({
            "verdict": "warn", "mode": "warn",
            "failures": [{"project": "demo", "check": "test", "message": "1 fail"}],
        })
        rc = vag.main()
        self.assertEqual(rc, 0)

    def test_fail_strict_denies(self):
        self._write_report({
            "verdict": "fail", "mode": "strict",
            "failures": [{"project": "demo", "check": "test", "message": "1 fail"}],
        })
        rc = vag.main()
        self.assertEqual(rc, 2)  # HOOK_DENY

    def test_corrupted_json_allows_with_warn(self):
        (self.report_dir / "acceptance.json").write_text("{broken json", encoding="utf-8")
        rc = vag.main()
        self.assertEqual(rc, 0)  # graceful

    def test_envvar_bypass_allows(self):
        self._write_report({
            "verdict": "fail", "mode": "strict",
            "failures": [{"project": "demo", "check": "test", "message": "1 fail"}],
        })
        with patch.dict(os.environ, {"SDD_ALLOW_ACCEPTANCE_BYPASS": "1"}):
            rc = vag.main()
        self.assertEqual(rc, 0)

    def test_unknown_verdict_allows(self):
        self._write_report({"verdict": "weird", "mode": "strict"})
        rc = vag.main()
        self.assertEqual(rc, 0)


class TestProjectsScopingFlag(unittest.TestCase):
    """Security audit 2026-06-06 (LOT 8.7) : --projects scoping pour éviter
    de scanner tous les projets en CI."""

    def test_parse_args_accepts_projects_flag(self):
        args = va._parse_args(["--projects", "ProjA,ProjB"])
        self.assertEqual(args.projects, "ProjA,ProjB")

    def test_parse_args_default_timeout_120(self):
        args = va._parse_args([])
        self.assertEqual(args.timeout, 120,
                         "DEFAULT_TIMEOUT must be 120s (was 300s pre-audit 2026-06-06)")

    def test_parse_args_custom_timeout(self):
        args = va._parse_args(["--timeout", "60"])
        self.assertEqual(args.timeout, 60)

    def test_default_max_projects_constant(self):
        self.assertEqual(va.DEFAULT_MAX_PROJECTS, 8,
                         "Cap to 8 projects max — symptôme de mauvais scoping au-delà.")


if __name__ == "__main__":
    unittest.main()
