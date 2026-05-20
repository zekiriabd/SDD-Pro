#!/usr/bin/env python3
"""SDD_Pro telemetry hook — record real token usage per subagent invocation.

Fires on `PostToolUse` (matcher=Agent) and `SubagentStop` to capture token
usage exposed by Claude Code in the tool_response payload.

Mode controlled by env $SDD_TOKEN_USAGE_MODE:
    - "off"    (default) : silent skip, exit 0 (v6.4.2 strict behaviour)
    - "record"           : insert row into workspace/output/db/console.db
                            (table token_usage)
    - "debug"            : record + dump full payload to .audit/token-debug/

v6.10 — telemetry now persists in console.db (token_usage table). The
former token-usage.jsonl ledger has been retired; readers must query the
DB via sdd_lib.console_db.connect().

Design: defensive multi-path lookup of the `usage` block — Claude Code
hook payload schema may evolve, and the same field can live under
`tool_response.usage`, `tool_response.message.usage`, or top-level
`usage`. We try them all and tag the source for forensics.

Output schema (one JSON object per line in token-usage.jsonl):
    {
      "ts": "2026-05-15T14:32:18.123Z",
      "hook_event": "PostToolUse.Agent" | "SubagentStop",
      "subagent_type": "dev-backend" | null,
      "feat": 1 | null,
      "us_id": "1-2" | null,
      "model": "claude-opus-4-7" | null,
      "input_tokens": 42153,
      "output_tokens": 8721,
      "cache_creation_input_tokens": 3210,
      "cache_read_input_tokens": 15432,
      "raw_usage_found": true,
      "usage_source_path": "tool_response.usage"
    }

Non-blocking by design — always exit 0. A failure of telemetry must never
break the pipeline. The ledger is informational, consumed by
report_token_usage.py for aggregation.

v6.5.1 — additive feature, opt-in via env var. Default mode "off"
guarantees byte-identical behaviour vs v6.4.2 when not enabled.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect, ensure_initialized, insert_token_usage  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_nested,
    get_subagent_type,
    read_hook_input,
)
from sdd_lib.paths import iso_now_ms, repo_root  # noqa: E402


# Candidate paths in the payload where `usage` may live.
# Tried in order; first hit wins. usage_source_path is recorded for forensics.
USAGE_CANDIDATE_PATHS: tuple[tuple[str, ...], ...] = (
    ("tool_response", "usage"),
    ("tool_response", "message", "usage"),
    ("response", "usage"),
    ("response", "message", "usage"),
    ("usage",),
    ("message", "usage"),
)

# Field names inside the usage dict (Claude API canonical names).
USAGE_FIELDS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _find_usage(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Walk candidate paths; return (usage_dict, source_path_str) or (None, None)."""
    for path in USAGE_CANDIDATE_PATHS:
        node = get_nested(payload, *path)
        if isinstance(node, dict) and any(k in node for k in USAGE_FIELDS):
            return node, ".".join(path)
    return None, None


def _find_model(payload: dict[str, Any]) -> str | None:
    """Best-effort extraction of model id from common payload locations."""
    candidates = (
        ("tool_response", "model"),
        ("tool_response", "message", "model"),
        ("response", "model"),
        ("model",),
    )
    for path in candidates:
        node = get_nested(payload, *path)
        if isinstance(node, str) and node.strip():
            return node.strip()
    return None


def _extract_feat_and_us(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    """Re-use the regex pattern from preflight_agent_budget for consistency."""
    prompt = get_nested(payload, "tool_input", "prompt", default="") or ""
    descr = get_nested(payload, "tool_input", "description", default="") or ""
    haystack = f"{prompt} {descr}"

    m_us = re.search(r"\b(\d{1,3})-(\d{1,3})(?:-[A-Za-z][A-Za-z0-9\-]*)?\b", haystack)
    if m_us:
        return int(m_us.group(1)), f"{m_us.group(1)}-{m_us.group(2)}"

    m_feat = re.search(
        r"(?i)\b(?:FEAT|feat-?|sdd-full|us-generate|dev-run|dev-plan|qa-generate)"
        r"\s*[-:]?\s*(\d{1,3})\b",
        haystack,
    )
    if m_feat:
        return int(m_feat.group(1)), None
    return None, None


def _hook_event_name(payload: dict[str, Any]) -> str:
    """Identify which hook event fired (PostToolUse.Agent vs SubagentStop).

    Claude Code passes `hook_event_name` at the payload root in newer versions.
    Fallback heuristic: presence of `tool_response` -> PostToolUse, else SubagentStop.
    """
    explicit = payload.get("hook_event_name")
    if isinstance(explicit, str) and explicit.strip():
        # Differentiate Agent vs other tools when PostToolUse fires
        tool_name = payload.get("tool_name")
        if explicit == "PostToolUse" and tool_name:
            return f"PostToolUse.{tool_name}"
        return explicit
    if "tool_response" in payload or "response" in payload:
        return "PostToolUse.Agent"
    return "SubagentStop"


def _persist_to_db(entry: dict[str, Any]) -> None:
    """Insert one row into console.db (table token_usage).

    Concurrent inserts are handled by SQLite WAL + busy_timeout=5s,
    so we don't need a per-file lock anymore."""
    ensure_initialized()
    with connect() as conn:
        insert_token_usage(
            conn,
            agent=entry.get("subagent_type") or entry.get("hook_event") or "unknown",
            model=entry.get("model"),
            ts=entry.get("ts"),
            feat_n=entry.get("feat"),
            us_id=entry.get("us_id"),
            input_tokens=int(entry.get("input_tokens") or 0),
            output_tokens=int(entry.get("output_tokens") or 0),
            cache_creation_tokens=int(entry.get("cache_creation_input_tokens") or 0),
            cache_read_tokens=int(entry.get("cache_read_input_tokens") or 0),
        )


def _debug_dump_payload(payload: dict[str, Any], audit_dir: Path) -> None:
    """Dump full payload to audit dir for forensic inspection (debug mode only)."""
    dump_dir = audit_dir / "token-debug"
    dump_dir.mkdir(parents=True, exist_ok=True)
    ts = iso_now_ms().replace(":", "-").replace(".", "-")
    target = dump_dir / f"payload-{ts}.json"
    try:
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def main() -> int:
    mode = os.environ.get("SDD_TOKEN_USAGE_MODE", "off").strip().lower()
    if mode not in {"record", "debug"}:
        return 0  # off / unknown -> silent skip, no-op vs v6.4.2

    try:
        payload = read_hook_input()
    except Exception:
        return 0
    if not payload:
        return 0

    root = repo_root()
    audit_dir = root / "workspace" / "output" / ".sys" / ".audit"

    if mode == "debug":
        try:
            _debug_dump_payload(payload, audit_dir)
        except Exception:
            pass  # never block on debug dump

    usage_dict, usage_path = _find_usage(payload)
    feat, us_id = _extract_feat_and_us(payload)

    entry: dict[str, Any] = {
        "ts": iso_now_ms(),
        "hook_event": _hook_event_name(payload),
        "subagent_type": get_subagent_type(payload),
        "feat": feat,
        "us_id": us_id,
        "model": _find_model(payload),
        "raw_usage_found": usage_dict is not None,
        "usage_source_path": usage_path,
    }

    if usage_dict is not None:
        for field in USAGE_FIELDS:
            val = usage_dict.get(field)
            entry[field] = val if isinstance(val, int) else None
    else:
        for field in USAGE_FIELDS:
            entry[field] = None

    try:
        _persist_to_db(entry)
    except Exception:
        # Telemetry must never break the pipeline.
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
