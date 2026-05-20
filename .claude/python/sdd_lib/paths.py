"""Repo root detection + cross-platform path helpers."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    """UTC ISO-8601 timestamp with `Z` suffix, second precision.

    Canonical for status/audit/gate timestamps (gate_decide.py,
    validate_inline_rules.py).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_now_ms() -> str:
    """UTC ISO-8601 timestamp with millisecond precision + `Z` suffix.

    For event log timestamps (sdd_state.py — `events` table since v6.10)
    where ordering within the same second matters.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def normalize(path: str | os.PathLike[str]) -> str:
    """Normalize backslashes to forward slashes (Windows -> Unix style)."""
    return str(path).replace("\\", "/")


def repo_root() -> Path:
    """Locate the SDD_Pro repo root (containing `.claude/`).

    Resolution order :
      1. `$SDD_REPO_ROOT` env override (CI, tests, multi-repo setups)
      2. Walk up from CWD looking for a directory containing `.claude/`
      3. Walk up from this file's location (CWD-independent fallback —
         fixes scripts called from outside the repo tree, ex. background
         agents, MCP server, ad-hoc REPL from /tmp)
      4. Final fallback : CWD (preserves legacy behaviour if every other
         strategy fails — caller will get a clear FileNotFoundError later)
    """
    override = os.environ.get("SDD_REPO_ROOT")
    if override:
        p = Path(override).resolve()
        if (p / ".claude").is_dir():
            return p

    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".claude").is_dir():
            return parent

    # CWD-independent fallback : walk up from this file's location.
    # paths.py lives in `<repo>/.claude/python/sdd_lib/paths.py`, so the
    # repo root is the 3rd parent (3 levels up from this file).
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".claude").is_dir():
            return parent

    return cur


def relative_to_root(absolute: str | os.PathLike[str], root: Path | None = None) -> str:
    """Return path relative to repo root, normalized to forward slashes."""
    if root is None:
        root = repo_root()
    abs_path = Path(absolute).resolve()
    try:
        rel = abs_path.relative_to(root)
        return normalize(rel)
    except ValueError:
        return normalize(abs_path)
