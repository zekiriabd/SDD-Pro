#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook — validate stack combo before /sdd-full or /sdd-poc.

Fires on `PreToolUse` (matcher=Skill). Filters internally to only run before
`/sdd-full` and `/sdd-poc` skill invocations (other skills exit 0 silent).

Calls sdd_scripts/validate_stack_combo.py to check if the active combo from
workspace/input/stack/stack.md matches a PoC-validated combo (C1/C2/...).

Exit semantics (propagated to Claude Code hook decision):
    0  validated OR experimental w/ WARN OR non-applicable skill (continue silent)
    2  untested combo + SDD_ALLOW_UNTESTED_COMBO not set (BLOCK + stderr message)

Non-blocking by design for `experimental` combos (exit 1 from script → exit 0 here +
log warn). Only `untested` (script exit 2) and `invalid` (exit 3) actually block.

v7.0.0-alpha (audit C5 — 2026-06-05) — closes the gap "validate_stack_combo.py exists
but never wired to a hook". Previously documented as recommended in docs/validated-combos.md
§4.3 but never actually enforced.
"""
from __future__ import annotations

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.paths import project_root_for_hook as _resolve_project_root

import json
import os
import subprocess
import sys
from pathlib import Path


# Skills that trigger pipeline execution → require combo validation
PIPELINE_SKILLS = frozenset({"sdd-full", "sdd-poc", "dev-run"})


def _read_payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def _extract_skill_name(payload: dict) -> str | None:
    """Best-effort skill name extraction (Claude Code payload schema may vary)."""
    tool_input = payload.get("tool_input") or {}
    skill = tool_input.get("skill") or tool_input.get("name") or tool_input.get("slash_command")
    if isinstance(skill, str):
        return skill.lstrip("/").lower()
    return None


def main() -> int:
    payload = _read_payload()
    skill = _extract_skill_name(payload)

    # Not a pipeline-execution skill → no-op silent
    if skill not in PIPELINE_SKILLS:
        return HOOK_ALLOW
    # Allow explicit bypass for known-experimental teams
    if os.environ.get("SDD_ALLOW_UNTESTED_COMBO", "").lower() in ("1", "true", "yes"):
        sys.stderr.write(f"[stack-combo] /{skill} : bypass via SDD_ALLOW_UNTESTED_COMBO=1\n")
        return HOOK_ALLOW
    root = _resolve_project_root()
    script = root / ".claude" / "python" / "sdd_scripts" / "validate_stack_combo.py"
    if not script.is_file():
        # Script absent (degraded install) — fail-open
        return HOOK_ALLOW
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--json"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        sys.stderr.write(f"[stack-combo] script execution failed: {exc} — fail-open\n")
        return HOOK_ALLOW
    # Parse JSON output for status
    status = "unknown"
    signature = "?"
    try:
        out = json.loads(result.stdout or "{}")
        status = out.get("status", "unknown")
        signature = out.get("signature", "?")
    except json.JSONDecodeError:
        pass

    code = result.returncode

    if code == 0:
        # validated — silent OK
        return HOOK_ALLOW
    if code == 1:
        # experimental — WARN but continue (non-blocking)
        sys.stderr.write(
            f"[stack-combo] /{skill} WARN — combo experimental "
            f"(signature: {signature}, status: {status}). "
            f"Bypass any-time : SDD_ALLOW_UNTESTED_COMBO=1.\n"
        )
        return HOOK_ALLOW
    if code == 2:
        # untested — BLOCK (unless bypass env var)
        sys.stderr.write(
            f"ERROR: /{skill} blocked — combo non testé\n"
            f"CAUSE: [STACK_COMBO_UNTESTED] signature={signature} status={status} — au moins un composant 🔴\n"
            f"FIX: vérifier workspace/input/stack/stack.md OU bypass via SDD_ALLOW_UNTESTED_COMBO=1\n"
        )
        return HOOK_DENY
    if code == 3:
        # invalid — BLOCK strict
        sys.stderr.write(
            f"ERROR: /{skill} blocked — combo invalide\n"
            f"CAUSE: [STACK_COMBO_INVALID] signature={signature}\n"
            f"FIX: corriger workspace/input/stack/stack.md (cf. .claude/docs/validated-combos.md)\n"
        )
        return HOOK_DENY
    if code == 4:
        # io_error (stack.md absent) — fail-open with warn
        sys.stderr.write(
            f"[stack-combo] /{skill} WARN — stack.md illisible (peut-être projet vierge)\n"
        )
        return HOOK_ALLOW
    # Unknown exit code — fail-open
    sys.stderr.write(f"[stack-combo] unknown exit {code} — fail-open\n")
    return HOOK_ALLOW
if __name__ == "__main__":
    sys.exit(main())
