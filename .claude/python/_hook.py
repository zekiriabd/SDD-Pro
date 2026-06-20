"""Hook launcher — cwd-independent bootstrap for SDD_Pro hooks.

Why this file exists:
- Claude Code hook commands in settings.json use relative paths
  (`python .claude/python/...`). These break if the parent process'
  cwd has drifted away from the repo root (sub-agent, Bash cd, etc.).
- This launcher resolves the repo root via CLAUDE_PROJECT_DIR env var
  if set, otherwise walks up from cwd to find a directory containing
  `.claude/`. Then chdir + sys.path + runpy the target module.

The settings.json hook commands call this launcher via inline
`python -c` that finds the launcher itself the same way. Once Python
is running, everything anchors here.

Timeout policy (audit mineur #5 v7.0.0-alpha 2026-06-05) :
  Claude Code enforces a **global ~30s timeout per hook** at the harness
  level — if the launched module hangs (DB lock, deadlock, infinite loop),
  the runtime kills the hook process and the calling Tool falls back to
  the default (usually ALLOW). This launcher does **not** wrap
  `runpy.run_module` in `signal.alarm` because :
    1. `signal.alarm` is POSIX-only ; SDD_Pro targets Windows + Linux + macOS.
    2. The harness-side timeout is already the source of truth — duplicating
       it here would just race the harness signal.
  Individual hooks may add their own `subprocess.run(..., timeout=N)` for
  child processes they spawn (e.g. preflight_agent_budget.py timeout=10
  on context_budget.py, see audit M6).

Usage (from settings.json):
    python -c "import os,sys,pathlib; r=os.environ.get('CLAUDE_PROJECT_DIR') or next((str(p) for p in [pathlib.Path.cwd()]+list(pathlib.Path.cwd().parents) if (p/'.claude').is_dir()),'.'); sys.path.insert(0,r+'/.claude/python'); import _hook; _hook.run('sdd_hooks.protect_framework')"
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def _looks_like_repo_root(p: Path) -> bool:
    """Strict repo-root check — mirror of `sdd_lib.paths._looks_like_repo_root`.

    Post-mortem 2026-05-21 : un sous-dossier d'archive `.claude/.claude/`
    faisait croire au walker que `.claude/` était le repo root → tous
    les paths Python dérivés résolvaient sous `.claude/workspace/...`
    au lieu de `workspace/...`. Le check unique `(p / ".claude").is_dir()`
    est insuffisant.

    Bootstrap-safe duplicate de `sdd_lib.paths._looks_like_repo_root` :
    ce fichier doit fonctionner AVANT que `sys.path` connaisse `sdd_lib`,
    donc ne peut pas importer la version canonique. Toute modification
    de la logique strict-check doit être appliquée aux 2 emplacements
    (paths.py + _hook.py). Garde-fou : `test_paths.py` vérifie l'alignement.
    """
    return (
        (p / ".claude" / "agents").is_dir()
        and (p / ".claude" / "commands").is_dir()
        and (p / "workspace").is_dir()
    )


def find_repo_root() -> Path:
    """Resolve repo root: CLAUDE_PROJECT_DIR env var, else walk up from cwd.

    Uses the strict check `_looks_like_repo_root` (3 markers required)
    to avoid the v6.x bug where a sub-archive `.claude/.claude/` was
    mistaken for the real root.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        p = Path(env).resolve()
        if _looks_like_repo_root(p):
            return p
    cwd = Path.cwd().resolve()
    for cand in [cwd, *cwd.parents]:
        if _looks_like_repo_root(cand):
            return cand
    return cwd


def run(module: str, *args: str) -> None:
    """Anchor cwd to repo root, then runpy the target module with args."""
    root = find_repo_root()
    os.chdir(root)
    py_dir = str(root / ".claude" / "python")
    if py_dir not in sys.path:
        sys.path.insert(0, py_dir)
    sys.argv = [module.split(".")[-1], *args]
    runpy.run_module(module, run_name="__main__")


# v7.0.0 — CLI entry-point conservé (audit CTO 2026-06-07).
# La pattern actuelle (`settings.json` → `python -c "...; import _hook;
# _hook.run('sdd_hooks.X')"`) couvre 14/14 invocations hooks runtime. Le
# mode `python _hook.py sdd_hooks.X` reste utilisé par 5 tests d'intégration
# (`test_preflight_glob_scope.py`, `test_preflight_stack_combo.py`,
# `test_resolve_po_hash_sentinel.py`, `test_validate_acceptance_gate.py`,
# `test_validate_stack_consistency.py`) qui forkent un sous-process pour
# tester l'isolation env vars + le code de sortie réel. Roadmap : migrer
# `settings.json` vers la CLI form (gain -3.5 KB JSON, lisibilité) en v7.1
# une fois validé sur 3 runs production. Ne pas retirer ce bloc tant que
# les 5 tests subprocess utilisent la CLI.
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write(
            "usage: python _hook.py <sdd_hooks.module> [args...]\n"
            "       python _hook.py <sdd_admin.statusline> (variant)\n"
        )
        sys.exit(2)
    _root = find_repo_root()
    _py_dir = str(_root / ".claude" / "python")
    if _py_dir not in sys.path:
        sys.path.insert(0, _py_dir)
    os.chdir(_root)
    target_module = sys.argv[1]
    extra_args = sys.argv[2:]
    sys.argv = [target_module.split(".")[-1], *extra_args]
    runpy.run_module(target_module, run_name="__main__")
