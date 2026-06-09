"""Smoke test : every sdd_hooks/*.py is importable (audit CTO 2026-06-09 #24).

Catch silent import-time regressions in any hook script. The hooks are
invoked by Claude Code via `_hook.run('sdd_hooks.X')` — if `X.py` has an
import error, the hook fails silently at runtime and the protection it
implements is bypassed without warning.

Strategy : enumerate `sdd_hooks/*.py` (excluding `__init__.py`), import
each one via importlib. Any ImportError / SyntaxError / NameError fails
the test with a clear pointer to the offending file.

Complements `test_critical_scripts_smoke.py` (which targets `sdd_admin/`
and `sdd_scripts/`).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

HOOKS_DIR = _PY_ROOT / "sdd_hooks"


def _discover_hook_modules() -> list[str]:
    """Return list of module names under sdd_hooks/ (excludes __init__)."""
    if not HOOKS_DIR.is_dir():
        return []
    return sorted(
        f"sdd_hooks.{p.stem}"
        for p in HOOKS_DIR.glob("*.py")
        if p.stem != "__init__"
    )


_HOOK_MODULES = _discover_hook_modules()


def test_at_least_one_hook_discovered():
    """Defensive : ensures the discovery glob worked (catches future relayouts)."""
    assert len(_HOOK_MODULES) > 0, (
        f"No hook modules found under {HOOKS_DIR} — discovery is broken."
    )


@pytest.mark.parametrize("module_name", _HOOK_MODULES)
def test_hook_module_importable(module_name: str):
    """Each hook module must import cleanly (no ImportError / SyntaxError).

    This catches : missing imports, circular deps, top-level NameError,
    syntax regressions introduced by refactor, removed sdd_lib helpers.
    """
    try:
        # importlib.import_module is preferred over `import X` for parameterized tests
        # — it propagates import errors instead of silently caching None.
        importlib.import_module(module_name)
    except Exception as e:  # pragma: no cover — explicit failure
        pytest.fail(
            f"Hook `{module_name}` failed to import: {type(e).__name__}: {e}\n"
            f"  Fix: inspect {HOOKS_DIR / (module_name.split('.')[-1] + '.py')}"
        )
