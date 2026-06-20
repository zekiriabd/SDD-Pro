"""Smoke test : every `Agent: foo` mentioned in commands/rules/agents must
have a real `.claude/agents/foo.md`.

Audit P3 E3 (2026-06-08) — anti-phantom-agent enforcement. A subtle bug
class : an agent is renamed or retired, but some `.md` documentation still
mentions `Agent: old-name` as an invocation pattern. The LLM tries to
spawn `old-name`, the harness returns a "subagent not found" error, the
pipeline gets stuck without a clear diagnostic. This test catches the
drift at commit-time.

What we check :
- Pattern `Agent: <name>` (canonical SDDPro invocation syntax in docs)
- Pattern `Agent(<name>` (Python-style spawn references)
- Pattern `agent \`<name>\`` (informal references)

What we skip :
- Patterns inside fenced code blocks discussing Python `Agent` class API
- Generic mentions like "an agent" / "the agent"
- Retired agents listed under `RETIRED_AGENTS_V7` (those are explicitly
  documented as removed, mentions are historical)
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


def _repo_root() -> Path:
    cwd = Path(__file__).resolve()
    for p in [cwd, *cwd.parents]:
        if (p / ".claude").is_dir():
            return p
    raise RuntimeError("Cannot locate repo root")


# Mirror of tests/test_loader_contract.py — must stay in sync
_RETIRED_AGENTS = frozenset({
    "dashboard",
    "accessibility-auditor", "performance-auditor",
    "dev-backend-strict", "dev-frontend-strict",
    "validator",
})

# Known agents from .claude/agents/ — populated dynamically at test time
def _existing_agents() -> set[str]:
    agents_dir = _repo_root() / ".claude" / "agents"
    return {p.stem for p in agents_dir.glob("*.md")}


def _strip_code_fences(text: str) -> str:
    """Remove ```...``` fenced blocks to avoid matching Python API docs."""
    return re.sub(r"```[\s\S]*?```", "", text)


def _extract_agent_references(text: str) -> set[str]:
    r"""Extract agent names mentioned in markdown text via SDDPro patterns.

    Patterns matched (case-sensitive) :
    - `Agent: <name>` — canonical SDDPro invocation
    - `Agent(<name>` — Python spawn syntax
    - `Agent ID="<name>"` — internal ID reference
    - `agent \`<name>\`` — informal markdown ref
    """
    cleaned = _strip_code_fences(text)
    refs = set()

    # Pattern 1 : `Agent: foo-bar` or `Agent: \`foo-bar\``
    for m in re.finditer(r"\bAgent:\s*`?([a-z][a-z0-9-]+)`?", cleaned):
        refs.add(m.group(1))

    # Pattern 2 : `Agent(\"foo-bar\"` or `Agent('foo-bar'`
    for m in re.finditer(r"\bAgent\(\s*[\"']([a-z][a-z0-9-]+)[\"']", cleaned):
        refs.add(m.group(1))

    # Pattern 3 : `Agent name="foo-bar"` (YAML-ish)
    for m in re.finditer(r"\bAgent\s+name=[\"']?([a-z][a-z0-9-]+)", cleaned):
        refs.add(m.group(1))

    # Pattern 4 : explicit `agent \`foo-bar\`` (lowercase 'agent') — common in French docs
    for m in re.finditer(r"\bagent\s+`([a-z][a-z0-9-]+)`", cleaned):
        refs.add(m.group(1))

    return refs


# Common false positives — words that match `agent X` but aren't agent names
_NON_AGENT_WORDS = {
    "id",        # `agent ID`
    "name",      # `agent name`
    "type",      # `agent type`
    "is",        # `agent is`
    "must",      # `agent must`
    "should",    # `agent should`
    "ne",        # FR `agent ne...`
    "doit",      # FR `agent doit`
    "qui",       # FR `agent qui`
    "spawn",     # `agent spawn`
    "tool",      # `agent tool`
    "owner",     # `agent owner`
    "context",   # `agent context`
    "report",    # `agent report`
    "verdict",   # `agent verdict`
    "actif",     # FR `agent actif`
    "active",    # `agent active`
    "haiku",     # `agent Haiku 4.5`
    "sonnet",    # `agent Sonnet 4.6`
    "opus",      # `agent Opus 4.7`
    "llm",       # `agent LLM`
    "sdd",       # `agent SDD`
    "auditor",   # `agent auditor`
    "reviewer",  # `agent reviewer`
}


def _is_false_positive(name: str) -> bool:
    """Filter words that match the regex but aren't real agent names."""
    return name in _NON_AGENT_WORDS


class TestAgentReferencesIntegrity(unittest.TestCase):
    """Every Agent: X mentioned in docs has a real agents/X.md (or is retired)."""

    def test_no_phantom_agent_references(self):
        root = _repo_root()
        existing = _existing_agents()
        retired = _RETIRED_AGENTS

        # Scan files most likely to reference agents
        scan_dirs = [
            root / ".claude" / "commands",
            root / ".claude" / "rules",
            root / ".claude" / "agents",
            root / ".claude" / "skills",
        ]

        phantom: list[tuple[str, str]] = []  # (file_rel, agent_name)
        for d in scan_dirs:
            if not d.is_dir():
                continue
            for md in d.rglob("*.md"):
                text = md.read_text(encoding="utf-8", errors="replace")
                refs = _extract_agent_references(text)
                for name in sorted(refs):
                    if _is_false_positive(name):
                        continue
                    if name in existing:
                        continue
                    if name in retired:
                        continue
                    phantom.append((md.relative_to(root).as_posix(), name))

        if phantom:
            details = "\n".join(
                f"  - {file}: references Agent '{name}' (no agents/{name}.md, not retired)"
                for file, name in phantom
            )
            self.fail(
                f"\nPhantom agent references detected — docs mention agents "
                f"that don't exist on disk and aren't in RETIRED_AGENTS_V7 :\n"
                f"{details}\n\n"
                f"Fix options :\n"
                f"  1. Create the missing agents/X.md file\n"
                f"  2. Remove the stale reference from the doc\n"
                f"  3. Add to RETIRED_AGENTS_V7 in tests/test_loader_contract.py\n"
                f"  4. Add to _NON_AGENT_WORDS in this test if false positive\n"
            )


if __name__ == "__main__":
    unittest.main()
