#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (matcher=Bash) — block envvar bypass attempts.

Defense-in-depth complement to settings.json `permissions.deny` Bash patterns,
which are case-sensitive and miss obvious bypass variants:
  - sDd_AlLoW_X=1 (case)
  - "SDD_ALLOW_X"=1 (quoted)
  - export   SDD_ALLOW_X=1 (extra whitespace)
  - bash -c 'SDD_ALLOW_X=1 …' (nested shell)
  - SDD_ALLOW_X="1" (quoted value)

This hook receives the Bash invocation payload on stdin (Claude Code PreToolUse
schema), normalizes the command string, and rejects ANY case-insensitive
occurrence of the protected envvar names being SET to a truthy value, regardless
of escaping/casing/quoting.

Exit codes:
  0 = ALLOW
  2 = DENY (hook protocol — Claude refuses the tool call)

Bypass for legitimate use cases (rare): set SDD_ALLOW_ENV_BYPASS=1 in the parent
shell BEFORE starting Claude Code. That envvar itself is in the protected set so
it cannot be set mid-session — only inherited from the parent process.
"""
from __future__ import annotations

import json
import os
import re
import sys

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402


# Protected envvar name patterns (case-insensitive substring match on var name).
# These names, when SET to a truthy value, bypass cost caps, security gates, or
# other guardrails. Setting them mid-session would let an agent or executed
# script silently disable protections.
PROTECTED_PATTERNS = [
    r"SDD_ALLOW_[A-Z_]*",
    r"SDD_DISABLE_[A-Z_]*",
]

# Compile a single regex that catches:
#   [export ]   ?   NAME   ? = ? "?value"?
#   $env:NAME = "value"
#   setx NAME value
#   Set-Variable env:NAME value
# Where NAME matches any PROTECTED_PATTERNS, case-insensitively.
_NAME_GROUP = "(?:" + "|".join(PROTECTED_PATTERNS) + ")"

_BYPASS_REGEXES = [
    # POSIX: [export] NAME=val   |   NAME="val"   |   NAME='val'
    re.compile(rf"(?:^|[\s;&|`(])(?:export\s+)?[\"']?{_NAME_GROUP}[\"']?\s*=\s*[\"']?\S",
               re.IGNORECASE),
    # PowerShell: $env:NAME = "val"
    re.compile(rf"\$env:[\"']?{_NAME_GROUP}[\"']?\s*=", re.IGNORECASE),
    # Windows: setx NAME val
    re.compile(rf"\bsetx\s+[\"']?{_NAME_GROUP}[\"']?\s+\S", re.IGNORECASE),
    # PowerShell: Set-Variable / Set-Item env:NAME val
    re.compile(rf"\b(?:Set-Variable|Set-Item)\s+(?:-Name\s+)?[\"']?env:{_NAME_GROUP}[\"']?",
               re.IGNORECASE),
]


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read() or "{}"
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _extract_command(payload: dict) -> str:
    # Claude Code Bash tool payload shape: {"tool_input": {"command": "..."}, ...}
    tool_input = payload.get("tool_input") or {}
    cmd = tool_input.get("command")
    if isinstance(cmd, str):
        return cmd
    return ""


def _matches_bypass(cmd: str) -> str | None:
    """Return the matching pattern (for logging) or None if clean."""
    if not cmd:
        return None
    for rx in _BYPASS_REGEXES:
        m = rx.search(cmd)
        if m:
            return m.group(0)[:120]
    return None


def main() -> int:
    # Inherited-from-parent bypass: must be set BEFORE Claude Code starts.
    # We can't reliably distinguish "inherited" from "just-set" inside the same
    # session, but we can detect the canonical pattern: if it's set AND the
    # current Bash command does NOT try to set it, allow.
    payload = _read_payload()
    cmd = _extract_command(payload)
    match = _matches_bypass(cmd)
    if match is None:
        return HOOK_ALLOW

    # Allow only if the parent-process bypass flag was set BEFORE this command
    # tries to set an envvar — and the command itself is NOT trying to set
    # one of the protected names (which would re-enable a bypass mid-session).
    if os.environ.get("SDD_ALLOW_ENV_BYPASS", "").lower() in ("1", "true", "yes"):
        # Even with the bypass flag set, refuse to let the command itself set
        # one of the protected vars — defense-in-depth.
        sys.stderr.write(
            "[block-env-bypass] WARN: SDD_ALLOW_ENV_BYPASS=1 inherited, but still "
            "blocking attempt to set protected envvar mid-session.\n"
            f"matched: {match}\n"
        )

    sys.stderr.write(
        "ERROR: Bash command attempts to set a protected SDD_* envvar mid-session.\n"
        f"CAUSE: [ENV_BYPASS_BLOCKED] matched pattern: {match}\n"
        "FIX: protected envvars (SDD_ALLOW_*, SDD_DISABLE_*) must be set in the\n"
        "     parent shell BEFORE starting Claude Code. Setting them mid-session\n"
        "     would bypass cost-cap / acceptance-gate / security guardrails.\n"
    )
    return HOOK_DENY


if __name__ == "__main__":
    sys.exit(main())
