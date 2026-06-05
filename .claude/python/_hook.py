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


def find_repo_root() -> Path:
    """Resolve repo root: CLAUDE_PROJECT_DIR env var, else walk up from cwd."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        p = Path(env).resolve()
        if (p / ".claude").is_dir():
            return p
    cwd = Path.cwd().resolve()
    for cand in [cwd, *cwd.parents]:
        if (cand / ".claude").is_dir():
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


# v7.0.0-alpha (audit MAJ-13, 2026-06-04) — CLI entry point. Allows the
# settings.json hook commands to invoke the launcher as a regular script
# (`python .claude/python/_hook.py sdd_hooks.X`) instead of repeating
# the 250-char inline `python -c "..."` bootstrap 8 times.
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write(
            "usage: python _hook.py <sdd_hooks.module> [args...]\n"
            "       python _hook.py <sdd_admin.statusline> (variant)\n"
        )
        sys.exit(2)
    # Resolve repo + sys.path BEFORE importing target — the inline
    # bootstrap (settings.json invocation) is `python .claude/python/_hook.py`
    # which means cwd may not contain .claude/.
    _root = find_repo_root()
    _py_dir = str(_root / ".claude" / "python")
    if _py_dir not in sys.path:
        sys.path.insert(0, _py_dir)
    os.chdir(_root)
    target_module = sys.argv[1]
    extra_args = sys.argv[2:]
    sys.argv = [target_module.split(".")[-1], *extra_args]
    runpy.run_module(target_module, run_name="__main__")
