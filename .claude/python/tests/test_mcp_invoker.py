"""Unit tests for sdd_mcp.claude_invoker — subprocess abstraction.

Uses SDD_MCP_FAKE_CLAUDE=1 so tests don't depend on the real `claude` CLI
being installed. The fake mode reshapes argv to a Python one-liner that
prints a deterministic marker string.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
_PY_ROOT = REPO_ROOT / ".claude" / "python"
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_mcp import claude_invoker  # noqa: E402


class TestResolveClaudeBin(unittest.TestCase):
    def test_explicit_env_var_wins(self) -> None:
        with mock.patch.dict(os.environ, {claude_invoker.CLAUDE_BIN_ENV: "/custom/claude"}):
            self.assertEqual(claude_invoker.resolve_claude_bin(), "/custom/claude")

    def test_fake_mode_returns_python_interpreter(self) -> None:
        with mock.patch.dict(
            os.environ,
            {claude_invoker.FAKE_FLAG_ENV: "1"},
            clear=False,
        ):
            os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
            os.environ.pop(claude_invoker.FAKE_BIN_ENV, None)
            self.assertEqual(claude_invoker.resolve_claude_bin(), sys.executable)

    def test_fake_bin_override(self) -> None:
        with mock.patch.dict(
            os.environ,
            {claude_invoker.FAKE_FLAG_ENV: "1", claude_invoker.FAKE_BIN_ENV: "/fake/path"},
            clear=False,
        ):
            os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
            self.assertEqual(claude_invoker.resolve_claude_bin(), "/fake/path")

    def test_no_claude_no_fake_returns_none_or_path(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in (
                claude_invoker.CLAUDE_BIN_ENV,
                claude_invoker.FAKE_FLAG_ENV,
                claude_invoker.FAKE_BIN_ENV,
            ):
                os.environ.pop(key, None)
            with mock.patch.object(claude_invoker.shutil, "which", return_value=None):
                self.assertIsNone(claude_invoker.resolve_claude_bin())


class TestInvokeSync(unittest.TestCase):
    def test_fake_mode_returns_marker(self) -> None:
        with mock.patch.dict(os.environ, {claude_invoker.FAKE_FLAG_ENV: "1"}, clear=False):
            os.environ.pop(claude_invoker.FAKE_BIN_ENV, None)
            os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
            result = claude_invoker.invoke_sync("/feat-generate Auth")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("FAKE CLAUDE OK: /feat-generate Auth", result.stdout)
        self.assertFalse(result.timed_out)
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_claude_not_found_raises(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in (
                claude_invoker.CLAUDE_BIN_ENV,
                claude_invoker.FAKE_FLAG_ENV,
                claude_invoker.FAKE_BIN_ENV,
            ):
                os.environ.pop(key, None)
            with mock.patch.object(claude_invoker.shutil, "which", return_value=None):
                with self.assertRaises(FileNotFoundError):
                    claude_invoker.invoke_sync("/sdd-full 1")


class TestSpawnAsync(unittest.TestCase):
    def test_spawn_writes_stdout_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.log"
            err = Path(tmp) / "err.log"
            with mock.patch.dict(os.environ, {claude_invoker.FAKE_FLAG_ENV: "1"}, clear=False):
                os.environ.pop(claude_invoker.FAKE_BIN_ENV, None)
                os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
                proc = claude_invoker.spawn_async("/sdd-full 1", str(out), str(err))
                proc.wait(timeout=10)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("FAKE CLAUDE OK: /sdd-full 1", out.read_text(encoding="utf-8"))


class TestClaudeAvailable(unittest.TestCase):
    def test_available_when_fake(self) -> None:
        with mock.patch.dict(os.environ, {claude_invoker.FAKE_FLAG_ENV: "1"}, clear=False):
            os.environ.pop(claude_invoker.FAKE_BIN_ENV, None)
            os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
            self.assertTrue(claude_invoker.claude_available())

    def test_not_available_without_claude(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in (
                claude_invoker.CLAUDE_BIN_ENV,
                claude_invoker.FAKE_FLAG_ENV,
                claude_invoker.FAKE_BIN_ENV,
            ):
                os.environ.pop(key, None)
            with mock.patch.object(claude_invoker.shutil, "which", return_value=None):
                self.assertFalse(claude_invoker.claude_available())


if __name__ == "__main__":
    unittest.main()
