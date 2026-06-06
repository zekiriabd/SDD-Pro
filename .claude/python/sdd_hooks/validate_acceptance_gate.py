#!/usr/bin/env python3
"""SDD_Pro SubagentStop hook — Acceptance Gate VERDICT READER (refactor 2026-06-05).

Reads the report `workspace/output/.sys/.acceptance/acceptance.json` produced by
`sdd_scripts/validate_acceptance.py` (invoked by the qa agent during its STEP).

Why this hook does NOT run npm test / dotnet build / pytest itself anymore
─────────────────────────────────────────────────────────────────────────
Previous implementation (v7.0.0-alpha audit P5) ran the full check suite
INSIDE this SubagentStop hook. Two problems:
  1. Claude Code hooks must complete in < 5s; running `npm test + dotnet build`
     blocks the agent for minutes and corrupts the agent timeout budget.
  2. The hook held stdin/stderr captured, masking real test output from the
     Tech Lead in the chat.

New design (audit P0-security 2026-06-05):
  - Agent qa explicitly invokes `python .claude/python/sdd_scripts/validate_acceptance.py`
    during its run (it has time, it owns its output stream).
  - That script writes a verdict JSON at a stable path.
  - THIS hook only reads the JSON and decides BLOCK vs ALLOW.
  - Total hook latency: < 100ms (single file read + JSON parse).

Exit codes:
  0 = ALLOW   (verdict=pass / warn / skipped / bypass, OR report missing — see below)
  2 = DENY    (verdict=fail in strict mode)

Report missing behaviour
────────────────────────
If `acceptance.json` is absent, this hook returns 0 (ALLOW) with a stderr
warning. Rationale: the qa agent may have legitimately skipped this STEP
(e.g. mode=off, no projects yet, or the agent's prompt did not invoke the
script). Refusing to ALLOW in that case would make adoption painful and
would not protect against the real attack model: the user running qa
must trust that the agent invoked the script when relevant.

Bypass : SDD_ALLOW_ACCEPTANCE_BYPASS=1 env var (audit-logged in script).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.paths import project_root_for_hook as _resolve_project_root


def main() -> int:
    if os.environ.get("SDD_ALLOW_ACCEPTANCE_BYPASS", "").lower() in ("1", "true", "yes"):
        sys.stderr.write("[acceptance-gate] SDD_ALLOW_ACCEPTANCE_BYPASS=1 — bypass\n")
        return HOOK_ALLOW

    root = _resolve_project_root()
    report_path = root / "workspace" / "output" / ".sys" / ".acceptance" / "acceptance.json"

    if not report_path.is_file():
        # Agent qa did not produce a report this run — non-blocking (see module docstring).
        sys.stderr.write(
            "[acceptance-gate] WARN: no acceptance.json report — "
            "qa agent should invoke `python .claude/python/sdd_scripts/validate_acceptance.py`\n"
        )
        return HOOK_ALLOW

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        sys.stderr.write(f"[acceptance-gate] WARN: cannot parse acceptance.json: {e}\n")
        return HOOK_ALLOW  # corrupt report is not the hook's job to enforce — log and pass

    verdict = (payload.get("verdict") or "").lower()
    mode = (payload.get("mode") or "").lower()

    if verdict in ("pass", "warn", "skipped", "bypass"):
        if verdict == "warn":
            failures = payload.get("failures", [])
            sys.stderr.write(
                f"[acceptance-gate] WARN ({len(failures)} fail(s) in non-strict mode)\n"
            )
        return HOOK_ALLOW

    if verdict == "fail" and mode == "strict":
        failures = payload.get("failures", [])
        sys.stderr.write(
            f"ERROR: AcceptanceGate ({mode}) {len(failures)} échec(s)\n"
            "CAUSE: [ACCEPTANCE_GATE_FAILED]\n"
        )
        for f in failures[:20]:
            msg_tail = (f.get("message") or "").splitlines()[-1] if f.get("message") else ""
            sys.stderr.write(f"  - {f.get('project')} / {f.get('check')} : {msg_tail[:120]}\n")
        sys.stderr.write(
            "FIX: corriger les checks fail OU set AcceptanceGate=warn dans Project Config\n"
        )
        return HOOK_DENY

    # Unknown verdict — non-blocking
    sys.stderr.write(f"[acceptance-gate] WARN: unknown verdict='{verdict}' mode='{mode}'\n")
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
