"""SDD_Pro stdlib unittest suite for critical scripts.

Run from repo root (any of):
    python -m unittest discover -s .claude/python/tests -t .claude/python -v
    python -m pytest .claude/python/tests/
    python .claude/python/tests/test_<name>.py

The `-t .claude/python` matters: it sets the top-level package
directory so that `sdd_scripts.*`, `sdd_hooks.*`, etc. resolve.
Without it, unittest tries to import `.claude.python.tests.X`
which is invalid (dots in directory names).

This __init__ also adds `.claude/python/` to sys.path so that tests
work regardless of the invocation mode (pytest discovery via
conftest.py, unittest discover, direct script execution).

Total: 59 tests across 5 files.
"""
import sys
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))
