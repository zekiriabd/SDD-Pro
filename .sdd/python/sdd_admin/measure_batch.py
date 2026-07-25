#!/usr/bin/env python3
"""SDD_Pro: parse Claude Code session JSONL logs and aggregate by skill.

Usage:
    python measure_batch.py
    python measure_batch.py --session-id <uuid>
    python measure_batch.py --since "2026-05-05"
    python measure_batch.py --out-file metrics.csv
    python measure_batch.py --project-slug g--Developement-SDD-Framework

Migrated from .claude/scripts/measure-batch.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--session-id", default="")
    p.add_argument("--since", default="")
    p.add_argument("--out-file", default="")
    p.add_argument("--project-slug", default="g--Developement-SDD-Framework",
                   help="Slug of .claude/projects/<slug>/ to scan")
    return p.parse_args()


def safe_int(v: Any) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return SUCCESS
def main() -> int:
    args = parse_args()

    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or "")
    projects_root = home / ".claude" / "projects"
    project_dir = projects_root / args.project_slug

    if not project_dir.is_dir():
        warn(f"Project dir not found: {project_dir}")
        return FAIL_FAST
    files = sorted(project_dir.glob("*.jsonl"))
    if args.session_id:
        files = [f for f in files if f.stem == args.session_id]
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since)
        except ValueError:
            warn(f"Invalid --since format: {args.since}")
            return FAIL_FAST
        files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) >= since_dt]

    if not files:
        print("No session files matched.")
        return SUCCESS
    print(f"Processing {len(files)} session file(s)...")

    rows: list[dict[str, Any]] = []
    for f in files:
        sid = f.stem
        try:
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        j = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if j.get("type") != "assistant":
                        continue
                    msg = j.get("message") or {}
                    usage = msg.get("usage") or {}
                    if not usage:
                        continue
                    rows.append({
                        "session":      sid,
                        "timestamp":    j.get("timestamp", ""),
                        "cwd":          j.get("cwd", ""),
                        "skill":        j.get("attributionSkill") or "(none)",
                        "model":        msg.get("model", ""),
                        "input":        safe_int(usage.get("input_tokens")),
                        "cache_create": safe_int(usage.get("cache_creation_input_tokens")),
                        "cache_read":   safe_int(usage.get("cache_read_input_tokens")),
                        "output":       safe_int(usage.get("output_tokens")),
                        "isSidechain":  bool(j.get("isSidechain")),
                    })
        except OSError:
            continue

    if not rows:
        print("No assistant messages with usage found.")
        return SUCCESS
    # Aggregation par session + skill
    by_cmd: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        key = (r["session"], r["skill"])
        by_cmd.setdefault(key, []).append(r)

    by_cmd_rows: list[dict] = []
    for (sid, skill), group in by_cmd.items():
        timestamps = [r["timestamp"] for r in group if r["timestamp"]]
        first = min(timestamps) if timestamps else ""
        last = max(timestamps) if timestamps else ""
        duration = 0
        if first and last:
            try:
                dt_first = datetime.fromisoformat(first.replace("Z", "+00:00"))
                dt_last = datetime.fromisoformat(last.replace("Z", "+00:00"))
                duration = int((dt_last - dt_first).total_seconds())
            except ValueError:
                duration = 0
        total_input = sum(r["input"] for r in group)
        total_cache_create = sum(r["cache_create"] for r in group)
        total_cache_read = sum(r["cache_read"] for r in group)
        total_in = total_input + total_cache_create + total_cache_read
        total_output = sum(r["output"] for r in group)
        sub_calls = sum(1 for r in group if r["isSidechain"])
        by_cmd_rows.append({
            "session":      sid,
            "skill":        skill,
            "messages":     len(group),
            "sub_calls":    sub_calls,
            "input":        total_input,
            "cache_create": total_cache_create,
            "cache_read":   total_cache_read,
            "output":       total_output,
            "total_in":     total_in,
            "duration_s":   duration,
            "started":      first,
        })
    by_cmd_rows.sort(key=lambda r: r["started"] or "")

    print()
    print("=== Per-command breakdown (per session) ===")
    if by_cmd_rows:
        cols = ["session", "skill", "messages", "sub_calls", "total_in",
                "output", "duration_s", "started"]
        widths = {c: max(len(c), max(len(str(r[c])) for r in by_cmd_rows)) for c in cols}
        header = "  ".join(f"{c:<{widths[c]}}" for c in cols)
        print(header)
        print("-" * len(header))
        for r in by_cmd_rows:
            print("  ".join(f"{str(r[c]):<{widths[c]}}" for c in cols))

    # Per-skill aggregation
    by_skill: dict[str, list[dict]] = {}
    for r in rows:
        by_skill.setdefault(r["skill"], []).append(r)

    by_skill_rows: list[dict] = []
    for skill, group in by_skill.items():
        total_input = sum(r["input"] for r in group)
        total_cache_create = sum(r["cache_create"] for r in group)
        total_cache_read = sum(r["cache_read"] for r in group)
        total_output = sum(r["output"] for r in group)
        by_skill_rows.append({
            "skill":        skill,
            "messages":     len(group),
            "input":        total_input,
            "cache_create": total_cache_create,
            "cache_read":   total_cache_read,
            "output":       total_output,
            "total_in":     total_input + total_cache_create + total_cache_read,
        })
    by_skill_rows.sort(key=lambda r: r["total_in"], reverse=True)

    print()
    print("=== Totaux globaux par skill (toutes sessions) ===")
    if by_skill_rows:
        cols = ["skill", "messages", "input", "cache_create", "cache_read", "output", "total_in"]
        widths = {c: max(len(c), max(len(str(r[c])) for r in by_skill_rows)) for c in cols}
        header = "  ".join(f"{c:<{widths[c]}}" for c in cols)
        print(header)
        print("-" * len(header))
        for r in by_skill_rows:
            print("  ".join(f"{str(r[c]):<{widths[c]}}" for c in cols))

    tot_input = sum(r["input"] for r in rows)
    tot_cache_create = sum(r["cache_create"] for r in rows)
    tot_cache_read = sum(r["cache_read"] for r in rows)
    tot_in = tot_input + tot_cache_create + tot_cache_read
    tot_out = sum(r["output"] for r in rows)
    cache_total = tot_cache_create + tot_cache_read
    cache_hit_pct = round(100 * tot_cache_read / cache_total, 1) if cache_total > 0 else 0

    print()
    print("=== Grand total ===")
    print(f"  Messages assistant : {len(rows)}")
    print(f"  Total input  (input + cache_create + cache_read) : {tot_in}")
    print(f"  Total output : {tot_out}")
    print(f"  Cache hit ratio (read / (create+read))            : {cache_hit_pct} %")

    if args.out_file:
        out_path = Path(args.out_file)
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(by_cmd_rows[0].keys()) if by_cmd_rows else [])
            writer.writeheader()
            for r in by_cmd_rows:
                writer.writerow(r)
        print(f"\nCSV written to: {args.out_file}")

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
