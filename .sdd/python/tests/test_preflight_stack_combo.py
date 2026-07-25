"""Subprocess tests for sdd_hooks/preflight_stack_combo.py.

Audit CTO 2026-06-07 — hook is `PreToolUse matcher=Skill`, gates
/sdd-full /sdd-poc /dev-run on combo validation. Pre-fix : zero test
coverage despite being blocking (exit 2 on untested combos).

Baseline pinned :
  - Empty stdin → ALLOW
  - Non-pipeline Skill (e.g. arch-init) → ALLOW (filter applied)
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
_MODULE = "sdd_hooks.preflight_stack_combo"

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


class TestPreflightStackCombo(unittest.TestCase):
    def test_empty_stdin_allows(self):
        r = _run_hook({})
        self.assertEqual(r.returncode, 0)

    def test_non_pipeline_skill_allows(self):
        """Hook filters internally to {sdd-full, sdd-poc, dev-run}. Other
        skills (sdd-status, feat-generate, etc.) must pass through."""
        payload = {"tool_name": "Skill", "tool_input": {"skill": "sdd-status"}}
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)

    def test_bypass_env_allows(self):
        """SDD_ALLOW_UNTESTED_COMBO=1 disables the combo gate."""
        payload = {"tool_name": "Skill", "tool_input": {"skill": "sdd-full"}}
        r = _run_hook(payload, {"SDD_ALLOW_UNTESTED_COMBO": "1"})
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
