#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook — REVERSE-GATE before /sdd-full, /sdd-poc, /dev-run.

Fires on `PreToolUse` (matcher=Skill). Filters internally to only run before
pipeline-execution skills; other skills exit 0 silent.

Closes audit finding M1-reverse (2026-06-12): a FEAT produced by the reverse
module (`generated-by: sdd-reverse`) with confidence ∈ {medium, low} could be
fed to `/sdd-full` with **no automatic obstacle** — the only gate
(`check_reverse_feat_for_full.py`) was documented as a *manual* Tech-Lead
invocation and wired nowhere. This additive hook enforces it WITHOUT touching
`/sdd-full` itself (design doc §3.1 isolation): it resolves the target FEAT
from the skill args and delegates the verdict to the existing deterministic
script.

Exit semantics (propagated to Claude Code hook decision):
    0  non-reverse FEAT, reverse+high, bypass set, or any infra ambiguity
       (FEAT not found / not determinable) → fail-open, continue silent
    2  reverse FEAT with confidence ∈ {medium, low} and no bypass → BLOCK

Bypass (audit-logged via the script's own contract): set
`SDD_ALLOW_REVERSE_LOW=1` → the gate passes `--allow-reverse-low` and the
script returns 0. Mirrors the `SDD_ALLOW_UNTESTED_COMBO` pattern of
`preflight_stack_combo.py`.

Fail-open philosophy: any uncertainty (no feat number in args, FEAT glob
matches 0 or >1 files, script missing, subprocess error) → ALLOW. The gate
only ever blocks on an unambiguous reverse+low/medium verdict (script exit 1).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import get_nested, read_hook_input  # noqa: E402
from sdd_lib.paths import workspace_root, project_root_for_hook as _resolve_project_root  # noqa: E402

# Skills that execute the forward pipeline on a FEAT → require the reverse gate.
PIPELINE_SKILLS = frozenset({"sdd-full", "sdd-poc", "dev-run"})


def _extract_skill_name(payload: dict) -> str | None:
    for key in ("skill", "name", "slash_command", "command"):
        v = get_nested(payload, "tool_input", key)
        if isinstance(v, str) and v.strip():
            return v.lstrip("/").lower()
    return None


def _extract_feat_number(payload: dict) -> int | None:
    for key in ("args", "arguments", "input"):
        v = get_nested(payload, "tool_input", key)
        if isinstance(v, str):
            m = re.search(r"\b(\d+)\b", v)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    return None
    return None


def main() -> int:
    payload = read_hook_input()
    skill = _extract_skill_name(payload)
    if skill not in PIPELINE_SKILLS:
        return HOOK_ALLOW

    feat_n = _extract_feat_number(payload)
    if feat_n is None:
        # Can't determine which FEAT → fail-open (gate is best-effort).
        return HOOK_ALLOW

    root = _resolve_project_root()
    feats_dir = workspace_root(root) / "feats"
    matches = sorted(feats_dir.glob(f"{feat_n}-*.md")) if feats_dir.is_dir() else []
    if len(matches) != 1:
        # 0 = FEAT not created yet (or wrong dir) ; >1 = ambiguous → fail-open.
        return HOOK_ALLOW

    script = root / ".sdd" / "python" / "sdd_reverse_scripts" / "check_reverse_feat_for_full.py"
    if not script.is_file():
        return HOOK_ALLOW  # reverse module absent (degraded install) → fail-open

    cmd = [sys.executable, str(script), "--feat-path", str(matches[0]), "--json"]
    bypass = os.environ.get("SDD_ALLOW_REVERSE_LOW", "").lower() in ("1", "true", "yes")
    if bypass:
        cmd.append("--allow-reverse-low")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(root), timeout=15
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        sys.stderr.write(f"[reverse-gate] /{skill} : script error {exc} — fail-open\n")
        return HOOK_ALLOW

    code = result.returncode
    if code == 0:
        if bypass:
            sys.stderr.write(
                f"[reverse-gate] /{skill} FEAT {feat_n} : bypass via SDD_ALLOW_REVERSE_LOW=1\n"
            )
        return HOOK_ALLOW
    if code == 1:
        # Unambiguous reverse + confidence ∈ {medium, low}, no bypass → BLOCK.
        sys.stderr.write(
            f"ERROR: /{skill} blocked — reverse FEAT {feat_n} not validated for /sdd-full\n"
            f"CAUSE: [REVERSE_GATE_BLOCKED] {matches[0].name} confidence != high "
            f"(REVERSE-GATE allow-sdd-full=false) — human review required\n"
            f"FIX: review the reverse FEAT, raise its confidence after verification, OR "
            f"bypass (audit-logged) via SDD_ALLOW_REVERSE_LOW=1\n"
        )
        return HOOK_DENY
    # Script infra error (exit 2: FEAT unreadable / ambiguous glob) → fail-open.
    sys.stderr.write(f"[reverse-gate] /{skill} : check exit {code} — fail-open\n")
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
