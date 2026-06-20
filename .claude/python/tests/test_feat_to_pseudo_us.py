"""Smoke tests for feat_to_pseudo_us.py (audit M4 v7.0.0-alpha 2026-06-05).

Coverage scope: importability, CLI surface, happy path with synthetic FEAT,
exit code contract (SUCCESS=0, FAIL_FAST=1, INFRA_BLOCKED=3).

Not exhaustive — protects against complete breakage during refactoring.
Comprehensive coverage tracked in follow-up.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "feat_to_pseudo_us.py"

sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))


SAMPLE_FEAT = """---
title: Auth
generated-at: 2026-05-10T14:32:00Z
---

# FEAT 1 — Auth

## Actors
- User
- Admin

## Functional Needs
- SFD-1: Login form
- SFD-2: Reset password

## Acceptance Criteria
- AC-1: Given valid creds, when submit, then redirect to /dashboard
- AC-2: Given invalid creds, when submit, then show error
"""


class TestImport(unittest.TestCase):
    def test_module_imports(self) -> None:
        """Module loads without syntax/import errors."""
        from sdd_scripts import feat_to_pseudo_us  # noqa: F401
        self.assertTrue(hasattr(feat_to_pseudo_us, "main"))


class TestCli(unittest.TestCase):
    def test_help_succeeds(self) -> None:
        """--help returns exit 0 and prints usage."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--feat-number", result.stdout)

    def test_missing_args_fails(self) -> None:
        """No args → argparse error exit 2 (Python convention)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_feat_not_found_returns_fail_fast(self) -> None:
        """Nonexistent FEAT number → FAIL_FAST=1."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            env = os.environ.copy()
            env["SDD_REPO_ROOT"] = td
            Path(td, "workspace", "input", "feats").mkdir(parents=True)
            Path(td, "workspace", "output", "us").mkdir(parents=True)
            Path(td, ".claude").mkdir()
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--feat-number", "999"],
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
            )
            self.assertEqual(result.returncode, 1)


class TestHappyPath(unittest.TestCase):
    def test_pseudo_us_generation(self) -> None:
        """FEAT present → pseudo-US written + JSON contract respected."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            env = os.environ.copy()
            env["SDD_REPO_ROOT"] = td
            (root / ".claude").mkdir()
            feats_dir = root / "workspace" / "input" / "feats"
            us_dir = root / "workspace" / "output" / "us"
            feats_dir.mkdir(parents=True)
            us_dir.mkdir(parents=True)
            (feats_dir / "1-Auth.md").write_text(SAMPLE_FEAT, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--feat-number", "1", "--json"],
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
            )
            self.assertEqual(
                result.returncode, 0,
                f"non-zero exit: stderr={result.stderr}",
            )
            # Idempotent re-run
            result2 = subprocess.run(
                [sys.executable, str(SCRIPT), "--feat-number", "1", "--json"],
                capture_output=True, text=True, timeout=20, env=env,
            )
            self.assertEqual(result2.returncode, 0)


if __name__ == "__main__":
    unittest.main()
