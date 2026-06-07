#!/usr/bin/env python3
"""SDD_Pro cache manifest exporter (audit C1 partial, 2026-06-06).

Reads `.claude/loader.yml` and emits a JSON manifest binding each agent
to the cache_layer of each file it reads. Used by the v7.1 Anthropic SDK
wrapper to place `cache_control: ephemeral` markers on stable/semi
content, cutting Opus cost ~50 % on average.

v7.0.x scope (this script) : extraction + JSON export only. The actual
API call instrumentation lives in the harness (v7.1, slated post-FREEZE
2026-06-18 lift).

Usage::

    # Dump full manifest for all agents
    python -m sdd_admin.cache_manifest --json

    # Single agent
    python -m sdd_admin.cache_manifest --agent dev-backend --json

    # Human report
    python -m sdd_admin.cache_manifest --agent dev-backend

Output schema (per agent)::

    {
      "agent": "dev-backend",
      "reads": [
        {"path": "workspace/output/us/{n}-{m}-*.md", "cache_layer": "volatile"},
        {"path": ".claude/stacks/backend/{active}.md", "cache_layer": "stable"},
        ...
      ],
      "summary": {"stable": 7, "semi": 2, "volatile": 3}
    }

Exit codes:
  0 = SUCCESS
  1 = invalid arg / unknown agent
  2 = loader.yml unreadable / malformed
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.loader_yml import (  # noqa: E402
    CACHE_LAYERS,
    loader_path,
    parse_agent_cache_annotations,
)


_AGENT_LINE_RE = re.compile(r"^([a-z][a-z-]*):\s*$")


def list_agents(root: Path | None = None) -> list[str]:
    """Scan loader.yml top-level agent keys."""
    path = loader_path(root)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    agents: list[str] = []
    for line in text.splitlines():
        m = _AGENT_LINE_RE.match(line)
        if m and m.group(1) not in {"version", "updated"}:
            agents.append(m.group(1))
    return agents


def manifest_for_agent(agent: str) -> dict:
    reads = parse_agent_cache_annotations(agent)
    summary: dict[str, int] = {layer: 0 for layer in CACHE_LAYERS}
    for entry in reads:
        summary[entry["cache_layer"]] = summary.get(entry["cache_layer"], 0) + 1
    return {"agent": agent, "reads": reads, "summary": summary}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--agent", help="Single agent (default: all)")
    p.add_argument("--json", action="store_true", help="JSON output")
    args = p.parse_args()

    agents = [args.agent] if args.agent else list_agents()
    if not agents:
        print("FAIL: no agents found in loader.yml", file=sys.stderr)
        return CORRECTIBLE
    if args.agent and args.agent not in list_agents():
        print(f"FAIL: unknown agent {args.agent!r}", file=sys.stderr)
        return FAIL_FAST
    manifests = [manifest_for_agent(a) for a in agents]

    if args.json:
        print(json.dumps({"manifests": manifests}, indent=2, ensure_ascii=False))
    else:
        print("=== Cache Manifest (audit C1) ===")
        for m in manifests:
            s = m["summary"]
            total = sum(s.values())
            cacheable = s.get("stable", 0) + s.get("semi", 0)
            ratio = (cacheable / total * 100) if total else 0
            print(
                f"\n{m['agent']:<28} reads={total}  stable={s.get('stable',0)}  "
                f"semi={s.get('semi',0)}  volatile={s.get('volatile',0)}  "
                f"cacheable={ratio:.0f}%"
            )
        print(
            "\nNote: v7.0.x extraction only. v7.1 wires cache_control markers "
            "into the Anthropic SDK request payload."
        )

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
