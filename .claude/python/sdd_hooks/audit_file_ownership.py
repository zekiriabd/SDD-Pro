#!/usr/bin/env python3
"""SDD_Pro SubagentStop hook.

Audits the matrice file-ownership.md §1 after each sub-agent dispatch.
For files modified during the dispatch window, checks the path matches
one of the "Owner" patterns allowed for that agent.

- Detect agent via input JSON (`tool_input.subagent_type`)
- Glob files modified since env $SDD_DISPATCH_START_TS (ISO 8601),
  fallback to last 5 minutes
- Append violations to workspace/output/.sys/.audit/ownership-violations.log
- Silent on chat (minimal-verbosity), Tech Lead consults log post-batch
- Non-blocking (always exit 0)

Migrated from .claude/scripts/audit-file-ownership.ps1 (2026-05-13).
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.hook_input import get_subagent_type, read_hook_input  # noqa: E402
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402


# Matrix extracted from file-ownership.md §1 (must stay in sync)
OWNERSHIP_MATRIX: dict[str, list[str]] = {
    "po": [
        r"^workspace/output/us/.+\.md$",
        r"^workspace/output/\.sys/\.context/constitution\.md$",  # append-only §3 §2
    ],
    "arch": [
        r"^workspace/output/src/[^/]+\.sln$",
        r"^workspace/output/src/[^/]+/(\w+\.csproj|package\.json|pyproject\.toml|build\.gradle.*)$",
        r"^workspace/output/src/[^/]+/Entities/.+",
        r"^workspace/output/src/[^/]+/CLAUDE\.md$",
        r"^workspace/output/db/.+",
        r"^workspace/output/\.sys/\.context/(constitution\.md|adrs/.+)$",
    ],
    "dev-backend": [
        r"^workspace/output/src/[^/]+/(Services|Endpoints|DTOs|Mappers|Validators|Controllers)/.+",
        r"^workspace/output/src/[^/]+/Program\.cs$",
        r"^workspace/output/src/[^/]+/Models/.+",
        r"^workspace/output/plans/.+\.back\.md$",
        r"^workspace/output/\.sys/\.context/adrs/ADR-.+\.md$",
    ],
    "dev-frontend": [
        r"^workspace/output/src/[^/]+/(Pages|Components|Layouts|Auth)/.+",
        r"^workspace/output/src/[^/]+/wwwroot/.+",
        r"^workspace/output/src/[^/]+/Program\.cs$",
        r"^.+\.razor\.css$",
        r"^workspace/output/plans/.+\.front\.md$",
        r"^workspace/output/\.sys/\.context/adrs/ADR-.+\.md$",
    ],
    "qa": [
        r"^workspace/output/src/.+\.Tests/.+",
        r"^workspace/output/src/.+/__tests__/.+",
        r"^workspace/output/src/.+\.(FEAT|test)\.(ts|tsx|js|jsx)$",
        r"^workspace/output/src/.+(Test|FEAT)\.kt$",
        r"^workspace/output/src/.+test_.+\.py$",
        r"^workspace/output/qa/feat-.+/(report\.md|coverage\.json|quality\.json|api-tests\.(json|md))$",
    ],
    # `dashboard` retiré v7.0.0 (governance-major-auditors-trim) — remplacé par
    # script déterministe index_adrs.py. Aucune entrée matrice nécessaire.
    "elicitor": [
        r"^workspace/input/feats/.+\.md$",  # append-only
        r"^workspace/output/\.sys/\.context/constitution\.md$",  # append-only §7
    ],
}

# Paths to ignore during ownership audit
IGNORE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.sys/\.audit/"),
    re.compile(r"\.sys/\.state/"),
    re.compile(r"\.tmp$"),
)

# Pre-compiled ownership patterns (M7 fix v7.0.0-alpha 2026-06-05).
# Previously these were re.compile()d inside main() on every SubagentStop —
# 76 patterns × ~6-10 invocations per /sdd-full = wasted CPU on hot path.
# Module-level cache : compiled once at import, reused across invocations.
_COMPILED_OWNERSHIP: dict[str, list[re.Pattern[str]]] = {
    agent: [re.compile(p) for p in patterns]
    for agent, patterns in OWNERSHIP_MATRIX.items()
}


def _parse_cutoff() -> datetime:
    """Return cutoff datetime: env $SDD_DISPATCH_START_TS, marker file, or now-5min.

    v7.0.1 : delegated resolution to sdd_lib/run_id helper which scopes the
    cutoff to the current run's start (run_id marker mtime) when the env
    var is not explicitly set. Final fallback remains now-5min for safety.
    """
    raw = os.environ.get("SDD_DISPATCH_START_TS", "").strip()
    if not raw:
        try:
            from sdd_lib.run_id import get_or_create_dispatch_start_ts
            raw = get_or_create_dispatch_start_ts()
        except Exception:
            return datetime.now(timezone.utc) - timedelta(minutes=5)
    # Accept ISO 8601 with optional 'Z' suffix
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(timezone.utc) - timedelta(minutes=5)


# Directories to skip during the workspace walk. These are either
# vendor-managed (node_modules), build artifacts (dist/build/bin/obj/target),
# venvs, caches, or VCS metadata. Including them in the walk wasted seconds
# per SubagentStop on real projects with 50k+ files in node_modules.
# Audit P0-doc 2026-06-05.
_AUDIT_SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", "dist", "build", "bin", "obj", "out", "target",
    ".venv", "venv", ".tox", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".gradle", ".angular", ".next", ".nuxt", ".svelte-kit",
    ".vite", ".turbo", "coverage", ".nyc_output",
    ".git", ".hg", ".svn",
    ".idea", ".vscode",
})


def _iter_modified_files_git(workspace: Path, cutoff: datetime) -> list[Path] | None:
    """v7.0.1 audit REFACTOR-2 2026-06-08 — fast-path via `git diff`.

    When the workspace is inside a git repository, prefer `git diff --name-only`
    (~10-50ms regardless of project size) over `os.walk` (~100ms-3s scaling
    with project size). The diff covers both staged + unstaged + untracked
    files modified since the cutoff timestamp.

    Returns :
      - list[Path] of modified files (filtered by cutoff mtime) if git
        invocation succeeds and yields meaningful results
      - None if git is unavailable, workspace not a repo, or anything
        else goes wrong → fallback to `_iter_modified_files_walk`.

    Why use git diff vs --since :
      `--since=<timestamp>` works only with `git log`, not `git diff`.
      We list ALL diff entries then filter by mtime client-side. The
      diff is bounded by the working-tree state, so size is independent
      of history depth (orders of magnitude smaller than walk on a
      project with node_modules).

    Why fallback to walk :
      User workspaces may not be git repos (some `/sdd-bootstrap` flows
      generate output outside git tracking). Hook must remain functional
      either way — git diff is a fast-path optimization, not a hard
      dependency.
    """
    import subprocess
    cutoff_ts = cutoff.timestamp()
    try:
        # Probe : is this a git repo ?
        # --is-inside-work-tree is the canonical git command for this check.
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            return None
        # Collect modified + staged + untracked files.
        # --untracked-files=all surfaces files agents wrote without staging.
        # --porcelain=v1 gives stable parseable output.
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all", "-z"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None
    # Parse `git status --porcelain -z` : each entry is
    # `XY filename\0` (no trailing newline thanks to -z). XY = 2-char
    # status code. Untracked files appear as `?? filename`.
    repo_root_path = workspace
    # Resolve repo root from probe response (we trust workspace is at/under it).
    out: list[Path] = []
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        # Skip the 2-char status code + 1 space ; rename entries use a
        # different format ("R src -> dst") but our subagents don't rename
        # tracked files so we can ignore that subtlety.
        if len(entry) < 4:
            continue
        rel = entry[3:]
        full = (repo_root_path / rel).resolve()
        try:
            # Filter by cutoff : git status only tells us WHAT changed,
            # not WHEN. We still mtime-check to scope to current dispatch.
            if full.is_file() and full.stat().st_mtime > cutoff_ts:
                out.append(full)
        except OSError:
            continue
    return out


def _iter_modified_files_walk(workspace: Path, cutoff: datetime) -> list[Path]:
    """Walk workspace/ and yield files modified after cutoff (fallback).

    Uses `os.walk(topdown=True)` with in-place dirs pruning to skip vendor
    directories (node_modules, .venv, build artifacts, VCS metadata). On a
    real project with 50k+ files under node_modules, this changes the
    SubagentStop latency from seconds to ~100ms.

    Renamed from `_iter_modified_files` (v7.0.1 audit REFACTOR-2) — the
    public API is now `_iter_modified_files` which tries git first then
    falls back to walk. Walk impl kept as fallback for non-git workspaces.
    """
    import os
    cutoff_ts = cutoff.timestamp()
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(workspace, topdown=True):
        # Prune: mutate dirnames in-place to skip vendor/build dirs.
        dirnames[:] = [d for d in dirnames if d not in _AUDIT_SKIP_DIRS]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                if full.stat().st_mtime > cutoff_ts:
                    out.append(full)
            except OSError:
                continue
    return out


def _iter_modified_files(workspace: Path, cutoff: datetime) -> list[Path]:
    """Yield files modified after cutoff. Tries git diff first, falls back to walk.

    v7.0.1 audit REFACTOR-2 2026-06-08 — fast-path via `git status` reduces
    SubagentStop latency from ~100-300ms (os.walk) to ~10-50ms (git status)
    on git-managed workspaces. Saves ~2-3 s/pipeline (14 subagent stops).
    """
    git_result = _iter_modified_files_git(workspace, cutoff)
    if git_result is not None:
        return git_result
    return _iter_modified_files_walk(workspace, cutoff)


def main() -> int:
    payload = read_hook_input()
    subagent = get_subagent_type(payload)
    if not subagent or subagent not in _COMPILED_OWNERSHIP:
        return HOOK_ALLOW
    allowed = _COMPILED_OWNERSHIP[subagent]  # M7 : reuse precompiled patterns

    root = repo_root()
    workspace = root / "workspace"
    if not workspace.is_dir():
        return HOOK_ALLOW
    cutoff = _parse_cutoff()
    modified = _iter_modified_files(workspace, cutoff)
    if not modified:
        return HOOK_ALLOW
    violations: list[str] = []
    for f in modified:
        try:
            rel = normalize(f.relative_to(root))
        except ValueError:
            continue

        if any(ign.search(rel) for ign in IGNORE_PATTERNS):
            continue

        if not any(pat.match(rel) for pat in allowed):
            violations.append(rel)

    if not violations:
        return HOOK_ALLOW
    audit_dir = root / "workspace" / "output" / ".sys" / ".audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    log_file = audit_dir / "ownership-violations.log"

    timestamp = datetime.now(timezone.utc).isoformat()
    with log_file.open("a", encoding="utf-8") as fh:
        for v in violations:
            fh.write(
                f"{timestamp} [FILE_OWNERSHIP] {subagent} wrote {v} "
                f"(pattern hors matrice ownership.md §1)\n"
            )

    # v7.0.0 audit hardening 2026-05-20 — mode resolution :
    #   - $SDD_AUDIT_OWNERSHIP_MODE = warn|strict|off
    #   - default : 'strict' in CI (any CI env var), 'warn' otherwise
    #
    # v7.0.1 audit P0 v2 (2026-06-08) — strict mode is now BLOCKING in CI
    # (HOOK_DENY = exit 2). Previously strict was only verbosity tweak +
    # exit 0 — which contradicted INVARIANTS.yml "file-ownership-matrix-enforced"
    # invariant (purely informational despite the load-bearing claim).
    #
    # Behavior matrix :
    #   strict + CI         → HOOK_DENY (exit 2, blocks SubagentStop)
    #   strict + interactive → WARN only, exit 0 (preserve dev ergonomics)
    #   warn                → WARN only, exit 0 (legacy non-blocking)
    #   off                 → silent, exit 0
    mode = (os.environ.get("SDD_AUDIT_OWNERSHIP_MODE") or "").strip().lower()
    is_ci = any(
        (os.environ.get(v, "").strip().lower() not in ("", "0", "false", "no"))
        for v in (
            "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
            "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
            "BITBUCKET_BUILD_NUMBER",
        )
    )
    if mode not in ("warn", "strict", "off"):
        mode = "strict" if is_ci else "warn"

    if mode != "off":
        msg_level = "ERROR" if mode == "strict" else "WARN"
        warn(
            f"{msg_level} audit-file-ownership : {subagent} a viole la matrice "
            f"ownership.md §1 ({len(violations)} fichier(s) hors perimetre) — "
            f"voir {log_file.relative_to(root).as_posix()}"
        )
        if mode == "strict":
            warn(f"CAUSE: [FILE_OWNERSHIP] cf. log ci-dessus pour la liste")
            warn(f"FIX: (a) corriger le prompt agent ou la matrice ownership.md")
            warn(f"     (b) bypass interactif : export SDD_AUDIT_OWNERSHIP_MODE=warn")
            # v7.0.1 P0 v2 : block in CI strict mode. Bypass via
            # SDD_AUDIT_OWNERSHIP_MODE=warn (audit-loggué dans hook stderr).
            if is_ci:
                warn(
                    f"     (c) CI BLOCKING : audit_file_ownership returns HOOK_DENY "
                    f"in strict mode CI (audit P0 v2 2026-06-08). Set "
                    f"SDD_AUDIT_OWNERSHIP_MODE=warn explicitly to bypass."
                )
                return HOOK_DENY

    return HOOK_ALLOW
if __name__ == "__main__":
    sys.exit(main())
