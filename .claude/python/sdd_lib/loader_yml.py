"""Parse `.claude/loader.yml` to extract reads/writes per agent.

Hand-rolled YAML parser limited to the loader.yml structure (avoids PyYAML dep).
Format expected:

    agent_name:
      reads:
        - path/one
        - path/two   # comment
      writes:
        - path/three
      forbidden_reads:
        - path/four
"""
from __future__ import annotations

import re
from pathlib import Path

from sdd_lib.paths import repo_root

_AGENT_RE = re.compile(r"^([a-z][a-z-]*):\s*$")
_SECTION_RE = re.compile(r"^\s{2}([a-zA-Z_]+):\s*$")
_ITEM_RE = re.compile(r"^\s{4}-\s*(.+?)\s*(?:#.*)?$")


def loader_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".claude" / "loader.yml"


def parse_agent_section(
    agent_name: str,
    section: str = "reads",
    root: Path | None = None,
) -> list[str]:
    """Extract list items from `agent: -> section: -> - item` in loader.yml.

    Args:
        agent_name: e.g. "po", "arch", "dev-backend"
        section: "reads", "writes", "forbidden_reads", etc.

    Returns:
        List of unquoted, comment-stripped strings (may be empty).
    """
    path = loader_path(root)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    items: list[str] = []
    in_agent = False
    in_section = False

    for line in text.splitlines():
        agent_match = _AGENT_RE.match(line)
        if agent_match:
            in_agent = agent_match.group(1) == agent_name
            in_section = False
            continue

        if not in_agent:
            continue

        section_match = _SECTION_RE.match(line)
        if section_match:
            in_section = section_match.group(1) == section
            continue

        if in_section:
            item_match = _ITEM_RE.match(line)
            if item_match:
                raw = item_match.group(1).strip().strip('"').strip("'")
                if raw and not raw.startswith("#"):
                    items.append(raw)

    return items
