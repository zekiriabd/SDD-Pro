"""Subprocess tests for sdd_hooks/resolve_po_hash_sentinel.py.

Audit CTO 2026-06-07 — hook is `SubagentStop matcher=po`, defense-in-depth
that resolves `Parent FEAT hash: sha256:COMPUTE_REQUIRED` sentinels after
`po` agent stops. Pre-fix : zero test coverage.

Baseline pinned :
  - Empty stdin / no po session → ALLOW silently
  - No sentinels in any US → ALLOW
  - Defensive : even on internal error, hook is non-blocking (ALLOW)
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
_MODULE = "sdd_hooks.resolve_po_hash_sentinel"

pytestmark = pytest.mark.smoke


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Invoke the hook via the canonical `_hook.py` launcher (mirrors settings.json)."""
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


class TestResolvePoHashSentinel(unittest.TestCase):
    def test_empty_stdin_allows(self):
        r = _run_hook({})
        # Hook is non-blocking by design (defense-in-depth)
        self.assertEqual(r.returncode, 0)

    def test_other_agent_subagent_allows(self):
        """The hook is wired to po only, but defensive: other agent → no-op."""
        payload = {"subagent_type": "qa", "stop_reason": "completed"}
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)

    def test_po_stop_no_us_files_allows(self):
        """When po stops but no US files have sentinels → silent OK."""
        payload = {"subagent_type": "po", "stop_reason": "completed"}
        r = _run_hook(payload)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
