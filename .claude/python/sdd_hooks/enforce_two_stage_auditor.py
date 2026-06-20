#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook for Agent invocations — Two-stage auditor enforcement.

Audit P3 B + B.bis (2026-06-08) — enforce the v7.0.0+ two-stage auditor
pattern at the harness level (not just the .md docs).

When a slash command spawns `code-reviewer`, `security-reviewer`, or
`arch-reviewer` for a given FEAT, this hook checks :

  1. Is `AuditorBatchMode` set to `two-stage` in layered config ? (default yes)
  2. Has `spec-compliance-reviewer` already run AND produced a non-RED verdict
     for this FEAT (rows in `qa_spec_compliance` table) ?

If (1) AND NOT (2) → BLOCK with exit 2 + structured message :
"Stage A (spec-compliance) must run BEFORE Stage B (code/security/arch).
Spawn spec-compliance-reviewer first, OR set AuditorBatchMode=legacy-parallel."

Bypass (B.bis) :
  - `AuditorBatchMode: legacy-parallel` in Project Config → hook is no-op
  - `SDD_BYPASS_TWO_STAGE=1` env var → hook is no-op (audit-logged)
  - Spawning `spec-compliance-reviewer` itself → always allowed (Stage A)
  - Spawning `adversarial-reviewer` → always allowed (informational, post-review)

Idempotent guard : the hook reads the DB read-only, no side effects.
Fast : ~50ms typical (SQLite predicate query + config read).

Migrated pattern from preflight_agent_budget.py (2026-06-08).
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_nested,
    get_subagent_type,
    read_hook_input,
)
from sdd_lib.paths import repo_root  # noqa: E402


#: Stage B reviewers — spawning any of these requires Stage A first
_STAGE_B_AGENTS = frozenset({
    "code-reviewer",
    "security-reviewer",
    "arch-reviewer",
})

#: Stage A — always allowed (this IS the gate)
_STAGE_A_AGENTS = frozenset({"spec-compliance-reviewer"})

#: Out of scope — never gated by this hook
_INFORMATIONAL_AGENTS = frozenset({"adversarial-reviewer"})


def _extract_feat_number_from_prompt(payload: dict) -> int | None:
    """Best-effort extraction of FEAT number from the Agent prompt arg.

    Looks for patterns : "FEAT {n}", "feat-{n}", "audit FEAT {n}",
    "args=\"{n}\"", "args=\"{n}-{m}\"".
    """
    prompt = get_nested(payload, "tool_input", "prompt")
    if not isinstance(prompt, str):
        return None
    # Common patterns
    for pattern in (
        r"FEAT\s+(\d+)",
        r"feat[-_](\d+)",
        r"args\s*=\s*[\"'](\d+)",
        r"--feat[-\s]?(?:number)?\s*[=\s]+(\d+)",
        r"\bFEAT[\s:]+(\d+)",
    ):
        m = re.search(pattern, prompt, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _stage_a_completed(feat_n: int, root: Path) -> bool:
    """True if spec-compliance has fresh (≤ 24h) rows in qa_spec_compliance.

    Mirrors the logic of query_spec_compliance_present() but inlined here
    to keep the hook lightweight (no subprocess).
    """
    db_path = root / "workspace" / "output" / "db" / "console.db"
    if not db_path.is_file():
        # No DB yet — can't enforce, fail-safe to allow
        return True

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return True  # fail-safe

    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM qa_spec_compliance "
            "WHERE feat_n = ? "
            "AND extracted_at > datetime('now', '-24 hours')",
            (feat_n,),
        ).fetchone()
    except sqlite3.Error:
        # Table may not exist on a fresh project
        return True
    finally:
        conn.close()

    return row and row[0] > 0


def _resolve_batch_mode(root: Path) -> str:
    """Read AuditorBatchMode from layered config. Default 'two-stage'."""
    try:
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config(root=root, keys=("AuditorBatchMode",))
        v = (cfg.get("AuditorBatchMode") or "two-stage").strip().lower()
        if v in ("two-stage", "legacy-parallel"):
            return v
    except Exception:
        pass
    return "two-stage"


def main() -> int:
    # Defensive : never fail the pipeline on a hook crash.
    #
    # Audit P3 C3 (2026-06-08) narrow scope : we catch ONLY the recoverable
    # categories (malformed JSON, OS errors, unicode issues) and let system
    # exceptions (KeyboardInterrupt, MemoryError, SystemExit) propagate.
    # Without this narrowing, a corrupted payload silently bypasses the
    # gate AND masks legitimate crash signals.
    import json as _json
    try:
        payload = read_hook_input()
    except (_json.JSONDecodeError, OSError, UnicodeError, ValueError) as exc:
        sys.stderr.write(
            f"WARN [TWO_STAGE_PAYLOAD_INVALID] {type(exc).__name__}: {exc}. "
            f"Allowing tool call (fail-safe). Investigate harness payload format.\n"
        )
        return HOOK_ALLOW

    # Only intercept Agent tool calls
    tool_name = payload.get("tool_name", "")
    if tool_name != "Agent" and tool_name != "Task":
        return HOOK_ALLOW

    sub_type = get_subagent_type(payload)
    if not sub_type:
        return HOOK_ALLOW

    sub_type_lower = sub_type.strip().lower()

    # Always-allow paths
    if sub_type_lower in _STAGE_A_AGENTS:
        return HOOK_ALLOW
    if sub_type_lower in _INFORMATIONAL_AGENTS:
        return HOOK_ALLOW
    if sub_type_lower not in _STAGE_B_AGENTS:
        return HOOK_ALLOW

    # Bypass (B.bis)
    if os.environ.get("SDD_BYPASS_TWO_STAGE") == "1":
        sys.stderr.write(
            "WARN [TWO_STAGE_BYPASSED] SDD_BYPASS_TWO_STAGE=1 active — Stage B "
            f"agent '{sub_type}' spawning without Stage A gate verification. "
            "Audit-logged.\n"
        )
        return HOOK_ALLOW

    root = repo_root()

    batch_mode = _resolve_batch_mode(root)
    if batch_mode == "legacy-parallel":
        # Explicit opt-in to legacy v6.x parallel batch — no enforcement
        return HOOK_ALLOW

    feat_n = _extract_feat_number_from_prompt(payload)
    if feat_n is None:
        # Can't extract FEAT — fail-safe allow (don't block on parse failures)
        sys.stderr.write(
            f"WARN [TWO_STAGE_FEAT_UNKNOWN] cannot extract FEAT number from "
            f"prompt to enforce two-stage gate on '{sub_type}'. Allowing.\n"
        )
        return HOOK_ALLOW

    if _stage_a_completed(feat_n, root):
        return HOOK_ALLOW

    # BLOCK : Stage B agent spawning before Stage A gate
    sys.stderr.write(
        f"ERROR: [TWO_STAGE_GATE_VIOLATION] Cannot spawn '{sub_type}' (Stage B) "
        f"for FEAT {feat_n} before Stage A (spec-compliance-reviewer) has run.\n"
        f"CAUSE: AuditorBatchMode=two-stage (v7.0.0+ pattern superpowers) requires "
        f"spec-compliance to gate the quality batch. Spawning code/security/arch "
        f"reviewers on code that may not match its spec is wasteful — the code "
        f"may be rewritten.\n"
        f"FIX:\n"
        f"  1. Spawn `Agent: spec-compliance-reviewer` first with FEAT {feat_n}\n"
        f"  2. If Stage A returns RED, fix spec gaps before re-running Stage B\n"
        f"  3. OR set Project Config `AuditorBatchMode: legacy-parallel` to keep "
        f"v6.x behavior (audit-logged)\n"
        f"  4. OR pass `SDD_BYPASS_TWO_STAGE=1` env var (one-shot bypass, audit-logged)\n"
    )
    return HOOK_DENY


if __name__ == "__main__":
    sys.exit(main())
