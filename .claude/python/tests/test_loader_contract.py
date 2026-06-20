"""Cross-agent contract enforcement tests (audit CTO 2026-06-07, Sprint 4 #19).

The `loader.yml` SSoT documents `reads:`, `writes:`, `forbidden_reads:`,
`forbidden_writes:` per agent. These tests pin the contract at framework
level so any future drift is surfaced :

  1. Every documented agent has a non-empty `reads:` block.
  2. Every agent declared in `loader.yml` has a corresponding
     `.claude/agents/{name}.md` prompt file on disk.
  3. Every agent prompt on disk has a `loader.yml` entry (no orphan agents).
  4. The 12 "alive" agents v7.0.0 are all present and accounted for.

These are STATIC contract tests — they don't intercept runtime, but they
ensure the SSoT relationship `prompts ↔ loader.yml` cannot silently drift.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.loader_yml import parse_agent_section  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402

pytestmark = pytest.mark.smoke

#: 12 alive agents per CLAUDE.md §4 (v7.0.0+ post-cleanup C2 2026-06-08).
#: Static — must stay in sync with agents/*.md and framework_smoke.EXPECTED_AGENTS.
ALIVE_AGENTS_V7 = frozenset({
    "po", "arch", "dev-backend", "dev-frontend",
    "elicitor", "qa", "constitutioner",
    "code-reviewer", "security-reviewer",
    "spec-compliance-reviewer", "arch-reviewer",
    "adversarial-reviewer",
})

#: Documentation-only agents : .md exists on disk as a rubric/spec reference
#: but the agent is NEVER spawned by any pipeline. Replaced by a deterministic
#: Python script. Distinct from RETIRED (which deletes the .md from disk).
#:
#: Audit C2 cleanup (2026-06-08) : complexity-router's LLM agent was retired
#: per audit P1 M2 ; the .md stays as the canonical spec of the scoring rubric
#: that `sdd_scripts/complexity_router.py` implements verbatim.
DOC_ONLY_AGENTS_V7 = frozenset({
    "complexity-router",
})

#: Agents retired in v7.0.0 — must NOT be in loader.yml as active entries
#: AND must NOT have a .md file on disk. Distinct from DOC_ONLY (kept as spec).
RETIRED_AGENTS_V7 = frozenset({
    "dashboard",
    "accessibility-auditor", "performance-auditor",
    "dev-backend-strict", "dev-frontend-strict",
    "validator",
})

#: Reverse engineering workflow agents — declared in `loader.reverse.yml`
#: (autonomous loader for the reverse workflow, isolated from `loader.yml`).
#: These agents have prompt files in `.claude/agents/` but their context-budget
#: contract lives in `loader.reverse.yml` per master prompt §3.2 D4 decision.
#:
#: Adding a new reverse agent : append here AND declare it in `loader.reverse.yml`.
#: This list stays in sync with the `available_in_mvp` agents from loader.reverse.yml.
REVERSE_AGENTS_V7 = frozenset({
    "reverse-inventory",
    "reverse-functional-extractor",
    "reverse-ui-extractor",  # MVP v0.2 — Phase 4 runtime capture (2026-06-10)
    # V2 (hors MVP, à ajouter quand implémentés) :
    # "reverse-tech-auditor",
})


def _agents_dir() -> Path:
    return repo_root() / ".claude" / "agents"


class TestLoaderAgentCoverage(unittest.TestCase):
    """Every alive agent in CLAUDE.md §4 has a loader.yml entry + prompt.

    Note: `parse_agent_section` returns [] for missing agents (no exception),
    so we use the `reads` list non-emptiness as a proxy for "agent declared".
    """

    def test_all_12_alive_agents_have_loader_reads(self):
        missing = [name for name in sorted(ALIVE_AGENTS_V7)
                   if not parse_agent_section(name, "reads")]
        self.assertFalse(missing, f"agents missing from loader.yml `reads:`: {missing}")

    def test_all_12_alive_agents_have_prompt_files(self):
        agents_dir = _agents_dir()
        missing = [name for name in ALIVE_AGENTS_V7
                   if not (agents_dir / f"{name}.md").is_file()]
        self.assertFalse(missing, f"agents missing prompt .md: {missing}")

    def test_no_retired_agents_have_prompt_files(self):
        """v7.0.0 removals must be effective on disk."""
        agents_dir = _agents_dir()
        zombies = [name for name in RETIRED_AGENTS_V7
                   if (agents_dir / f"{name}.md").is_file()]
        self.assertFalse(zombies, f"retired v7 agents still on disk: {zombies}")


class TestLoaderReadsWritesShape(unittest.TestCase):
    """Each alive agent has both reads + writes declared."""

    def test_every_agent_declares_reads_non_empty(self):
        for agent_name in sorted(ALIVE_AGENTS_V7):
            reads = parse_agent_section(agent_name, "reads")
            self.assertTrue(reads, f"agent {agent_name} has empty `reads:` in loader.yml")

    def test_every_agent_declares_writes_non_empty(self):
        """Even read-only reviewers declare writes for report files."""
        for agent_name in sorted(ALIVE_AGENTS_V7):
            writes = parse_agent_section(agent_name, "writes")
            self.assertTrue(
                writes,
                f"agent {agent_name} has empty `writes:` — even reviewers "
                f"write their report files (workspace/output/.sys/.validation/)",
            )


class TestLoaderNoOrphanPromptFiles(unittest.TestCase):
    """Every `.claude/agents/*.md` is declared in loader.yml (no orphan prompt)."""

    def test_no_orphan_prompts(self):
        agents_dir = _agents_dir()
        on_disk = {p.stem for p in agents_dir.glob("*.md")}
        orphans = [name for name in on_disk
                   if name not in ALIVE_AGENTS_V7
                   and name not in DOC_ONLY_AGENTS_V7
                   and name not in RETIRED_AGENTS_V7
                   and name not in REVERSE_AGENTS_V7
                   and not parse_agent_section(name, "reads")]
        self.assertFalse(
            orphans,
            f"prompt files without loader.yml entry: {orphans}",
        )

    def test_doc_only_agents_not_in_alive(self):
        """A doc-only agent must not also be in ALIVE_AGENTS_V7 (mutually exclusive)."""
        overlap = ALIVE_AGENTS_V7 & DOC_ONLY_AGENTS_V7
        self.assertFalse(
            overlap,
            f"agents listed in both ALIVE and DOC_ONLY: {overlap}. "
            f"Decide: spawnable agent OR documentation-only rubric — not both.",
        )


if __name__ == "__main__":
    unittest.main()
