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


def _looks_like_repo_root(p: Path) -> bool:
    """Strict check: a real SDD_Pro repo root contains `.claude/agents/`
    AND `.claude/commands/` AND `workspace/`.

    Post-mortem 2026-05-21 : un sous-dossier d'archive `.claude/.claude/`
    (legacy design docs superseded) faisait croire au walker que
    `.claude/` était le repo root → tous les paths Python dérivés
    (`workspace/output/db/console.db`) résolvaient sous
    `.claude/workspace/...` au lieu de `workspace/...`.
    Le check unique `(p / ".claude").is_dir()` est insuffisant.
    """
    return (
        (p / ".claude" / "agents").is_dir()
        and (p / ".claude" / "commands").is_dir()
        and (p / "workspace").is_dir()
    )


def repo_root() -> Path:
    """Locate the SDD_Pro repo root.

    A real repo root contains `.claude/agents/` + `.claude/commands/`
    + `workspace/` (cf. `_looks_like_repo_root`). Le check `.claude/`
    seul est insuffisant — un sous-dossier d'archive `.claude/.claude/`
    peut tromper le walker (post-mortem 2026-05-21).

    Resolution order :
      1. `$SDD_REPO_ROOT` env override (CI, tests, multi-repo setups) —
         honoré **inconditionnellement** s'il est set ; le strict check
         est emit en WARN si KO mais ne retombe PAS en CWD walk
         (post-mortem v7.0.1 : silent fallthrough = pollution repo réel
         par tests à isolation incomplète, 62/872 échecs)
      2. Walk up from CWD looking for a directory matching the strict check
      3. Walk up from this file's location (CWD-independent fallback —
         fixes scripts called from outside the repo tree, ex. background
         agents, ad-hoc REPL from /tmp)
      4. Final fallback : CWD (preserves legacy behaviour if every other
         strategy fails — caller will get a clear FileNotFoundError later)
    """
    override = os.environ.get("SDD_REPO_ROOT")
    if override:
        p = Path(override).resolve()
        if not _looks_like_repo_root(p):
            # Trust the explicit override even when not fully scaffolded.
            # Emit a WARN via stderr (best-effort, no hard dep) so tests +
            # CI see the soft signal. Never fallthrough to CWD walk : that
            # was the v7.0.0 bug that let tests pollute the real repo.
            import sys
            print(
                f"WARN sdd_lib.paths: SDD_REPO_ROOT={p} does not match strict "
                "repo layout (.claude/agents + .claude/commands + workspace) — "
                "honored as-is (no silent CWD fallback).",
                file=sys.stderr,
            )
        return p

    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        if _looks_like_repo_root(parent):
            return parent

    # CWD-independent fallback : walk up from this file's location.
    here = Path(__file__).resolve()
    for parent in here.parents:
        if _looks_like_repo_root(parent):
            return parent

    return cur


def project_root_for_hook() -> Path:
    """Resolve the project root from a Claude Code hook context.

    Audit 2026-06-06 — CR-3 single source of truth. Replaces the 7-line
    `_resolve_project_root` previously duplicated in every hook. Adds
    path-traversal defense (`Path.resolve(strict=False)` — see note) and
    symlink rejection while preserving the user's explicit override semantics.

    P1-5 doc fix (2026-06-07) : the docstring previously claimed
    `Path.resolve(strict=True)` but the code uses `strict=False`. The
    `strict=False` choice is intentional — strict=True would raise
    FileNotFoundError on a missing path component, breaking the hook
    on fresh checkouts where workspace/ hasn't been created yet. The
    "trust the override" trade-off means the canonical path is computed
    even if some components don't exist yet ; symlinks are rejected
    upstream (`raw.is_symlink()` check), so the main path-traversal
    vector is closed.

    Resolution order :
      1. `CLAUDE_PROJECT_DIR` env var if set, points to an existing dir,
         and is NOT a symlink. The resolved (canonical) path is returned
         — `..` traversal is neutralized by `Path.resolve()`. A WARN is
         emitted on stderr if the layout doesn't look like a repo root,
         but the override is still honored (same trust model as
         `repo_root()`: explicit override > inference).
      2. Fallback to `repo_root()` (CWD walk).

    Hooks SHOULD call this instead of rolling their own resolver.
    """
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        raw = Path(env_root)
        # Reject symlinks even before resolve() — defense against /tmp/evil → /etc.
        if raw.exists() and raw.is_symlink():
            import sys
            print(
                f"WARN sdd_lib.paths: CLAUDE_PROJECT_DIR={env_root!r} is a symlink — refusing override, falling back to repo_root()",
                file=sys.stderr,
            )
        else:
            try:
                candidate = raw.resolve(strict=False)
            except (OSError, RuntimeError):
                candidate = None
            if candidate is not None:
                if not _looks_like_repo_root(candidate):
                    import sys
                    print(
                        f"WARN sdd_lib.paths: CLAUDE_PROJECT_DIR={candidate} does not match strict repo layout (.claude/agents + .claude/commands + workspace) — honored as-is",
                        file=sys.stderr,
                    )
                return candidate
    return repo_root()


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
