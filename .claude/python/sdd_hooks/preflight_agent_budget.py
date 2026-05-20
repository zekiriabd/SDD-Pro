#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook for Agent invocations.

Intercepts Agent tool calls: extracts `subagent_type` + best-effort
FEAT/US identifiers from the prompt, delegates to context_budget script
which writes the JSONL ledger.

Mode controlled by env $SDD_BUDGET_MODE:
    - "warn"   (default) : ledger + WARN on stderr, exit 0
    - "strict"            : block invocation if budget exceeded (exit 2)
    - "off"               : silent skip (exit 0)

Migrated from .claude/hooks/preflight-agent-budget.ps1 (2026-05-13).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.hook_input import (  # noqa: E402
    get_nested,
    get_subagent_type,
    read_hook_input,
)
from sdd_lib.stderr import warn  # noqa: E402


ALLOWED_AGENTS: set[str] = {
    # Core + support (4 + 3 + 1)
    "po", "arch", "dev-backend", "dev-frontend",
    "qa", "elicitor", "constitutioner",
    "dashboard",
    # Auditors retained in v7.0.0 (4) — accessibility-auditor and
    # performance-auditor were removed in v7.0.0
    # (governance-major-auditors-trim) ; their context_budget script
    # entries remain for legacy reading of historical runs but the
    # hook intentionally rejects new invocations.
    "code-reviewer", "security-reviewer",
    "spec-compliance-reviewer", "arch-reviewer",
}


def extract_us_and_feat(haystack: str) -> tuple[int, str]:
    """Best-effort regex extraction of FEAT number and US id from the prompt."""
    feat_number = 0
    us_id = ""

    m_us = re.search(r"\b(\d{1,3})-(\d{1,3})(?:-[A-Za-z][A-Za-z0-9\-]*)?\b", haystack)
    if m_us:
        us_id = f"{m_us.group(1)}-{m_us.group(2)}"
        feat_number = int(m_us.group(1))
    else:
        m_feat = re.search(
            r"(?i)\b(?:FEAT|feat-?|sdd-full|us-generate|dev-run|dev-plan|qa-generate)\s*[-:]?\s*(\d{1,3})\b",
            haystack,
        )
        if m_feat:
            feat_number = int(m_feat.group(1))

    return feat_number, us_id


def main() -> int:
    mode = os.environ.get("SDD_BUDGET_MODE", "warn").lower()
    if mode == "off":
        return 0

    payload = read_hook_input()
    if not payload:
        return 0

    subagent = get_subagent_type(payload)
    if not subagent or subagent not in ALLOWED_AGENTS:
        return 0

    prompt = get_nested(payload, "tool_input", "prompt", default="") or ""
    descr = get_nested(payload, "tool_input", "description", default="") or ""
    haystack = f"{prompt} {descr}"
    feat_number, us_id = extract_us_and_feat(haystack)

    script_path = Path(__file__).resolve().parent.parent / "sdd_scripts" / "context_budget.py"
    if not script_path.is_file():
        warn(f"WARN preflight-agent-budget: context_budget.py introuvable ({script_path})")
        return 0

    cmd: list[str] = [sys.executable, str(script_path), "--agent", subagent]
    if feat_number > 0:
        cmd += ["--feat-number", str(feat_number)]
    if us_id:
        cmd += ["--us-id", us_id]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as e:
        warn(f"WARN preflight-agent-budget: subprocess failed: {e}")
        return 0

    # Forward all output to stderr (visible to Claude/user)
    for line in (result.stdout or "").splitlines():
        warn(line)
    for line in (result.stderr or "").splitlines():
        warn(line)

    if result.returncode != 0:
        if mode == "strict":
            warn(f"ERROR: preflight-agent-budget - agent '{subagent}' refuse")
            warn(
                f"CAUSE: context_budget.py exit={result.returncode} "
                f"(BUDGET_EXCEEDED ou UNBOUNDED_GLOB)"
            )
            warn(
                "FIX: voir table `context_budget` dans workspace/output/db/console.db "
                "(query_console_db.py ou /api/audit) ; reduire reads/ du loader "
                "OU exporter SDD_BUDGET_MODE=warn"
            )
            return 2
        warn(
            f"WARN preflight-agent-budget: budget depasse pour '{subagent}' "
            "(mode=warn, non bloquant)"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
