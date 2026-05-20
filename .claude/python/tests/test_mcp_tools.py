"""Integration tests for sdd_mcp.tools.* — wrap real sdd_scripts/* subprocesses.

These tests verify that each Phase 1 tool produces the MCP-shaped result
envelope and propagates exit codes correctly. We use a fake repo with a
`.claude/` marker and minimal workspace fixtures, so the underlying scripts
detect the right `repo_root()`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
_PY_ROOT = REPO_ROOT / ".claude" / "python"
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))


def _setup_fake_repo(root: Path, *, with_us: bool = False) -> None:
    """Create a minimal `.claude/` + workspace skeleton so repo_root() resolves here."""
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "output" / "us").mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "input" / "feats").mkdir(parents=True, exist_ok=True)
    if with_us:
        # Minimal v2-shaped US for compute/set/validate tests
        us = root / "workspace" / "output" / "us" / "1-1-Connexion.md"
        us.write_text(
            "---\n"
            "us: 1-1-Connexion\n"
            "Status: Draft\n"
            "---\n"
            "\n"
            "# 1-1 Connexion\n"
            "\n"
            "## Covers\n"
            "- SFD-1\n"
            "\n"
            "## Acceptance Criteria\n"
            "- AC-1: l'utilisateur peut se connecter\n"
            "\n"
            "## Dependencies\n"
            "- NONE\n"
            "\n"
            "## Metadata\n"
            "```json\n"
            "{}\n"
            "```\n",
            encoding="utf-8",
        )


def _import_in_cwd(fake_root: Path):
    """Run helper imports with `cwd` patched so repo_root() resolves the fake repo."""
    return mock.patch.object(Path, "cwd", return_value=fake_root)


class TestSubprocessHelper(unittest.TestCase):
    def test_script_path_resolves_existing(self) -> None:
        from sdd_mcp.subprocess_helper import script_path
        p = script_path("sdd_state")
        self.assertTrue(p.is_file())
        self.assertEqual(p.name, "sdd_state.py")

    def test_script_path_missing_raises(self) -> None:
        from sdd_mcp.subprocess_helper import script_path
        with self.assertRaises(FileNotFoundError):
            script_path("does_not_exist_xyz")

    def test_run_script_captures_exit_code(self) -> None:
        from sdd_mcp.subprocess_helper import run_script
        result = run_script("sdd_state", ["--help"])
        self.assertIn("content", result)
        self.assertIn("isError", result)
        self.assertIn("_meta", result)
        self.assertIn("exitCode", result["_meta"])


class TestStatusTools(unittest.TestCase):
    def test_validate_readiness_no_feat_returns_error(self) -> None:
        from sdd_mcp.tools.status import _handle_validate_readiness  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _setup_fake_repo(root)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                result = _handle_validate_readiness({"feat_number": 999})
                self.assertTrue(result["isError"])
                self.assertNotEqual(result["_meta"]["exitCode"], 0)
            finally:
                os.chdir(cwd)

    def test_sdd_status_list_runs_empty(self) -> None:
        from sdd_mcp.tools.status import _handle_sdd_status  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _setup_fake_repo(root)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                result = _handle_sdd_status({})
                # list-runs on an empty fake repo should not crash; it returns
                # either an empty list or "no runs" message.
                self.assertIn("content", result)
                self.assertEqual(result["_meta"]["exitCode"], 0)
            finally:
                os.chdir(cwd)


class TestUsOpsTools(unittest.TestCase):
    def test_set_us_status_requires_us(self) -> None:
        from sdd_mcp.tools.us_ops import _handle_set_us_status  # type: ignore[attr-defined]
        result = _handle_set_us_status({})
        self.assertTrue(result["isError"])
        self.assertIn("us", result["content"][0]["text"])

    def test_set_us_status_get_on_real_us(self) -> None:
        from sdd_mcp.tools.us_ops import _handle_set_us_status  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _setup_fake_repo(root, with_us=True)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                result = _handle_set_us_status({"us": "1-1", "get": True})
                self.assertEqual(result["_meta"]["exitCode"], 0)
                self.assertIn("Draft", result["content"][0]["text"])
            finally:
                os.chdir(cwd)

    def test_validate_us_deps_requires_one_selector(self) -> None:
        from sdd_mcp.tools.us_ops import _handle_validate_us_deps  # type: ignore[attr-defined]
        result = _handle_validate_us_deps({})
        self.assertTrue(result["isError"])
        result = _handle_validate_us_deps({"feat": 1, "all": True})
        self.assertTrue(result["isError"])

    def test_validate_us_deps_on_fake_feat(self) -> None:
        from sdd_mcp.tools.us_ops import _handle_validate_us_deps  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _setup_fake_repo(root, with_us=True)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                result = _handle_validate_us_deps({"feat": 1})
                # Valid graph with one US (NONE deps) -> exit 0
                self.assertEqual(result["_meta"]["exitCode"], 0)
                self.assertIsNotNone(result["_meta"]["json"])
            finally:
                os.chdir(cwd)

    def test_compute_us_complexity_requires_us(self) -> None:
        from sdd_mcp.tools.us_ops import _handle_compute_us_complexity  # type: ignore[attr-defined]
        with self.assertRaises(KeyError):
            _handle_compute_us_complexity({})

    def test_compute_us_complexity_on_real_us(self) -> None:
        from sdd_mcp.tools.us_ops import _handle_compute_us_complexity  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _setup_fake_repo(root, with_us=True)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                result = _handle_compute_us_complexity({"us": "1-1"})
                self.assertEqual(result["_meta"]["exitCode"], 0)
                parsed = result["_meta"]["json"]
                self.assertIsNotNone(parsed)
                self.assertIn("complexity", parsed)
            finally:
                os.chdir(cwd)

    def test_migrate_us_v1_to_v2_requires_one_selector(self) -> None:
        from sdd_mcp.tools.us_ops import _handle_migrate_us_v1_to_v2  # type: ignore[attr-defined]
        # Neither us nor all
        result = _handle_migrate_us_v1_to_v2({})
        self.assertTrue(result["isError"])
        # Both us and all
        result = _handle_migrate_us_v1_to_v2({"us": "1-1", "all": True})
        self.assertTrue(result["isError"])

    def test_migrate_us_v1_to_v2_dry_run(self) -> None:
        from sdd_mcp.tools.us_ops import _handle_migrate_us_v1_to_v2  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _setup_fake_repo(root, with_us=True)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                result = _handle_migrate_us_v1_to_v2({"all": True, "dry_run": True})
                self.assertEqual(result["_meta"]["exitCode"], 0)
            finally:
                os.chdir(cwd)


class TestRegistryWiring(unittest.TestCase):
    def test_phase_1_tools_present(self) -> None:
        """Phase 1 (read-only) — must always be present in the default registry."""
        from sdd_mcp.registry import build_default_registry
        reg = build_default_registry()
        names = {t["name"] for t in reg.list_descriptors()}
        phase_1 = {
            "sdd_status",
            "validate_readiness",
            "feat_validate",
            "set_us_status",
            "validate_us_deps",
            "compute_us_complexity",
            "migrate_us_v1_to_v2",
        }
        self.assertTrue(phase_1.issubset(names), f"missing: {phase_1 - names}")

    def test_all_tools_have_input_schema(self) -> None:
        from sdd_mcp.registry import build_default_registry
        for descriptor in build_default_registry().list_descriptors():
            self.assertEqual(descriptor["inputSchema"]["type"], "object", descriptor["name"])
            self.assertIn("description", descriptor)


if __name__ == "__main__":
    unittest.main()
