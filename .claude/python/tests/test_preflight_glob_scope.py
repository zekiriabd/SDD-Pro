"""Subprocess tests for sdd_hooks/preflight_glob_scope.py.

Audit CTO 2026-06-07 — verify the broad-Glob defense works as specified.
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
_MODULE = "sdd_hooks.preflight_glob_scope"

pytestmark = pytest.mark.smoke


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SDD_GLOB")}
    env.pop("SDD_DISABLE_GLOB_SCOPE", None)
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


def _glob_payload(pattern: str) -> dict:
    return {"tool_name": "Glob", "tool_input": {"pattern": pattern}}


class TestPreflightGlobScopeWarn(unittest.TestCase):
    """Default WARN mode : emit stderr but allow."""

    def test_broad_pattern_warns_but_allows(self):
        r = _run_hook(_glob_payload("workspace/output/src/**/*"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARN", r.stderr)

    def test_scoped_pattern_silent(self):
        r = _run_hook(_glob_payload("workspace/output/src/MyApp/Services/**/*.cs"))
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("WARN", r.stderr)

    def test_glob_outside_src_silent(self):
        r = _run_hook(_glob_payload(".claude/agents/*.md"))
        self.assertEqual(r.returncode, 0)

    def test_missing_pattern_allows(self):
        r = _run_hook({"tool_name": "Glob", "tool_input": {}})
        self.assertEqual(r.returncode, 0)


class TestPreflightGlobScopeStrict(unittest.TestCase):
    """SDD_GLOB_SCOPE_STRICT=1 → exit 2 on broad pattern."""

    def test_strict_blocks_broad(self):
        r = _run_hook(_glob_payload("workspace/output/src/**/*"),
                      {"SDD_GLOB_SCOPE_STRICT": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("GLOB_SCOPE_TOO_BROAD", r.stderr)

    def test_strict_allows_scoped(self):
        r = _run_hook(_glob_payload("workspace/output/src/MyApp/**/*.ts"),
                      {"SDD_GLOB_SCOPE_STRICT": "1"})
        # Wait — this pattern matches `workspace/output/src/**/*.ts` which is
        # NOT in the broad list (we only ban naked `**/*` without extension).
        # But the regex matches the LITERAL pattern, not its semantic. Let me
        # verify : "workspace/output/src/MyApp/**/*.ts" has extension → allowed.
        self.assertEqual(r.returncode, 0)

    def test_strict_blocks_naked_double_star(self):
        r = _run_hook(_glob_payload("**/*"),
                      {"SDD_GLOB_SCOPE_STRICT": "1"})
        self.assertEqual(r.returncode, 2)

    def test_bypass_env_overrides_strict(self):
        r = _run_hook(_glob_payload("workspace/output/src/**/*"),
                      {"SDD_GLOB_SCOPE_STRICT": "1",
                       "SDD_DISABLE_GLOB_SCOPE": "1"})
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
