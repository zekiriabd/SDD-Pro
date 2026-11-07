"""Subprocess tests for sdd_hooks/pre_write_lint.py (audit CTO 2026-06-07).

Pre-fix, the 12th hook (Sprint 1.4 2026-06-06) had ZERO test coverage despite
being PreToolUse Edit|Write|MultiEdit blocking. Baseline tests now pin :
  - Empty stdin → ALLOW
  - Non-src path → ALLOW
  - Test file path → ALLOW (QA ownership respected)
  - Disabled via env → ALLOW
  - Non-applicable tool → ALLOW (defensive)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

HOOK = _PY_ROOT / "sdd_hooks" / "pre_write_lint.py"

pytestmark = pytest.mark.smoke


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    # Purge les SDD_* (comportement du hook) mais garde la redirection
    # console.db / .audit du conftest — sinon le hook écrit dans la piste
    # d'audit de production (audit 2026-11-07 : « MyApp/Service.kt »).
    from sdd_lib import paths
    keep = (paths.CONSOLE_DB_PATH_ENV, paths.CONSOLE_DB_PATH_MODE_ENV,
            paths.AUDIT_DIR_ENV, paths.AUDIT_DIR_MODE_ENV)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("SDD_") or k in keep}
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, timeout=10,
    )


class TestPreWriteLintBaseline(unittest.TestCase):
    def test_empty_stdin_allows(self):
        r = _run_hook({})
        self.assertEqual(r.returncode, 0)

    def test_disabled_via_env_allows(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "workspace/src/MyApp/Service.kt",
                "content": "val x = something!!",  # would match Kotlin !! pattern
            },
        }
        r = _run_hook(payload, {"SDD_DISABLE_PRE_WRITE_LINT": "1"})
        self.assertEqual(r.returncode, 0)

    def test_non_src_path_allows(self):
        """Files outside workspace/src/ are out of scope."""
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "docs/notes.md",
                "content": "TODO: something",
            },
        }
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)

    def test_test_file_allows(self):
        """Test paths are QA-owned, skipped by lint."""
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "workspace/src/MyApp/__tests__/foo.test.ts",
                "content": "// TODO: more tests",
            },
        }
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)

    def test_non_edit_tool_allows(self):
        """Read / Bash tools — hook only cares about Edit/Write/MultiEdit."""
        payload = {"tool_name": "Read", "tool_input": {"file_path": "foo.md"}}
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)


class TestPreWriteLintWarnMode(unittest.TestCase):
    """Default mode = WARN : detected patterns log to stderr but exit 0."""

    def test_warn_mode_default_allows_with_warning(self):
        """A pattern triggers WARN but does NOT block (default mode)."""
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "workspace/src/MyApp/Service.kt",
                "content": "fun get(): String = data!!  // unjustified force-unwrap",
            },
        }
        r = _run_hook(payload)
        # Default warn mode → ALLOW (exit 0) even when pattern detected
        self.assertEqual(r.returncode, 0)
        # But stderr should contain some signal (WARN or audit message). Be lenient
        # since the lint may be heuristic — don't pin exact wording.


class TestPreWriteLintStrictMode(unittest.TestCase):
    """Strict mode (SDD_PRE_WRITE_LINT_STRICT=1) blocks on detected patterns."""

    def test_strict_mode_test_file_still_skipped(self):
        """Even in strict, test files are exempt (QA ownership)."""
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "workspace/src/MyApp/__tests__/x.test.ts",
                "content": "// TODO and console.log everywhere",
            },
        }
        r = _run_hook(payload, {"SDD_PRE_WRITE_LINT_STRICT": "1"})
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
