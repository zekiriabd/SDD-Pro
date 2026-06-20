"""Tests for sdd_hooks.protect_framework — PreToolUse framework-protection hook.

Invokes the hook as a subprocess with controlled stdin (JSON hook protocol),
env vars (SDD_PROTECT_FRAMEWORK_MODE, CI signals), then asserts exit codes
+ stderr content. This mirrors the actual Claude Code hook invocation.

Exit codes (sdd_lib.exit_codes) :
  - HOOK_ALLOW = 0 : continue, no block
  - HOOK_DENY  = 2 : block edit, surface stderr to operator

Mode resolution precedence (cf. hook _resolve_mode) :
  1. SDD_PROTECT_FRAMEWORK_MODE = warn|strict|off (explicit)
  2. CI auto-detect → strict
  3. Default → warn (exit 0)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

# Smoke marker — these tests gate the framework_smoke.py CI / Stop hook.
# Audit CTO 2026-06-07 : the protect_framework CWD bug had passed previous
# smoke runs because pytest was NOT invoked. The 2 tests below
# (`test_user_file_outside_framework_passes_silently` and
# `test_user_file_unaffected_in_strict`) reproduce the bug deterministically.
# Tagging them `smoke` ensures any future regression is surfaced by the
# Stop hook / CI smoke gate, NOT silently green.
pytestmark = pytest.mark.smoke

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

HOOK = _PY_ROOT / "sdd_hooks" / "protect_framework.py"

# CI env vars the hook auto-detects — must be cleared for deterministic tests
CI_VARS = (
    "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
    "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
    "BITBUCKET_BUILD_NUMBER",
)


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a deterministic env: clear CI vars + mode override, apply extras."""
    env = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    env.pop("SDD_PROTECT_FRAMEWORK_MODE", None)
    # Required for subprocess Python on Windows
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra:
        env.update(extra)
    return env


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Invoke the hook with given JSON stdin payload and env. Returns CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        env=_clean_env(env_extra),
        capture_output=True,
        text=True,
        check=False,
    )


class TestProtectFrameworkWarnMode(unittest.TestCase):
    """Default interactive mode : emit WARN on stderr, never block (exit 0)."""

    def test_user_file_outside_framework_passes_silently(self):
        """Edit on user code → no warning, exit 0."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "workspace/output/src/MyApp/Pages/Login.tsx"},
        }
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)
        # No warning expected — path is not framework-owned
        self.assertNotIn("propriete framework", r.stderr)

    def test_framework_rules_edit_warns_but_allows(self):
        """Edit on .claude/rules/X.md → WARN visible, exit 0 in warn mode."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/rules/build-and-loop.md"},
        }
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0, f"Expected ALLOW in warn mode, got exit {r.returncode}")
        self.assertIn("propriete framework SDD_Pro", r.stderr)

    def test_framework_loader_yml_emits_loader_specific_reminder(self):
        """Edit on .claude/loader.yml → reminder line about loader sync."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/loader.yml"},
        }
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)
        self.assertIn("loader.yml", r.stderr)

    def test_framework_claude_md_emits_specific_reminder(self):
        """Edit on .claude/CLAUDE.md → reminder line about CHANGELOG sync."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/CLAUDE.md"},
        }
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)
        self.assertIn("CHANGELOG", r.stderr)


class TestProtectFrameworkStrictMode(unittest.TestCase):
    """Strict mode (CI or explicit) : block framework edits with exit 2."""

    def test_framework_edit_blocked_in_strict(self):
        """SDD_PROTECT_FRAMEWORK_MODE=strict → exit 2 on framework path."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/agents/po.md"},
        }
        r = _run_hook(payload, {"SDD_PROTECT_FRAMEWORK_MODE": "strict"})
        self.assertEqual(r.returncode, 2, f"Expected DENY (2), got {r.returncode}")
        self.assertIn("[FRAMEWORK_PROTECTED]", r.stderr)

    def test_user_file_unaffected_in_strict(self):
        """Strict mode does not block paths outside framework."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "workspace/output/src/MyBackend/Services/Foo.cs"},
        }
        r = _run_hook(payload, {"SDD_PROTECT_FRAMEWORK_MODE": "strict"})
        self.assertEqual(r.returncode, 0)

    def test_ci_env_triggers_strict_auto(self):
        """CI=true env var → auto-strict (no need for SDD_PROTECT_FRAMEWORK_MODE)."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/stacks/backend/dotnet-minimalapi.md"},
        }
        r = _run_hook(payload, {"CI": "true"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("[FRAMEWORK_PROTECTED]", r.stderr)

    def test_explicit_mode_wins_over_ci(self):
        """Explicit SDD_PROTECT_FRAMEWORK_MODE=warn beats CI=true auto-strict."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/rules/quality.md"},
        }
        r = _run_hook(payload, {"CI": "true", "SDD_PROTECT_FRAMEWORK_MODE": "warn"})
        self.assertEqual(r.returncode, 0)
        self.assertIn("propriete framework", r.stderr)


class TestProtectFrameworkOffMode(unittest.TestCase):
    """Off mode : completely disabled, never emits WARN nor blocks."""

    def test_off_mode_skips_everything(self):
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/agents/dev-backend.md"},
        }
        r = _run_hook(payload, {"SDD_PROTECT_FRAMEWORK_MODE": "off", "CI": "true"})
        self.assertEqual(r.returncode, 0)
        # No emission expected — even framework edit passes silently
        self.assertNotIn("propriete framework", r.stderr)


class TestProtectFrameworkEdgeCases(unittest.TestCase):
    """Boundary conditions on hook input."""

    def test_empty_payload_allows(self):
        """Empty stdin → exit 0 (defensive : never break the pipeline)."""
        r = _run_hook({})
        self.assertEqual(r.returncode, 0)

    def test_missing_file_path_allows(self):
        """Payload without file_path → exit 0 (other tools : Bash, Read, etc.)."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)

    def test_python_subdir_is_protected(self):
        """All .claude/python/ files are framework-owned."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/python/sdd_lib/paths.py"},
        }
        r = _run_hook(payload, {"SDD_PROTECT_FRAMEWORK_MODE": "strict"})
        self.assertEqual(r.returncode, 2)

    def test_templates_subdir_is_protected(self):
        """All .claude/templates/ files are framework-owned."""
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/templates/us.template.md"},
        }
        r = _run_hook(payload, {"SDD_PROTECT_FRAMEWORK_MODE": "strict"})
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
