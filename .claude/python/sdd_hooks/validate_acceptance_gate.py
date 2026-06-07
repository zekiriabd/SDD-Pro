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

Report missing behaviour (audit 2026-06-06 D7 — strict mode in CI)
─────────────────────────────────────────────────────────────────
If `acceptance.json` is absent, behaviour now depends on context:

  - CI (auto-detected via $CI / $GITHUB_ACTIONS / $GITLAB_CI / ...)
    → DENY with `[ACCEPTANCE_REPORT_MISSING]` so the build fails loud.
    Rationale: in CI, the absence of acceptance.json signals either a
    misconfigured pipeline (qa agent did NOT invoke the script) or a
    silent skip — both are bugs that must surface before merge.

  - Interactive (Tech Lead running /sdd-full locally)
    → ALLOW with stderr WARN. Rationale: legitimate workflows include
    intentional skip (mode=off, no projects yet) and adoption ramp.
    The Tech Lead sees the WARN and decides.

  - Bypass for both contexts: SDD_ALLOW_ACCEPTANCE_BYPASS=1.

Before this audit fix, the missing-report case ALWAYS returned ALLOW,
including in CI — silent failure mode. The change aligns with the
existing pattern in preflight_cost_cap.py (telemetry-unavailable case).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sdd_lib.ci import is_ci as _detect_ci  # noqa: E402  # SSoT audit 2026-06-07
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.paths import project_root_for_hook as _resolve_project_root


def main() -> int:
    if os.environ.get("SDD_ALLOW_ACCEPTANCE_BYPASS", "").lower() in ("1", "true", "yes"):
        sys.stderr.write("[acceptance-gate] SDD_ALLOW_ACCEPTANCE_BYPASS=1 — bypass\n")
        return HOOK_ALLOW

    root = _resolve_project_root()
    report_path = root / "workspace" / "output" / ".sys" / ".acceptance" / "acceptance.json"

    if not report_path.is_file():
        # Audit 2026-06-06 D7 — strict mode in CI, soft mode interactive.
        # The pre-D7 behaviour was ALWAYS ALLOW, which made the gate purely
        # decorative whenever the qa agent skipped the validate_acceptance.py
        # call (intentionally or by bug). Now CI fails loud, interactive
        # warns and continues. Bypass for both via SDD_ALLOW_ACCEPTANCE_BYPASS.
        is_ci = _detect_ci()
        # Audit final 2026-06-07 (CRIT-4 closure) : retrait du fallback
        # interactif HOOK_ALLOW. Avant ce fix, agent qa qui oubliait
        # d'invoquer validate_acceptance.py voyait son SubagentStop allow
        # silencieusement → l'Acceptance Gate ne tournait JAMAIS en
        # interactif. Désormais symétrique CI/interactif : DENY systématique
        # avec bypass explicite SDD_ALLOW_ACCEPTANCE_BYPASS=1.
        sys.stderr.write(
            "[acceptance-gate] DENY: no acceptance.json report\n"
            "CAUSE: [ACCEPTANCE_REPORT_MISSING] qa agent did not invoke "
            "validate_acceptance.py — gate cannot verify pass/fail\n"
            "FIX: ensure agent qa runs `python .claude/python/sdd_scripts/"
            "validate_acceptance.py` before SubagentStop, OR set env var "
            "SDD_ALLOW_ACCEPTANCE_BYPASS=1 to skip gate (audit-logged)\n"
        )
        return HOOK_DENY

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
