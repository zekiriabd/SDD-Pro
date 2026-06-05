"""Smoke tests for validate_stack_combo.py (audit M4 v7.0.0-alpha 2026-06-05).

Coverage scope: importability, CLI surface, --quiet + --json behavior.
Not exhaustive — protects against breakage during refactoring.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "validate_stack_combo.py"

sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))


class TestImport(unittest.TestCase):
    def test_module_imports(self) -> None:
        from sdd_scripts import validate_stack_combo  # noqa: F401
        self.assertTrue(hasattr(validate_stack_combo, "main"))


class TestCli(unittest.TestCase):
    def test_help_succeeds(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--json", result.stdout)

    def test_json_output_is_parseable(self) -> None:
        """--json must emit valid JSON regardless of verdict."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--json", "--quiet"],
            capture_output=True, text=True, timeout=20,
            cwd=str(REPO_ROOT),
        )
        # Exit code may be 0 or non-zero depending on workspace state ;
        # what matters here is that stdout is JSON-parseable.
        if result.stdout.strip():
            try:
                json.loads(result.stdout)
            except json.JSONDecodeError as e:
                self.fail(f"--json output not parseable: {e}\nstdout={result.stdout!r}")

    def test_quiet_suppresses_human_output(self) -> None:
        """--quiet → stdout is either empty or pure JSON."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--quiet"],
            capture_output=True, text=True, timeout=20,
            cwd=str(REPO_ROOT),
        )
        # Without --json, --quiet should produce minimal stdout
        # (verdict line at most). No multi-line human-friendly output.
        if result.stdout:
            self.assertLessEqual(
                result.stdout.count("\n"), 2,
                f"--quiet emitted multi-line output: {result.stdout!r}",
            )


if __name__ == "__main__":
    unittest.main()
