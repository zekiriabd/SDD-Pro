#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Edit|Write|MultiEdit).

Detects when an agent targets a framework-owned file.

Mode (v7.0.0 audit hardening 2026-05-20) :
  - Interactive (default) : WARN on stderr, exit 0 (Tech Lead may
    deliberately edit framework in dev — current behavior preserved).
  - CI auto-detect     : BLOCKING exit 2 (an agent must NEVER modify
    framework in CI — that's a regression vector).
  - $SDD_PROTECT_FRAMEWORK_MODE = warn|strict|off : explicit override.

Migrated from .claude/hooks/protect-framework.ps1 (2026-05-13).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.ci import is_ci  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import get_file_path, read_hook_input  # noqa: E402
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


# Framework-owned paths, relative to repo root. P1-5 fix 2026-06-07 :
# was substring-matched via `any(p in normalized_path for p in ...)` which
# could (a) false-positive on a project file like `workspace/output/src/X/.claude/rules/foo.md`,
# (b) false-negative on `..\..\.claude\rules\x.md` paths after partial normalization.
# Now we canonicalize via `Path.resolve()` + `relative_to(repo_root)` for
# strict path-prefix matching.
FRAMEWORK_OWNED: tuple[str, ...] = (
    ".claude/rules/",
    ".claude/stacks/",
    ".claude/agents/",
    ".claude/templates/",
    ".claude/commands/",
    ".claude/skills/",
    ".claude/python/",
    ".claude/loader.yml",
    ".claude/CLAUDE.md",
    ".claude/docs/MIGRATION.md",
    ".claude/docs/CHANGELOG.md",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/config.base.yml",
)


def _is_framework_path(file_path: str, repo: Path) -> bool:
    """Strict check : file_path resolves to a path inside one of FRAMEWORK_OWNED
    prefixes, RELATIVE to repo root. Defense against substring false-positives
    (workspace/output/src/X/.claude/... no longer matches) and path-traversal
    false-negatives (..\\..\\.claude\\... after resolve() lives outside repo
    and is filtered out).

    CRITICAL fix (2026-06-07) : relative `file_path` MUST be resolved against
    `repo`, NOT against `Path.cwd()`. The previous implementation used
    `Path(file_path).resolve()` which silently anchors to CWD — if pytest /
    background agent / a `cd .claude/python` shell invoked the hook, a user
    edit on `workspace/output/src/MyApp/x.tsx` would resolve to
    `<repo>/.claude/python/workspace/output/src/MyApp/x.tsx`, whose
    `relative_to(repo)` starts with `.claude/python/` → false positive +
    [FRAMEWORK_PROTECTED] in strict mode → CI blocks ALL user edits.
    Reproduced by tests `test_user_file_*_in_strict` / `..._passes_silently`.
    """
    try:
        p = Path(file_path)
        # Anchor relative paths to repo root (not CWD) — see docstring.
        if not p.is_absolute():
            p = repo / p
        abs_path = p.resolve()
        rel = abs_path.relative_to(repo.resolve())
    except (ValueError, OSError):
        # Path outside repo tree → not framework-owned (user can edit freely)
        return False
    rel_str = normalize(str(rel))
    # Strict prefix match : "foo/.claude/rules/" must NOT match "rules/" pattern
    for owned in FRAMEWORK_OWNED:
        if owned.endswith("/"):
            # Directory : exact prefix from repo root
            if rel_str.startswith(owned):
                return True
        else:
            # Single file : exact equality from repo root
            if rel_str == owned:
                return True
    return False


def _resolve_mode() -> str:
    """Precedence : env override > CI auto-detect > 'warn' default.

    CI detection delegated to `sdd_lib.ci.is_ci` (SSoT, audit CTO 2026-06-07)
    instead of a duplicated local `_detect_ci`.
    """
    explicit = (os.environ.get("SDD_PROTECT_FRAMEWORK_MODE") or "").strip().lower()
    if explicit in ("warn", "strict", "off"):
        return explicit
    return "strict" if is_ci() else "warn"


def _main_inner() -> int:
    mode = _resolve_mode()
    if mode == "off":
        return HOOK_ALLOW
    payload = read_hook_input()
    file_path = get_file_path(payload)
    if not file_path:
        return HOOK_ALLOW
    # P1-5 fix 2026-06-07 : canonicalized check via repo_root + relative_to
    # (was substring match — could false-positive/negative).
    if not _is_framework_path(file_path, repo_root()):
        return HOOK_ALLOW
    norm = normalize(file_path)
    if mode == "strict":
        warn(f"ERROR: protect-framework — '{file_path}' est propriete framework SDD_Pro")
        warn(f"CAUSE: [FRAMEWORK_PROTECTED] tentative d'edit en mode strict (CI ou explicite)")
        warn(f"FIX: (a) si edit legitime Tech Lead : export SDD_PROTECT_FRAMEWORK_MODE=warn")
        warn(f"     (b) si agent produit modifie le framework : c'est un BUG, ne pas bypass")
        return HOOK_DENY

    # warn mode (default interactive)
    warn(f"WARNING: '{file_path}' est un fichier propriete framework SDD_Pro.")
    warn("         Les agents produit (po, arch, dev-*, qa) ne doivent pas le modifier.")
    warn("         Maintenance framework autorisee deliberement (Tech Lead).")

    if ".claude/CLAUDE.md" in norm:
        warn("         Rappel: synchroniser .claude/docs/CHANGELOG.md et docs/ si changement architectural.")
    if ".claude/loader.yml" in norm:
        warn("         Rappel: loader.yml doit refleter les reads/writes reels des agents.")

    return HOOK_ALLOW


def _is_ci_environment() -> bool:
    """Detect CI environment via standard env vars.

    Returns True if any common CI signal env var is set to a truthy value.
    Shared with audit_file_ownership.py (same heuristic).
    """
    return any(
        (os.environ.get(v, "").strip().lower() not in ("", "0", "false", "no"))
        for v in (
            "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
            "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
            "BITBUCKET_BUILD_NUMBER",
        )
    )


def main() -> int:
    """Outer wrapper — fail-OPEN interactive, fail-CLOSED in CI.

    Interactive (dev local) : fail-OPEN on any internal exception
    (audit C4 fix v7.0.0-alpha 2026-06-04). Without this guard, an
    exception in `normalize()` (e.g. ValueError on UNC paths, broken
    symlinks, paths outside the repo tree) would propagate up and BLOCK
    the entire Edit|Write|MultiEdit chain until Claude Code restart.
    Fail-open preserves user's ability to Edit, with a visible WARN.

    CI (v7.0.1 audit P1 v2 2026-06-08) : fail-CLOSED. An exception in
    the framework-protection logic is a signal that an attacker may be
    probing edge cases (UNC paths `\\\\?\\GLOBALROOT\\...`, symlink
    games, etc.) to bypass the protection. In CI, we'd rather block
    legitimate edits and force investigation than let a bypass attempt
    through. Bypass via `SDD_PROTECT_FRAMEWORK_FAIL_OPEN=1` (explicit,
    audit-loggable).
    """
    try:
        return _main_inner()
    except Exception as e:
        warn(f"WARN protect-framework: internal error suppressed ({type(e).__name__}: {e})")
        if _is_ci_environment() and (
            os.environ.get("SDD_PROTECT_FRAMEWORK_FAIL_OPEN", "").strip().lower()
            not in ("1", "true", "yes")
        ):
            # CI fail-CLOSED : block the edit, force investigation.
            warn(f"     CI fail-CLOSED (audit P1 v2 2026-06-08) : refusing edit.")
            warn(f"     CAUSE: [INFRA_BLOCKED] hook internal exception — possible bypass probe.")
            warn(f"     FIX: investigate stderr, then if legitimate :")
            warn(f"          SDD_PROTECT_FRAMEWORK_FAIL_OPEN=1 to bypass once.")
            return HOOK_DENY
        warn(f"     Hook fail-OPEN to avoid blocking Edit|Write globally.")
        warn(f"     If this repeats, capture stderr + report at .claude/python/sdd_hooks/protect_framework.py")
        return HOOK_ALLOW
if __name__ == "__main__":
    sys.exit(main())
