#!/usr/bin/env python3
"""SDD_Pro telemetry aggregator — reads token-usage.jsonl and reports.

Reads `workspace/output/.sys/.audit/token-usage.jsonl` produced by the
`sdd_hooks.record_token_usage` hook, then aggregates token consumption
by agent, by FEAT, and globally.

Outputs:
    - stdout      : human-readable Markdown report
    - --json      : machine-readable JSON to stdout
    - --output P  : write Markdown report to file P
    - --json-out P: write JSON report to file P

Filters:
    --feat N        : only entries for FEAT N
    --agent NAME    : only entries for subagent_type=NAME
    --since TS      : only entries with ts >= TS (ISO-8601)
    --us ID         : only entries for US ID (e.g. "1-2")

Health check:
    If raw_usage_found rate < 0.5 across all entries, emit a WARN on stderr
    indicating that Claude Code may not expose usage tokens in the hook
    payload (design assumption broken; see ADR).

v6.5.1 — companion to sdd_hooks.record_token_usage. Read-only on the
ledger, never mutates it.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect_ro  # noqa: E402  (RO reader — no WAL, no init)
from sdd_lib.paths import iso_now  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import SUCCESS  # noqa: E402


USAGE_FIELDS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _load_ledger(path: Path | None = None) -> list[dict[str, Any]]:
    """Load token_usage rows from console.db (v6.10) and map to the legacy
    entry shape (subagent_type/feat/cache_creation_input_tokens/...).

    The `path` parameter is preserved for backward-compat with callers/tests
    that used to pass a JSONL path but is now ignored — telemetry lives in
    the DB only.

    v6.10.4-LTS PATCH: uses ``connect_ro()`` — does not require a writable
    DB directory, does not toggle journal_mode to WAL, and raises a clear
    ``FileNotFoundError`` if the DB has never been bootstrapped.

    The ``FileNotFoundError`` is raised at ``__enter__`` of the context
    manager (not at construction), so the try/except must wrap the
    ``with`` statement, not the ``connect_ro()`` call."""
    entries: list[dict[str, Any]] = []
    try:
        with connect_ro() as conn:
            cur = conn.execute(
                """
                SELECT ts, agent, model, feat_n, us_id,
                       input_tokens, output_tokens,
                       cache_creation_tokens, cache_read_tokens
                  FROM token_usage
                 ORDER BY ts ASC
                """
            )
            rows = cur.fetchall()
    except FileNotFoundError as exc:
        warn(str(exc))
        return entries
    for row in rows:
        has_tokens = any(
            int(row[k] or 0) > 0
            for k in ("input_tokens", "output_tokens",
                      "cache_creation_tokens", "cache_read_tokens")
        )
        entries.append({
            "ts": row["ts"],
            "subagent_type": row["agent"],
            "model": row["model"],
            "feat": row["feat_n"],
            "us_id": row["us_id"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cache_creation_input_tokens": row["cache_creation_tokens"],
            "cache_read_input_tokens": row["cache_read_tokens"],
            "raw_usage_found": has_tokens,
        })
    return entries


def _passes_filters(
    entry: dict[str, Any],
    feat: int | None,
    agent: str | None,
    since: str | None,
    us_id: str | None,
) -> bool:
    if feat is not None and entry.get("feat") != feat:
        return False
    if agent is not None and entry.get("subagent_type") != agent:
        return False
    if since is not None:
        ts = entry.get("ts")
        if not isinstance(ts, str) or ts < since:
            return False
    if us_id is not None and entry.get("us_id") != us_id:
        return False
    return True


def _zero_bucket() -> dict[str, int]:
    return {field: 0 for field in USAGE_FIELDS} | {"calls": 0, "missing_usage": 0}


def _accumulate(bucket: dict[str, int], entry: dict[str, Any]) -> None:
    bucket["calls"] += 1
    if not entry.get("raw_usage_found"):
        bucket["missing_usage"] += 1
        return
    for field in USAGE_FIELDS:
        val = entry.get(field)
        if isinstance(val, int):
            bucket[field] += val


def _total_tokens(bucket: dict[str, int]) -> int:
    """Sum input + output + cache_creation (cache_read is read-only, not billed
    at standard rate but still counted for transparency)."""
    return (
        bucket.get("input_tokens", 0)
        + bucket.get("output_tokens", 0)
        + bucket.get("cache_creation_input_tokens", 0)
    )


def aggregate(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_agent: dict[str, dict[str, int]] = defaultdict(_zero_bucket)
    by_feat: dict[str, dict[str, int]] = defaultdict(_zero_bucket)
    by_agent_feat: dict[str, dict[str, int]] = defaultdict(_zero_bucket)
    global_bucket = _zero_bucket()

    for e in entries:
        agent = e.get("subagent_type") or "(unknown)"
        feat = e.get("feat")
        feat_key = f"feat-{feat}" if feat is not None else "(no-feat)"
        agent_feat_key = f"{agent}|{feat_key}"

        _accumulate(by_agent[agent], e)
        _accumulate(by_feat[feat_key], e)
        _accumulate(by_agent_feat[agent_feat_key], e)
        _accumulate(global_bucket, e)

    return {
        "global": global_bucket,
        "by_agent": dict(by_agent),
        "by_feat": dict(by_feat),
        "by_agent_feat": dict(by_agent_feat),
        "entry_count": len(entries),
    }


def _format_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _format_bucket_row(name: str, b: dict[str, int]) -> str:
    return (
        f"| {name} "
        f"| {b['calls']} "
        f"| {_format_int(b.get('input_tokens', 0))} "
        f"| {_format_int(b.get('output_tokens', 0))} "
        f"| {_format_int(b.get('cache_read_input_tokens', 0))} "
        f"| {_format_int(b.get('cache_creation_input_tokens', 0))} "
        f"| {_format_int(_total_tokens(b))} "
        f"| {b['missing_usage']} |"
    )


def render_markdown(agg: dict[str, Any], source_label: str) -> str:
    out: list[str] = []
    out.append(f"# Token usage report — generated {iso_now()}")
    out.append("")
    out.append(f"Source: `{source_label}`  ")
    out.append(f"Entries: **{agg['entry_count']}**")
    out.append("")

    global_b = agg["global"]
    missing = global_b["missing_usage"]
    calls = global_b["calls"]
    if calls > 0:
        rate = missing / calls
        if rate >= 0.5:
            out.append(
                f"> ⚠️ **WARN** : {missing}/{calls} entrées sans usage tokens "
                f"({rate:.0%}). Claude Code n'expose probablement pas `usage` "
                "dans le payload hook. Voir ADR `telemetry-tokens-fallback`."
            )
            out.append("")

    header = (
        "| Scope | Calls | Input | Output | Cache read | Cache creation "
        "| Total billed | Missing usage |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|"

    out.append("## Global")
    out.append(header)
    out.append(sep)
    out.append(_format_bucket_row("**ALL**", global_b))
    out.append("")

    out.append("## Par agent")
    out.append(header)
    out.append(sep)
    for agent, bucket in sorted(
        agg["by_agent"].items(),
        key=lambda kv: _total_tokens(kv[1]),
        reverse=True,
    ):
        out.append(_format_bucket_row(agent, bucket))
    out.append("")

    out.append("## Par FEAT")
    out.append(header)
    out.append(sep)
    for feat, bucket in sorted(agg["by_feat"].items()):
        out.append(_format_bucket_row(feat, bucket))
    out.append("")

    out.append("## Par agent × FEAT")
    out.append(header)
    out.append(sep)
    for key, bucket in sorted(
        agg["by_agent_feat"].items(),
        key=lambda kv: _total_tokens(kv[1]),
        reverse=True,
    ):
        out.append(_format_bucket_row(key, bucket))
    out.append("")

    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report_token_usage",
        description="Aggregate SDD_Pro token usage ledger.",
    )
    p.add_argument("--feat", type=int, default=None, help="Filter by FEAT number")
    p.add_argument("--agent", type=str, default=None, help="Filter by subagent_type")
    p.add_argument("--since", type=str, default=None, help="ISO-8601 cutoff (inclusive)")
    p.add_argument("--us", type=str, default=None, help='Filter by US id, e.g. "1-2"')
    p.add_argument("--json", action="store_true", help="Emit JSON to stdout instead of Markdown")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write Markdown report to this path (also kept on stdout)",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write JSON report to this path",
    )
    p.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="(legacy / ignored since v6.10) telemetry now lives in console.db",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source_label = "console.db (table token_usage)"

    entries = _load_ledger()
    filtered = [
        e for e in entries
        if _passes_filters(e, args.feat, args.agent, args.since, args.us)
    ]
    agg = aggregate(filtered)

    md = render_markdown(agg, source_label)
    payload = {
        "generated_at": iso_now(),
        "source": source_label,
        "filters": {
            "feat": args.feat, "agent": args.agent,
            "since": args.since, "us": args.us,
        },
        **agg,
    }

    if args.json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(md)
        sys.stdout.write("\n")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
