"""Behavioral tests for sdd_hooks.enforce_two_stage_auditor — the PreToolUse
hook that enforces the v7.0.0+ two-stage auditor pattern
(invariant `spec-gate-before-quality-batch`).

Until now this critical enforcer was only covered by the importability smoke
(`test_hooks_importable_smoke`). MI-7 (audit 2026-06-09) adds the missing
behavioral coverage : the gate must DENY a Stage B reviewer
(code/security/arch) when Stage A (spec-compliance) has not produced fresh
rows in `qa_spec_compliance`, and ALLOW once it has.

Style mirrors `test_preflight_cost_cap.py` : a fully isolated tmp
`$SDD_REPO_ROOT` + an initialized console.db, driven via stdin JSON →
exit code (HOOK_ALLOW=0 / HOOK_DENY=2).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402

HOOK = _PY_ROOT / "sdd_hooks" / "enforce_two_stage_auditor.py"

CI_VARS = (
    "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
    "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
    "BITBUCKET_BUILD_NUMBER",
)


def _clean_env(repo: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    for k in ("SDD_BYPASS_TWO_STAGE", "SDD_RUN_ID"):
        env.pop(k, None)
    env["SDD_REPO_ROOT"] = str(repo)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra:
        env.update(extra)
    return env


def _run_hook(payload: dict, repo: Path,
              env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        env=_clean_env(repo, env_extra),
        capture_output=True,
        text=True,
        check=False,
    )


def _make_repo(tmp_path: Path) -> Path:
    """Synthetic SDD repo skeleton matching sdd_lib.paths._looks_like_repo_root."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / "workspace").mkdir()
    return tmp_path


def _init_db(repo: Path) -> Path:
    """Initialize an empty console.db (schema only, no spec-compliance rows)."""
    from sdd_lib import console_db
    db_path = repo / "workspace" / "db" / "console.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    console_db.ensure_initialized(db_path)
    return db_path


def _seed_spec_compliance(db_path: Path, feat_n: int,
                          verdict: str = "verified") -> None:
    """Insert a fresh qa_spec_compliance row for `feat_n`.

    DB fallback path : when no JSON report exists, the hook counts rows
    < 24h old (per-AC verdicts, no overall verdict available there) — a
    single row marks Stage A as "completed". The authoritative verdict
    path is the JSON report (see `_write_report` / audit 2026-06-11 M1).
    We disable FK enforcement during seeding to avoid having to
    materialize parent feats/us rows — the hook reads with a separate
    read-only connection.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO qa_spec_compliance "
            "(feat_n, us_id, ac_id, extracted_at, verdict) "
            "VALUES (?, ?, ?, datetime('now'), ?)",
            (feat_n, f"{feat_n}-1", "AC-1", verdict),
        )
        conn.commit()
    finally:
        conn.close()


def _write_report(repo: Path, feat_n: int, verdict: str) -> Path:
    """Write the authoritative Stage A JSON report (audit 2026-06-11 M1)."""
    report = (repo / "workspace" / ".sys" / ".validation"
              / f"{feat_n}-spec-compliance.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"summary": {"verdict": verdict}}), encoding="utf-8",
    )
    return report


def _stage_b_payload(feat_n: int, agent: str = "code-reviewer") -> dict:
    return {
        "tool_name": "Agent",
        "tool_input": {
            "subagent_type": agent,
            "prompt": f"Audit FEAT {feat_n} — quality batch (cf. {agent}.md).",
        },
    }


class TestStageBlocking(unittest.TestCase):
    """Stage B reviewers are gated by Stage A (spec-compliance) freshness."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_spec_absent_denies_quality_batch(self):
        """(a) DB present, NO spec-compliance rows → DENY code-reviewer."""
        _init_db(self.repo)  # schema only, zero qa_spec_compliance rows
        proc = _run_hook(_stage_b_payload(1, "code-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_DENY,
                         msg=f"expected DENY, got {proc.returncode}\n{proc.stderr}")
        self.assertIn("TWO_STAGE_GATE_VIOLATION", proc.stderr)

    def test_spec_present_allows_quality_batch(self):
        """(b) spec-compliance row present (GREEN) → ALLOW code-reviewer."""
        db = _init_db(self.repo)
        _seed_spec_compliance(db, feat_n=1, verdict="verified")
        proc = _run_hook(_stage_b_payload(1, "code-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW,
                         msg=f"expected ALLOW, got {proc.returncode}\n{proc.stderr}")

    def test_security_reviewer_also_gated(self):
        """The gate covers security-reviewer too (Stage B set)."""
        _init_db(self.repo)
        proc = _run_hook(_stage_b_payload(2, "security-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_DENY,
                         msg=f"expected DENY, got {proc.returncode}\n{proc.stderr}")

    def test_arch_reviewer_allowed_after_stage_a(self):
        db = _init_db(self.repo)
        _seed_spec_compliance(db, feat_n=3)
        proc = _run_hook(_stage_b_payload(3, "arch-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW,
                         msg=f"expected ALLOW, got {proc.returncode}\n{proc.stderr}")


class TestReportVerdictGate(unittest.TestCase):
    """Audit 2026-06-11 M1 — le hook lit le VERDICT du rapport Stage A.

    Avant ce fix, un Stage A 🔴 RED laissait spawner les reviewers Stage B
    (le hook ne testait que l'existence de rows fraîches en DB).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_red_report_denies_even_with_fresh_db_rows(self):
        db = _init_db(self.repo)
        _seed_spec_compliance(db, feat_n=1, verdict="not_verified")
        _write_report(self.repo, 1, "🔴 RED")
        proc = _run_hook(_stage_b_payload(1, "code-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_DENY,
                         msg=f"expected DENY on RED report\n{proc.stderr}")
        self.assertIn("TWO_STAGE_GATE_VIOLATION", proc.stderr)
        self.assertIn("RED", proc.stderr)

    def test_green_report_allows_without_db_rows(self):
        _init_db(self.repo)  # zero rows — fallback DB would DENY
        _write_report(self.repo, 1, "green")
        proc = _run_hook(_stage_b_payload(1, "code-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)

    def test_warn_report_allows(self):
        _init_db(self.repo)
        _write_report(self.repo, 1, "🟡 WARN")
        proc = _run_hook(_stage_b_payload(1, "code-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)

    def test_corrupted_report_falls_back_to_db(self):
        db = _init_db(self.repo)
        report = _write_report(self.repo, 1, "green")
        report.write_text("{not json", encoding="utf-8")
        # Fallback DB : fresh row present → ALLOW (statu quo historique)
        _seed_spec_compliance(db, feat_n=1)
        proc = _run_hook(_stage_b_payload(1, "code-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)

    def test_corrupted_report_no_db_rows_denies(self):
        _init_db(self.repo)
        report = _write_report(self.repo, 1, "green")
        report.write_text("{not json", encoding="utf-8")
        proc = _run_hook(_stage_b_payload(1, "code-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_DENY, msg=proc.stderr)


class TestAlwaysAllowPaths(unittest.TestCase):
    """Stage A agent, informational agents, and non-reviewer tools pass through."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))
        _init_db(self.repo)  # no spec rows — would DENY a Stage B agent

    def tearDown(self):
        self._tmp.cleanup()

    def test_spec_compliance_reviewer_always_allowed(self):
        """Stage A itself is never gated (it IS the gate)."""
        proc = _run_hook(_stage_b_payload(1, "spec-compliance-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)

    def test_adversarial_reviewer_allowed(self):
        proc = _run_hook(_stage_b_payload(1, "adversarial-reviewer"), self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)

    def test_non_agent_tool_passthrough(self):
        proc = _run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}}, self.repo,
        )
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)

    def test_unrelated_subagent_passthrough(self):
        """A dev-backend spawn is not a reviewer — not gated."""
        proc = _run_hook(_stage_b_payload(1, "dev-backend"), self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)


class TestBypasses(unittest.TestCase):
    """Env bypass and legacy-parallel config disable enforcement."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))
        _init_db(self.repo)  # no spec rows → would DENY by default

    def tearDown(self):
        self._tmp.cleanup()

    def test_env_bypass_allows(self):
        proc = _run_hook(
            _stage_b_payload(1, "code-reviewer"), self.repo,
            env_extra={"SDD_BYPASS_TWO_STAGE": "1"},
        )
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)
        self.assertIn("TWO_STAGE_BYPASSED", proc.stderr)

    def test_no_db_fails_safe_allow(self):
        """No console.db yet → cannot enforce → fail-safe ALLOW."""
        # Fresh repo without DB init
        tmp2 = tempfile.TemporaryDirectory()
        try:
            repo2 = _make_repo(Path(tmp2.name))
            proc = _run_hook(_stage_b_payload(1, "code-reviewer"), repo2)
            self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)
        finally:
            tmp2.cleanup()

    def test_feat_unextractable_fails_safe_allow(self):
        """Prompt without a parseable FEAT number → fail-safe ALLOW."""
        payload = {
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "code-reviewer",
                "prompt": "Review the code quality for the current changes.",
            },
        }
        proc = _run_hook(payload, self.repo)
        self.assertEqual(proc.returncode, HOOK_ALLOW, msg=proc.stderr)


if __name__ == "__main__":
    unittest.main()
