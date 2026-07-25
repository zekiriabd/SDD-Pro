"""Backward-compat shim: legacy `.claude/python/_hook` -> `.sdd/python/_hook`.

Why this file exists (2026-07-25) :
- The SSoT for Python code moved from `.claude/python/` to `.sdd/python/`
  during Phase 2 of MIGRATION-PLAN-multi-harness-multi-provider.md
  (branch `refactor/sdd-move-common`, ~331 scripts relocated).
- `.claude/settings.json` still references the legacy path in 20 hook
  commands (PreToolUse/PostToolUse/SubagentStop/SessionStart/Stop) via
  `sys.path.insert(0, r+'/.claude/python'); import _hook`.
- Without this shim, every hook fails silently at import with
  `ModuleNotFoundError: No module named '_hook'` and *all* runtime
  protections (protect_framework, enforce_tdd, preflight_cost_cap,
  block_env_bypass, enforce_two_stage_auditor, audit_file_ownership,
  session_start, framework_smoke Stop) become doc-only.

The shim loads the real `.sdd/python/_hook.py` by explicit path
(bypasses `sys.modules['_hook'] == shim`), then re-exports `run` so
that `_hook.run('sdd_hooks.protect_framework')` continues to work
verbatim. No settings.json edit required.

Roadmap : once settings.json is updated to reference `.sdd/python/`
directly (v7.1), this shim can be deleted. Anti-rot guard : the shim
is content-stable — it should never grow logic. All hook behaviour
lives in `.sdd/python/_hook.py` (the authoritative launcher).
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_SHIM = pathlib.Path(__file__).resolve()
_REPO = _SHIM.parent.parent.parent  # .claude/python/_hook.py -> repo root
_SDD_PY = _REPO / ".sdd" / "python"

# Ensure sdd_hooks/sdd_admin/sdd_lib are importable when the real launcher
# forwards to runpy.run_module('sdd_hooks.X').
_sdd_py_str = str(_SDD_PY)
if _sdd_py_str not in sys.path:
    sys.path.insert(0, _sdd_py_str)

# Load the real _hook by explicit path — bypasses sys.modules['_hook']
# which currently points to this shim.
_real_path = _SDD_PY / "_hook.py"
if not _real_path.is_file():
    raise ImportError(
        f"SDD_Pro shim: real _hook.py not found at {_real_path}. "
        "Repo layout may be broken — expected .sdd/python/_hook.py."
    )
_spec = importlib.util.spec_from_file_location("_hook_real", _real_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

# Public API re-export — the only symbol used by settings.json hook commands.
run = _mod.run  # noqa: F401
find_repo_root = _mod.find_repo_root  # noqa: F401  (used by a few tests)
