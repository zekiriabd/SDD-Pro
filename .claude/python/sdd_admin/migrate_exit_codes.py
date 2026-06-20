#!/usr/bin/env python3
"""One-shot migration : `return 0/1/2/3` -> exit_codes constants.

v7.0.0-alpha (audit CRIT-7, 2026-06-04) — sweep mécanique pour enforcer
la convention `sdd_lib/exit_codes.py` sur les scripts qui retournent les
4 codes canoniques (SUCCESS=0, FAIL_FAST=1, CORRECTIBLE=2, INFRA_BLOCKED=3).

**Out of scope (granular exceptions per exit_codes.py docstring)** :
  - sdd_scripts/set_us_status.py            (exit 1-5 granular)
  - sdd_scripts/validate_us_deps.py         (exit 3/4/5 granular)
  - sdd_scripts/sdd_review.py               (exit 2/3 granular)
  - sdd_scripts/phase_planner.py            (exit 2 STACK_MALFORMED)
  - sdd_scripts/mark_breaking_resolved.py   (already migrated v7.0.0)
  - sdd_scripts/feat_to_pseudo_us.py        (uses sys.exit only at module bottom)

**Hooks** are migrated to `HOOK_ALLOW`/`HOOK_DENY` (different protocol —
Claude Code 0=allow, 2=deny — separate convention also defined in
exit_codes.py).

Usage :
    python -m sdd_admin.migrate_exit_codes [--dry-run] [--check]

  --dry-run : show changes that would be made, no write
  --check   : exit 1 if any target script still has hardcoded returns
              (use as CI gate to prevent future drift)

Idempotent : running twice produces zero change on the second pass.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / ".claude" / "python"

# Scripts that intentionally use granular exit codes — never rewritten.
EXCEPTIONS: frozenset[str] = frozenset({
    "sdd_scripts/set_us_status.py",
    "sdd_scripts/validate_us_deps.py",
    "sdd_scripts/sdd_review.py",
    "sdd_scripts/phase_planner.py",        # exit 2 STACK_MALFORMED granular
    "sdd_scripts/mark_breaking_resolved.py",
    "sdd_scripts/feat_to_pseudo_us.py",
    "sdd_admin/migrate_exit_codes.py",     # this file itself
})

# Hook scripts use a DIFFERENT protocol (Claude Code : 0=allow, 2=deny).
HOOKS_DIR_REL = "sdd_hooks/"

# Standard SDD script convention.
STD_MAPPING: dict[str, str] = {
    "0": "SUCCESS",
    "1": "FAIL_FAST",
    "2": "CORRECTIBLE",
    "3": "INFRA_BLOCKED",
}

# Hook convention (only 0 / 2 are meaningful).
HOOK_MAPPING: dict[str, str] = {
    "0": "HOOK_ALLOW",
    "2": "HOOK_DENY",
}

_RETURN_RE = re.compile(r"^(\s*)return ([0-3])\s*$", re.MULTILINE)
_IMPORT_RE = re.compile(r"^from sdd_lib\.exit_codes import (.+)$", re.MULTILINE)


def _target_files() -> list[Path]:
    """Iterate sdd_scripts/*.py + sdd_hooks/*.py + sdd_admin/*.py (excl. exceptions)."""
    targets: list[Path] = []
    for sub in ("sdd_scripts", "sdd_hooks", "sdd_admin"):
        d = PYTHON_ROOT / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("_"):
                continue
            rel = f"{sub}/{f.name}"
            if rel in EXCEPTIONS:
                continue
            targets.append(f)
    return targets


def _is_hook(path: Path) -> bool:
    return HOOKS_DIR_REL in path.as_posix()


def _rewrite_returns(content: str, mapping: dict[str, str]) -> tuple[str, dict[str, int]]:
    """Replace `return N` -> `return {CONST}` using the given mapping.

    Returns (new_content, used_constants_count).
    """
    used: dict[str, int] = {}

    def sub(m: re.Match[str]) -> str:
        indent, num = m.group(1), m.group(2)
        const = mapping.get(num)
        if const is None:
            return m.group(0)  # unchanged
        used[const] = used.get(const, 0) + 1
        return f"{indent}return {const}"

    new_content = _RETURN_RE.sub(sub, content)
    return new_content, used


def _ensure_import(content: str, needed: set[str]) -> str:
    """Ensure all `needed` constants are imported from sdd_lib.exit_codes.

    If an import line already exists, extend it. Otherwise, insert a new
    line after the existing `from sdd_lib.*` imports (or after the
    `sys.path.insert` line). Idempotent.
    """
    if not needed:
        return content

    m = _IMPORT_RE.search(content)
    if m:
        existing = {tok.strip() for tok in m.group(1).split("#")[0].split(",") if tok.strip()}
        merged = sorted(existing | needed)
        if merged == sorted(existing):
            return content  # nothing to add
        new_line = f"from sdd_lib.exit_codes import {', '.join(merged)}"
        # Preserve trailing comment, if any (e.g. `# noqa: E402`).
        comment_idx = m.group(0).find("#")
        if comment_idx > 0:
            new_line += "  " + m.group(0)[comment_idx:].rstrip()
        return content[: m.start()] + new_line + content[m.end():]

    # No existing import — insert one. Find a good anchor : the last
    # `from sdd_lib.* import` block, or after `sys.path.insert`.
    # v7.0.0-alpha hotfix (2026-06-04) : skip multi-line `import (` anchors
    # that don't close on the same line (would insert IN THE MIDDLE of an
    # open parenthesized import — broke init_console_db.py + validate_semantic.py
    # before this guard).
    anchor_re = re.compile(r"^from sdd_lib\.[^\n]+$", re.MULTILINE)
    new_line = (
        f"from sdd_lib.exit_codes import {', '.join(sorted(needed))}  # noqa: E402"
    )
    anchors = [
        m for m in anchor_re.finditer(content)
        if not m.group(0).rstrip().endswith("(")
    ]
    if anchors:
        last = anchors[-1]
        return content[: last.end()] + "\n" + new_line + content[last.end():]
    # Fall back to the very END of any multi-line parenthesized sdd_lib
    # import (find the closing `)` of the LAST `from sdd_lib.X import (...)`).
    multi_re = re.compile(
        r"^from sdd_lib\.[^\n]+ import \(.*?\)",
        re.MULTILINE | re.DOTALL,
    )
    multi_anchors = list(multi_re.finditer(content))
    if multi_anchors:
        last = multi_anchors[-1]
        return content[: last.end()] + "\n" + new_line + content[last.end():]

    sys_path_re = re.compile(r"^sys\.path\.insert\([^\n]+\)$", re.MULTILINE)
    sp = sys_path_re.search(content)
    if sp:
        return content[: sp.end()] + "\n\n" + new_line + content[sp.end():]

    # Last resort : after the `from __future__` line (or at top).
    future_re = re.compile(r"^from __future__ import [^\n]+$", re.MULTILINE)
    fut = future_re.search(content)
    if fut:
        return content[: fut.end()] + "\n\n" + new_line + content[fut.end():]

    return new_line + "\n\n" + content


def migrate_file(path: Path, dry_run: bool = False) -> dict[str, int] | None:
    """Apply migration to one file. Returns counts dict or None if no change."""
    original = path.read_text(encoding="utf-8")
    mapping = HOOK_MAPPING if _is_hook(path) else STD_MAPPING
    new_content, used = _rewrite_returns(original, mapping)
    if not used:
        return None
    new_content = _ensure_import(new_content, set(used.keys()))
    if new_content == original:
        return None
    if not dry_run:
        path.write_text(new_content, encoding="utf-8")
    return used


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any target still has hardcoded `return [0-3]`")
    args = parser.parse_args(argv)

    targets = _target_files()
    total_changes: dict[str, int] = {}
    files_changed = 0
    drift_files: list[str] = []

    for path in targets:
        used = migrate_file(path, dry_run=args.dry_run or args.check)
        if used is None:
            continue
        if args.check:
            drift_files.append(str(path.relative_to(REPO_ROOT)))
            continue
        files_changed += 1
        for k, v in used.items():
            total_changes[k] = total_changes.get(k, 0) + v
        print(f"[{'dry-run' if args.dry_run else 'OK'}] {path.relative_to(REPO_ROOT)} : {used}")

    if args.check:
        if drift_files:
            sys.stderr.write(
                "[CHECK FAIL] hardcoded `return [0-3]` in :\n  - "
                + "\n  - ".join(drift_files) + "\n"
            )
            return 1
        print("[CHECK OK] no hardcoded `return [0-3]` outside documented exceptions")
        return 0

    print(f"\nSummary : {files_changed} files {'would be ' if args.dry_run else ''}"
          f"updated, totals = {total_changes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
