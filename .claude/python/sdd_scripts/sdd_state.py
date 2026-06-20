#!/usr/bin/env python3
"""SDD_Pro v6.10: state machine + event log for /sdd-full, /dev-run, /qa-generate.

Source de vérité : `workspace/output/db/console.db` (tables `runs`,
`run_phases`, `events`). Plus aucun fichier state/run-*.json ni events.jsonl
écrit sur le FS depuis v6.10.

Canonical event types (emitted via emit-event) — identique à v6.2 :
    Pipeline orchestration:
        run.start, run.end, phase.start, phase.end
    Plan Cache Strict (v6.2):
        plan_validate, plan_validate_postgen, plan_cache_evaluation,
        plan_cache_fallback, dev_backend_strict_start/end,
        dev_frontend_strict_start/end

Usage:
    python sdd_state.py new-run    --feat-number N [--command C] [--tags "a,b,c"]
    python sdd_state.py set-phase  --run-id R --phase P --status start|pass|warn|fail|skip
                                   [--payload-json '{}']
    python sdd_state.py end-run    --run-id R [--status success|partial|failed]
    python sdd_state.py get-run    --feat-number N [--latest]
    python sdd_state.py show-run   --run-id R
    python sdd_state.py list-runs  [--feat-number N] [--limit 10]
    python sdd_state.py emit-event --run-id R --event-type T [--payload-json '{}']

Migrated from .claude/scripts/sdd-state.ps1 (2026-05-13), refactored to SQLite
(2026-05-17, v6.10).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import (  # noqa: E402
    connect, ensure_initialized, get_run, get_run_phases, insert_event, list_runs,
    upsert_run, upsert_run_phase,
)
from sdd_lib.paths import iso_now_ms as iso_now, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402


VALID_PHASE_STATUSES = {
    "start", "pass", "warn", "fail", "skip",
    "running", "success", "partial", "failed",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)

    s_new = sub.add_parser("new-run")
    s_new.add_argument("--feat-number", type=int, required=True)
    s_new.add_argument("--command", default="")
    s_new.add_argument("--tags", default="")

    s_set = sub.add_parser("set-phase")
    s_set.add_argument("--run-id", required=True)
    s_set.add_argument("--phase", required=True)
    s_set.add_argument("--status", required=True, choices=sorted(VALID_PHASE_STATUSES))
    s_set.add_argument("--payload-json", default="")

    s_end = sub.add_parser("end-run")
    s_end.add_argument("--run-id", required=True)
    s_end.add_argument("--status", default="success",
                       choices=["success", "partial", "failed"])

    s_get = sub.add_parser("get-run",
        help="Return the active (or latest, if --latest) run row for a FEAT as JSON.")
    s_get.add_argument("--feat-number", type=int, required=True,
        help="FEAT number to query.")
    s_get.add_argument("--latest", action="store_true",
        help="(audit M15 doc 2026-06-07) If set, return the most recent run "
             "for this FEAT regardless of status (including failed/partial). "
             "If absent, returns only ACTIVE runs (status='running'). "
             "Use --latest from /sdd-full STEP 1.ter to resume after a crash.")

    s_show = sub.add_parser("show-run")
    s_show.add_argument("--run-id", required=True)

    s_list = sub.add_parser("list-runs")
    s_list.add_argument("--feat-number", type=int, default=0)
    s_list.add_argument("--limit", type=int, default=10)

    s_emit = sub.add_parser("emit-event")
    s_emit.add_argument("--run-id", required=True)
    s_emit.add_argument("--event-type", required=True)
    s_emit.add_argument("--payload-json", default="")

    # status — état global ou par FEAT (utilisé par /sdd-status command)
    s_status = sub.add_parser("status",
        help="Global state summary (or per-FEAT if --feat-number passed)")
    s_status.add_argument("--feat-number", type=int, default=0,
        help="Restrict status to FEAT N (0 = global summary)")

    # resume-target — détermine le STEP de reprise d'un run partiel
    # (audit 2026-06-06 D5 — vrai routing --resume, pas juste récupération ID)
    s_resume = sub.add_parser("resume-target",
        help="Compute next STEP to execute for a run, based on phases status")
    s_resume.add_argument("--run-id", required=True,
        help="Existing run_id (typically from `get-run --latest`)")

    # should-skip-step — gate de décision shell-safe pour le routing --resume
    # (audit CTO 2026-06-07 — pré-fix, sdd-full.md utilisait `[ X > Y ]` qui
    # est UNE REDIRECTION SHELL, pas une comparaison ; doublement cassé sur
    # STEP_2.6 vs STEP_10 en compare lexicographique). Encapsule la logique
    # d'ordre dans Python (déterministe, testé).
    #
    # Exit codes : 0 = SKIP this step (resume target is past it),
    #              1 = RUN this step (we've reached or not yet hit target).
    # Conçu pour : `if python ... should-skip-step --target $RT --current STEP_X; then continue; fi`
    s_skip = sub.add_parser("should-skip-step",
        help="Shell-safe gate : exit 0 to skip STEP, exit 1 to run it")
    s_skip.add_argument("--target", required=True,
        help="Resume target STEP label (from `resume-target` output)")
    s_skip.add_argument("--current", required=True,
        help="STEP about to be evaluated (e.g. STEP_2, STEP_4.5)")

    return p.parse_args()


def parse_payload(text: str) -> Any:
    if not text or not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def get_feat_name(n: int) -> str | None:
    feats_dir = repo_root() / "workspace" / "input" / "feats"
    if not feats_dir.is_dir():
        return None
    files = list(feats_dir.glob(f"{n}-*.md"))
    if len(files) != 1:
        return None
    m = re.match(rf"^{n}-(.+)$", files[0].stem)
    return m.group(1) if m else None


def _row_to_dict(row, phases: list[Any] | None = None) -> dict[str, Any]:
    """Map a sqlite3.Row from `runs` to the legacy state dict shape."""
    tags = json.loads(row["tags_json"]) if row["tags_json"] else []
    out: dict[str, Any] = {
        "runId":        row["run_id"],
        "FeatNumber":   row["feat_n"],
        "FeatName":     row["feat_name"],
        "command":      row["command"],
        "tags":         tags,
        "startedAt":    row["started_at"],
        "updatedAt":    row["updated_at"],
        "endedAt":      row["ended_at"],
        "status":       row["status"],
        "currentPhase": row["current_phase"],
        "phases":       {},
    }
    if phases is not None:
        for ph in phases:
            out["phases"][ph["phase"]] = {
                "status":    ph["status"],
                "startedAt": ph["started_at"],
                "endedAt":   ph["ended_at"],
                "payload":   json.loads(ph["payload_json"]) if ph["payload_json"] else None,
            }
    return out


def action_new_run(args: argparse.Namespace) -> int:
    if args.feat_number <= 0:
        warn("new-run requires --feat-number > 0")
        return FAIL_FAST
    # v7.0.0-alpha audit Sprint 1.1 (2026-06-06) — single source of truth for run_id.
    # Previously generated a 12-char uuid here while hooks resolved their own id via
    # sdd_lib.run_id.get_or_create_run_id() — two ids never matched, token_usage rows
    # could not FK-link to runs, ROI metrics broken by construction.
    # Fix : reuse the hook-side resolver so SDD orchestrator and Claude Code hooks
    # share one stable run_id. Persisted to marker file workspace/.sys/.state/run-id.current.
    #
    # v7.0.1 (audit M7 closure 2026-06-07) : honor SDD_RUN_ID env var if set
    # by a parent orchestrator (e.g. /sdd-full exports SDD_RUN_ID before
    # invoking /dev-run). Allows continuous run_id across nested commands
    # → audit-trail stays linked, resume after crash possible.
    from sdd_lib.run_id import get_or_create_run_id
    inherited_run_id = os.environ.get("SDD_RUN_ID", "").strip()
    if inherited_run_id:
        run_id = inherited_run_id
        warn(f"[new-run] reusing inherited SDD_RUN_ID={run_id} (M7 parent-orchestrator propagation)")
    else:
        run_id = get_or_create_run_id(force_new=True)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    command = args.command or "unknown"
    feat_name = get_feat_name(args.feat_number)
    now = iso_now()
    ensure_initialized()
    with connect() as conn:
        upsert_run(
            conn,
            run_id=run_id, command=command,
            feat_n=args.feat_number, feat_name=feat_name,
            started_at=now, status="running", tags=tags,
        )
        insert_event(
            conn,
            event_type="run.start", ts=now, run_id=run_id,
            feat_n=args.feat_number,
            payload={"cmd": command, "tags": tags},
        )
    print(run_id)
    return SUCCESS
def action_set_phase(args: argparse.Namespace) -> int:
    ensure_initialized()
    now = iso_now()
    payload = parse_payload(args.payload_json)
    with connect() as conn:
        row = get_run(conn, args.run_id)
        if row is None:
            warn(f"Unknown runId: {args.run_id}")
            return FAIL_FAST
        feat_n = row["feat_n"]

        if args.status == "start":
            upsert_run_phase(
                conn, run_id=args.run_id, phase=args.phase, status="running",
                started_at=now, payload=payload,
            )
            event_type = "phase.start"
        else:
            # v7.0.0 audit fix 2026-05-20 — phase timing trou #3.
            # Historically, callers in /sdd-full only emitted `set-phase ...
            # --status {pass|fail|warn|skip}` at the END of each phase, never
            # at the START. Result : every run_phases row had started_at=NULL,
            # so report_roi.py phase_timing was always 0.0s.
            # Defensive fix : when emitting end without prior start, query
            # the existing row's started_at — if NULL, set it to `now` so
            # at least the row is complete (duration = 0ms is preferable to
            # NULL for downstream aggregations).
            existing = conn.execute(
                "SELECT started_at FROM run_phases "
                "WHERE run_id = ? AND phase = ?",
                (args.run_id, args.phase),
            ).fetchone()
            started_fallback = None
            if existing is None or not existing["started_at"]:
                # No prior start row → backfill started_at = now (defensive)
                started_fallback = now
            upsert_run_phase(
                conn, run_id=args.run_id, phase=args.phase, status=args.status,
                started_at=started_fallback, ended_at=now, payload=payload,
            )
            event_type = "phase.end"

        upsert_run(
            conn, run_id=args.run_id, command=row["command"],
            current_phase=args.phase, status=row["status"],
        )

        evt_payload: dict[str, Any] = {"status": args.status}
        if payload is not None:
            evt_payload["payload"] = payload
        insert_event(
            conn, event_type=event_type, ts=now, run_id=args.run_id,
            feat_n=feat_n, phase=args.phase, payload=evt_payload,
        )
    return SUCCESS
def action_end_run(args: argparse.Namespace) -> int:
    ensure_initialized()
    now = iso_now()
    with connect() as conn:
        row = get_run(conn, args.run_id)
        if row is None:
            warn(f"Unknown runId: {args.run_id}")
            return FAIL_FAST
        feat_n = row["feat_n"]
        try:
            started = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
            ended = datetime.fromisoformat(now.replace("Z", "+00:00"))
            dur_ms = int((ended - started).total_seconds() * 1000)
        except (ValueError, AttributeError, TypeError):
            dur_ms = 0

        upsert_run(
            conn, run_id=args.run_id, command=row["command"],
            ended_at=now, status=args.status,
        )
        insert_event(
            conn, event_type="run.end", ts=now, run_id=args.run_id,
            feat_n=feat_n, payload={"status": args.status, "durationMs": dur_ms},
        )
    print(f"run {args.run_id} ended status={args.status} durationMs={dur_ms}")
    return SUCCESS
def action_get_run(args: argparse.Namespace) -> int:
    ensure_initialized()
    with connect() as conn:
        rows = list_runs(conn, feat_n=args.feat_number, limit=10_000)
    if not rows:
        return FAIL_FAST
    if args.latest:
        print(rows[0]["run_id"])
    else:
        for r in rows:
            print(r["run_id"])
    return SUCCESS
def action_show_run(args: argparse.Namespace) -> int:
    ensure_initialized()
    with connect() as conn:
        row = get_run(conn, args.run_id)
        if row is None:
            warn(f"Unknown runId: {args.run_id}")
            return FAIL_FAST
        phases = get_run_phases(conn, args.run_id)
    state = _row_to_dict(row, phases)
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return SUCCESS
def action_list_runs(args: argparse.Namespace) -> int:
    ensure_initialized()
    with connect() as conn:
        rows = list_runs(
            conn,
            feat_n=args.feat_number if args.feat_number > 0 else None,
            limit=args.limit,
        )
    if not rows:
        print("(no runs)")
        return SUCCESS
    runs = [{
        "runId":     r["run_id"],
        "FEAT":      r["feat_n"] or "",
        "cmd":       r["command"] or "",
        "status":    r["status"] or "",
        "phase":     r["current_phase"] or "",
        "startedAt": r["started_at"] or "",
        "endedAt":   r["ended_at"] or "",
    } for r in rows]
    cols = ["runId", "FEAT", "cmd", "status", "phase", "startedAt", "endedAt"]
    widths = {c: max(len(c), max(len(str(r[c])) for r in runs)) for c in cols}
    header = "  ".join(f"{c:<{widths[c]}}" for c in cols)
    print(header)
    print("-" * len(header))
    for r in runs:
        print("  ".join(f"{str(r[c]):<{widths[c]}}" for c in cols))
    return SUCCESS
def action_emit_event(args: argparse.Namespace) -> int:
    ensure_initialized()
    payload = parse_payload(args.payload_json)
    with connect() as conn:
        row = get_run(conn, args.run_id)
        feat_n = row["feat_n"] if row else 0
        insert_event(
            conn, event_type=args.event_type, ts=iso_now(),
            run_id=args.run_id, feat_n=feat_n, payload=payload,
        )
    return SUCCESS
def action_status(args: argparse.Namespace) -> int:
    """Global or per-FEAT state summary — JSON output (used by /sdd-status command).

    Without --feat-number: aggregates total runs, FEATs touched, last run, phase distribution.
    With --feat-number N : returns runs/phases/last-status for that FEAT only.
    """
    ensure_initialized()
    with connect() as conn:
        if args.feat_number > 0:
            runs = list_runs(conn, feat_n=args.feat_number, limit=50)
        else:
            runs = list_runs(conn, feat_n=None, limit=50)

    runs_list = [dict(r) for r in runs]
    feats_touched = sorted({r["feat_n"] for r in runs_list if r.get("feat_n")})
    by_status: dict[str, int] = {}
    for r in runs_list:
        s = r.get("status") or "unknown"
        by_status[s] = by_status.get(s, 0) + 1

    last_run = runs_list[0] if runs_list else None

    out = {
        "scope": "feat" if args.feat_number > 0 else "global",
        "feat_number": args.feat_number if args.feat_number > 0 else None,
        "runs_total": len(runs_list),
        "feats_touched": feats_touched,
        "runs_by_status": by_status,
        "last_run": {
            "runId":     last_run["run_id"] if last_run else None,
            "feat":      last_run.get("feat_n") if last_run else None,
            "command":   last_run.get("command") if last_run else None,
            "status":    last_run.get("status") if last_run else None,
            "phase":     last_run.get("current_phase") if last_run else None,
            "startedAt": last_run.get("started_at") if last_run else None,
            "endedAt":   last_run.get("ended_at") if last_run else None,
        } if last_run else None,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return SUCCESS


#: Ordered list of phases in the /sdd-full pipeline.
#: Maps a logical phase to the STEP label the orchestrating command should
#: jump to. The order matters : the first phase whose status is NOT in
#: {pass, warn, skip} is the resume target.
#:
#: Audit final 2026-06-07 (CRIT-1 closure) : labels alignés strictement
#: sur les `## STEP` headings de `commands/sdd-full.md`. Avant ce fix,
#: us_generate était mappé STEP_2 (mais doc = STEP 3), readiness STEP_2.6
#: (doc = STEP 3.5), arch STEP_3.5 (collision avec readiness !), qa STEP_5
#: (doc = STEP 4.5). Conséquence : `should-skip-step --current STEP_3.5`
#: était ambigu (arch OU readiness) → `--resume` skip workflow au mauvais
#: endroit. Désormais : labels = headings réels.
#:
#: Note arch : `/sdd-full` ne lance pas `arch` séparément — il est interne
#: à `/dev-run` (STEP 4.bis short-circuit). Mappé sur STEP_4 (même cible
#: que dev_run) pour permettre set-phase arch=pass sans casser le routing
#: pipeline. Pour invocation `/arch-init` standalone, le label STEP_3.5_arch
#: pourrait être ajouté en v7.1 si un cas standalone se présente.
_PIPELINE_PHASES_ORDER: tuple[tuple[str, str], ...] = (
    ("us_generate",  "STEP_3"),     # /us-generate (sdd-full.md STEP 3)
    ("readiness",    "STEP_3.5"),   # /feat-validate (sdd-full.md STEP 3.5)
    ("plan",         "STEP_3.6"),   # /dev-plan optional (sdd-full.md STEP 3.6)
    ("arch",         "STEP_4"),     # arch interne à /dev-run STEP 4.bis — même cible que dev_run
    ("dev_run",      "STEP_4"),     # /dev-run (sdd-full.md STEP 4)
    ("qa",           "STEP_4.5"),   # /qa-generate (sdd-full.md STEP 4.5)
    ("sdd_review",   "STEP_4.8"),   # /sdd-review (sdd-full.md STEP 4.8)
)

_RESUME_DONE_STATUSES = {"pass", "warn", "success", "skip"}


def action_resume_target(args: argparse.Namespace) -> int:
    """Compute the next STEP to execute given a partial run state.

    Audit 2026-06-06 D5 — Pre-fix, `--resume` only re-read $RUN_ID via
    get-run --latest, but the orchestrating command (sdd-full.md) had no
    mechanism to actually SKIP past completed phases : all STEPs ran
    again (idempotent thanks to each agent's own gating, but wasteful in
    LLM cost — a $30 run that crashed at STEP 5 would re-cost ~$25).

    The pipeline phases order is fixed by `_PIPELINE_PHASES_ORDER`. We
    iterate, finding the first phase whose status is NOT done. That
    phase's STEP label is the resume target.

    Output : single STEP label on stdout (e.g. `STEP_4`).
    Exit 0 always (resume target is a hint, not a hard fact).
    Edge cases :
      - Run unknown OR no phases recorded → emit `STEP_2` (start at us-generate)
      - All phases done → emit `STEP_END` (nothing to resume — clean run)
    """
    ensure_initialized()
    with connect() as conn:
        run_row = get_run(conn, args.run_id)
        if run_row is None:
            print("STEP_2")  # unknown run — fresh start
            return SUCCESS
        phase_rows = get_run_phases(conn, args.run_id)

    # Build {phase: status} map. Missing phases stay un-keyed → treated
    # as NOT done.
    by_phase: dict[str, str] = {
        ph["phase"]: (ph["status"] or "").lower() for ph in phase_rows
    }

    for phase_key, step_label in _PIPELINE_PHASES_ORDER:
        status = by_phase.get(phase_key, "")
        if status not in _RESUME_DONE_STATUSES:
            print(step_label)
            return SUCCESS

    # All phases done — clean run, nothing to resume
    print("STEP_END")
    return SUCCESS


def action_should_skip_step(args: argparse.Namespace) -> int:
    """Gate de décision shell-safe : --current doit-il être skipped ?

    Audit CTO 2026-06-07 — remplace le bash cassé `[ "$RT" > "STEP_X" ]`
    qui était (a) une redirection vers fichier nommé `STEP_X`, (b)
    lexicographiquement faux sur `STEP_2.6` vs `STEP_10`. Cette commande
    encapsule la logique d'ordre déterministe dans Python.

    Logique :
      - Construit la liste ordonnée des STEP labels du pipeline.
      - Si --target ∉ pipeline OU --current ∉ pipeline → RUN (exit 1)
        par sécurité (gate non-applicable, on exécute).
      - Si --target == "STEP_END" → SKIP toute STEP (exit 0).
      - Si index(current) < index(target) → SKIP (exit 0).
      - Sinon → RUN (exit 1).

    Usage shell :
        if python sdd_state.py should-skip-step --target $RT --current STEP_4; then
            echo "[RESUME] skipping STEP 4"
            continue
        fi
    """
    target = (args.target or "").strip()
    current = (args.current or "").strip()
    # Built-in: "STEP_END" means all phases done — skip everything.
    if target == "STEP_END":
        return SUCCESS  # exit 0 → SKIP
    # Build ordered STEP list from _PIPELINE_PHASES_ORDER.
    step_order = [step for _phase, step in _PIPELINE_PHASES_ORDER]
    try:
        idx_current = step_order.index(current)
        idx_target = step_order.index(target)
    except ValueError:
        # Either label not in pipeline → can't gate, default to RUN.
        return 1  # exit 1 → RUN
    if idx_current < idx_target:
        return SUCCESS  # exit 0 → SKIP (current is before resume target)
    return 1  # exit 1 → RUN


DISPATCH = {
    "new-run":      action_new_run,
    "set-phase":    action_set_phase,
    "end-run":      action_end_run,
    "get-run":      action_get_run,
    "show-run":     action_show_run,
    "list-runs":    action_list_runs,
    "emit-event":   action_emit_event,
    "status":       action_status,
    "resume-target": action_resume_target,
    "should-skip-step": action_should_skip_step,
}


def main() -> int:
    args = parse_args()
    return DISPATCH[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
