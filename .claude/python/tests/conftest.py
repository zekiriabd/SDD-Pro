"""pytest auto-discovery: ensure `.claude/python/` is on sys.path.

Pytest imports this file before any test collection. It guarantees
that `from sdd_scripts.X import Y` works regardless of pytest's cwd
or invocation mode.
"""
import sys
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))
