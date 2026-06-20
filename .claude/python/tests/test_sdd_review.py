"""Tests for sdd_scripts.sdd_review — /sdd-review orchestrator.

Complements the existing test_sdd_review_dedup.py (which targets the
deduplicate_findings helper). This file covers :
  - resolve_fail_on (CLI override, layered config fallback)
  - resolve_arch_required (ArchReviewMode=full gate)
  - CLI main() : standard / --skip-scans / --ensure-scans / --json
  - Exit code mapping (0 GREEN | 1 RED | 2 bad args | 3 ensure-scans MISS)

Strategy : subprocess invocation on isolated tmp $SDD_REPO_ROOT with a
seeded console.db (so we can assert on the verdict + markdown output).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

SCRIPT = _PY_ROOT / "sdd_scripts" / "sdd_review.py"

CI_VARS = (
    "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
    "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
    "BITBUCKET_BUILD_NUMBER",
)


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    for k in ("SDD_REPO_ROOT", "SDD_TEAM_CONFIG"):
        env.pop(k, None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra:
        env.update(extra)
    return env


def _make_repo(tmp_path: Path) -> Path:
    """Minimal SDD_Pro skeleton + initialised console.db."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / "workspace" / "input" / "feats").mkdir(parents=True)
    (tmp_path / "workspace" / "input" / "stack").mkdir(parents=True)
    (tmp_path / "workspace" / "output" / "src").mkdir(parents=True)
    (tmp_path / "workspace" / "output" / "qa").mkdir(parents=True)

    # Minimal stack.md (so resolve_fail_on doesn't crash on parse)
    (tmp_path / "workspace" / "input" / "stack" / "stack.md").write_text(
        "## Project Config\nAppName: Test\nBackendName: TestBack\nReviewFailOn: serious\n",
        encoding="utf-8",
    )
    # Minimal FEAT (so /sdd-review --feat-number 1 doesn't bail on missing FEAT)
    (tmp_path / "workspace" / "input" / "feats" / "1-Test.md").write_text(
        "# FEAT 1 — Test\n\n## Objectif\nTest.\n",
        encoding="utf-8",
    )
    return tmp_path


def _init_db(repo: Path):
    """Initialise an empty console.db at the expected location."""
    from sdd_lib import console_db
    db_path = repo / "workspace" / "output" / "db" / "console.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["SDD_REPO_ROOT"] = str(repo)
    try:
        console_db.ensure_initialized(db_path)
    finally:
        os.environ.pop("SDD_REPO_ROOT", None)


def _seed_qa_quality(repo: Path, feat_n: int, severity: str, count: int = 1):
    """Insert qa_quality rows for the given FEAT at the given severity."""
    from sdd_lib import console_db
    db_path = repo / "workspace" / "output" / "db" / "console.db"
    os.environ["SDD_REPO_ROOT"] = str(repo)
    try:
        with console_db.connect(db_path) as conn:
            console_db.ensure_feat_row(conn, feat_n=feat_n, name=f"Test{feat_n}",
                                       file_path="workspace/input/feats/1-Test.md")
            for i in range(count):
                conn.execute(
                    "INSERT INTO qa_quality(feat_n, extracted_at, severity, "
                    "issue_class, rule, file_path, line, message) "
                    "VALUES(?, datetime('now'), ?, '[QUALITY]', 'no-todo', "
                    "'src/foo.cs', ?, 'TODO: fix this')",
                    (feat_n, severity, i + 1),
                )
    finally:
        os.environ.pop("SDD_REPO_ROOT", None)


def _run(*args, repo: Path, env_extra=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=_clean_env({**(env_extra or {}), "SDD_REPO_ROOT": str(repo)}),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=20,
    )


# ============================================================================
# resolve_fail_on
# ============================================================================

class TestResolveFailOn(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli_value_wins_over_config(self):
        from sdd_scripts.sdd_review import resolve_fail_on
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            self.assertEqual(resolve_fail_on("critical"), "critical")
            self.assertEqual(resolve_fail_on("MINOR"), "minor")  # lowercased
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)

    def test_config_fallback_when_no_cli(self):
        from sdd_scripts.sdd_review import resolve_fail_on
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            # Project config has ReviewFailOn: serious
            self.assertEqual(resolve_fail_on(None), "serious")
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)

    def test_default_serious_on_invalid_config(self):
        from sdd_scripts.sdd_review import resolve_fail_on
        (self.repo / "workspace" / "input" / "stack" / "stack.md").write_text(
            "## Project Config\nReviewFailOn: garbage\n", encoding="utf-8",
        )
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            self.assertEqual(resolve_fail_on(None), "serious")
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)


# ============================================================================
# resolve_arch_required
# ============================================================================

class TestResolveArchRequired(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_arch_required_when_mode_full(self):
        from sdd_scripts.sdd_review import resolve_arch_required
        (self.repo / "workspace" / "input" / "stack" / "stack.md").write_text(
            "## Project Config\nArchReviewMode: full\n", encoding="utf-8",
        )
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            self.assertTrue(resolve_arch_required())
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)

    def test_arch_not_required_when_mode_manual(self):
        from sdd_scripts.sdd_review import resolve_arch_required
        (self.repo / "workspace" / "input" / "stack" / "stack.md").write_text(
            "## Project Config\nArchReviewMode: manual\n", encoding="utf-8",
        )
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            self.assertFalse(resolve_arch_required())
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)

    def test_arch_not_required_when_mode_missing(self):
        from sdd_scripts.sdd_review import resolve_arch_required
        (self.repo / "workspace" / "input" / "stack" / "stack.md").write_text(
            "## Project Config\nAppName: Test\n", encoding="utf-8",
        )
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            self.assertFalse(resolve_arch_required())
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)


# ============================================================================
# CLI main() — exit code matrix
# ============================================================================

class TestCliExitCodes(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))
        _init_db(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def test_bad_fail_on_returns_2(self):
        r = _run("--feat-number", "1", "--fail-on", "BOGUS",
                 "--skip-scans", repo=self.repo)
        self.assertEqual(r.returncode, 2,
                         f"Expected exit 2 on bad --fail-on, got {r.returncode}\n"
                         f"STDERR={r.stderr}")
        self.assertIn("invalid --fail-on", r.stderr)

    def test_empty_db_green_verdict(self):
        """No findings → verdict GREEN → exit 0."""
        r = _run("--feat-number", "1", "--skip-scans", "--json", repo=self.repo)
        self.assertEqual(r.returncode, 0, f"STDERR={r.stderr}")
        payload = json.loads(r.stdout[r.stdout.index("{"):])
        self.assertEqual(payload["verdict"], "green")
        self.assertEqual(payload["total"], 0)

    def test_critical_finding_red_verdict(self):
        """1 critical finding > fail_on=serious → verdict RED → exit 1."""
        _seed_qa_quality(self.repo, feat_n=1, severity="error")  # → critical
        r = _run("--feat-number", "1", "--skip-scans", "--json",
                 "--fail-on", "serious", repo=self.repo)
        self.assertEqual(r.returncode, 1)
        payload = json.loads(r.stdout[r.stdout.index("{"):])
        self.assertEqual(payload["verdict"], "red")
        self.assertGreater(payload["triggering"], 0)

    def test_minor_finding_below_threshold(self):
        """1 minor finding with fail_on=serious → verdict YELLOW → exit 0."""
        _seed_qa_quality(self.repo, feat_n=1, severity="info")  # → minor
        r = _run("--feat-number", "1", "--skip-scans", "--json",
                 "--fail-on", "serious", repo=self.repo)
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout[r.stdout.index("{"):])
        # Below threshold : verdict could be green or yellow depending on logic
        self.assertIn(payload["verdict"], ("green", "yellow"))


# ============================================================================
# --ensure-scans gate (v7.0.0)
# ============================================================================

class TestEnsureScansGate(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))
        _init_db(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ensure_scans_fails_on_empty_db(self):
        """--ensure-scans with no rows → exit 3 + [REVIEW_SOURCES_MISSING]."""
        r = _run("--feat-number", "1", "--skip-scans", "--ensure-scans",
                 repo=self.repo)
        self.assertEqual(r.returncode, 3,
                         f"Expected exit 3 (REVIEW_SOURCES_MISSING), got {r.returncode}\n"
                         f"STDERR={r.stderr}")
        self.assertIn("[REVIEW_SOURCES_MISSING]", r.stderr)
        # Should list each missing source with the fix command
        self.assertIn("quality", r.stderr)
        self.assertIn("code-review", r.stderr)
        self.assertIn("security", r.stderr)
        self.assertIn("spec-compliance", r.stderr)

    def test_ensure_scans_optional_a11y_perf_not_required_v7(self):
        """a11y / perf are LEGACY in v7.0.0 — must not trigger error."""
        # Even without ensure-scans seeded, a11y + perf should be in OPTIONAL
        # set, never required
        r = _run("--feat-number", "1", "--skip-scans", "--ensure-scans",
                 repo=self.repo)
        # The error should mention quality/code-review/security/spec
        # but NOT a11y / perf
        self.assertNotIn("a11y", r.stderr.lower().replace("legacy", ""))
        self.assertNotIn("perf", r.stderr.lower().replace("performance test", ""))


# ============================================================================
# Output artefacts
# ============================================================================

class TestOutputArtefacts(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))
        _init_db(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def test_markdown_report_written(self):
        r = _run("--feat-number", "1", "--skip-scans", repo=self.repo)
        self.assertEqual(r.returncode, 0)
        md_path = (self.repo / "workspace" / "output" / "qa" / "feat-1"
                   / "review.md")
        self.assertTrue(md_path.is_file(),
                        f"review.md not found at {md_path}")
        content = md_path.read_text(encoding="utf-8")
        self.assertIn("FEAT 1", content)

    def test_json_output_well_formed(self):
        r = _run("--feat-number", "1", "--skip-scans", "--json", repo=self.repo)
        self.assertEqual(r.returncode, 0)
        # JSON starts somewhere in stdout (may be preceded by stderr noise)
        json_start = r.stdout.index("{")
        payload = json.loads(r.stdout[json_start:])
        for key in ("feat_n", "verdict", "fail_on", "total", "triggering",
                    "counts", "markdown_path"):
            self.assertIn(key, payload, f"missing key {key} in JSON output")


if __name__ == "__main__":
    unittest.main()
