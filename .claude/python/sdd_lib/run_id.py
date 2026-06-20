"""SDD_Pro — Stable run_id resolution for hook telemetry.

Background
----------
Hooks `preflight_cost_cap.py`, `record_token_usage.py` and
`audit_file_ownership.py` consume `SDD_RUN_ID` and `SDD_DISPATCH_START_TS`
env vars to scope their telemetry to the current pipeline invocation. If
those env vars are unset (no orchestrating command sourced them), the
hooks fall back to a "today window" or "now-5min" — degraded but safe.

The degraded fallback breaks down when **2 parallel `/sdd-full` runs**
share the same window : their token_usage rows collide and the cost_cap
gate sees the sum rather than per-run usage.

This module provides a deterministic resolver :

1. If `SDD_RUN_ID` is set in env → use it verbatim.
2. Else look for a fresh marker file `.sys/.state/run-id.current` whose
   mtime is within `SDD_RUN_ID_TTL_SECONDS` (default 3 h).
3. Else generate a fresh `run_id = {YYYYMMDDTHHmmss}-{rand4}`, persist
   the marker file, and return it.

The marker file is a simple text file with the run_id on a single line.
Concurrent processes that all call `get_or_create_run_id()` within the
TTL window will see the same id (first-writer-wins via atomic_write).
"""

from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from .atomic_write import atomic_write_text
from .paths import repo_root

_RUN_ID_TTL_SECONDS = int(os.environ.get("SDD_RUN_ID_TTL_SECONDS", "10800"))  # 3 h default


def _marker_path() -> Path:
    """Return path to the run_id marker file (workspace-scoped).

    Uses `repo_root()` which honors `$SDD_REPO_ROOT` and falls back to a
    CWD walk → file-location walk → CWD. Bug fix v7.0.0-alpha 2026-05-21 :
    previous import `find_project_root` did not exist in `paths.py`,
    causing `preflight_cost_cap.py` to crash on every hook invocation
    (eager import). `record_token_usage.py` masked the same bug with a
    try/except, leading to silent `run_id IS NULL` rows in the DB.
    """
    return repo_root() / "workspace" / "output" / ".sys" / ".state" / "run-id.current"


def _generate_run_id() -> str:
    """Generate a fresh ISO-8601-compact run_id with 4-char random suffix."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{ts}-{secrets.token_hex(2)}"


def get_or_create_run_id(force_new: bool = False) -> str:
    """Resolve a stable run_id for the current pipeline invocation.

    Order of precedence (default `force_new=False`):
        1. Env var `SDD_RUN_ID` (set by orchestrating command)
        2. Fresh marker file (within TTL)
        3. Newly generated id (persisted as marker)

    If `force_new=True` (called by `sdd_state.py new-run` when starting a
    fresh pipeline) : bypass env + marker lookup, generate a new id and
    overwrite the marker so subsequent hook invocations resolve to the
    same value (Sprint 1.1 fix 2026-06-06 — was generating uuid that hooks
    never saw, breaking token_usage→runs FK link).

    Returns the run_id as a string. Always succeeds (never raises) —
    fall through to a fresh id on any I/O error.
    """
    marker = _marker_path()

    if not force_new:
        env_id = os.environ.get("SDD_RUN_ID", "").strip()
        if env_id:
            return env_id
        try:
            if marker.exists():
                age = time.time() - marker.stat().st_mtime
                if age < _RUN_ID_TTL_SECONDS:
                    cached = marker.read_text(encoding="utf-8").strip()
                    if cached:
                        return cached
        except OSError:
            pass  # fall through to generation

    new_id = _generate_run_id()
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(marker, new_id + "\n")
    except OSError:
        pass  # best-effort persistence; return the id regardless
    return new_id


def get_or_create_dispatch_start_ts() -> str:
    """Resolve a stable dispatch start timestamp (ISO-8601 UTC).

    Used by `audit_file_ownership.py` to scope the modified-files glob.
    Falls back to "now" if env var unset and no marker file present.
    """
    env_ts = os.environ.get("SDD_DISPATCH_START_TS", "").strip()
    if env_ts:
        return env_ts
    # Reuse the run_id marker's mtime as the dispatch start (good enough
    # for ownership-audit scoping — same pipeline = same start window).
    marker = _marker_path()
    try:
        if marker.exists():
            mt = datetime.fromtimestamp(marker.stat().st_mtime, tz=timezone.utc)
            return mt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
