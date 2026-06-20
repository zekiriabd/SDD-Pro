"""Subprocess tests for sdd_hooks/validate_acceptance_gate.py.

Audit CTO 2026-06-07 — hook is `SubagentStop matcher=qa`, runs acceptance
gate (test/lint/build/coverage) on every project under workspace/output/src/.
Pre-fix : zero test coverage despite being potentially-blocking.

Baseline pinned :
  - Empty stdin / no qa session → DENY (CRIT-4 audit 2026-06-07 : symmetric)
  - Bypass env `SDD_ALLOW_ACCEPTANCE_BYPASS=1` → ALLOW even with broken project
  - No projects in workspace/output/src/ → DENY (no acceptance.json) — use bypass
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

_HOOK_LAUNCHER = _PY_ROOT / "_hook.py"
_MODULE = "sdd_hooks.validate_acceptance_gate"

pytestmark = pytest.mark.smoke


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None,
              cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SDD_")}
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(_HOOK_LAUNCHER), _MODULE],
        input=json.dumps(payload),
        env=env,
        cwd=str(cwd) if cwd else None,
        capture_output=True, text=True,
        check=False, timeout=15,
    )


class TestValidateAcceptanceGate(unittest.TestCase):
    def test_empty_stdin_denies(self):
        # CRIT-4 audit 2026-06-07 : symmetric DENY without acceptance.json
        r = _run_hook({})
        self.assertEqual(r.returncode, 2)

    def test_bypass_env_allows(self):
        """SDD_ALLOW_ACCEPTANCE_BYPASS=1 → never blocks (audit-logged)."""
        payload = {"subagent_type": "qa", "stop_reason": "completed"}
        r = _run_hook(payload, {"SDD_ALLOW_ACCEPTANCE_BYPASS": "1"})
        self.assertEqual(r.returncode, 0)

    def test_no_projects_under_src_denies(self):
        """Empty workspace/output/src/ + no acceptance.json → DENY (CRIT-4)."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create empty .claude marker so paths resolution finds repo root
            (root / ".claude").mkdir()
            (root / "workspace" / "output" / "src").mkdir(parents=True)
            payload = {"subagent_type": "qa", "stop_reason": "completed"}
            r = _run_hook(payload, {"SDD_REPO_ROOT": str(root)}, cwd=root)
            self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
