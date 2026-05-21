"""Integration tests for sdd_mcp.tools.pipeline (Phase 2 LLM-driven tools).

These tests run with SDD_MCP_FAKE_CLAUDE=1 so they never invoke a real
LLM. The fake claude binary is the current Python interpreter producing
a deterministic marker string + exit code 0.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
_PY_ROOT = REPO_ROOT / ".claude" / "python"
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_mcp import claude_invoker, job_store  # noqa: E402
from sdd_mcp.tools import pipeline  # noqa: E402


def _make_fake_repo(root: Path) -> None:
    """Scaffold a tmp dir as a valid SDD_Pro repo root.

    v7.0.1 fix : `_looks_like_repo_root()` in sdd_lib.paths now requires
    `.claude/agents/` + `.claude/commands/` + `workspace/` (strict check,
    post-mortem `.claude/.claude/` archive false positive). Creating only
    `.claude/` made repo_root() fail the strict check and walk up to the
    real repo → console.db pollution. Tests now create the full layout.
    """
    (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
    (root / "workspace").mkdir(parents=True, exist_ok=True)


def _fake_env() -> dict[str, str]:
    return {claude_invoker.FAKE_FLAG_ENV: "1"}


class TestClaudeCheck(unittest.TestCase):
    def test_available_when_faked(self) -> None:
        with mock.patch.dict(os.environ, _fake_env(), clear=False):
            os.environ.pop(claude_invoker.FAKE_BIN_ENV, None)
            os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
            result = pipeline._handle_claude_check({})
        self.assertFalse(result["isError"])
        payload = result["_meta"]["payload"]
        self.assertTrue(payload["available"])

    def test_unavailable_when_not_installed(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in (
                claude_invoker.CLAUDE_BIN_ENV,
                claude_invoker.FAKE_FLAG_ENV,
                claude_invoker.FAKE_BIN_ENV,
            ):
                os.environ.pop(key, None)
            with mock.patch.object(claude_invoker.shutil, "which", return_value=None):
                result = pipeline._handle_claude_check({})
        self.assertTrue(result["isError"])
        self.assertEqual(result["_meta"]["exitCode"], 127)


class TestFeatGenerate(unittest.TestCase):
    def test_invalid_name_rejected(self) -> None:
        with mock.patch.dict(os.environ, _fake_env(), clear=False):
            result = pipeline._handle_feat_generate({"name": "lowercase-bad"})
        self.assertTrue(result["isError"])

    def test_valid_name_invokes_fake(self) -> None:
        with mock.patch.dict(os.environ, _fake_env(), clear=False):
            os.environ.pop(claude_invoker.FAKE_BIN_ENV, None)
            os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
            result = pipeline._handle_feat_generate({"name": "Auth"})
        self.assertFalse(result["isError"])
        self.assertIn("FAKE CLAUDE OK: /feat-generate Auth", result["content"][0]["text"])

    def test_no_claude_returns_127(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in (
                claude_invoker.CLAUDE_BIN_ENV,
                claude_invoker.FAKE_FLAG_ENV,
                claude_invoker.FAKE_BIN_ENV,
            ):
                os.environ.pop(key, None)
            with mock.patch.object(claude_invoker.shutil, "which", return_value=None):
                result = pipeline._handle_feat_generate({"name": "Auth"})
        self.assertTrue(result["isError"])
        self.assertEqual(result["_meta"]["exitCode"], 127)


class TestUsGenerate(unittest.TestCase):
    def test_calls_with_feat_number(self) -> None:
        with mock.patch.dict(os.environ, _fake_env(), clear=False):
            os.environ.pop(claude_invoker.FAKE_BIN_ENV, None)
            os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
            result = pipeline._handle_us_generate({"feat_number": 42})
        self.assertFalse(result["isError"])
        self.assertIn("/us-generate 42", result["content"][0]["text"])


class TestSddFullCommandBuilder(unittest.TestCase):
    def test_minimal_command(self) -> None:
        cmd = pipeline._build_sdd_full_command({"feat_number": 1})
        self.assertEqual(cmd, "/sdd-full 1")

    def test_all_flags(self) -> None:
        cmd = pipeline._build_sdd_full_command({
            "feat_number": 3,
            "plan_only": True,
            "force": True,
            "rebuild_arch": True,
            "manual_gates": "us,readiness",
        })
        self.assertIn("/sdd-full 3", cmd)
        self.assertIn("--plan", cmd)
        self.assertIn("--force", cmd)
        self.assertIn("--rebuild-arch", cmd)
        self.assertIn("--manual-gates=us,readiness", cmd)


class TestSddFullAsync(unittest.TestCase):
    def test_spawn_returns_job_id_and_persists_state(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            with (
                mock.patch.dict(os.environ, _fake_env(), clear=False),
                mock.patch.object(Path, "cwd", return_value=root),
            ):
                os.environ.pop(claude_invoker.FAKE_BIN_ENV, None)
                os.environ.pop(claude_invoker.CLAUDE_BIN_ENV, None)
                result = pipeline._handle_sdd_full({"feat_number": 1})
            self.assertFalse(result["isError"])
            payload = result["_meta"]["payload"]
            job_id = payload["job_id"]
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["command"], "/sdd-full 1")

            # Wait for the fake process to finish — short python one-liner.
            for _ in range(50):
                state = job_store.read_state(job_id, root)
                if state and not job_store._is_pid_alive(state.pid or -1):
                    break
                time.sleep(0.05)

            # Status tool should now detect completion (terminal state).
            with mock.patch.object(Path, "cwd", return_value=root):
                status_result = pipeline._handle_get_sdd_full_status({"job_id": job_id})
            terminal = status_result["_meta"]["payload"]["status"]
            self.assertIn(terminal, ("success", "failed", "running"))

    def test_status_unknown_job(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            with mock.patch.object(Path, "cwd", return_value=root):
                result = pipeline._handle_get_sdd_full_status({"job_id": "nope"})
            self.assertTrue(result["isError"])
            self.assertEqual(result["_meta"]["exitCode"], 2)

    def test_no_claude_returns_127(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            with (
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(Path, "cwd", return_value=root),
            ):
                for key in (
                    claude_invoker.CLAUDE_BIN_ENV,
                    claude_invoker.FAKE_FLAG_ENV,
                    claude_invoker.FAKE_BIN_ENV,
                ):
                    os.environ.pop(key, None)
                with mock.patch.object(claude_invoker.shutil, "which", return_value=None):
                    result = pipeline._handle_sdd_full({"feat_number": 1})
        self.assertTrue(result["isError"])
        self.assertEqual(result["_meta"]["exitCode"], 127)


class TestListJobs(unittest.TestCase):
    def test_empty_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            with mock.patch.object(Path, "cwd", return_value=root):
                result = pipeline._handle_list_sdd_full_jobs({})
            self.assertFalse(result["isError"])
            self.assertEqual(result["_meta"]["payload"]["total"], 0)

    def test_filter_by_status(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            s1 = job_store.JobState(
                job_id="aaa", command="/sdd-full 1", feat_number=1, status="success",
            )
            s2 = job_store.JobState(
                job_id="bbb", command="/sdd-full 2", feat_number=2, status="failed",
            )
            job_store.write_state(s1, root)
            job_store.write_state(s2, root)
            with mock.patch.object(Path, "cwd", return_value=root):
                result = pipeline._handle_list_sdd_full_jobs({"status_filter": "success"})
            payload = result["_meta"]["payload"]
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["jobs"][0]["job_id"], "aaa")


class TestCancel(unittest.TestCase):
    def test_cancel_unknown_returns_error(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            with mock.patch.object(Path, "cwd", return_value=root):
                result = pipeline._handle_cancel_sdd_full({"job_id": "ghost"})
            self.assertTrue(result["isError"])

    def test_cancel_terminal_is_noop(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            state = job_store.JobState(
                job_id="done1", command="/sdd-full 1", feat_number=1, status="success",
            )
            job_store.write_state(state, root)
            with mock.patch.object(Path, "cwd", return_value=root):
                result = pipeline._handle_cancel_sdd_full({"job_id": "done1"})
            self.assertFalse(result["isError"])
            payload = result["_meta"]["payload"]
            self.assertTrue(payload.get("noop"))


class TestRegistryWiring(unittest.TestCase):
    def test_default_registry_exposes_14_tools(self) -> None:
        from sdd_mcp.registry import build_default_registry

        names = sorted(t["name"] for t in build_default_registry().list_descriptors())
        expected = sorted([
            # Phase 1
            "sdd_status", "validate_readiness", "feat_validate",
            "set_us_status", "validate_us_deps", "compute_us_complexity",
            "migrate_us_v1_to_v2",
            # Phase 2
            "claude_check", "feat_generate", "us_generate",
            "sdd_full", "get_sdd_full_status", "cancel_sdd_full",
            "list_sdd_full_jobs",
        ])
        self.assertEqual(names, expected)


if __name__ == "__main__":
    unittest.main()
