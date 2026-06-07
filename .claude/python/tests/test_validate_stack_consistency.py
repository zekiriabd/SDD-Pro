"""Subprocess tests for sdd_hooks/validate_stack_consistency.py.

Audit CTO 2026-06-07 — hook is `PostToolUse Edit|Write|MultiEdit`. Pre-fix :
zero test coverage despite being potentially-blocking (exit 2 on
[STACK_MULTI_INCOHERENT]).

Baseline pinned :
  - Empty stdin → ALLOW
  - Edit outside stack.md → ALLOW (filter applied)
  - Bypass env → ALLOW
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

_HOOK_LAUNCHER = _PY_ROOT / "_hook.py"
_MODULE = "sdd_hooks.validate_stack_consistency"

pytestmark = pytest.mark.smoke


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SDD_")}
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(_HOOK_LAUNCHER), _MODULE],
        input=json.dumps(payload),
        env=env,
        capture_output=True, text=True,
        check=False, timeout=10,
    )


class TestValidateStackConsistency(unittest.TestCase):
    def test_empty_stdin_allows(self):
        r = _run_hook({})
        self.assertEqual(r.returncode, 0)

    def test_edit_outside_stack_md_allows(self):
        """Hook filters internally to edits of workspace/input/stack/stack.md.
        Other paths must not trigger the multi-stack consistency check."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "workspace/output/src/MyApp/Service.cs"},
        }
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)

    def test_bypass_env_allows(self):
        """SDD_ALLOW_MULTISTACK=1 disables the consistency gate."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "workspace/input/stack/stack.md"},
        }
        r = _run_hook(payload, {"SDD_ALLOW_MULTISTACK": "1"})
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
