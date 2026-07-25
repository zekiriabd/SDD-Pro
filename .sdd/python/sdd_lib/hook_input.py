"""Parse JSON stdin payload from Claude Code hooks, with regex fallback."""
from __future__ import annotations

import json
import re
import sys
from typing import Any


def read_hook_input() -> dict[str, Any]:
    """Read full stdin and parse as JSON.

    Returns:
        Parsed payload dict, or {} on empty/invalid input.
    """
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return _regex_fallback(raw)


def _regex_fallback(text: str) -> dict[str, Any]:
    """Best-effort field extraction when JSON parsing fails.

    Mimics the PowerShell fallback regex behaviour for `file_path`,
    `tool_name`, `subagent_type`.
    """
    out: dict[str, Any] = {}
    tool_input: dict[str, Any] = {}

    fp = re.search(r'"file_path"\s*:\s*"([^"]+)"', text)
    if fp:
        tool_input["file_path"] = fp.group(1)

    tn = re.search(r'"tool_name"\s*:\s*"([^"]+)"', text)
    if tn:
        out["tool_name"] = tn.group(1)

    sa = re.search(r'"subagent_type"\s*:\s*"([^"]+)"', text)
    if sa:
        tool_input["subagent_type"] = sa.group(1)

    prompt = re.search(r'"prompt"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if prompt:
        tool_input["prompt"] = prompt.group(1)

    descr = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if descr:
        tool_input["description"] = descr.group(1)

    if tool_input:
        out["tool_input"] = tool_input
    return out


def get_nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Walk nested dict keys, return default if any key missing or wrong type."""
    cur: Any = payload
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def get_file_path(payload: dict[str, Any]) -> str | None:
    """Extract tool_input.file_path, fallback root file_path."""
    fp = get_nested(payload, "tool_input", "file_path")
    if not isinstance(fp, str) or not fp.strip():
        fp = get_nested(payload, "file_path")
    if isinstance(fp, str) and fp.strip():
        return fp
    return None


def get_tool_name(payload: dict[str, Any]) -> str | None:
    val = payload.get("tool_name")
    return val if isinstance(val, str) and val.strip() else None


def get_subagent_type(payload: dict[str, Any]) -> str | None:
    val = get_nested(payload, "tool_input", "subagent_type")
    if not isinstance(val, str) or not val.strip():
        val = payload.get("subagent_type")
    return val if isinstance(val, str) and val.strip() else None
