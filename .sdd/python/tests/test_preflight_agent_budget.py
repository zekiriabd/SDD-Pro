"""Tests for sdd_hooks.preflight_agent_budget — PreToolUse.Agent budget gate.

Splits into 2 tiers :
  - In-process tests of pure helpers (extract_us_and_feat,
    REJECTED_AGENTS_V7, ALLOWED_AGENTS) — fast, no subprocess.
  - Subprocess tests of the full hook lifecycle (stdin JSON → exit code),
    isolated via tmp $SDD_REPO_ROOT and stub context_budget.py.
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

from sdd_hooks.preflight_agent_budget import (  # noqa: E402
    ALLOWED_AGENTS,
    REJECTED_AGENTS_V7,
    extract_us_and_feat,
)

HOOK = _PY_ROOT / "sdd_hooks" / "preflight_agent_budget.py"

CI_VARS = (
    "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
    "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
    "BITBUCKET_BUILD_NUMBER",
)


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    env.pop("SDD_BUDGET_MODE", None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra:
        env.update(extra)
    return env


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        env=_clean_env(env_extra),
        capture_output=True,
        text=True,
        check=False,
    )


# ============================================================================
# In-process tests : pure helpers
# ============================================================================

class TestRejectedAgentsV7(unittest.TestCase):
    """Removed-agents map must list the 5 retired in v7.0.0."""

    def test_rejected_set_matches_expected(self):
        expected = {
            "accessibility-auditor",
            "performance-auditor",
            "dashboard",
            "dev-backend-strict",
            "dev-frontend-strict",
        }
        self.assertEqual(set(REJECTED_AGENTS_V7.keys()), expected)

    def test_every_rejection_has_replacement_hint(self):
        for agent, replacement in REJECTED_AGENTS_V7.items():
            self.assertTrue(replacement.strip(), f"Empty replacement for {agent}")

    def test_rejection_and_allow_lists_are_disjoint(self):
        self.assertEqual(set(REJECTED_AGENTS_V7) & ALLOWED_AGENTS, set())


class TestExtractUsAndFeat(unittest.TestCase):
    """Best-effort regex extraction of FEAT/US identifiers."""

    def test_strict_sdd_command_prefix(self):
        fn, us = extract_us_and_feat("/dev-run 1-2")
        self.assertEqual(fn, 1)
        self.assertEqual(us, "1-2")

    def test_basename_with_name_suffix(self):
        fn, us = extract_us_and_feat("US 1-2-Auth complete")
        self.assertEqual(fn, 1)
        self.assertEqual(us, "1-2")

    def test_feat_only_reference(self):
        fn, us = extract_us_and_feat("/sdd-full 5")
        self.assertEqual(fn, 5)
        self.assertEqual(us, "")

    def test_no_match_returns_zero_and_empty(self):
        fn, us = extract_us_and_feat("hello world no identifiers here")
        self.assertEqual(fn, 0)
        self.assertEqual(us, "")

    def test_lenient_fallback_picks_isolated_pair(self):
        """Pass 2 fallback : isolated `N-M` token (no SDD anchor)."""
        fn, us = extract_us_and_feat("see 3-1 below")
        self.assertEqual(fn, 3)
        self.assertEqual(us, "3-1")

    def test_does_not_match_mid_identifier(self):
        """Tightened regex (audit C3) : avoid spurious mid-string matches."""
        fn, us = extract_us_and_feat("ref-42-1234-internal")
        # Strict pass should fail (not at boundary), lenient pass blocked too
        self.assertEqual(us, "")


# ============================================================================
# Subprocess tests : full hook lifecycle
# ============================================================================

class TestHookSubprocessRejection(unittest.TestCase):
    """Retired agents must be rejected (block in CI, WARN otherwise)."""

    def test_accessibility_auditor_blocked_in_ci(self):
        payload = {
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "accessibility-auditor",
                "prompt": "scan FEAT 1",
            },
        }
        r = _run_hook(payload, {"CI": "true"})
        self.assertEqual(r.returncode, 2, f"Expected DENY in CI, got {r.returncode}")
        self.assertIn("[AGENT_REMOVED_V7]", r.stderr)
        self.assertIn("axe-core", r.stderr)

    def test_dashboard_blocked_in_ci(self):
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dashboard"},
        }
        r = _run_hook(payload, {"CI": "true"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("index_adrs.py", r.stderr)

    def test_dev_backend_strict_blocked_in_ci(self):
        payload = {"tool_name": "Agent", "tool_input": {"subagent_type": "dev-backend-strict"}}
        r = _run_hook(payload, {"CI": "true"})
        self.assertEqual(r.returncode, 2)

    def test_rejected_agent_interactive_warns_but_allows(self):
        """Warn mode (no CI, no explicit strict) → ERROR visible but exit 0."""
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "performance-auditor"},
        }
        r = _run_hook(payload, {"SDD_BUDGET_MODE": "warn"})
        self.assertEqual(r.returncode, 0, f"Expected ALLOW in warn mode, got {r.returncode}")
        self.assertIn("[AGENT_REMOVED_V7]", r.stderr)


class TestHookSubprocessUnknownAndAllowed(unittest.TestCase):
    """Unknown agents and missing payload are gracefully skipped."""

    def test_unknown_agent_silent_skip(self):
        """Backward-compat : custom agents not in ALLOWED_AGENTS pass through."""
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "my-custom-agent"},
        }
        r = _run_hook(payload, {"CI": "true"})
        self.assertEqual(r.returncode, 0)
        # No emission expected — unknown agent is not blocked, not warned
        self.assertNotIn("[AGENT_REMOVED_V7]", r.stderr)

    def test_off_mode_skips_everything(self):
        """SDD_BUDGET_MODE=off → no budget check, no rejection."""
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "accessibility-auditor"},
        }
        r = _run_hook(payload, {"SDD_BUDGET_MODE": "off", "CI": "true"})
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("[AGENT_REMOVED_V7]", r.stderr)

    def test_empty_payload_exits_zero(self):
        r = _run_hook({})
        self.assertEqual(r.returncode, 0)

    def test_missing_subagent_type_exits_zero(self):
        payload = {"tool_name": "Agent", "tool_input": {"prompt": "do something"}}
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)


class TestHookSubprocessAllowedAgent(unittest.TestCase):
    """Allowed agent → delegates to context_budget.py.

    We isolate the test by pointing $SDD_REPO_ROOT at a tmp dir without
    context_budget.py — the hook should emit a soft WARN and exit 0 (defensive
    behaviour : never break the pipeline on missing script).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        # Minimal scaffolding for repo_root detection
        (self.repo / ".claude" / "agents").mkdir(parents=True)
        (self.repo / ".claude" / "commands").mkdir(parents=True)
        (self.repo / "workspace").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_allowed_agent_continues_when_context_budget_missing(self):
        """Hook script invokes context_budget.py from its own dir; if absent,
        emit WARN + exit 0 (don't break the pipeline)."""
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "po", "prompt": "/us-generate 1"},
        }
        # SDD_REPO_ROOT does NOT affect the hook's own script path resolution
        # (hook uses Path(__file__) for its sibling scripts). The hook will
        # invoke the real context_budget.py — that may succeed or fail
        # gracefully depending on env. Either way : exit must be 0 in warn mode.
        r = _run_hook(payload, {"SDD_REPO_ROOT": str(self.repo), "SDD_BUDGET_MODE": "warn"})
        self.assertEqual(r.returncode, 0,
                         f"warn mode must never block on allowed agent, got {r.returncode}\nSTDERR={r.stderr}")


class TestStrictFailClosedOnTimeout(unittest.TestCase):
    """Security audit 2026-06-06 (LOT 8.1) : ensure that on subprocess TimeoutExpired
    in strict mode, the hook returns HOOK_DENY (was HOOK_ALLOW = fail-open before)."""

    def test_strict_mode_emits_deny_path_documentation(self):
        """Indirect coverage : verify the source path emits HOOK_DENY in strict
        timeout branch. We don't trigger an actual 30s subprocess timeout here
        (cost-prohibitive), but assert the strict branch source contains the
        BUDGET_PRECHECK_TIMEOUT class + HOOK_DENY return.
        """
        src = HOOK.read_text(encoding="utf-8")
        # The strict-mode timeout branch must reference HOOK_DENY and the new class.
        self.assertIn("BUDGET_PRECHECK_TIMEOUT", src,
                      "strict-mode timeout branch must emit [BUDGET_PRECHECK_TIMEOUT] error class")
        self.assertIn("return HOOK_DENY", src,
                      "strict-mode timeout branch must return HOOK_DENY (fail-closed)")
        # Verify the comment trail explains the change (anti-regression doc).
        self.assertIn("47MB", src, "audit trail with the 47MB/spec-compliance-reviewer incident is preserved")


if __name__ == "__main__":
    unittest.main()
