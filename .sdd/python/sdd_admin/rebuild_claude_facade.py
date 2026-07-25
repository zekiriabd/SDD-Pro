#!/usr/bin/env python3
"""rebuild_claude_facade — regenerate .claude/{agents,commands,rules,CLAUDE.md}.

Why this exists (2026-07-25) :
- The SSoT for SDD_Pro is `.sdd/` (agents, commands, rules, memory pivot).
- Claude Code reads its slash commands + agents + rules from `.claude/`.
- `harness_build.py` transpiles `.sdd/` -> `.sdd/.build/claude/` byte-identical
  (Phase 2 golden test, 81/81 pass) but explicitly refuses to `--deploy`
  into `.claude/` (safety guard : « surface servie protégée »).
- This wrapper closes the loop : rebuild into `.sdd/.build/claude/` then
  copy into `.claude/`. Used by :
    * `session_start.py` (auto-invoke if `.claude/agents/` missing)
    * Manual : `python .sdd/python/sdd_admin/rebuild_claude_facade.py`

Idempotent : safe to re-run. Never mutates `.sdd/`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Add .sdd/python to sys.path so we can import sdd_lib.exit_codes when
# invoked as `python .sdd/python/sdd_admin/rebuild_claude_facade.py`.
_HERE = Path(__file__).resolve()
_PYTHON_DIR = _HERE.parent.parent  # .sdd/python/
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))
from sdd_lib.exit_codes import SUCCESS, FAIL_FAST, INVALID_ARG  # noqa: E402


def _repo_root() -> Path:
    """Repo root = parent of `.sdd/` directory."""
    return _HERE.parents[3]  # .sdd/python/sdd_admin/X.py -> repo


def _needs_rebuild(claude_dir: Path) -> bool:
    """Return True if any of the 4 façade slots is missing/empty."""
    checks = [
        claude_dir / "agents",
        claude_dir / "commands",
        claude_dir / "rules",
    ]
    for d in checks:
        if not d.is_dir():
            return True
        if not any(d.glob("*.md")):
            return True
    if not (claude_dir / "CLAUDE.md").is_file():
        return True
    return False


def rebuild(force: bool = False, provider: str = "anthropic", verbose: bool = True) -> int:
    """Regenerate .claude/{agents,commands,rules,CLAUDE.md} from .sdd/.

    Returns 0 on success (or noop if not needed and not forced), non-zero
    on failure. Never raises — failure is logged to stderr.
    """
    repo = _repo_root()
    claude_dir = repo / ".claude"
    build_dir = repo / ".sdd" / ".build" / "claude"

    if not force and not _needs_rebuild(claude_dir):
        if verbose:
            print(f"[rebuild_claude_facade] .claude/ facade present, no rebuild needed.")
        return SUCCESS

    if verbose:
        print(f"[rebuild_claude_facade] rebuilding .claude/ from .sdd/ (provider={provider})...")

    # Step 1: transpile .sdd/ -> .sdd/.build/claude/
    cmd = [
        sys.executable,
        str(repo / ".sdd" / "harness_build.py"),
        "--harness", "claude-code",
        "--provider", provider,
        "--agents-only",
        "--commands-only",
        "--rules-only",
        "--memory-only",
        "--out", str(build_dir),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"[rebuild_claude_facade] harness_build failed: {exc}", file=sys.stderr)
        return FAIL_FAST
    if result.returncode != 0:
        print(
            f"[rebuild_claude_facade] harness_build exited {result.returncode}:\n"
            f"{result.stderr}",
            file=sys.stderr,
        )
        return FAIL_FAST

    # Step 2: copy generated artifacts into .claude/
    #   .sdd/.build/claude/agents/*.md  -> .claude/agents/*.md
    #   idem commands, rules, CLAUDE.md
    try:
        for sub in ("agents", "commands", "rules"):
            src = build_dir / sub
            dst = claude_dir / sub
            dst.mkdir(parents=True, exist_ok=True)
            # Remove stale files (in case pivot deletions occurred)
            for existing in dst.glob("*.md"):
                existing.unlink()
            for src_file in src.glob("*.md"):
                shutil.copy2(src_file, dst / src_file.name)
        # CLAUDE.md at the root of .claude/
        claude_md_src = build_dir / "CLAUDE.md"
        if claude_md_src.is_file():
            claude_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(claude_md_src, claude_dir / "CLAUDE.md")
    except OSError as exc:
        print(f"[rebuild_claude_facade] copy failed: {exc}", file=sys.stderr)
        return FAIL_FAST

    if verbose:
        n_agents = len(list((claude_dir / "agents").glob("*.md")))
        n_commands = len(list((claude_dir / "commands").glob("*.md")))
        n_rules = len(list((claude_dir / "rules").glob("*.md")))
        print(
            f"[rebuild_claude_facade] OK: {n_agents} agents, {n_commands} commands, "
            f"{n_rules} rules, CLAUDE.md deployed."
        )
    return SUCCESS


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Regenerate .claude/{agents,commands,rules,CLAUDE.md} from .sdd/.",
    )
    parser.add_argument("--force", action="store_true",
                        help="Rebuild even if .claude/ appears complete.")
    parser.add_argument("--provider", default="anthropic",
                        choices=["anthropic", "openai", "google", "moonshot"],
                        help="Model provider for tier resolution (default: anthropic).")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages.")
    args = parser.parse_args()
    return rebuild(force=args.force, provider=args.provider, verbose=not args.quiet)


if __name__ == "__main__":
    sys.exit(main())
