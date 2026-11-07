"""Guard for the framework_smoke pytest-smoke pre-selection (audit timing 2026-11-07).

`framework_smoke._check_pytest_smoke` passes every test module whose text never
names `mark.smoke` as `--ignore`, so pytest does not import ~180 modules just to
deselect them. That optimisation is only sound if the text scan is a SUPERSET
of the modules that really hold smoke-marked tests. This test proves it against
a full, un-filtered `pytest -m smoke --collect-only` — if a module ever gets the
marker some other way (conftest hook, alias, getattr…), it fails here instead of
silently shrinking the smoke gate.

Deliberately NOT marked `smoke` : it runs a full collection (~3-4 s).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_admin.framework_smoke import (  # noqa: E402
    _pytest_smoke_cmd,
    _pytest_smoke_env,
    smoke_test_modules,
)

_TESTS_DIR = Path(__file__).resolve().parent


def _collected_smoke_modules(extra_args: list[str]) -> set[str]:
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "smoke", "--collect-only", "-q",
         "-p", "no:cacheprovider", *extra_args],
        cwd=str(_PY_ROOT), env=_pytest_smoke_env(),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    mods: set[str] = set()
    for line in res.stdout.splitlines():
        # `-q` → `tests/test_x.py::T::t` ; `-qq` → `tests/test_x.py: 12`
        m = re.match(r"^(\S*test_[\w]+\.py)(?:::|:\s*\d+)", line.strip())
        if m:
            mods.add(Path(m.group(1)).name)
    return mods


def test_text_scan_is_a_superset_of_really_smoke_marked_modules():
    scanned = {p.name for p in smoke_test_modules(_TESTS_DIR)[0]}
    collected = _collected_smoke_modules([str(_TESTS_DIR)])
    assert collected, "full collection found no smoke test (parser drift?)"
    missed = sorted(collected - scanned)
    assert not missed, (
        f"modules carrying smoke tests that the text pre-scan would --ignore : "
        f"{missed} — widen `framework_smoke._SMOKE_MARK_RE`."
    )


def test_smoke_command_selects_the_same_modules_as_a_full_collection():
    cmd = _pytest_smoke_cmd(_TESTS_DIR)
    ignores = [a for a in cmd if a.startswith("--ignore=")]
    assert ignores, "pre-selection inactive (no --ignore emitted)"
    filtered = _collected_smoke_modules(ignores + [str(_TESTS_DIR)])
    full = _collected_smoke_modules([str(_TESTS_DIR)])
    assert filtered == full


def test_smoke_env_disables_only_plugin_autoload():
    env = _pytest_smoke_env()
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env.get("PATH") == os.environ.get("PATH")
