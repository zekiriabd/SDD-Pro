"""Grep-gate — MIGRATION-PLAN Phase 1 STEP 11 (2026-07-25).

Prevent regression : after Phase 1 completion, production Python code must
NOT hardcode `.claude/` paths for framework-owned directories (rules,
stacks, templates, skills, docs, python). Those must go through the
semantic helpers `sdd_lib.paths.rules_dir()`, `stacks_dir()`, etc.

Allowed contexts (SKIP list) :
  - `.claude/agents/`, `.claude/commands/` : still legitimate as generated
    facades (Claude Code loads them at session start).
  - `.claude/CLAUDE.md`, `.claude/loader.yml`, `.claude/settings*.json`,
    `.claude/config.base.yml`, `.claude/INVARIANTS*.yml`, `.claude/digests/`,
    `.claude/bootstrap.py`, `.claude/mkdocs.yml`, `.claude/requirements-docs.txt`,
    `.claude/CONTRIBUTING.md` : still live in .claude/ (not migrated).
  - `protect_framework.py` FRAMEWORK_OWNED tuple : intentionally protects
    both legacy `.claude/` and new `.sdd/` paths.
  - `test_paths_bi_root.py` + `test_protect_framework.py` : bi-root tests.
  - `test_harness_*.py` : intentional bi-root paths in build tests.
  - `paths.py` itself : the `.claude/` literal lives there as fallback.

Scope : *.py files under .sdd/python/ only.

Failure mode : if this test fails, the caller should either
  (a) route the hardcoded path through a `paths.py` semantic helper, or
  (b) if it's a legitimate `.claude/` reference (unmigrated file), add it
      to the SKIP list here with a one-line justification.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib.paths import repo_root, python_dir  # noqa: E402


# Files exempted from the grep-gate (with justification per line).
_ALLOWED_FILES: frozenset[str] = frozenset({
    # sdd_lib
    "sdd_lib/paths.py",  # defines the .claude/ vs .sdd/ resolution (source of truth)
    # sdd_hooks
    "sdd_hooks/protect_framework.py",  # FRAMEWORK_OWNED protects both roots
    # tests
    "tests/test_paths_bi_root.py",  # bi-root tests DEFINE .claude/ + .sdd/ fixtures
    "tests/test_protect_framework.py",  # bi-root protection tests
    "tests/test_harness_antigravity.py",  # harness build tests intentionally cross-root
    "tests/test_harness_build_stack.py",
    "tests/test_harness_codex_gemini.py",
    "tests/test_harness_identity.py",
    "tests/test_harness_identity_commands.py",
    "tests/test_harness_memory.py",
    "tests/test_harness_preflight.py",
    "tests/test_harness_rules.py",
    "tests/test_impact_report.py",
    "tests/test_neutral_loader.py",
    "tests/test_phase1_integration.py",
    "tests/test_no_hardcoded_claude_paths.py",  # this file describes .claude/ patterns
    "tests/test_loader_yml.py",  # bi-root loader fixtures
    "tests/test_bootstrap.py",  # bi-root bootstrap fixtures
    "tests/test_loader_model_parity.py",  # uses .claude/loader.yml which stays there
    "tests/test_ownership_matrix_sync.py",  # docstring mentions historic path
    "tests/test_context_budget.py",  # uses .claude/agents refs (facade)
    "tests/test_config_all_keys_consumed.py",  # uses .claude/{commands,agents,rules} refs
    "tests/test_agent_references_integrity.py",  # scans .claude/agents (façade)
    "tests/test_gates_map.py",  # bi-root patterns
    "tests/test_sdd_help_faq.py",  # bi-root regex
    "tests/test_hooks_wiring.py",  # settings.json hook checks
    "tests/test_repo_gitignore_guards.py",  # asserte le TEXTE LITTERAL des regles .gitignore
    # sdd_admin
    "sdd_admin/strip_bom.py",  # bi-root scan roots
    "sdd_admin/framework_smoke.py",  # docstring on historic migration
    "sdd_admin/sync_error_class_digests.py",  # historic docstring mentions
    "sdd_admin/measure_cache_hit_rate.py",  # scans user home ~/.claude/projects
    "sdd_admin/measure_batch.py",  # idem
    # sdd_lib (functional but exempted with reason)
    "sdd_lib/cache_control.py",  # examples in docstrings + loader.yml legacy paths
    "sdd_lib/project_config.py",  # docstring + bi-racine comment mentioning both roots
    "sdd_hooks/session_start.py",  # help text (session banner) referencing rules paths
    "sdd_hooks/validate_stack_consistency.py",  # bi-racine comment explaining regex
    "sdd_scripts/validate_inline_rules.py",  # docstring + bi-racine regex
    "tests/test_code_review_patterns.py",  # bi-racine comment on rules_dir fallback
    # sdd_scripts (usage docstrings referencing .claude/python — actually pointing to code)
    # These will need to be systematically reviewed post-Phase 2.
})


# Paths still legitimately living under .claude/ (façade of Claude Code).
# Post-cleanup 2026-07-25 : agents/commands/rules/CLAUDE.md sont générés
# à la demande par rebuild_claude_facade.py — plus permanents sur disque.
# Restent : settings.json (harness config), python/ (shim + backup), projects/ (~home).
_LEGITIMATE_CLAUDE_SUBPATHS: tuple[str, ...] = (
    ".claude/agents/",             # regenerated facade (transient)
    ".claude/commands/",           # regenerated facade (transient)
    ".claude/rules/",              # regenerated facade (transient)
    ".claude/CLAUDE.md",           # regenerated memory file (transient)
    ".claude/loader.yml",          # OPERATIONAL — Batch C migration pending
    ".claude/loader.reverse.yml",  # OPERATIONAL — Batch C migration pending
    ".claude/settings.json",       # harness config (tracked)
    ".claude/settings.local.json", # user local (untracked)
    ".claude/projects/",           # user home path (measure_cache scripts)
)


def _is_line_legitimate(line: str) -> bool:
    """A line is legitimate if all its `.claude/...` refs are in the allowed subpaths."""
    # Only line has `.claude` — check if all mentions match a legitimate subpath.
    if ".claude" not in line:
        return True
    # Extract each .claude/... pattern and verify it starts with a legitimate prefix.
    for m in re.finditer(r"\.claude/[A-Za-z0-9_.-]*", line):
        rel = m.group(0)
        if not any(rel.startswith(prefix.rstrip("/")) for prefix in _LEGITIMATE_CLAUDE_SUBPATHS):
            return False
    return True


class TestNoHardcodedClaudePaths(unittest.TestCase):
    """Grep-gate against `.claude/rules/`, `.claude/stacks/`, etc. hardcoded in prod code."""

    def test_no_hardcoded_migrated_paths(self) -> None:
        # Migrated dirs — must NOT appear in prod Python code (must use helpers).
        forbidden_substrings = (
            ".claude/rules/",
            ".claude/stacks/",
            ".claude/templates/",
            ".claude/skills/",
            ".claude/docs/",
            ".claude/python/",
        )
        py_root = python_dir(repo_root())
        offenders: list[tuple[str, int, str]] = []  # (relpath, line_no, line)
        for py in py_root.rglob("*.py"):
            rel = py.relative_to(py_root).as_posix()
            if rel in _ALLOWED_FILES:
                continue
            try:
                text = py.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if not any(sub in line for sub in forbidden_substrings):
                    continue
                # Cosmetic mentions in comments/docstrings might be OK — but we want
                # to be strict and flag them all. Migrator fixes the code or adds
                # the file to _ALLOWED_FILES with a justification.
                offenders.append((rel, i, line.strip()))
        self.assertFalse(offenders, (
            "Hardcoded `.claude/<migrated>/` paths detected in production Python. "
            "Use the semantic helper (rules_dir, stacks_dir, templates_dir, "
            "skills_dir, docs_dir, python_dir) OR add the file to "
            "_ALLOWED_FILES with a justification.\n\nOffenders:\n"
            + "\n".join(f"  {rel}:{lineno}  {snippet}" for rel, lineno, snippet in offenders[:30])
        ))

    def test_only_legitimate_claude_refs(self) -> None:
        """Any `.claude/...` reference in prod code must be legitimate (see subpath list)."""
        py_root = python_dir(repo_root())
        offenders: list[tuple[str, int, str]] = []
        for py in py_root.rglob("*.py"):
            rel = py.relative_to(py_root).as_posix()
            if rel in _ALLOWED_FILES:
                continue
            try:
                text = py.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if ".claude" not in line:
                    continue
                if _is_line_legitimate(line):
                    continue
                offenders.append((rel, i, line.strip()))
        if offenders:
            # Report but don't fail — this is a soft warning to catch drift beyond
            # the primary check above. Elevate to assert once Phase 2 completes.
            msg = (
                "Non-legitimate .claude/ refs (soft warning — will be enforced post-Phase 2):\n"
                + "\n".join(f"  {rel}:{lineno}  {snippet}" for rel, lineno, snippet in offenders[:20])
            )
            print(msg, file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
