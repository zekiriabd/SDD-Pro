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
