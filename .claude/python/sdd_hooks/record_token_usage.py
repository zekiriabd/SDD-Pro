#!/usr/bin/env python3
"""SDD_Pro telemetry hook — record real token usage per subagent invocation.

Fires on `PostToolUse` (matcher=Agent) and `SubagentStop` to capture token
usage exposed by Claude Code in the tool_response payload.

Mode resolved with explicit precedence (highest wins) :
    1. env $SDD_TOKEN_USAGE_MODE (debug override, dev/CI)
    2. effective layered config `TokenUsageMode`
       (base.yml ← team.yml ← project stack.md ## Project Config)
    3. "off" (hard default if config unreadable)

Modes:
    - "off"    : silent skip, exit 0 (v6.4.2 strict behaviour)
    - "record" : insert row into workspace/output/db/console.db (token_usage)
    - "debug"  : record + dump full payload to .audit/token-debug/

v7.0.0 — config-aware mode resolution. Previous versions only read the env
var, which silently ignored the v7.0.0 default flip in config.base.yml
(TokenUsageMode: "record"). Now the layered config is honored, env var
remains a debug escape hatch.

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
from sdd_lib.exit_codes import HOOK_ALLOW  # noqa: E402

# Valid modes (lower-cased, env + config normalized to these)
VALID_MODES: frozenset[str] = frozenset({"off", "record", "debug"})

# Module-level memo of the resolved mode. The mode is invariant within a
# pipeline run (config files are not edited mid-run, env vars set at spawn),
# so resolving once per process saves ~50 ms × N hook calls (audit P2 perf
# 2026-06-08 : record_token_usage measured 62 ms cold-start, dominated by
# the layered_config import + read).
_MODE_CACHE: str | None = None


def _resolve_mode() -> str:
    """Resolve effective token-usage mode (memoized).

    Precedence (highest wins):
      1. env $SDD_TOKEN_USAGE_MODE (debug override)
      2. effective layered config `TokenUsageMode`
         (base.yml ← team.yml ← project stack.md)
      3. "off" (hard default)

    Any unknown value normalizes to "off" (defensive — never break the run).
    """
    global _MODE_CACHE
    if _MODE_CACHE is not None:
        return _MODE_CACHE

    # 1. env var override — short-circuit, avoid expensive config import
    env_val = (os.environ.get("SDD_TOKEN_USAGE_MODE") or "").strip().lower()
    if env_val in VALID_MODES:
        _MODE_CACHE = env_val
        return env_val

    # 2. layered config (lazy-import — only paid if env was not set).
    # layered_config is optional; telemetry must never break on import errors.
    try:
        from sdd_lib.layered_config import read_layered_config  # noqa: E402
        cfg = read_layered_config()
        cfg_val = str(cfg.get("TokenUsageMode") or "").strip().lower()
        if cfg_val in VALID_MODES:
            _MODE_CACHE = cfg_val
            return cfg_val
    except Exception:
        # Config layering is opt-in and may fail on partial repos;
        # telemetry MUST NOT raise — fall through to hard default.
        pass

    # 3. hard default
    _MODE_CACHE = "off"
    return "off"


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
    so we don't need a per-file lock anymore.

    v7.0.0 audit P1 fix 2026-05-20 — scope par run_id (env $SDD_RUN_ID,
    set par sdd_state.py au début de /sdd-full). Permet à
    preflight_cost_cap.py de filtrer par run_id exact au lieu de la
    fenêtre temporelle started_at/ended_at (fragile en concurrence)."""
    ensure_initialized()
    # v7.0.1 : always resolve a stable run_id via sdd_lib/run_id helper
    # (env > workspace marker > generated). Avoids null run_id rows that
    # broke per-run aggregation in preflight_cost_cap.
    try:
        from sdd_lib.run_id import get_or_create_run_id
        run_id = get_or_create_run_id()
    except Exception:
        run_id = (os.environ.get("SDD_RUN_ID") or "").strip() or None
    with connect() as conn:
        # v7.0.0-alpha P0 fix 2026-05-21 — upsert a parent runs row before
        # inserting token_usage. Required by FK constraint
        # token_usage.run_id -> runs(run_id). Previously masked by the
        # silently-broken `find_project_root` import (ran the except branch,
        # producing NULL run_id rows which SQLite allowed). With run_id.py
        # fixed, we always have a valid run_id but no guarantee that the
        # orchestrator (/sdd-full STEP 1.ter) was the one that created
        # the runs row — e.g. ad-hoc Agent calls outside /sdd-full. The
        # upsert is idempotent and inexpensive.
        if run_id:
            try:
                from sdd_lib.console_db import upsert_run
                upsert_run(
                    conn,
                    run_id=run_id,
                    command=os.environ.get("SDD_RUN_COMMAND") or "hook",
                    status="running",
                )
            except Exception:
                # Defensive : never break the token record path on a parent
                # upsert error — fall back to NULL run_id to preserve the row.
                run_id = None
        insert_token_usage(
            conn,
            agent=entry.get("subagent_type") or entry.get("hook_event") or "unknown",
            model=entry.get("model"),
            ts=entry.get("ts"),
            run_id=run_id,
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
    mode = _resolve_mode()
    if mode not in {"record", "debug"}:
        return HOOK_ALLOW  # off → silent skip (normalized 2026-06-06)

    try:
        payload = read_hook_input()
    except Exception:
        return HOOK_ALLOW
    if not payload:
        return HOOK_ALLOW
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
    except Exception as exc:
        # Telemetry must never break the pipeline — but we must NOT swallow
        # silently either, or we regress to pre-fix state (0 rows accumulated).
        # v7.0.0 audit fix : log failure to a fail counter file ; preflight hook
        # reads it and emits a visible WARN when telemetry is going dark.
        _record_telemetry_failure(audit_dir, exc)
        return HOOK_ALLOW
    return HOOK_ALLOW
def _record_telemetry_failure(audit_dir: Path, exc: Exception) -> None:
    """Append failure to .audit/token-telemetry-failures.log + maintain counter.

    Schema (one JSON line) :
        {"ts": "...", "error_type": "OperationalError", "message": "..."}

    Counter file `.audit/token-telemetry-failure-count` holds the integer
    count since last successful insert. Read by preflight_cost_cap to emit
    a visible operator alert when telemetry is broken (≥ 3 consecutive
    failures or any failure within last 5 min)."""
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
        log_path = audit_dir / "token-telemetry-failures.log"
        counter_path = audit_dir / "token-telemetry-failure-count"
        # v7.0.1 audit P1 v2 audit anti-patterns 2026-06-08 (AP-1) — use
        # `with` context manager to guarantee FD closure even on partial
        # write failure (Windows : orphan FD = file lock for that path).
        # Rotation handled by sdd_admin/rotate_audit_logs.py.
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "ts": iso_now_ms(),
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:200],
                }) + "\n"
            )
        # Bump counter — BEST-EFFORT, EVENTUAL CONSISTENCY.
        #
        # v7.0.1 audit AP-4 2026-06-08 : the read-modify-write below is
        # NOT atomic. Two parallel hook invocations can race and lose
        # increments. This is intentionally acceptable :
        #   - The counter is a DIAGNOSTIC (operator alert when telemetry
        #     is broken), not a billing primitive.
        #   - Telemetry failures are rare (~0/1000 invocations normally).
        #   - The threshold check (≥ 3 consecutive) tolerates undercount
        #     by 1-2 — operator will still see the alert after enough
        #     failures accumulate.
        # If exact counting becomes required, replace with file_locks lock
        # or SQLite atomic INCREMENT (console_db.token_telemetry_failures).
        try:
            cur = int(counter_path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            cur = 0
        counter_path.write_text(str(cur + 1), encoding="utf-8")
    except OSError:
        # Last resort — even the failure log failed. Nothing more we can do
        # without breaking the pipeline contract.
        pass


if __name__ == "__main__":
    sys.exit(main())
