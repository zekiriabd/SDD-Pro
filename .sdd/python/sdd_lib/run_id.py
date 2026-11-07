"""SDD_Pro — Stable run_id resolution for hook telemetry.

Background
----------
Hooks `preflight_cost_cap.py`, `record_token_usage.py` and
`audit_file_ownership.py` consume `SDD_RUN_ID` and `SDD_DISPATCH_START_TS`
env vars to scope their telemetry to the current pipeline invocation. If
those env vars are unset (no orchestrating command sourced them), the
hooks fall back to a marker file — degraded but safe.

The degraded fallback used to be a SINGLE marker `.sys/.state/run-id.current`
with a 3 h TTL. Audit « fiabilité des données et des états » (2026-11-07) :
**2 sessions Claude Code parallèles** partageaient ce marker (leurs
`token_usage` se mélangeaient, le cost cap voyait la somme), et le TTL
remettait silencieusement le cost cap à zéro toutes les 3 h.

Resolver (deterministic) :

1. If `SDD_RUN_ID` is set in env → use it verbatim.
2. Else resolve a **session id** : the explicit `session_id=` argument
   (hook payloads carry `session_id` — hooks should pass it), else
   `$CLAUDE_SESSION_ID`, else `$SDD_SESSION_ID`. With a session id the
   marker is **per session** (`.sys/.state/run-id.<session_id>`), has **no
   TTL** : a run ends when it is explicitly closed (`console_db.run_end` /
   `sdd_scripts/run_close.py` / `sdd_state.py end-run`, which also clears
   the marker) or when the session changes (new marker).
3. Else (no session id anywhere — legacy compat) : shared marker
   `run-id.current` whose mtime must be within `SDD_RUN_ID_TTL_SECONDS`
   (default **24 h**, was 3 h) ; a WARN is emitted on stderr once per
   process so the degraded mode is never silent.
4. Else generate a fresh `run_id = {YYYYMMDDTHHmmss}-{rand4}`, persist the
   marker file, and return it.

The marker file is a simple text file with the run_id on a single line.
Concurrent processes of the same session that all call
`get_or_create_run_id()` will see the same id (first-writer-wins via
atomic_write).
"""

from __future__ import annotations

import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .atomic_write import atomic_write_text
from .paths import repo_root, workspace_root

#: Legacy (session-less) marker TTL. 24 h since audit 2026-11-07 (was 3 h —
#: cost cap silently reset mid-run on long pipelines).
_RUN_ID_TTL_SECONDS = int(os.environ.get("SDD_RUN_ID_TTL_SECONDS", str(24 * 3600)))

#: Env vars consulted (in order) when no explicit `session_id` is given.
SESSION_ID_ENV_VARS = ("CLAUDE_SESSION_ID", "SDD_SESSION_ID")

_LEGACY_MARKER_NAME = "run-id.current"
_SESSION_MARKER_PREFIX = "run-id."
_SESSION_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_SESSION_ID_MAX_LEN = 80

_legacy_warned = False


def _state_dir() -> Path:
    """`workspace/.sys/.state/` — uses `repo_root()` ($SDD_REPO_ROOT > walks)."""
    return workspace_root(repo_root()) / ".sys" / ".state"


def resolve_session_id(session_id: str | None = None) -> str | None:
    """Return a filesystem-safe session id, or None when none is known.

    Precedence : explicit argument > `$CLAUDE_SESSION_ID` > `$SDD_SESSION_ID`.
    The value is sanitised (`[A-Za-z0-9_.-]`, ≤ 80 chars) because it becomes
    part of a file name under `.sys/.state/`.
    """
    raw = (session_id or "").strip()
    if not raw:
        for var in SESSION_ID_ENV_VARS:
            raw = os.environ.get(var, "").strip()
            if raw:
                break
    if not raw:
        return None
    safe = _SESSION_ID_SAFE_RE.sub("-", raw).strip("-.")[:_SESSION_ID_MAX_LEN]
    return safe or None


def _marker_path(session_id: str | None = None) -> Path:
    """Marker file for the given (resolved) session, or the legacy shared one.

    Bug fix v7.0.0-alpha 2026-05-21 : previous import `find_project_root`
    did not exist in `paths.py`, causing `preflight_cost_cap.py` to crash on
    every hook invocation (eager import).
    """
    if session_id:
        return _state_dir() / f"{_SESSION_MARKER_PREFIX}{session_id}"
    return _state_dir() / _LEGACY_MARKER_NAME


def _generate_run_id() -> str:
    """Generate a fresh ISO-8601-compact run_id with 4-char random suffix."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{ts}-{secrets.token_hex(2)}"


def _warn_legacy_once() -> None:
    global _legacy_warned
    if _legacy_warned:
        return
    _legacy_warned = True
    print(
        "WARN sdd_lib.run_id: aucun session_id (argument, $CLAUDE_SESSION_ID, "
        "$SDD_SESSION_ID) — marker partagé `run-id.current` avec TTL "
        f"{_RUN_ID_TTL_SECONDS // 3600} h : des sessions parallèles peuvent "
        "partager le même run_id (cost cap cumulé). Passer session_id= depuis "
        "le payload hook.",
        file=sys.stderr,
    )


def _read_marker(marker: Path, *, ttl_seconds: int | None) -> str | None:
    """Return the marker's run_id if present (and fresh when ttl given)."""
    try:
        if not marker.exists():
            return None
        if ttl_seconds is not None:
            age = time.time() - marker.stat().st_mtime
            if age >= ttl_seconds:
                return None
        cached = marker.read_text(encoding="utf-8").strip()
        return cached or None
    except OSError:
        return None


def get_or_create_run_id(
    force_new: bool = False,
    session_id: str | None = None,
) -> str:
    """Resolve a stable run_id for the current pipeline invocation.

    Order of precedence (default `force_new=False`):
        1. Env var `SDD_RUN_ID` (set by orchestrating command)
        2. Session marker `run-id.<session_id>` (no TTL) when a session id is
           known — `session_id=` argument, `$CLAUDE_SESSION_ID`, `$SDD_SESSION_ID`
        3. Legacy shared marker `run-id.current` (TTL 24 h, WARN stderr)
        4. Newly generated id (persisted as marker)

    If `force_new=True` (called by `sdd_state.py new-run` when starting a
    fresh pipeline) : bypass env + marker lookup, generate a new id and
    overwrite the marker so subsequent hook invocations resolve to the
    same value (Sprint 1.1 fix 2026-06-06 — was generating uuid that hooks
    never saw, breaking token_usage→runs FK link).

    Returns the run_id as a string. Always succeeds (never raises) —
    fall through to a fresh id on any I/O error.
    """
    sid = resolve_session_id(session_id)
    marker = _marker_path(sid)

    if not force_new:
        env_id = os.environ.get("SDD_RUN_ID", "").strip()
        if env_id:
            return env_id
        if sid:
            cached = _read_marker(marker, ttl_seconds=None)
        else:
            _warn_legacy_once()
            cached = _read_marker(marker, ttl_seconds=_RUN_ID_TTL_SECONDS)
        if cached:
            return cached

    new_id = _generate_run_id()
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(marker, new_id + "\n")
    except OSError:
        pass  # best-effort persistence; return the id regardless
    return new_id


def clear_run_id_marker(session_id: str | None = None, *, run_id: str | None = None) -> bool:
    """Remove the marker of a closed run (session-scoped, or legacy).

    Called by `run_close.py` / `sdd_state.py end-run` so the next hook of the
    same session opens a NEW run instead of reviving the closed one. When
    `run_id` is given, the marker is only removed if it still holds that id
    (never delete a marker already re-pointed to a newer run).
    Returns True if a marker was removed.
    """
    sid = resolve_session_id(session_id)
    marker = _marker_path(sid)
    try:
        if not marker.exists():
            return False
        if run_id is not None:
            current = marker.read_text(encoding="utf-8").strip()
            if current != run_id:
                return False
        marker.unlink()
        return True
    except OSError:
        return False


def get_or_create_dispatch_start_ts(session_id: str | None = None) -> str:
    """Resolve a stable dispatch start timestamp (ISO-8601 UTC).

    Used by `audit_file_ownership.py` to scope the modified-files glob.
    Falls back to "now" if env var unset and no marker file present.
    """
    env_ts = os.environ.get("SDD_DISPATCH_START_TS", "").strip()
    if env_ts:
        return env_ts
    # Reuse the run_id marker's mtime as the dispatch start (good enough
    # for ownership-audit scoping — same pipeline = same start window).
    marker = _marker_path(resolve_session_id(session_id))
    try:
        if marker.exists():
            mt = datetime.fromtimestamp(marker.stat().st_mtime, tz=timezone.utc)
            return mt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
