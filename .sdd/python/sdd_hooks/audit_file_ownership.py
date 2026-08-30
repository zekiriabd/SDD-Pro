#!/usr/bin/env python3
"""SDD_Pro SubagentStop hook.

Audits the matrice file-ownership.md §1 after each sub-agent dispatch.
For files modified during the dispatch window, checks the path matches
one of the "Owner" patterns allowed for that agent.

- Detect agent via input JSON (`tool_input.subagent_type`)
- Glob files modified since env $SDD_DISPATCH_START_TS (ISO 8601),
  fallback to last 5 minutes
- Append violations to workspace/.sys/.audit/ownership-violations.log
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
from sdd_lib.paths import workspace_root, normalize, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402


# Matrix extracted from file-ownership.md §1 (must stay in sync)
OWNERSHIP_MATRIX: dict[str, list[str]] = {
    "po": [
        r"^workspace/us/.+\.md$",
        r"^workspace/\.sys/\.context/constitution\.md$",  # append-only §3 §2
    ],
    "arch": [
        r"^workspace/src/[^/]+\.sln$",
        r"^workspace/src/[^/]+/(\w+\.csproj|package\.json|pyproject\.toml|build\.gradle.*)$",
        r"^workspace/src/[^/]+/Entities/.+",
        r"^workspace/src/[^/]+/CLAUDE\.md$",
        r"^workspace/db/.+",
        r"^workspace/\.sys/\.context/(constitution\.md|adrs/.+)$",
    ],
    "dev-backend": [
        r"^workspace/src/[^/]+/(Services|Endpoints|DTOs|Mappers|Validators|Controllers)/.+",
        r"^workspace/src/[^/]+/Program\.cs$",
        r"^workspace/src/[^/]+/Models/.+",
        r"^workspace/plans/.+\.back\.md$",
        r"^workspace/\.sys/\.context/adrs/ADR-.+\.md$",
    ],
    "dev-frontend": [
        r"^workspace/src/[^/]+/(Pages|Components|Layouts|Auth)/.+",
        r"^workspace/src/[^/]+/wwwroot/.+",
        r"^workspace/src/[^/]+/Program\.cs$",
        r"^.+\.razor\.css$",
        r"^workspace/plans/.+\.front\.md$",
        r"^workspace/\.sys/\.context/adrs/ADR-.+\.md$",
    ],
    "qa": [
        r"^workspace/src/.+\.Tests/.+",
        r"^workspace/src/.+/__tests__/.+",
        r"^workspace/src/.+\.(FEAT|test)\.(ts|tsx|js|jsx)$",
        r"^workspace/src/.+(Test|FEAT)\.kt$",
        r"^workspace/src/.+test_.+\.py$",
        # 2026-07-06 : QA telemetry is SQLite-only (no qa/). The only file
        # the qa agent still writes is the transient api-tests JSON under
        # .sys/.validation/, which ingest_agent_report.py ingests then deletes.
        r"^workspace/\.sys/\.validation/[0-9]+-api-tests\.json$",
    ],
    # `dashboard` retiré v7.0.0 (governance-major-auditors-trim) — remplacé par
    # script déterministe index_adrs.py. Aucune entrée matrice nécessaire.
    "elicitor": [
        r"^workspace/feats/.+\.md$",  # append-only
        r"^workspace/\.sys/\.context/constitution\.md$",  # append-only §7
    ],
    # ----------------------------------------------------------------------- #
    # Module db-reverse (base de données → FEAT). Audit 2026-08-29, M3.
    #
    # Ces 6 agents n'avaient AUCUNE entrée ici, alors que la doc de deux d'entre
    # eux annonce une séparation faits/hypothèses « garantie par construction ».
    # Rien ne l'auditait : un Write direct sur la branche de faits de
    # db-context.json ne laissait aucune trace.
    #
    # Deux mécanismes, complémentaires et volontairement distincts :
    #   - `merge_architect_output` (db_context.py) est la whitelist de fusion :
    #     seules les clés de `hypotheses` passent, tout le reste est droppé.
    #     C'est ce qui protège le CONTENU.
    #   - cette matrice est l'audit a posteriori : elle constate quel agent a
    #     touché quel fichier pendant sa fenêtre de dispatch. C'est ce qui
    #     protège le PÉRIMÈTRE.
    #   - le blocage a priori d'un Write direct relève de `protect_framework.py`
    #     (hook PreToolUse), pas d'ici : ce hook-ci tourne APRÈS l'écriture.
    #
    # `db-context.json`, son digest et l'arbre de fiches figurent dans le
    # périmètre de l'architecte parce que le script de fusion qu'il DOIT invoquer
    # (`db_context_build.py --merge-hypotheses`) les régénère pendant sa fenêtre
    # de dispatch. Les y interdire produirait une violation à chaque exécution
    # nominale, et un journal d'audit qui crie toujours n'est plus lu.
    "reverse-db-architect": [
        # Le seul fichier que l'agent écrit lui-même (Phase 0.B).
        r"^workspace/old/[^/]+/\.sys/db-context\.hypotheses\.json$",
        # Régénérés par db_context_build.py, que l'agent invoque.
        r"^workspace/old/[^/]+/\.sys/db-context\.json$",
        r"^workspace/old/[^/]+/\.sys/db-context\.digest\.json$",
        r"^workspace/old/[^/]+/\.sys/db-context\.waves-completed\.json$",
        r"^workspace/old/[^/]+/\.sys/db-context/.+",
    ],
    # Les 4 spécialistes d'objet SQL n'écrivent QU'UNE User Story (1 objet = 1
    # US). Ni FEAT, ni contexte, ni snapshot : le corps qu'ils lisent est
    # produit en amont, en lecture seule, par l'introspection.
    "reverse-sql-analyst": [
        r"^workspace/us/.+\.md$",
    ],
    "reverse-sql-function-analyst": [
        r"^workspace/us/.+\.md$",
    ],
    "reverse-sql-view-analyst": [
        r"^workspace/us/.+\.md$",
    ],
    "reverse-sql-trigger-analyst": [
        r"^workspace/us/.+\.md$",
    ],
    # Rung 2 : compose la FEAT du module, et back-fille les US du module
    # (`Covers:` / `Status` / `Parent FEAT hash`) — cf. l'agent, section
    # anti-derive « Écrit uniquement … (+ Edit back-fill des US du module) ».
    "reverse-sql-feat-composer": [
        r"^workspace/feats/.+\.md$",
        r"^workspace/us/.+\.md$",
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


def _iter_modified_files_walk(workspace: Path, cutoff: datetime) -> list[Path]:
    """Walk workspace/ and yield files modified after cutoff (fallback).

    Uses `os.walk(topdown=True)` with in-place dirs pruning to skip vendor
    directories (node_modules, .venv, build artifacts, VCS metadata). On a
    real project with 50k+ files under node_modules, this changes the
    SubagentStop latency from seconds to ~100ms.

    This is the sole implementation since the 2026-06-12 audit fix: the
    `git status` fast-path (REFACTOR-2) was removed because it could NEVER
    see the files this hook must audit. The agents write under
    `workspace/`, which is **gitignored by design** — `git status`
    (even with `--untracked-files=all`) does not list ignored files, so the
    fast-path returned 0 files where the walk finds thousands, silently
    disabling the ownership matrix (INVARIANTS.yml `file-ownership-matrix-
    enforced`). The pruned walk (~100ms, vendor dirs skipped) is correct and
    fast enough.
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
    """Yield files modified after cutoff via a pruned walk of `workspace/`.

    v7.0.1 audit REFACTOR-2 (2026-06-08) introduced a `git status` fast-path;
    the 2026-06-12 audit removed it (see `_iter_modified_files_walk` docstring)
    — the audit targets are gitignored, so git could not see them. This
    indirection is kept as the stable public entry-point in case a
    git-ignored-aware fast-path is reintroduced later.
    """
    return _iter_modified_files_walk(workspace, cutoff)


def main() -> int:
    payload = read_hook_input()
    subagent = get_subagent_type(payload)
    if not subagent or subagent not in _COMPILED_OWNERSHIP:
        return HOOK_ALLOW
    allowed = _COMPILED_OWNERSHIP[subagent]  # M7 : reuse precompiled patterns

    root = repo_root()
    workspace = workspace_root(root)
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
    audit_dir = workspace_root(root) / ".sys" / ".audit"
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
