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

    s_get = sub.add_parser("get-run")
    s_get.add_argument("--feat-number", type=int, required=True)
    s_get.add_argument("--latest", action="store_true")

    s_show = sub.add_parser("show-run")
    s_show.add_argument("--run-id", required=True)

    s_list = sub.add_parser("list-runs")
    s_list.add_argument("--feat-number", type=int, default=0)
    s_list.add_argument("--limit", type=int, default=10)

    s_emit = sub.add_parser("emit-event")
    s_emit.add_argument("--run-id", required=True)
    s_emit.add_argument("--event-type", required=True)
    s_emit.add_argument("--payload-json", default="")

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
        return 1
    run_id = uuid.uuid4().hex[:12]
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
    return 0


def action_set_phase(args: argparse.Namespace) -> int:
    ensure_initialized()
    now = iso_now()
    payload = parse_payload(args.payload_json)
    with connect() as conn:
        row = get_run(conn, args.run_id)
        if row is None:
            warn(f"Unknown runId: {args.run_id}")
            return 1
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
    return 0


def action_end_run(args: argparse.Namespace) -> int:
    ensure_initialized()
    now = iso_now()
    with connect() as conn:
        row = get_run(conn, args.run_id)
        if row is None:
            warn(f"Unknown runId: {args.run_id}")
            return 1

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
    return 0


def action_get_run(args: argparse.Namespace) -> int:
    ensure_initialized()
    with connect() as conn:
        rows = list_runs(conn, feat_n=args.feat_number, limit=10_000)
    if not rows:
        return 1
    if args.latest:
        print(rows[0]["run_id"])
    else:
        for r in rows:
            print(r["run_id"])
    return 0


def action_show_run(args: argparse.Namespace) -> int:
    ensure_initialized()
    with connect() as conn:
        row = get_run(conn, args.run_id)
        if row is None:
            warn(f"Unknown runId: {args.run_id}")
            return 1
        phases = get_run_phases(conn, args.run_id)
    state = _row_to_dict(row, phases)
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


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
        return 0

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
    return 0


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
    return 0


DISPATCH = {
    "new-run":    action_new_run,
    "set-phase":  action_set_phase,
    "end-run":    action_end_run,
    "get-run":    action_get_run,
    "show-run":   action_show_run,
    "list-runs":  action_list_runs,
    "emit-event": action_emit_event,
}


def main() -> int:
    args = parse_args()
    return DISPATCH[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
