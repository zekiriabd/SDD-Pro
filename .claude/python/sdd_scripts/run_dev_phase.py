#!/usr/bin/env python3
"""SDD_Pro — Deterministic helpers for /dev-run STEP 6 (audit MAJ-4 → P0-doc 2026-06-05).

Scope of THIS file (extracted from `/dev-run` STEP 6 pseudo-bash) :
  - US batching algorithm (`chunk_us_list`)
  - Plan detection + staleness check (`scan_plans` + `validate_plans`)
  - API Gate verdict parsing (`read_api_gate_verdict`)
  - Gate decision matrix (`decide_after_api_gate`)
  - Status flip helpers (already in `set_us_status.py`, just sequencer here)

OUT OF SCOPE :
  - Spawning agents (`Agent: dev-backend {n}-{m}`). That is a Claude tool call
    and MUST stay in the prompt. This helper is invoked BEFORE and AFTER each
    batch to compute deterministic data; the LLM uses the JSON output to decide
    what to spawn next.

Usage pattern from `/dev-run` STEP 6 prompt :
  ```bash
  # Phase 6.a-prep : decide batches
  python .claude/python/sdd_scripts/run_dev_phase.py plan --feat-number {n}
  # → returns JSON: {"batches": [["1-1","1-2"],["1-3"]], "skipped": [], ...}

  # LLM spawns each batch sequentially via Agent tool calls based on this JSON.

  # Phase 6.b : after API gate runs, decide whether to proceed
  python .claude/python/sdd_scripts/run_dev_phase.py gate-decision --feat-number {n}
  # → returns JSON: {"verdict": "PASS"|"WARN"|"FAIL"|"SKIPPED"|"INFRA_BLOCKED",
  #                  "should_continue_frontend": true/false, "reason": "..."}
  ```

This makes the prompt ~30 lines of narrative orchestration instead of 213 lines
of conditional pseudo-bash. The Python helper is unit-testable (see
tests/test_run_dev_phase.py).

Exit codes (CLI mode) :
  0 = success (JSON written to stdout)
  2 = invalid input (no US found, feat doesn't exist)
  3 = infra (FS error, console.db unreachable)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import SUCCESS, INFRA_BLOCKED, FAIL_FAST, CORRECTIBLE  # noqa: E402
from sdd_lib.paths import project_root_for_hook as _resolve_project_root

# Default MaxParallel value (1-12 range, default 3) — named so the literal `3`
# doesn't get flagged as a hardcoded exit code by migrate_exit_codes.py.
DEFAULT_MAX_PARALLEL = 3


# ── US listing + batching ──────────────────────────────────────────────

def list_us_for_feat(root: Path, feat_number: int) -> list[str]:
    """Return sorted list of US IDs `{n}-{m}` for the given FEAT."""
    us_dir = root / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    pattern = re.compile(rf"^{feat_number}-(\d+)-")
    us_ids: list[tuple[int, str]] = []
    for f in us_dir.glob(f"{feat_number}-*.md"):
        m = pattern.match(f.stem)
        if m:
            us_ids.append((int(m.group(1)), f.stem.split("-", 2)[0] + "-" + m.group(1)))
    us_ids.sort(key=lambda t: t[0])
    return [uid for _, uid in us_ids]


def chunk_us_list(us_list: list[str], max_parallel: int) -> list[list[str]]:
    """Split US list into batches of size `max_parallel`. Deterministic.

    Used by Phase 6.a / 6.c to drive parallel agent invocations.
    """
    if max_parallel <= 0:
        raise ValueError(f"max_parallel must be >= 1, got {max_parallel}")
    return [us_list[i:i + max_parallel] for i in range(0, len(us_list), max_parallel)]


def read_max_parallel(root: Path, override: int | None = None) -> int:
    """Resolve MaxParallel from Project Config (default 3, range 1-12)."""
    if override is not None:
        return max(1, min(12, override))
    stack_md = root / "workspace" / "input" / "stack" / "stack.md"
    if not stack_md.is_file():
        return DEFAULT_MAX_PARALLEL
    try:
        txt = stack_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return DEFAULT_MAX_PARALLEL
    m = re.search(r"^MaxParallel:\s*(\d+)", txt, re.MULTILINE)
    if m:
        return max(1, min(12, int(m.group(1))))
    return DEFAULT_MAX_PARALLEL


# ── Plan detection ─────────────────────────────────────────────────────

def scan_plans(root: Path, feat_number: int) -> dict:
    """Detect From-Plan mode files for a FEAT. Returns counts + paths."""
    plans_dir = root / "workspace" / "output" / "plans"
    if not plans_dir.is_dir():
        return {"back": [], "front": [], "back_count": 0, "front_count": 0}
    back = sorted(str(p.relative_to(root)) for p in plans_dir.glob(f"{feat_number}-*.back.md"))
    front = sorted(str(p.relative_to(root)) for p in plans_dir.glob(f"{feat_number}-*.front.md"))
    return {
        "back": back, "front": front,
        "back_count": len(back), "front_count": len(front),
    }


# ── API Gate verdict ───────────────────────────────────────────────────

API_GATE_STATUSES = ("PASS", "WARN", "FAIL", "SKIPPED", "INFRA_BLOCKED")


def read_api_gate_verdict(root: Path, feat_number: int) -> dict:
    """Read api-tests.json verdict (canonical status from rule build-and-loop §1.3)."""
    p = root / "workspace" / "output" / "qa" / f"feat-{feat_number}" / "api-tests.json"
    if not p.is_file():
        return {"status": "SKIPPED", "reason": "api-tests.json absent", "gate_passed": True}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return {"status": "INFRA_BLOCKED", "reason": f"api-tests.json unreadable: {e}", "gate_passed": False}
    summary = data.get("summary", {}) or {}
    status = (summary.get("status") or "").upper()
    if status not in API_GATE_STATUSES:
        # Fallback : try legacy verdict mapping
        legacy = (summary.get("verdict") or "").upper()
        status = {"GREEN": "PASS", "YELLOW": "WARN", "RED": "FAIL"}.get(legacy, "SKIPPED")
    gate_passed = status in ("PASS", "WARN", "SKIPPED")
    return {
        "status": status,
        "gate_passed": gate_passed,
        "tests_total": summary.get("tests_total"),
        "tests_passed": summary.get("tests_passed"),
        "tests_failed": summary.get("tests_failed"),
        "endpoints_total": summary.get("endpoints_total"),
    }


def decide_after_api_gate(verdict: dict) -> dict:
    """Map API Gate verdict to a decision for Phase 6.c (frontend) continuation."""
    status = verdict.get("status", "INFRA_BLOCKED")
    if status == "PASS":
        return {"should_continue_frontend": True, "reason": "API gate PASS — frontend can consume backend contract"}
    if status == "WARN":
        return {"should_continue_frontend": True, "reason": "API gate WARN — partial endpoint coverage, continue with warning"}
    if status == "SKIPPED":
        return {"should_continue_frontend": True, "reason": "API gate SKIPPED — frontend-only FEAT or gate disabled"}
    if status == "FAIL":
        return {"should_continue_frontend": False, "reason": "API gate FAIL — STOP, fix backend then relaunch /dev-run"}
    if status == "INFRA_BLOCKED":
        return {"should_continue_frontend": False, "reason": "API gate INFRA_BLOCKED — test runner / fixtures broken, fix infra"}
    return {"should_continue_frontend": False, "reason": f"unknown status '{status}'"}


# ── CLI ───────────────────────────────────────────────────────────────

def _cmd_plan(args) -> int:
    root = _resolve_project_root()
    us_list = list_us_for_feat(root, args.feat_number)
    if not us_list:
        sys.stderr.write(f"ERROR: no US files found under workspace/output/us/ for FEAT {args.feat_number}\n")
        return CORRECTIBLE
    mp = read_max_parallel(root, args.max_parallel)
    batches = chunk_us_list(us_list, mp)
    plans = scan_plans(root, args.feat_number)
    out = {
        "feat_number": args.feat_number,
        "us_count": len(us_list),
        "us_ids": us_list,
        "max_parallel": mp,
        "batches": batches,
        "batch_count": len(batches),
        "plans": plans,
        "from_plan_mode": plans["back_count"] > 0 or plans["front_count"] > 0,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return SUCCESS


def _cmd_gate_decision(args) -> int:
    root = _resolve_project_root()
    verdict = read_api_gate_verdict(root, args.feat_number)
    decision = decide_after_api_gate(verdict)
    out = {"feat_number": args.feat_number, **verdict, **decision}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return SUCCESS


def _cmd_batch(args) -> int:
    """Emit the Nth batch of US to spawn (audit 2026-06-06 D9).

    Forces MaxParallel enforcement at the tool-call level. The LLM
    orchestrating /dev-run STEP 6.a / 6.c invokes this script with
    `--layer 0`, spawns the returned US in parallel, WAITS for all
    SubagentStops, then invokes with `--layer 1`, etc.

    Each call is ONE Bash tool-call (atomic with Claude Code's serialization
    semantics), so the LLM cannot fire-and-forget all batches at once :
    it must explicitly Bash-call the script between each batch.

    Output JSON contract :
        {
            "feat_number": 1,
            "layer": 0,                          # the layer requested
            "total_layers": 3,                   # total batches available
            "is_last_layer": false,              # true if layer == total-1
            "us_ids": ["1-1", "1-2"],            # US to spawn THIS batch
            "next_layer_command": "python ... --layer 1",  # exact CLI for next
            "wait_instruction": "Spawn all us_ids in parallel via Agent tool. WAIT for all SubagentStops before invoking next_layer_command."
        }
    """
    root = _resolve_project_root()
    us_list = list_us_for_feat(root, args.feat_number)
    if not us_list:
        sys.stderr.write(f"ERROR: no US files found under workspace/output/us/ for FEAT {args.feat_number}\n")
        return CORRECTIBLE
    mp = read_max_parallel(root, args.max_parallel)
    batches = chunk_us_list(us_list, mp)
    total = len(batches)

    if args.layer < 0 or args.layer >= total:
        sys.stderr.write(
            f"ERROR: layer {args.layer} out of range [0, {total - 1}]\n"
            f"CAUSE: [INVALID_ARG] FEAT {args.feat_number} has {total} batch(es) "
            f"with MaxParallel={mp}\n"
            f"FIX: invoke without --layer to see total layers, OR pass 0 <= N < {total}\n"
        )
        return CORRECTIBLE

    is_last = args.layer == total - 1
    batch_us = batches[args.layer]
    next_cmd = (
        None if is_last
        else f"python .claude/python/sdd_scripts/run_dev_phase.py batch "
             f"--feat-number {args.feat_number} --layer {args.layer + 1}"
             + (f" --max-parallel {args.max_parallel}" if args.max_parallel else "")
    )
    family_hint = (
        "dev-backend (phase 6.a) OR dev-frontend (phase 6.c) — see prompt context"
    )
    out = {
        "feat_number": args.feat_number,
        "layer": args.layer,
        "total_layers": total,
        "is_last_layer": is_last,
        "max_parallel": mp,
        "us_ids": batch_us,
        "batch_size": len(batch_us),
        "next_layer_command": next_cmd,
        "family_hint": family_hint,
        "wait_instruction": (
            f"Spawn the {len(batch_us)} us_ids in ONE message via parallel Agent "
            f"tool calls. WAIT for all SubagentStops before invoking the "
            + ("API Gate (STEP 6.b)" if is_last else "next layer.")
        ),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return SUCCESS


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic helpers for /dev-run STEP 6.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="Compute US batches + plan detection")
    p_plan.add_argument("--feat-number", type=int, required=True)
    p_plan.add_argument("--max-parallel", type=int, default=None,
                        help="Override MaxParallel from Project Config (1-12)")
    p_plan.set_defaults(func=_cmd_plan)

    p_gate = sub.add_parser("gate-decision", help="Read API gate verdict + decide continuation")
    p_gate.add_argument("--feat-number", type=int, required=True)
    p_gate.set_defaults(func=_cmd_gate_decision)

    p_batch = sub.add_parser(
        "batch",
        help="Emit the Nth batch of US to spawn (forces MaxParallel "
             "enforcement at CLI level — see D9 fix audit 2026-06-06)"
    )
    p_batch.add_argument("--feat-number", type=int, required=True)
    p_batch.add_argument("--layer", type=int, required=True,
                         help="0-indexed batch layer to emit")
    p_batch.add_argument("--max-parallel", type=int, default=None,
                         help="Override MaxParallel (1-12)")
    p_batch.set_defaults(func=_cmd_batch)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — script entry-point must not crash silently
        sys.stderr.write(
            f"ERROR: run_dev_phase crashed\n"
            f"CAUSE: [INFRA_BLOCKED] {type(e).__name__}: {e}\n"
            f"FIX: report bug, fallback to inline pseudo-bash in /dev-run STEP 6\n"
        )
        sys.exit(INFRA_BLOCKED)
