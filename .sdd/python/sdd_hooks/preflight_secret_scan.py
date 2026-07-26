#!/usr/bin/env python3
"""SDD_Pro PreToolUse.Agent hook — visible WARN when secrets may leak to a non-Anthropic provider.

Audit 2026-07-26 R5 — the Tech Lead's `stack.md` holds live secrets in clear
text (`DB_PASSWORD`, `AUTH_JWT_SECRET`, `AZ_CLIENTSECRET`, `SMTP_PASSWORD` etc.
per CLAUDE.md §9 line "arch propage en appsettings.json / application.yml").
Under the reference combo `claude-code × anthropic` the file is only read by
Anthropic's Zero-Data-Retention endpoint. Under an alternative provider (OpenAI
without enterprise ZDR, Google without a no-log project flag, Moonshot with an
undocumented retention policy) the prompts containing these secrets may be
retained for **30 days for abuse review** by the provider.

This hook :
  1. Reads the active provider from `workspace/stack/stack.md` (`## Active Model Provider`).
  2. If provider ∈ {`openai`, `google`, `moonshot`} AND stack.md contains any of
     the known secret keys, emits a visible WARN with actionable guidance.
  3. Never DENY — this is awareness, not enforcement. Operators can opt out
     entirely with `SDD_ALLOW_SECRET_TO_PROVIDER=1` (audit-logged via
     `block_env_bypass`).
  4. Debounced : the WARN is emitted once per session run_id (marker file
     under `workspace/.sys/.audit/secret-scan-warned-{run_id}.marker`) so the
     Tech Lead is not spammed on every Agent spawn.

Design note : we do NOT scrub the secrets before the sub-agent spawn — that
would require intercepting the prompt payload after Claude constructs it,
which the hook protocol doesn't expose. The mitigation is upstream : either
use the reference combo, or verify the provider's ZDR / no-log flag before
running with secrets in stack.md.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW  # noqa: E402
from sdd_lib.hook_input import read_hook_input, get_subagent_type  # noqa: E402
from sdd_lib.run_id import get_or_create_run_id  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


# Providers assumed to retain prompts for abuse review by default (non-ZDR).
# Anthropic is not listed — with an enterprise or consumer API key, Anthropic
# offers Zero-Data-Retention flag; the default account still has short
# retention but the Anthropic policy is the reference contract of SDD_Pro.
_LEAK_RISK_PROVIDERS: tuple[str, ...] = (
    "openai",       # 30-day retention default; enterprise ZDR opt-in
    "google",       # Gemini API : 55-day retention default on consumer projects
    "moonshot",     # policy undocumented at 2026-07-26 (per moonshot.yaml notes)
)

# Secret keys expected in stack.md per CLAUDE.md §9 and library-and-stack.md §B.
# Regex on assignment form `KEY=value` (stack.md canonical) or `KEY: value`
# (YAML flavor). Case-sensitive per convention (`DB_PASSWORD` not `db_password`).
_SECRET_KEYS: tuple[str, ...] = (
    "DB_PASSWORD",
    "DB_ROOTPASSWORD",
    "AUTH_JWT_SECRET",
    "AUTH_SESSION_SECRET",
    "AZ_CLIENTSECRET",
    "AZ_CLIENTSECRETVALUE",
    "SMTP_PASSWORD",
    "REDIS_PASSWORD",
    "OAUTH_CLIENT_SECRET",
    "OPENAI_API_KEY",     # cross-provider — if a stack.md holds another provider's key
    "GEMINI_API_KEY",
    "MOONSHOT_API_KEY",
)


def _read_active_provider(stack_md: Path) -> str | None:
    """Extract the `Provider:` value from `## Active Model Provider` section.

    Returns lowercase provider id (`anthropic`|`openai`|`google`|`moonshot`)
    or None if the section is absent (rétrocompat = anthropic implicit).
    """
    try:
        text = stack_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = re.search(
        r"^##\s+Active\s+Model\s+Provider\s*$([\s\S]*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE,
    )
    if not m:
        return None
    body = m.group(1)
    p = re.search(r"^\s*Provider\s*:\s*([A-Za-z][A-Za-z0-9_-]*)", body, re.MULTILINE)
    if not p:
        return None
    return p.group(1).strip().lower()


def _stack_has_secrets(stack_md: Path) -> tuple[str, ...]:
    """Return the set of secret keys with non-empty values in stack.md."""
    try:
        text = stack_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ()
    found: list[str] = []
    for key in _SECRET_KEYS:
        # Match `KEY=<non-empty>` or `KEY: <non-empty>`, ignore obvious
        # placeholders (empty string, "TODO", "<...>", "REPLACE_ME").
        # Use `[^\S\n]*` (horizontal whitespace only) to prevent the regex
        # from crossing newlines and picking up the next line's key as this
        # key's value (regression seen 2026-07-26).
        pattern = (
            rf"^[^\S\n]*{re.escape(key)}[^\S\n]*[:=][^\S\n]*"
            rf"([^\s].*?)[^\S\n]*$"
        )
        for m in re.finditer(pattern, text, re.MULTILINE):
            val = m.group(1).strip().strip("\"'")
            if not val:
                continue
            if val.upper() in ("TODO", "REPLACE_ME", "CHANGEME"):
                continue
            if val.startswith("<") and val.endswith(">"):
                continue
            found.append(key)
            break
    return tuple(sorted(set(found)))


def _marker_path(run_id: str) -> Path | None:
    """Marker file to debounce the WARN once per run."""
    try:
        from sdd_lib.paths import workspace_root, repo_root
        d = workspace_root(repo_root()) / ".sys" / ".audit"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"secret-scan-warned-{run_id}.marker"
    except Exception:
        return None


def _resolve_stack_md() -> Path | None:
    try:
        from sdd_lib.paths import workspace_root, repo_root
        sp = workspace_root(repo_root()) / "stack" / "stack.md"
        return sp if sp.is_file() else None
    except Exception:
        return None


def main() -> int:
    # Opt-out : user explicitly accepts the risk (audit-logged via block_env_bypass).
    if (os.environ.get("SDD_ALLOW_SECRET_TO_PROVIDER", "").strip().lower()
            in ("1", "true", "yes")):
        return HOOK_ALLOW

    payload = read_hook_input()
    if not payload:
        return HOOK_ALLOW
    if not get_subagent_type(payload):
        return HOOK_ALLOW

    stack_md = _resolve_stack_md()
    if stack_md is None:
        return HOOK_ALLOW  # pre-bootstrap or workspace not initialized

    provider = _read_active_provider(stack_md)
    if provider is None:
        # Absence of section = anthropic implicit per stack_config.py — no risk.
        return HOOK_ALLOW
    if provider not in _LEAK_RISK_PROVIDERS:
        return HOOK_ALLOW

    secrets = _stack_has_secrets(stack_md)
    if not secrets:
        return HOOK_ALLOW  # nothing sensitive to leak

    # Debounce : only emit the WARN once per run_id.
    run_id = get_or_create_run_id()
    marker = _marker_path(run_id)
    if marker is not None and marker.is_file():
        return HOOK_ALLOW

    warn(
        f"WARN preflight-secret-scan : stack.md contains {len(secrets)} secret key(s) "
        f"({', '.join(secrets)}) AND active provider is `{provider}` — a non-Anthropic "
        f"endpoint may retain prompts for 30-55 days by default."
    )
    warn(
        f"CAUSE: [SECRET_PROVIDER_LEAK_RISK] stack.md secrets sent to `{provider}` "
        f"without an explicit no-log / ZDR contract on this project."
    )
    warn(
        f"FIX: (a) switch back to claude-code × anthropic for FEATs touching these "
        f"secrets, (b) verify the provider account has ZDR / no-log enabled and "
        f"document it in stack.md ## Active Model Provider `TelemetryOptOut: yes`, "
        f"or (c) accept the risk : export SDD_ALLOW_SECRET_TO_PROVIDER=1 in the "
        f"parent shell BEFORE starting the harness (audit-logged)."
    )

    if marker is not None:
        try:
            marker.write_text(f"warned at run_id={run_id}\n", encoding="utf-8")
        except Exception:
            pass  # marker best-effort — WARN was still emitted

    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
