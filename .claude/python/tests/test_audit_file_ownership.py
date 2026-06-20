"""Tests for sdd_hooks.audit_file_ownership — SubagentStop ownership audit.

Tests both the OWNERSHIP_MATRIX patterns (static, in-process) and the full
hook lifecycle (subprocess, tmp workspace, env-controlled cutoff).

The hook is intentionally non-blocking (always exit 0) — it appends
violations to workspace/output/.sys/.audit/ownership-violations.log and
emits stderr WARN/ERROR depending on $SDD_AUDIT_OWNERSHIP_MODE.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_hooks.audit_file_ownership import OWNERSHIP_MATRIX  # noqa: E402

HOOK = _PY_ROOT / "sdd_hooks" / "audit_file_ownership.py"

CI_VARS = (
    "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
    "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
    "BITBUCKET_BUILD_NUMBER",
)


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    env.pop("SDD_AUDIT_OWNERSHIP_MODE", None)
    env.pop("SDD_DISPATCH_START_TS", None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra:
        env.update(extra)
    return env


def _make_repo(tmp_path: Path) -> Path:
    """Create minimal scaffolding matching sdd_lib.paths._looks_like_repo_root."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / "workspace").mkdir()
    return tmp_path


def _run_hook(payload: dict, repo: Path, env_extra: dict[str, str] | None = None,
              dispatch_start: str | None = None) -> subprocess.CompletedProcess:
    extra = dict(env_extra or {})
    extra["SDD_REPO_ROOT"] = str(repo)
    if dispatch_start:
        extra["SDD_DISPATCH_START_TS"] = dispatch_start
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        env=_clean_env(extra),
        capture_output=True,
        text=True,
        check=False,
    )


def _read_log(repo: Path) -> str:
    log = repo / "workspace" / "output" / ".sys" / ".audit" / "ownership-violations.log"
    return log.read_text(encoding="utf-8") if log.is_file() else ""


class TestOwnershipMatrixPatterns(unittest.TestCase):
    """Verify the in-source OWNERSHIP_MATRIX matches its declared semantics."""

    def test_all_known_agents_have_patterns(self):
        """Each retained agent (v7.0.0) has at least one pattern."""
        expected_agents = {"po", "arch", "dev-backend", "dev-frontend", "qa", "elicitor"}
        for ag in expected_agents:
            self.assertIn(ag, OWNERSHIP_MATRIX, f"Missing matrix entry for {ag}")
            self.assertGreater(len(OWNERSHIP_MATRIX[ag]), 0, f"Empty patterns for {ag}")

    def test_dashboard_removed_v7(self):
        """`dashboard` agent retired v7.0.0 → no matrix entry."""
        self.assertNotIn("dashboard", OWNERSHIP_MATRIX)

    def test_po_writes_us_files(self):
        """po: workspace/output/us/N-M-Name.md is owned."""
        patterns = [re.compile(p) for p in OWNERSHIP_MATRIX["po"]]
        self.assertTrue(any(p.match("workspace/output/us/1-2-Auth.md") for p in patterns))

    def test_po_does_not_own_src(self):
        """po never writes to src/."""
        patterns = [re.compile(p) for p in OWNERSHIP_MATRIX["po"]]
        self.assertFalse(any(p.match("workspace/output/src/MyApp/Pages/Login.tsx") for p in patterns))

    def test_dev_backend_owns_services_endpoints_dtos(self):
        patterns = [re.compile(p) for p in OWNERSHIP_MATRIX["dev-backend"]]
        for path in (
            "workspace/output/src/Backend/Services/AuthService.cs",
            "workspace/output/src/Backend/Endpoints/AuthEndpoints.cs",
            "workspace/output/src/Backend/DTOs/LoginDto.cs",
            "workspace/output/src/Backend/Program.cs",
        ):
            self.assertTrue(
                any(p.match(path) for p in patterns),
                f"dev-backend should own {path}",
            )

    def test_dev_backend_must_not_write_us_or_pages(self):
        """dev-backend never writes US or frontend Pages."""
        patterns = [re.compile(p) for p in OWNERSHIP_MATRIX["dev-backend"]]
        for path in (
            "workspace/output/us/1-2-Auth.md",
            "workspace/output/src/MyApp/Pages/Login.tsx",
        ):
            self.assertFalse(any(p.match(path) for p in patterns))

    def test_dev_frontend_owns_pages_components_layouts(self):
        patterns = [re.compile(p) for p in OWNERSHIP_MATRIX["dev-frontend"]]
        for path in (
            "workspace/output/src/App/Pages/Login.razor",
            "workspace/output/src/App/Components/UserMenu.razor",
            "workspace/output/src/App/Layouts/MainLayout.razor",
        ):
            self.assertTrue(
                any(p.match(path) for p in patterns),
                f"dev-frontend should own {path}",
            )

    def test_qa_owns_test_projects(self):
        patterns = [re.compile(p) for p in OWNERSHIP_MATRIX["qa"]]
        for path in (
            "workspace/output/src/Backend.Tests/AuthServiceTests.cs",
            "workspace/output/qa/feat-1/coverage.json",
            "workspace/output/qa/feat-1/report.md",
        ):
            self.assertTrue(
                any(p.match(path) for p in patterns),
                f"qa should own {path}",
            )

    def test_arch_owns_sln_and_csproj(self):
        patterns = [re.compile(p) for p in OWNERSHIP_MATRIX["arch"]]
        self.assertTrue(any(p.match("workspace/output/src/MyApp.sln") for p in patterns))
        self.assertTrue(
            any(p.match("workspace/output/src/Backend/Backend.csproj") for p in patterns)
        )


class TestHookLifecycle(unittest.TestCase):
    """Subprocess-level tests : tmp workspace + controlled cutoff."""

    def setUp(self):
        # pytest tmp_path isn't directly accessible in unittest — use builtin
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _write_modified_file(self, rel_path: str):
        """Create a file under workspace/, fresh mtime."""
        p = self.repo / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("// generated by test\n", encoding="utf-8")
        # bump mtime to "now" explicitly (defensive against FS quirks)
        now = time.time()
        os.utime(p, (now, now))
        return p

    def test_no_subagent_in_payload_exits_silently(self):
        """Hook is a no-op if subagent_type is absent."""
        self._write_modified_file("workspace/output/src/Backend/Services/X.cs")
        r = _run_hook({}, self.repo, dispatch_start="2020-01-01T00:00:00Z")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(_read_log(self.repo), "")

    def test_unknown_subagent_exits_silently(self):
        """Custom agents not in matrix → silent skip (backward-compat)."""
        self._write_modified_file("workspace/output/src/Backend/Services/X.cs")
        payload = {"tool_input": {"subagent_type": "custom-agent"}}
        r = _run_hook(payload, self.repo, dispatch_start="2020-01-01T00:00:00Z")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(_read_log(self.repo), "")

    def test_dev_backend_writing_in_scope_no_violation(self):
        """dev-backend writing in Services/ → no log line."""
        self._write_modified_file("workspace/output/src/Backend/Services/AuthService.cs")
        payload = {"tool_input": {"subagent_type": "dev-backend"}}
        r = _run_hook(payload, self.repo, dispatch_start="2020-01-01T00:00:00Z")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(_read_log(self.repo), "")

    def test_dev_backend_writing_us_logs_violation(self):
        """dev-backend writing in workspace/output/us/ → violation logged."""
        self._write_modified_file("workspace/output/us/1-2-Auth.md")
        payload = {"tool_input": {"subagent_type": "dev-backend"}}
        r = _run_hook(payload, self.repo, dispatch_start="2020-01-01T00:00:00Z",
                      env_extra={"SDD_AUDIT_OWNERSHIP_MODE": "warn"})
        self.assertEqual(r.returncode, 0, "Hook must never block (always exit 0)")
        log = _read_log(self.repo)
        self.assertIn("[FILE_OWNERSHIP]", log)
        self.assertIn("dev-backend", log)
        self.assertIn("workspace/output/us/1-2-Auth.md", log)

    def test_off_mode_silences_stderr_but_log_still_written(self):
        """Off mode suppresses stderr emission; the audit log keeps tracking."""
        self._write_modified_file("workspace/output/us/1-2-Auth.md")
        payload = {"tool_input": {"subagent_type": "dev-backend"}}
        r = _run_hook(payload, self.repo, dispatch_start="2020-01-01T00:00:00Z",
                      env_extra={"SDD_AUDIT_OWNERSHIP_MODE": "off"})
        self.assertEqual(r.returncode, 0)
        # stderr should not carry the violation message in off mode
        self.assertNotIn("[FILE_OWNERSHIP]", r.stderr)
        # but log file is still written for forensic trace
        self.assertIn("[FILE_OWNERSHIP]", _read_log(self.repo))

    def test_strict_mode_emits_visible_error(self):
        """Strict mode (CI or explicit) → ERROR + FIX hints on stderr."""
        self._write_modified_file("workspace/output/us/1-2-Auth.md")
        payload = {"tool_input": {"subagent_type": "dev-backend"}}
        r = _run_hook(payload, self.repo, dispatch_start="2020-01-01T00:00:00Z",
                      env_extra={"SDD_AUDIT_OWNERSHIP_MODE": "strict"})
        self.assertEqual(r.returncode, 0)  # still non-blocking
        self.assertIn("ERROR audit-file-ownership", r.stderr)
        self.assertIn("[FILE_OWNERSHIP]", r.stderr)
        self.assertIn("FIX", r.stderr)

    def test_cutoff_filters_old_files(self):
        """File with mtime BEFORE cutoff is ignored — only fresh files audited."""
        p = self._write_modified_file("workspace/output/us/1-2-Auth.md")
        # Force the file's mtime to 1970 (well before any cutoff)
        os.utime(p, (1, 1))
        payload = {"tool_input": {"subagent_type": "dev-backend"}}
        # cutoff = today → 1970 file is ignored
        r = _run_hook(payload, self.repo,
                      dispatch_start="2026-01-01T00:00:00Z",
                      env_extra={"SDD_AUDIT_OWNERSHIP_MODE": "warn"})
        self.assertEqual(r.returncode, 0)
        # No violation logged because the old file is below the cutoff
        self.assertEqual(_read_log(self.repo), "")

    def test_audit_directory_is_ignored(self):
        """Files written under .sys/.audit/ are not subject to ownership check."""
        self._write_modified_file("workspace/output/.sys/.audit/some-trace.log")
        payload = {"tool_input": {"subagent_type": "dev-backend"}}
        r = _run_hook(payload, self.repo, dispatch_start="2020-01-01T00:00:00Z")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("[FILE_OWNERSHIP]", _read_log(self.repo))


if __name__ == "__main__":
    unittest.main()
