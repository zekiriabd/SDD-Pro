"""Smoke tests for validate_semantic.py (audit M4 v7.0.0-alpha 2026-06-05).

Coverage scope: importability, CLI surface, basic strictness modes.
Not exhaustive — protects against breakage during refactoring.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "validate_semantic.py"

sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))


class TestImport(unittest.TestCase):
    def test_module_imports(self) -> None:
        from sdd_scripts import validate_semantic  # noqa: F401
        self.assertTrue(hasattr(validate_semantic, "main"))


class TestCli(unittest.TestCase):
    def test_help_succeeds(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--feat-number", result.stdout)

    def test_invalid_strictness_rejected(self) -> None:
        """argparse choices guard against typos."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--feat-number", "1", "--strictness", "bogus"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_missing_feat_fails_gracefully(self) -> None:
        """Non-existent FEAT → no Python traceback on stderr (graceful exit)."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            env = os.environ.copy()
            env["SDD_REPO_ROOT"] = td
            Path(td, ".claude").mkdir()
            Path(td, "workspace", "input", "feats").mkdir(parents=True)
            result = subprocess.run(
                [sys.executable, str(SCRIPT),
                 "--feat-number", "9999", "--json"],
                capture_output=True, text=True, timeout=15, env=env,
            )
            # Exit code policy is script-specific (validate_semantic returns 0
            # for "FEAT absente" with a warning verdict — see source). What
            # matters here is no Python crash / traceback exposed.
            self.assertNotIn("Traceback (most recent call last)", result.stderr)


if __name__ == "__main__":
    unittest.main()
