"""paths.py — Resolution helpers for sdd_reverse data files (P1.7 closure).

Centralizes path resolution to avoid fragile `Path(__file__).parent.parent / ...`
patterns scattered across scripts. Supports three discovery modes (in order
of precedence):

    1. Explicit env var override : `SDD_REVERSE_DATA_DIR`
       (useful for packaged installs, CI sandboxes, or symlinked layouts)

    2. Package-relative resolution : `Path(__file__).parent`
       (default — works when sdd_reverse/ is importable as a package)

    3. Repo-root walk : ascend from CWD looking for `.claude/python/sdd_reverse/`
       (fallback for execution from unusual working directories)

Public API:
    sdd_reverse_dir() -> Path           # sdd_reverse/ directory
    language_signatures_path() -> Path  # sdd_reverse/language_signatures.yml
    feat_reverse_template_path() -> Path  # sdd_reverse/feat.reverse.template.md
    parity_snapshots_path() -> Path     # sdd_reverse/_parity_snapshots.json

All helpers raise FileNotFoundError with a clear message if no candidate is
locatable — never return a non-existent path silently.
"""
from __future__ import annotations

import os
from pathlib import Path


_ENV_VAR = "SDD_REVERSE_DATA_DIR"


def _candidate_from_env() -> Path | None:
    value = os.environ.get(_ENV_VAR)
    if not value:
        return None
    p = Path(value).expanduser().resolve()
    return p if p.is_dir() else None


def _candidate_from_package() -> Path | None:
    """Resolve sdd_reverse/ relative to this file (paths.py lives in it)."""
    here = Path(__file__).resolve().parent
    return here if here.is_dir() else None


def _candidate_from_cwd_walk() -> Path | None:
    """Walk up from CWD looking for `.claude/python/sdd_reverse/`."""
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / ".claude" / "python" / "sdd_reverse"
        if candidate.is_dir():
            return candidate
    return None


def sdd_reverse_dir() -> Path:
    """Return the `sdd_reverse/` directory (containing data + helpers).

    Resolution order:
        1. $SDD_REVERSE_DATA_DIR if set and existing
        2. Path next to this module file
        3. Walk up from CWD looking for .claude/python/sdd_reverse/

    Raises:
        FileNotFoundError if none of the candidates resolves.
    """
    for resolver in (_candidate_from_env, _candidate_from_package, _candidate_from_cwd_walk):
        candidate = resolver()
        if candidate is not None:
            return candidate
    raise FileNotFoundError(
        f"sdd_reverse data directory not found. Set ${_ENV_VAR} or run from "
        "a directory under the SDD_Pro repo."
    )


def repo_root() -> Path:
    """Return the SDD_Pro repo root (the directory containing `.claude/`).

    Audit 2026-06-10 (anomalie env) : two reverse scripts resolved
    `workspace/...` relative to the CWD, which silently created parasite
    `workspace/` trees when invoked from `.claude/python/`. All workspace
    paths must anchor here instead.
    """
    return sdd_reverse_dir().resolve().parents[2]


def workspace_root(repo_root_path: Path | None = None) -> Path:
    """Resolve the workspace root: nested `repo/workspace`, else sibling.

    Mirrors ``sdd_lib.paths.workspace_root`` but kept dependency-free — the
    reverse module MUST NOT import from ``sdd_lib`` (isolation invariant,
    cf. ``reverse_smoke.py``). Prefers a nested ``repo/workspace``; falls back
    to a sibling ``repo/../workspace`` (split layout where the framework lives
    in a sub-folder and the project workspace is external to it).
    """
    root = Path(repo_root_path or repo_root()).resolve()
    nested = root / "workspace"
    if nested.is_dir():
        return nested
    sibling = root.parent / "workspace"
    if sibling.is_dir():
        return sibling
    return nested


def language_signatures_path() -> Path:
    """Return the path to `language_signatures.yml` (source of D1).

    Raises FileNotFoundError if the file does not exist at the resolved
    sdd_reverse directory.
    """
    p = sdd_reverse_dir() / "language_signatures.yml"
    if not p.is_file():
        raise FileNotFoundError(
            f"language_signatures.yml missing at {p}. Reverse pipeline "
            "cannot proceed without language detection signatures."
        )
    return p


def feat_reverse_template_path() -> Path:
    """Return the path to `feat.reverse.template.md` (ADV-9 isolated copy)."""
    p = sdd_reverse_dir() / "feat.reverse.template.md"
    if not p.is_file():
        raise FileNotFoundError(
            f"feat.reverse.template.md missing at {p}. ADV-9 requires the "
            "local copy — fallback to standard SDD_Pro template is forbidden."
        )
    return p


def parity_snapshots_path() -> Path:
    """Return the path to `_parity_snapshots.json` (ADV-16 drift detection)."""
    p = sdd_reverse_dir() / "_parity_snapshots.json"
    if not p.is_file():
        raise FileNotFoundError(
            f"_parity_snapshots.json missing at {p}. Drift detection "
            "(reverse_smoke.check_helper_parity_drift) requires it."
        )
    return p
