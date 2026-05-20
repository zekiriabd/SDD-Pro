"""Pipeline MCP tools (Phase 2) — LLM-driven slash commands via `claude` CLI.

Five tools:

  claude_check         -> probe `claude` CLI availability (synchronous, fast)
  feat_generate        -> /feat-generate {Name}        (sync, may be long)
  us_generate          -> /us-generate {n}             (sync, may be long)
  sdd_full             -> /sdd-full {n} [flags]        (async, returns job_id)
  get_sdd_full_status  -> poll job_id                  (sync, fast)
  cancel_sdd_full      -> kill a running job_id        (sync, fast)
  list_sdd_full_jobs   -> list recent jobs             (sync, fast)

Async job state lives under workspace/output/.sys/.mcp-jobs/. See
sdd_mcp.job_store for details.

These tools require Claude Code to be installed locally (`claude` CLI on
PATH). Set env var SDD_MCP_FAKE_CLAUDE=1 to short-circuit for tests.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ..claude_invoker import (  # noqa: E402
    InvokeResult,
    claude_available,
    invoke_sync,
    resolve_claude_bin,
    spawn_async,
)
from ..job_store import (  # noqa: E402
    JobState,
    cancel,
    finalize,
    jobs_dir,
    list_jobs,
    new_job_id,
    read_state,
    state_path,
    stderr_path,
    stdout_path,
    tail_text,
    update_status_from_pid,
    write_state,
)
from ..registry import Tool  # noqa: E402


# --------------------------------------------------------------------------
# claude_check — diagnostic
# --------------------------------------------------------------------------

_CLAUDE_CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def _handle_claude_check(_args: dict[str, Any]) -> dict[str, Any]:
    bin_path = resolve_claude_bin()
    if not bin_path:
        return _err(
            "claude CLI not found on PATH. Install Claude Code or set SDD_MCP_CLAUDE_BIN.",
            exit_code=127,
        )
    return _ok({"claude_bin": bin_path, "available": True})


# --------------------------------------------------------------------------
# feat_generate (sync)
# --------------------------------------------------------------------------

_FEAT_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9-]{0,62}$")

_FEAT_GENERATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "pattern": "^[A-Z][A-Za-z0-9-]{0,62}$",
            "description": "FEAT name in PascalCase-with-dashes (e.g. 'Auth', 'Reset-Password').",
        },
        "timeout_seconds": {
            "type": "number",
            "minimum": 30,
            "maximum": 3600,
            "default": 600,
        },
    },
    "required": ["name"],
    "additionalProperties": False,
}


def _handle_feat_generate(args: dict[str, Any]) -> dict[str, Any]:
    name = args["name"]
    if not _FEAT_NAME_RE.match(name):
        return _err(f"Invalid FEAT name {name!r}. Must match {_FEAT_NAME_RE.pattern}.")
    timeout = float(args.get("timeout_seconds", 600))
    try:
        result = invoke_sync(f"/feat-generate {name}", timeout=timeout)
    except FileNotFoundError as e:
        return _err(str(e), exit_code=127)
    return _from_invoke_result(result)


# --------------------------------------------------------------------------
# us_generate (sync)
# --------------------------------------------------------------------------

_US_GENERATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "feat_number": {"type": "integer", "minimum": 1},
        "timeout_seconds": {
            "type": "number",
            "minimum": 30,
            "maximum": 3600,
            "default": 600,
        },
    },
    "required": ["feat_number"],
    "additionalProperties": False,
}


def _handle_us_generate(args: dict[str, Any]) -> dict[str, Any]:
    feat = int(args["feat_number"])
    timeout = float(args.get("timeout_seconds", 600))
    try:
        result = invoke_sync(f"/us-generate {feat}", timeout=timeout)
    except FileNotFoundError as e:
        return _err(str(e), exit_code=127)
    return _from_invoke_result(result)


# --------------------------------------------------------------------------
# sdd_full (async)
# --------------------------------------------------------------------------

_SDD_FULL_FLAGS = {
    "plan_only": "--plan",
    "force": "--force",
    "no_plan_on_warn": "--no-plan-on-warn",
    "no_validate": "--no-validate",
    "rebuild_arch": "--rebuild-arch",
    "no_manual_gates": "--no-manual-gates",
    "resume": "--resume",
}

_SDD_FULL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "feat_number": {"type": "integer", "minimum": 1},
        "plan_only": {"type": "boolean", "default": False},
        "force": {"type": "boolean", "default": False},
        "no_plan_on_warn": {"type": "boolean", "default": False},
        "no_validate": {"type": "boolean", "default": False},
        "rebuild_arch": {"type": "boolean", "default": False},
        "no_manual_gates": {"type": "boolean", "default": False},
        "resume": {"type": "boolean", "default": False},
        "manual_gates": {
            "type": "string",
            "description": "Comma-separated subset of {us,readiness,plan,code}.",
        },
    },
    "required": ["feat_number"],
    "additionalProperties": False,
}


def _build_sdd_full_command(args: dict[str, Any]) -> str:
    feat = int(args["feat_number"])
    parts = [f"/sdd-full {feat}"]
    for key, flag in _SDD_FULL_FLAGS.items():
        if args.get(key):
            parts.append(flag)
    if args.get("manual_gates"):
        parts.append(f"--manual-gates={args['manual_gates']}")
    return " ".join(parts)


def _handle_sdd_full(args: dict[str, Any]) -> dict[str, Any]:
    if not claude_available():
        return _err(
            "claude CLI not found on PATH. Install Claude Code or set SDD_MCP_CLAUDE_BIN.",
            exit_code=127,
        )
    command = _build_sdd_full_command(args)
    job_id = new_job_id()
    out = str(stdout_path(job_id))
    err = str(stderr_path(job_id))
    state = JobState(
        job_id=job_id,
        command=command,
        feat_number=int(args["feat_number"]),
        status="queued",
        stdout_path=out,
        stderr_path=err,
    )
    write_state(state)
    try:
        proc = spawn_async(command, out, err)
    except (FileNotFoundError, OSError) as e:
        state.status = "failed"
        state.error = f"spawn failed: {e}"
        write_state(state)
        return _err(f"Failed to spawn /sdd-full: {e}", exit_code=126)
    state.pid = proc.pid
    state.status = "running"
    write_state(state)
    return _ok({
        "job_id": job_id,
        "command": command,
        "status": "running",
        "pid": proc.pid,
        "stdout_path": out,
        "stderr_path": err,
        "poll_with": f"get_sdd_full_status(job_id={job_id!r})",
    })


# --------------------------------------------------------------------------
# get_sdd_full_status (sync, fast)
# --------------------------------------------------------------------------

_GET_STATUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "minLength": 1},
        "tail_bytes": {
            "type": "integer",
            "minimum": 0,
            "maximum": 65536,
            "default": 4096,
            "description": "Bytes of stdout/stderr to include in the response.",
        },
    },
    "required": ["job_id"],
    "additionalProperties": False,
}


def _handle_get_sdd_full_status(args: dict[str, Any]) -> dict[str, Any]:
    job_id = args["job_id"]
    state = read_state(job_id)
    if state is None:
        return _err(f"Unknown job_id {job_id!r}", exit_code=2)

    if state.status in ("queued", "running") and state.pid is not None:
        _refresh_from_pid(state)

    tail = int(args.get("tail_bytes", 4096))
    out_tail = tail_text(Path(state.stdout_path), max_bytes=tail) if tail else ""
    err_tail = tail_text(Path(state.stderr_path), max_bytes=tail) if tail else ""

    payload = state.to_dict()
    payload["stdout_tail"] = out_tail
    payload["stderr_tail"] = err_tail
    return _ok(payload, is_error=(state.status == "failed" or state.status == "timeout"))


def _refresh_from_pid(state: JobState) -> None:
    """If the subprocess has terminated, finalize state from exit code."""
    from ..job_store import _is_pid_alive  # local import to keep public surface clean

    if state.pid is None:
        return
    if _is_pid_alive(state.pid):
        return
    # Process dead — try to determine exit code. We don't keep the Popen
    # handle across MCP calls; best-effort: read state file again in case
    # another caller already finalized, otherwise mark failed (unknown).
    fresh = read_state(state.job_id)
    if fresh is not None and fresh.status in ("success", "failed", "timeout"):
        state.status = fresh.status
        state.exit_code = fresh.exit_code
        state.ended_at = fresh.ended_at
        state.duration_ms = fresh.duration_ms
        return
    update_status_from_pid(state)


# --------------------------------------------------------------------------
# cancel_sdd_full
# --------------------------------------------------------------------------

_CANCEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"job_id": {"type": "string", "minLength": 1}},
    "required": ["job_id"],
    "additionalProperties": False,
}


def _handle_cancel_sdd_full(args: dict[str, Any]) -> dict[str, Any]:
    state = read_state(args["job_id"])
    if state is None:
        return _err(f"Unknown job_id {args['job_id']!r}", exit_code=2)
    if state.status not in ("queued", "running"):
        return _ok({"job_id": state.job_id, "status": state.status, "noop": True})
    cancelled = cancel(state)
    return _ok({"job_id": cancelled.job_id, "status": cancelled.status})


# --------------------------------------------------------------------------
# list_sdd_full_jobs
# --------------------------------------------------------------------------

_LIST_JOBS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        "status_filter": {
            "type": "string",
            "enum": ["queued", "running", "success", "failed", "timeout"],
        },
    },
    "additionalProperties": False,
}


def _handle_list_sdd_full_jobs(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit", 20))
    status_filter = args.get("status_filter")
    all_jobs = list_jobs()
    if status_filter:
        all_jobs = [j for j in all_jobs if j.status == status_filter]
    out = [j.to_dict() for j in all_jobs[:limit]]
    return _ok({"total": len(all_jobs), "jobs": out})


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _from_invoke_result(result: InvokeResult) -> dict[str, Any]:
    text = result.stdout or "(no output)"
    if result.stderr:
        text = f"{text}\n--- stderr ---\n{result.stderr}".strip()
    return {
        "content": [{"type": "text", "text": text}],
        "isError": result.exit_code != 0,
        "_meta": {
            "exitCode": result.exit_code,
            "durationMs": result.duration_ms,
            "timedOut": result.timed_out,
        },
    }


def _ok(payload: Any, is_error: bool = False) -> dict[str, Any]:
    import json as _json

    return {
        "content": [{"type": "text", "text": _json.dumps(payload, ensure_ascii=False, indent=2)}],
        "isError": is_error,
        "_meta": {"exitCode": 0, "payload": payload},
    }


def _err(msg: str, exit_code: int = 2) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": f"ERROR: {msg}"}],
        "isError": True,
        "_meta": {"exitCode": exit_code, "payload": None},
    }


TOOLS: list[Tool] = [
    Tool(
        name="claude_check",
        description=(
            "Probe whether the `claude` Code CLI is available on PATH. "
            "Required for Phase 2 LLM-driven tools (feat_generate, us_generate, sdd_full). "
            "Returns the resolved binary path or an actionable error."
        ),
        input_schema=_CLAUDE_CHECK_SCHEMA,
        handler=_handle_claude_check,
    ),
    Tool(
        name="feat_generate",
        description=(
            "Run /feat-generate {Name} via the local Claude Code CLI (synchronous). "
            "Long-running (1-3 min typical). Note: the slash command is interactive "
            "by design — pre-fill workspace/input/stack/stack.md ## Project Config "
            "before calling, otherwise the agent will fail on unanswered questions."
        ),
        input_schema=_FEAT_GENERATE_SCHEMA,
        handler=_handle_feat_generate,
    ),
    Tool(
        name="us_generate",
        description=(
            "Run /us-generate {n} via the local Claude Code CLI (synchronous). "
            "Splits FEAT {n} into 1-6 User Stories. Long-running (~1 min)."
        ),
        input_schema=_US_GENERATE_SCHEMA,
        handler=_handle_us_generate,
    ),
    Tool(
        name="sdd_full",
        description=(
            "Start /sdd-full {n} as a background job. Returns a `job_id` immediately. "
            "Poll progress with `get_sdd_full_status(job_id)`. Cancel with `cancel_sdd_full`. "
            "Job state persists under workspace/output/.sys/.mcp-jobs/ so multiple MCP "
            "sessions can observe the same run."
        ),
        input_schema=_SDD_FULL_SCHEMA,
        handler=_handle_sdd_full,
    ),
    Tool(
        name="get_sdd_full_status",
        description=(
            "Poll an /sdd-full job by `job_id`. Returns current status "
            "(queued|running|success|failed|timeout), exit code (if terminal), "
            "and tails of stdout/stderr. Fast read-only call."
        ),
        input_schema=_GET_STATUS_SCHEMA,
        handler=_handle_get_sdd_full_status,
    ),
    Tool(
        name="cancel_sdd_full",
        description=(
            "Send SIGTERM (POSIX) or CTRL_BREAK (Windows) to a running /sdd-full job. "
            "Best-effort — the child may take a few seconds to exit. No-op on terminal jobs."
        ),
        input_schema=_CANCEL_SCHEMA,
        handler=_handle_cancel_sdd_full,
    ),
    Tool(
        name="list_sdd_full_jobs",
        description=(
            "List recent /sdd-full jobs sorted by start time (most recent first). "
            "Filter by status if desired. Returns up to `limit` jobs (default 20)."
        ),
        input_schema=_LIST_JOBS_SCHEMA,
        handler=_handle_list_sdd_full_jobs,
    ),
]
