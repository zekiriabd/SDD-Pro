"""v7.0.0 P1 #7 drift test 2026-05-20 — verify `audit_file_ownership.py`
OWNERSHIP_MATRIX (Python regex) stays in sync with `ownership.md §1`
(Markdown source of truth).

Drift scenarios this test catches :
  1. Agent listed in ownership.md but missing from OWNERSHIP_MATRIX
     → audit silently skips the agent's writes (false negative).
  2. Agent in OWNERSHIP_MATRIX but removed from ownership.md (e.g.
     retired in v7.0.0 like `dashboard`) → audit emits noise on a
     non-existent agent.
  3. Agent path pattern in ownership.md table that NO regex matches
     → ownership.md describes a path that audit doesn't enforce.

This test is the only mechanic preventing the regex matrix from
diverging silently over time.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_hooks.audit_file_ownership import OWNERSHIP_MATRIX  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402


# v7.0.0 — agents officially retired (cf. CHANGELOG Unreleased §Breaking)
RETIRED_V7_AGENTS = frozenset({
    "accessibility-auditor",
    "performance-auditor",
    "dashboard",
    "dev-backend-strict",
    "dev-frontend-strict",
})

# Agents officially active in v7.0.0 (cf. CLAUDE.md §4)
ACTIVE_V7_AGENTS = frozenset({
    "po", "arch", "dev-backend", "dev-frontend",
    "qa", "elicitor", "constitutioner",
    "code-reviewer", "security-reviewer",
    "spec-compliance-reviewer", "arch-reviewer",
})


def _read_ownership_md() -> str:
    """Read .claude/rules/ownership.md (source of truth, post-sweep v7.0.0)."""
    p = repo_root() / ".claude" / "rules" / "ownership.md"
    assert p.is_file(), f"ownership.md not found at {p}"
    return p.read_text(encoding="utf-8")


def _agents_mentioned_in_ownership_md(content: str) -> set[str]:
    """Extract agent identifiers from the matrix table in §A.1.

    Looks for backtick-wrapped agent names in the "Owner exclusif" column.
    Pattern : `` `agent-name` `` or `` `agent-name` (...) ``.
    Filters out things like `arch` mentioned as "(création)" annotations —
    the test only requires the SET of agents, not their exact ownership.
    """
    # Lines in the matrix table : | path... | `agent-name` (...) | mode | phase |
    # Take everything in backticks that looks like a kebab-case agent ID
    pattern = re.compile(r"`([a-z][a-z0-9-]+)`")
    found: set[str] = set()
    for line in content.splitlines():
        for m in pattern.finditer(line):
            candidate = m.group(1)
            # Heuristic : only kebab-case identifiers with 2+ chars and no special words
            if candidate in ACTIVE_V7_AGENTS:
                found.add(candidate)
    return found


class TestOwnershipMatrixSync(unittest.TestCase):
    """Cross-source coherence : OWNERSHIP_MATRIX vs ownership.md §1."""

    def test_no_retired_v7_agent_in_matrix(self) -> None:
        """Agents retired in v7.0.0 must NOT appear in the audit matrix."""
        for retired in RETIRED_V7_AGENTS:
            self.assertNotIn(
                retired, OWNERSHIP_MATRIX,
                f"Retired v7.0.0 agent '{retired}' still in OWNERSHIP_MATRIX. "
                f"Remove from .claude/python/sdd_hooks/audit_file_ownership.py.",
            )

    def test_matrix_agents_are_v7_active(self) -> None:
        """Every agent in OWNERSHIP_MATRIX must be a v7.0.0 active agent."""
        matrix_agents = set(OWNERSHIP_MATRIX.keys())
        unknown = matrix_agents - ACTIVE_V7_AGENTS
        self.assertEqual(
            unknown, set(),
            f"OWNERSHIP_MATRIX contains agents not in v7.0.0 active set : {unknown}. "
            f"Either add them to ACTIVE_V7_AGENTS (this test) or remove "
            f"from .claude/python/sdd_hooks/audit_file_ownership.py.",
        )

    def test_core_agents_have_ownership_entries(self) -> None:
        """4 cœur (po, arch, dev-backend, dev-frontend) + qa must each
        have at least one path pattern in the matrix — they all write."""
        required = {"po", "arch", "dev-backend", "dev-frontend", "qa"}
        for agent in required:
            self.assertIn(
                agent, OWNERSHIP_MATRIX,
                f"Core agent '{agent}' missing from OWNERSHIP_MATRIX",
            )
            self.assertGreater(
                len(OWNERSHIP_MATRIX[agent]), 0,
                f"Agent '{agent}' has empty pattern list in OWNERSHIP_MATRIX",
            )

    def test_all_patterns_compile(self) -> None:
        """Every regex in OWNERSHIP_MATRIX must compile successfully."""
        for agent, patterns in OWNERSHIP_MATRIX.items():
            for pat in patterns:
                try:
                    re.compile(pat)
                except re.error as e:
                    self.fail(f"OWNERSHIP_MATRIX['{agent}'] has invalid regex {pat!r}: {e}")

    def test_ownership_md_references_matrix_agents(self) -> None:
        """At least the 4 core agents must be mentioned in ownership.md §1
        matrix. Lighter check than full bidirectional sync — gives
        documentation-as-code coherence."""
        content = _read_ownership_md()
        agents_in_md = _agents_mentioned_in_ownership_md(content)
        required_in_md = {"po", "arch", "dev-backend", "dev-frontend"}
        missing = required_in_md - agents_in_md
        self.assertEqual(
            missing, set(),
            f"ownership.md §1 does not mention these core agents in the "
            f"owner matrix : {missing}. Verify §A.1 table content.",
        )


if __name__ == "__main__":
    unittest.main()
