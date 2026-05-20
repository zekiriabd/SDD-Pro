"""Unit tests for compute_plan_metadata.py — v2 frontmatter helper.

Coverage:
- YAML fragment output (default mode)
- JSON output (--json)
- us-hash deterministic SHA-256
- claude-md-hash optional inclusion
- capabilities-triggered passthrough
- Error handling (missing US file → exit 1, missing CLAUDE.md → exit 2)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "compute_plan_metadata.py"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TestComputePlanMetadata(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True,
        )

    def test_yaml_output_minimal(self) -> None:
        """Minimal invocation (us only) emits required YAML lines."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            us = Path(tmp) / "us.md"
            us.write_text("# US 1-2-Login\n## ACs\n- AC-1: foo\n", encoding="utf-8")
            result = self._run("--us-path", str(us))
            self.assertEqual(result.returncode, 0)
            output = result.stdout.strip().splitlines()
            self.assertIn("plan-schema-version: 2", output)
            self.assertIn("strict-ready: true", output)
            # Find us-hash line
            us_hash_lines = [l for l in output if l.startswith("us-hash:")]
            self.assertEqual(len(us_hash_lines), 1)
            expected = _sha256("# US 1-2-Login\n## ACs\n- AC-1: foo\n")
            self.assertIn(expected, us_hash_lines[0])

    def test_yaml_output_with_claude_md_and_capabilities(self) -> None:
        """Full invocation emits all v2 fields."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            us = Path(tmp) / "us.md"
            cm = Path(tmp) / "CLAUDE.md"
            us_content = "US content\n"
            cm_content = "CLAUDE.md content\n"
            us.write_text(us_content, encoding="utf-8")
            cm.write_text(cm_content, encoding="utf-8")
            result = self._run(
                "--us-path", str(us),
                "--claude-md-path", str(cm),
                "--capabilities", "auth-azure-ad,email,pdf",
            )
            self.assertEqual(result.returncode, 0)
            output = result.stdout
            self.assertIn("plan-schema-version: 2", output)
            self.assertIn(f"us-hash: sha256:{_sha256(us_content)}", output)
            self.assertIn(f"claude-md-hash: sha256:{_sha256(cm_content)}", output)
            self.assertIn("capabilities-triggered: auth-azure-ad,email,pdf", output)
            self.assertIn("strict-ready: true", output)

    def test_json_output_structure(self) -> None:
        """--json emits structured payload."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            us = Path(tmp) / "us.md"
            us_content = "US content\n"
            us.write_text(us_content, encoding="utf-8")
            result = self._run("--us-path", str(us), "--json")
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout.strip())
            self.assertEqual(payload["plan_schema_version"], 2)
            self.assertTrue(payload["strict_ready"])
            self.assertEqual(payload["us_hash"], f"sha256:{_sha256(us_content)}")
            self.assertIsNone(payload["claude_md_hash"])
            self.assertEqual(payload["capabilities_triggered"], [])
            self.assertIn("generated_at", payload)
            # ISO-8601 timestamp ends with Z
            self.assertTrue(payload["generated_at"].endswith("Z"))

    def test_capabilities_empty_string_passthrough(self) -> None:
        """Empty --capabilities does not emit capabilities-triggered line."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            us = Path(tmp) / "us.md"
            us.write_text("US\n", encoding="utf-8")
            result = self._run("--us-path", str(us), "--capabilities", "")
            self.assertEqual(result.returncode, 0)
            self.assertNotIn("capabilities-triggered:", result.stdout)

    def test_missing_us_file_exit_1(self) -> None:
        """Missing US file → exit 1 with PLAN_NOT_FOUND error block."""
        result = self._run("--us-path", "/nonexistent/us.md")
        self.assertEqual(result.returncode, 1)
        self.assertIn("PLAN_NOT_FOUND", result.stderr)
        # ERROR/CAUSE/FIX format
        self.assertIn("ERROR:", result.stderr)
        self.assertIn("CAUSE:", result.stderr)
        self.assertIn("FIX:", result.stderr)

    def test_missing_claude_md_exit_2(self) -> None:
        """Present US but missing CLAUDE.md → exit 2."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            us = Path(tmp) / "us.md"
            us.write_text("US\n", encoding="utf-8")
            result = self._run(
                "--us-path", str(us),
                "--claude-md-path", "/nonexistent/CLAUDE.md",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("PLAN_NOT_FOUND", result.stderr)

    def test_us_hash_matches_validate_plan_expectation(self) -> None:
        """us-hash format matches what validate_plan.py expects (sha256:hex)."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            us = Path(tmp) / "us.md"
            us.write_text("US\n", encoding="utf-8")
            result = self._run("--us-path", str(us), "--json")
            payload = json.loads(result.stdout.strip())
            # Format: "sha256:" + 64 hex chars
            self.assertTrue(payload["us_hash"].startswith("sha256:"))
            self.assertEqual(len(payload["us_hash"]) - len("sha256:"), 64)


if __name__ == "__main__":
    unittest.main()
