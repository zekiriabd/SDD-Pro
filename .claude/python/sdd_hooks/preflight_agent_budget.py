#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook for Agent invocations.

Intercepts Agent tool calls: extracts `subagent_type` + best-effort
FEAT/US identifiers from the prompt, delegates to context_budget script
which writes the JSONL ledger.

Mode controlled by env $SDD_BUDGET_MODE:
    - "warn"   (default in interactive) : ledger + WARN on stderr, exit 0
    - "strict"            : block invocation if budget exceeded (exit 2)
    - "off"               : silent skip (exit 0)

v7.0.0 (codex audit P0 #6 follow-up) : default flips to "strict"
automatically when CI env is detected (any of CI, GITHUB_ACTIONS,
GITLAB_CI, CIRCLECI, JENKINS_URL, BUILDKITE, TRAVIS env vars set
truthy). This converts the soft context_budget warning into a hard CI
gate without breaking interactive dev workflows. Override : explicit
SDD_BUDGET_MODE=warn in the CI env wins back the soft behavior.

Migrated from .claude/hooks/preflight-agent-budget.ps1 (2026-05-13).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.ci import is_ci  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_nested,
    get_subagent_type,
    read_hook_input,
)
from sdd_lib.stderr import warn  # noqa: E402


ALLOWED_AGENTS: set[str] = {
    # Core + support (4 + 3) — v7.0.0 : `dashboard` retiré
    # (remplacé par script déterministe index_adrs.py).
    "po", "arch", "dev-backend", "dev-frontend",
    "qa", "elicitor", "constitutioner",
    # Auditors retained in v7.0.0 (4) — accessibility-auditor and
    # performance-auditor were removed in v7.0.0
    # (governance-major-auditors-trim).
    "code-reviewer", "security-reviewer",
    "spec-compliance-reviewer", "arch-reviewer",
    # Adversarial reviewer (R1 v7.2.0 opt-in, informational verdict).
    # Audit 2026-06-06 RUPT-1 — l'agent était manifest+prompt+command
    # mais absent des 3 collections Python -> hard-fail
    # [AGENT_NOT_ALLOWLISTED] sur tout `/sdd-review --adversarial`.
    "adversarial-reviewer",
}

# Agents explicitly removed in v7.0.0 — the hook ACTIVELY rejects these
# invocations with [AGENT_REMOVED_V7] (exit 2 in strict, WARN in soft mode)
# instead of silently skipping. This catches stale callers (commands, hooks,
# scripts) that haven't been migrated yet.
REJECTED_AGENTS_V7: dict[str, str] = {
    "accessibility-auditor": "axe-core CI step in the generated project",
    "performance-auditor":   "Lighthouse CI + wrk/k6 in the generated project",
    "dashboard":             "sdd_scripts/index_adrs.py (0 token, deterministic)",
    "dev-backend-strict":    "dev-backend (Opus 4.7) — strict variant removed v7.0.0",
    "dev-frontend-strict":   "dev-frontend (Opus 4.7) — strict variant removed v7.0.0",
}


def extract_us_and_feat(haystack: str) -> tuple[int, str]:
    """Best-effort regex extraction of FEAT number and US id from the prompt.

    v7.0.1 (audit C3) : tightened regex to require an SDD-shaped anchor
    (FEAT/US prefix, command name, or `{n}-{m}-{Name}` SDD basename) to
    avoid spurious matches on arbitrary numeric pairs in the prompt
    (e.g. "42-1234" inside an unrelated identifier or path). The legacy
    free-form `\\b(\\d{1,3})-(\\d{1,3})\\b` pattern is preserved as a
    fallback so usability is unchanged in ambiguous contexts.
    """
    feat_number = 0
    us_id = ""

    # Pass 1 (strict) : SDD-anchored {n}-{m} reference. Either preceded by
    # a command/keyword, or followed by `-{Name}` capitalised basename.
    m_us = re.search(
        r"(?i)(?:"
        r"(?:FEAT|us|sdd-full|/?dev-run|/?dev-plan|/?dev-backend|/?dev-frontend"
        r"|/?qa-generate|/?us-generate|/?arch-init|/?feat-validate)"
        r"\s*[-:]?\s*"
        r"|\b"  # OR plain word boundary if followed by Capital basename
        r")(\d{1,3})-(\d{1,3})(?:-[A-Z][A-Za-z0-9\-]*)?\b",
        haystack,
    )
    if m_us:
        us_id = f"{m_us.group(1)}-{m_us.group(2)}"
        feat_number = int(m_us.group(1))
        return feat_number, us_id

    # Pass 2 (lenient fallback) : any {n}-{m} pair, but require both numbers
    # ≤ 999 and not adjacent to other digits/letters (avoid mid-identifier matches).
    m_us2 = re.search(r"(?<![\w-])(\d{1,3})-(\d{1,3})(?![\w-])", haystack)
    if m_us2:
        us_id = f"{m_us2.group(1)}-{m_us2.group(2)}"
        feat_number = int(m_us2.group(1))
        return feat_number, us_id

    # Pass 3 : FEAT-only reference (no US id)
    m_feat = re.search(
        r"(?i)\b(?:FEAT|feat-?|sdd-full|us-generate|dev-run|dev-plan|qa-generate)\s*[-:]?\s*(\d{1,3})\b",
        haystack,
    )
    if m_feat:
        feat_number = int(m_feat.group(1))

    return feat_number, us_id


def _resolve_mode() -> str:
    """Resolve the operative mode :
    1. SDD_BUDGET_MODE env var if explicitly set
    2. "strict" if CI env detected (codex P0 follow-up)
    3. "warn" otherwise

    CI detection delegated to `sdd_lib.ci.is_ci` (SSoT, audit CTO 2026-06-07).
    """
    explicit = os.environ.get("SDD_BUDGET_MODE", "").strip().lower()
    if explicit:
        return explicit
    if is_ci():
        return "strict"
    return "warn"


def main() -> int:
    mode = _resolve_mode()
    if mode == "off":
        return HOOK_ALLOW
    payload = read_hook_input()
    if not payload:
        return HOOK_ALLOW
    subagent = get_subagent_type(payload)
    if not subagent:
        return HOOK_ALLOW
    # v7.0.0 — explicitly reject removed agents (strict in CI, WARN otherwise).
    if subagent in REJECTED_AGENTS_V7:
        replacement = REJECTED_AGENTS_V7[subagent]
        warn(f"ERROR: preflight-agent-budget — agent '{subagent}' retire en v7.0.0")
        warn(f"CAUSE: [AGENT_REMOVED_V7] {subagent} supprime "
             f"(governance-major-auditors-trim)")
        warn(f"FIX: utiliser remplacement : {replacement}")
        # In strict mode (CI), block the invocation. In warn mode (interactive),
        # the operator sees the WARN but can proceed.
        if mode == "strict":
            return HOOK_DENY
        return HOOK_ALLOW

    if subagent not in ALLOWED_AGENTS:
        # Unknown agent — silent skip preserves backward-compat with custom
        # agents not registered in SDD_Pro framework.
        return HOOK_ALLOW

    prompt = get_nested(payload, "tool_input", "prompt", default="") or ""
    descr = get_nested(payload, "tool_input", "description", default="") or ""
    haystack = f"{prompt} {descr}"
    feat_number, us_id = extract_us_and_feat(haystack)

    script_path = Path(__file__).resolve().parent.parent / "sdd_scripts" / "context_budget.py"
    if not script_path.is_file():
        warn(f"WARN preflight-agent-budget: context_budget.py introuvable ({script_path})")
        return HOOK_ALLOW
    cmd: list[str] = [sys.executable, str(script_path), "--agent", subagent]
    if feat_number > 0:
        cmd += ["--feat-number", str(feat_number)]
    if us_id:
        cmd += ["--us-id", us_id]

    # Timeout 30s (security audit fix 2026-06-06 — was 10s with fail-OPEN, which
    # could bypass budget enforcement on the largest reads/ patterns precisely
    # where it matters most — e.g. spec-compliance-reviewer measured 47MB/$35
    # in 31s). New policy : timeout 30s + fail-CLOSED in strict mode (CI/cost cap)
    # to prevent silent bypass of budget guards. Warn mode keeps fail-OPEN
    # interactively to avoid blocking the Tech Lead on a stalled DB lock.
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        warn(f"WARN preflight-agent-budget: context_budget.py timed out (>30s)")
        if mode == "strict":
            warn(f"ERROR: preflight-agent-budget — agent '{subagent}' refuse (timeout strict)")
            warn(f"CAUSE: [BUDGET_PRECHECK_TIMEOUT] context_budget.py >30s on {subagent}")
            warn(f"FIX: investiguer reads/ patterns dans loader.yml ; OU exporter SDD_BUDGET_MODE=warn pour bypass interactif tracé")
            return HOOK_DENY
        warn(f"     Fail-OPEN (mode=warn, interactif). Investigate reads/ patterns in loader.yml.")
        return HOOK_ALLOW
    except OSError as e:
        warn(f"WARN preflight-agent-budget: subprocess failed: {e}")
        if mode == "strict":
            warn(f"ERROR: preflight-agent-budget — subprocess error en mode strict, refuse")
            return HOOK_DENY
        return HOOK_ALLOW
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
            return HOOK_DENY
        warn(
            f"WARN preflight-agent-budget: budget depasse pour '{subagent}' "
            "(mode=warn, non bloquant)"
        )

    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
