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
from datetime import datetime, timezone
from pathlib import Path

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.paths import project_root_for_hook  # noqa: E402


def _resolve_project_root() -> Path | None:
    """DRY shim — delegate to `sdd_lib.paths.project_root_for_hook`.

    Audit CTO 2026-06-07 — replaced the 7-line duplicate that pre-dated
    the introduction of `project_root_for_hook` (SSoT P1-5 fix 2026-06-07).
    The SSoT additionally hardens against `CLAUDE_PROJECT_DIR` symlink
    pointing outside the repo (defense against substituted env var).

    Returns the resolved root if a `.claude/` directory exists at it,
    else None (preserves the "skip silently in isolated tmpdir" semantic
    of the original implementation).
    """
    root = project_root_for_hook()
    if (root / ".claude").is_dir():
        return root
    return None


# v7.0.1 audit P1 v2 (2026-06-08) — secret masking before audit log write.
# If a user accidentally exports secrets inline with the bypass attempt
# (e.g. `export MY_DB_PASSWORD=foo SDD_ALLOW_FORCE=1 cmd`), the raw command
# excerpt would leak `MY_DB_PASSWORD=foo` to `.sys/.audit/env-bypass.jsonl`.
# This regex masks any `<NAME>=<value>` assignment where NAME matches
# common secret patterns (PASSWORD/SECRET/TOKEN/KEY/PASSWD/PWD/APIKEY/...).
# Tuned conservatively : only masks the VALUE, not the NAME, so forensics
# can still see WHICH key was exposed without the value itself.
_SECRET_MASK_RE = re.compile(
    r"(?P<prefix>(?P<name>[A-Za-z0-9_]*"
    r"(?:PASSWORD|PASSWD|PWD|SECRET|TOKEN|APIKEY|API_KEY|"
    r"PRIVATE_KEY|ACCESS_KEY|AUTH_KEY|JWT|BEARER|SESSION_ID|"
    r"COOKIE|CREDENTIAL|CRED))"
    r"[\s]*=[\s]*)"
    r"(?P<quote>[\"']?)"
    r"(?P<value>[^\s\"';|&]+)"
    r"(?P=quote)",
    re.IGNORECASE,
)


def _mask_secrets(text: str) -> str:
    """Replace `SECRET_NAME=value` patterns with `SECRET_NAME=***` in audit text.

    Conservative masking : only the VALUE is replaced. The key NAME is
    preserved so forensics can identify which secret was exposed without
    leaking the secret itself. Pattern matches common secret naming
    conventions (PASSWORD/SECRET/TOKEN/KEY/JWT/etc.) case-insensitive.

    Example :
        in:  `export DB_PASSWORD=hunter2 SDD_ALLOW_FORCE=1`
        out: `export DB_PASSWORD=*** SDD_ALLOW_FORCE=1`

    The SDD_ALLOW_* / SDD_DISABLE_* names themselves are NOT masked (they
    are the protected names we are auditing, not secrets).
    """
    return _SECRET_MASK_RE.sub(r"\g<prefix>\g<quote>***\g<quote>", text)


def _audit_log(match: str, cmd: str, bypass_set: bool) -> None:
    """Persist a JSONL audit line for env-bypass denials.

    Non-blocking: any I/O failure here must NOT change the deny decision.
    Path is anchored to CLAUDE_PROJECT_DIR (fallback : walk-up looking for
    `.claude/`) under workspace/output/.sys/.audit/env-bypass.jsonl.

    v7.0.1 audit P1 v2 (2026-06-08) — secret masking : `command_excerpt`
    is passed through `_mask_secrets()` before persistence to prevent
    leaks like `MY_DB_PASSWORD=hunter2` ending up in plain text in the
    audit log (which is gitignored but still on filesystem with potential
    read access by other tools / VSCode extensions).
    """
    try:
        root = _resolve_project_root()
        if root is None:
            return  # no project — skip silently (e.g. pytest in isolated tmpdir)
        audit_dir = root / "workspace" / "output" / ".sys" / ".audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        masked_excerpt = _mask_secrets(cmd[:240])
        line = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "event": "env_bypass_blocked",
            "matched_pattern": match,
            "command_excerpt": masked_excerpt,
            "bypass_flag_inherited": bypass_set,
            "decision": "DENY",
        }
        with (audit_dir / "env-bypass.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        # Audit must not break security. Swallow.
        pass


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
    # PowerShell: New-Item env:NAME (creating new env var without -Path)
    re.compile(rf"\bNew-Item\s+(?:-Path\s+)?[\"']?env:{_NAME_GROUP}[\"']?",
               re.IGNORECASE),
    # PowerShell: [Environment]::SetEnvironmentVariable("NAME", "val")
    re.compile(rf"\[(?:System\.)?Environment\]::SetEnvironmentVariable\s*\(\s*[\"']?{_NAME_GROUP}[\"']?",
               re.IGNORECASE),
    # v7.0.1 audit P0 v2 (2026-06-08) — bypass vectors étendus :
    #
    # POSIX: env VAR=val cmd ... (env-as-prefix invocation, not subshell)
    # Example: `env SDD_ALLOW_FORCE=1 claude /sdd-full 1` — env tool sets var
    # inline for the subprocess without touching parent shell.
    re.compile(rf"\benv\s+(?:-[a-zA-Z]+\s+)*[\"']?{_NAME_GROUP}[\"']?\s*=",
               re.IGNORECASE),
    # POSIX: eval / source / . (dot-source) reading text with VAR=val.
    # Example: `eval "$(echo SDD_ALLOW_X=1 cmd)"` — eval expands then executes.
    # We block any eval/source/`.` invocation containing the protected name in
    # arg context (won't catch every obfuscation — base64 / printf still need
    # the protected name to land in the eventual eval'd string).
    re.compile(rf"\b(?:eval|source|\.)\s+[\"'`(].*?{_NAME_GROUP}",
               re.IGNORECASE | re.DOTALL),
    # POSIX: printf "VAR=val" piped to eval / source.
    # Example: `printf 'SDD_ALLOW_X=1\nclaude\n' | bash`
    re.compile(rf"\bprintf\s+[\"'].*?{_NAME_GROUP}\s*=",
               re.IGNORECASE | re.DOTALL),
    # POSIX: IFS or similar field separator hack with bash -c containing protected name.
    # Example: `IFS=; bash -c "SDD_ALLOW_X=1 cmd"`.
    re.compile(rf"\bbash\s+-c\s+[\"'].*?{_NAME_GROUP}\s*=",
               re.IGNORECASE | re.DOTALL),
]

# Audit consolidé 2026-06-07 Sprint 3-5 — Strip heredoc bodies AVANT le scan
# bypass. Sinon `git commit -m "$(cat <<'EOF'\n... SDD_ALLOW_X=1 ...\nEOF)"`
# fait matcher la doc/message commit comme une vraie tentative de bypass.
# Pattern : `<<['\"]?TAG['\"]?\n ... \nTAG` (heredoc bash) ou son équivalent
# multiline. La regex DOTALL capture le body et le retire AVANT le scan.
_HEREDOC_RE = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?\s*\n.*?\n\1\b",
    re.MULTILINE | re.DOTALL,
)


def _strip_heredocs(cmd: str) -> str:
    """Remove heredoc bodies (between `<<TAG` and matching `TAG`) from a shell command.

    The bypass scan is intended to catch ACTUAL envvar assignment in the
    executable command, not envvar mentions inside heredoc bodies (commit
    messages, doc strings, here-strings). Without this strip, any commit
    message that legitimately documents `SDD_ALLOW_FORCE=1` (e.g. in this
    very hook's docstring referenced by example) would falsely trigger.
    """
    # Iteratively strip — there may be multiple heredocs.
    prev = None
    while prev != cmd:
        prev = cmd
        cmd = _HEREDOC_RE.sub("", cmd)
    return cmd


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
    """Return the matching pattern (for logging) or None if clean.

    Strips heredoc bodies first (audit Sprint 3-5 closure) — a commit message
    or doc string containing the literal `SDD_ALLOW_X=1` no longer triggers
    a false positive. Only ACTUAL assignment in executable command position
    is flagged.
    """
    if not cmd:
        return None
    cleaned = _strip_heredocs(cmd)
    for rx in _BYPASS_REGEXES:
        m = rx.search(cleaned)
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
    bypass_set = os.environ.get("SDD_ALLOW_ENV_BYPASS", "").lower() in ("1", "true", "yes")
    if bypass_set:
        # Even with the bypass flag set, refuse to let the command itself set
        # one of the protected vars — defense-in-depth.
        sys.stderr.write(
            "[block-env-bypass] WARN: SDD_ALLOW_ENV_BYPASS=1 inherited, but still "
            "blocking attempt to set protected envvar mid-session.\n"
            f"matched: {match}\n"
        )

    # Persistent audit (C5 audit 2026-06-06 hardening — JSONL ledger for forensics).
    _audit_log(match, cmd, bypass_set)

    sys.stderr.write(
        "ERROR: Bash command attempts to set a protected SDD_* envvar mid-session.\n"
        f"CAUSE: [ENV_BYPASS_BLOCKED] matched pattern: {match}\n"
        "FIX: protected envvars (SDD_ALLOW_*, SDD_DISABLE_*) must be set in the\n"
        "     parent shell BEFORE starting Claude Code. Setting them mid-session\n"
        "     would bypass cost-cap / acceptance-gate / security guardrails.\n"
        "AUDIT: persisted to workspace/output/.sys/.audit/env-bypass.jsonl\n"
    )
    return HOOK_DENY


if __name__ == "__main__":
    sys.exit(main())
