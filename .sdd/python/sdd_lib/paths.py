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
    """Strict check: a real SDD_Pro repo root contains agents/ + commands/
    (under `.sdd/` OR `.claude/` — bi-racine transitionnel Phase 1) AND a
    workspace root.

    Bi-racine (2026-07-25, MIGRATION-PLAN Phase 1) : le foyer neutre `.sdd/`
    devient à terme le SSoT et `.claude/` une façade générée. Pendant la
    transition, les deux layouts coexistent. La détection accepte l'un OU
    l'autre — les scripts consomment via `sdd_home()` / helpers sémantiques
    (`rules_dir()`, `stacks_dir()`, ...) qui préfèrent `.sdd/` si présent.

    Post-mortem 2026-05-21 : un sous-dossier d'archive `.claude/.claude/`
    (legacy design docs superseded) faisait croire au walker que
    `.claude/` était le repo root → tous les paths Python dérivés
    (`workspace/db/console.db`) résolvaient sous
    `.claude/workspace/...` au lieu de `workspace/...`.
    Le check unique `(p / ".claude").is_dir()` est insuffisant.

    The workspace may be either nested under the repo root (`repo/workspace/`)
    or located as a sibling directory (`repo/../workspace/`), which matches the
    layout used after moving the workspace outside the repository folder.
    """
    has_sdd_layout = (
        (p / ".sdd" / "agents").is_dir()
        and (p / ".sdd" / "commands").is_dir()
    )
    has_claude_layout = (
        (p / ".claude" / "agents").is_dir()
        and (p / ".claude" / "commands").is_dir()
    )
    if not (has_sdd_layout or has_claude_layout):
        return False

    nested_workspace = p / "workspace"
    sibling_workspace = p.parent / "workspace"
    return nested_workspace.is_dir() or sibling_workspace.is_dir()


def workspace_root(repo_root: Path | None = None) -> Path:
    """Resolve the workspace root for a repo root.

    Prefers a nested workspace directory when present; otherwise falls back to
    a sibling workspace directory, which is used by split layouts.
    """
    root = Path(repo_root or Path.cwd()).resolve()
    nested_workspace = root / "workspace"
    if nested_workspace.is_dir():
        return nested_workspace

    sibling_workspace = root.parent / "workspace"
    if sibling_workspace.is_dir():
        return sibling_workspace

    return nested_workspace


#: Env var relocating `console.db` (absolute path). Honored by
#: `console_db_path()` → `sdd_lib.console_db.default_db_path()`. Set by the
#: pytest `conftest.py` (autouse) so the suite never touches the runtime DB
#: (audit « fiabilité des données » 2026-11-07 : pytest faisait passer `gates`
#: de 49 à 56 lignes dans `workspace/db/console.db`).
CONSOLE_DB_PATH_ENV = "SDD_CONSOLE_DB_PATH"

#: Mode of `$SDD_CONSOLE_DB_PATH` :
#:   - unset / ``override`` (default, production contract) : the env path
#:     ALWAYS wins.
#:   - ``fallback`` (set by `tests/conftest.py`) : the env path is used only
#:     when the default resolution would land on the REAL framework repo's
#:     runtime DB. Tests that already isolate via a fake repo
#:     (`$SDD_REPO_ROOT`, mocked `repo_root`, `cwd=fake_repo`) keep their own
#:     `<fake>/workspace/db/console.db` and its path assertions.
CONSOLE_DB_PATH_MODE_ENV = "SDD_CONSOLE_DB_PATH_MODE"


def _framework_repo_root() -> Path | None:
    """Repo root that physically contains this file (walk-up, no env/CWD)."""
    for parent in Path(__file__).resolve().parents:
        if _looks_like_repo_root(parent):
            return parent
    return None


def runtime_console_db_path() -> Path | None:
    """The real runtime DB of the framework checkout this code lives in."""
    root = _framework_repo_root()
    return workspace_root(root) / "db" / "console.db" if root is not None else None


def _override_path(override: str) -> Path:
    p = Path(override)
    if not p.is_absolute():
        import sys
        print(
            f"WARN sdd_lib.paths: {CONSOLE_DB_PATH_ENV}={override!r} is not "
            "absolute — resolved against CWD (pass an absolute path).",
            file=sys.stderr,
        )
    return p.resolve()


def console_db_path(repo_root_path: Path | None = None) -> Path:
    """Resolve the console.db location.

    Resolution order :
      1. `$SDD_CONSOLE_DB_PATH` — explicit relocation (tests, CI, multi-run
         isolation). Expected absolute ; a relative value is resolved against
         CWD with a WARN on stderr (never silently ignored). With
         `$SDD_CONSOLE_DB_PATH_MODE=fallback` it only replaces a resolution
         that would hit the real runtime DB (see `CONSOLE_DB_PATH_MODE_ENV`).
      2. `<workspace_root>/db/console.db` (default, workspace-scoped).

    `repo_root_path` is an optional pre-resolved repo root (avoids a redundant
    walk-up when the caller already has it) — only used for case 2.
    """
    override = os.environ.get(CONSOLE_DB_PATH_ENV, "").strip()
    mode = os.environ.get(CONSOLE_DB_PATH_MODE_ENV, "override").strip().lower()
    if override and mode != "fallback":
        return _override_path(override)
    root = repo_root_path if repo_root_path is not None else repo_root()
    default = workspace_root(root) / "db" / "console.db"
    if override:  # fallback mode
        runtime = runtime_console_db_path()
        try:
            hits_runtime = runtime is not None and default.resolve() == runtime.resolve()
        except OSError:
            hits_runtime = True  # fail safe : redirect
        if hits_runtime:
            return _override_path(override)
    return default


#: Env var relocating `workspace/.sys/.audit/` (absolute path). Same contract
#: as `$SDD_CONSOLE_DB_PATH` : mode `override` by default, `fallback` (set by
#: `tests/conftest.py`) redirects only a resolution that would hit the REAL
#: framework repo's audit dir. Audit 2026-11-07 : pytest écrivait dans la piste
#: d'audit de production (`pre-write-lint.log` « MyApp/Service.kt »,
#: `env-bypass.jsonl` par lots de 42/84 commandes factices).
AUDIT_DIR_ENV = "SDD_AUDIT_DIR"
AUDIT_DIR_MODE_ENV = "SDD_AUDIT_DIR_MODE"


def runtime_audit_dir() -> Path | None:
    """The real audit dir of the framework checkout this code lives in."""
    root = _framework_repo_root()
    return workspace_root(root) / ".sys" / ".audit" if root is not None else None


def audit_dir_path(repo_root_path: Path | None = None, *, workspace: Path | None = None) -> Path:
    """Resolve `workspace/.sys/.audit/` — the single entry point for audit logs.

    Resolution order :
      1. `$SDD_AUDIT_DIR` (mode `override`, default) — explicit relocation.
      2. `<workspace>/.sys/.audit` — `workspace` if given, else
         `workspace_root(repo_root_path or repo_root())`. With
         `$SDD_AUDIT_DIR_MODE=fallback`, `$SDD_AUDIT_DIR` replaces this only
         when it is the real runtime audit dir.
    Never creates the directory (callers `mkdir` before writing).
    """
    override = os.environ.get(AUDIT_DIR_ENV, "").strip()
    mode = os.environ.get(AUDIT_DIR_MODE_ENV, "override").strip().lower()
    if override and mode != "fallback":
        return Path(override).resolve()
    if workspace is None:
        root = repo_root_path if repo_root_path is not None else repo_root()
        workspace = workspace_root(root)
    default = Path(workspace) / ".sys" / ".audit"
    if override:  # fallback mode
        runtime = runtime_audit_dir()
        try:
            hits_runtime = runtime is not None and default.resolve() == runtime.resolve()
        except OSError:
            hits_runtime = True  # fail safe : redirect
        if hits_runtime:
            return Path(override).resolve()
    return default


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
                "repo layout (.sdd/agents + .sdd/commands OR .claude/agents + "
                ".claude/commands, plus workspace) — honored as-is (no silent "
                "CWD fallback).",
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
                        f"WARN sdd_lib.paths: CLAUDE_PROJECT_DIR={candidate} does not match strict repo layout (.sdd/agents + .sdd/commands OR .claude/agents + .claude/commands, plus workspace) — honored as-is",
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


# ---------------------------------------------------------------------------
# SDD_HOME + helpers sémantiques bi-racines (MIGRATION-PLAN Phase 1, 2026-07-25)
# ---------------------------------------------------------------------------
#
# `.sdd/` devient à terme le SSoT unique (foyer neutre édité) ; `.claude/`,
# `.codex/`, `.gemini/` deviennent des façades générées par
# `.sdd/harness_build.py`. Pendant la transition (Phases 1→2), les deux
# racines coexistent — les helpers ci-dessous préfèrent `.sdd/` si présent,
# sinon retombent sur `.claude/` (legacy). Après Phase 2, `.claude/` reste
# un répertoire valide (façade) mais son contenu vient de `.sdd/`.
#
# Contrat pour les callers : NE PLUS écrire `repo_root() / ".claude" / "rules"`
# en dur — utiliser `rules_dir()` (ou l'équivalent sémantique). Le grep-gate
# `test_no_hardcoded_claude_paths.py` (STEP 11) enforcera cette règle.


def sdd_home(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Locate the SDD neutral core directory (`.sdd/` — SSoT versionné).

    Resolution order:
      1. `env["SDD_HOME"]` if provided (Phase 1 scaffolding API), else
         `$SDD_HOME` env override.
      2. `<base>/.sdd/` if `base` is provided (test-friendly API), else
         `<repo_root>/.sdd/`.
      3. Fallback transitionnel `<repo_root>/.claude/` (Phase 1) — supprimé
         Phase 2.

    Args:
        repo_root_path: override optionnel (évite un walk-up redondant
            quand le caller a déjà résolu le repo root).
        env: optional env mapping (Phase 1 scaffolding API — harness_build.py
            + config_loader.py use it for isolation-friendly invocation).
            Defaults to `os.environ`.
        base: optional base directory (Phase 1 scaffolding API — used by
            tests that build fake repos in temp dirs).

    Returns:
        Path absolu vers le foyer SDD.
    """
    src = env if env is not None else os.environ
    override = src.get("SDD_HOME")
    if override:
        return Path(override).resolve()

    if base is not None:
        return (base / ".sdd").resolve()

    root = repo_root_path if repo_root_path is not None else repo_root()
    sdd_dir = root / ".sdd"
    if sdd_dir.is_dir():
        return sdd_dir
    # Legacy transitional fallback — removed once Phase 2 completes.
    return root / ".claude"


def claude_home(repo_root_path: Path | None = None) -> Path:
    """Locate the Claude Code façade directory (`.claude/` — harness-specific).

    Après Phase 2, `.claude/` reste valide mais est **read-only généré**
    depuis `.sdd/` par `.sdd/harness_build.py`. Cet helper renvoie
    toujours `<repo_root>/.claude/` — ne pas confondre avec `sdd_home()`
    (qui renvoie le SSoT neutre).

    Cas d'usage légitime : les adapters (`.sdd/adapters/claude.py`) et le
    hook `protect_framework` qui doit distinguer les écritures sur le
    foyer neutre (bloquant sauf harness_build.py) vs sur les façades
    (bloquant pour tout le monde sauf builder).
    """
    root = repo_root_path if repo_root_path is not None else repo_root()
    return root / ".claude"


def _prefer_sdd(subdir: str, repo_root_path: Path | None = None,
                env: dict | None = None, base: Path | None = None) -> Path:
    """Return `<sdd_home>/<subdir>` si existe, sinon `<claude_home>/<subdir>`.

    Contrat commun aux helpers sémantiques (`rules_dir`, `stacks_dir`, ...).
    Évite d'inventer un chemin qui n'existe pas encore si la migration
    d'un sous-répertoire précis n'est pas faite (pattern additif Phase 1).

    Args accept `env=` / `base=` kwargs (Phase 1 scaffolding API) — if
    provided, `sdd_home(env=env, base=base)` resolves the parent home and
    the bi-root fallback is skipped (test-friendly, no filesystem probes).
    """
    if env is not None or base is not None:
        return sdd_home(env=env, base=base) / subdir
    root = repo_root_path if repo_root_path is not None else repo_root()
    sdd_candidate = root / ".sdd" / subdir
    if sdd_candidate.is_dir():
        return sdd_candidate
    return root / ".claude" / subdir


def agents_dir(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Directory containing agent files (pivot YAML in `.sdd/`, .md in `.claude/`)."""
    return _prefer_sdd("agents", repo_root_path, env=env, base=base)


def commands_dir(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Directory containing command files (pivot YAML in `.sdd/`, .md in `.claude/`)."""
    return _prefer_sdd("commands", repo_root_path, env=env, base=base)


def rules_dir(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Directory containing rules markdown files."""
    return _prefer_sdd("rules", repo_root_path, env=env, base=base)


def skills_dir(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Directory containing skills subdirectories (auto-triggered guidance)."""
    return _prefer_sdd("skills", repo_root_path, env=env, base=base)


def templates_dir(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Directory containing templates (feat.template.md, us.template.md, ...)."""
    return _prefer_sdd("templates", repo_root_path, env=env, base=base)


def stacks_dir(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Directory containing stack markdowns (grouped by category)."""
    return _prefer_sdd("stacks", repo_root_path, env=env, base=base)


def resolve(subdir: str, *parts: str, env: dict | None = None, base: Path | None = None) -> Path:
    """Resolve `<sdd_home>/<subdir>/<parts>` (Phase 1 scaffolding API).

    Compat helper used by config_loader.py + tests. Delegates to `sdd_home()`.
    """
    home = sdd_home(env=env, base=base)
    return home.joinpath(subdir, *parts)


def providers_dir(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Directory containing provider config YAML files (`.sdd/providers/`).

    Accepts `env=`/`base=` (Phase 1 scaffolding API) — resolves via sdd_home.
    """
    if env is not None or base is not None:
        return sdd_home(env=env, base=base) / "providers"
    return sdd_home(repo_root_path) / "providers"


def agent_bounds_path(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Path to `.sdd/agent-bounds.yaml` (tier_default/tier_floor/tier_ceiling)."""
    if env is not None or base is not None:
        return sdd_home(env=env, base=base) / "agent-bounds.yaml"
    return sdd_home(repo_root_path) / "agent-bounds.yaml"


def capability_matrix_path(repo_root_path: Path | None = None, env: dict | None = None, base: Path | None = None) -> Path:
    """Path to `.sdd/capability-matrix.yml` (harness x mechanism support)."""
    if env is not None or base is not None:
        return sdd_home(env=env, base=base) / "capability-matrix.yml"
    return sdd_home(repo_root_path) / "capability-matrix.yml"


def docs_dir(repo_root_path: Path | None = None) -> Path:
    """Directory containing framework documentation."""
    return _prefer_sdd("docs", repo_root_path)


def python_dir(repo_root_path: Path | None = None) -> Path:
    """Directory containing Python deterministic scripts (sdd_lib, sdd_admin, ...).

    Contract stricter than `_prefer_sdd` : returns `.sdd/python/` only if it
    contains the canonical marker `sdd_admin/framework_smoke.py` (real full
    installation), else falls back to `.sdd/python/`. Phase 1 scaffolding
    leaves `.sdd/python/` with a few stub files but the real 331-file
    codebase stays in `.sdd/python/` until STEP 7 git-mv (STEP 7 will
    populate `sdd_admin/framework_smoke.py` and flip this switch).
    """
    root = repo_root_path if repo_root_path is not None else repo_root()
    sdd_candidate = root / ".sdd" / "python"
    if (sdd_candidate / "sdd_admin" / "framework_smoke.py").is_file():
        return sdd_candidate
    return root / ".sdd" / "python"
