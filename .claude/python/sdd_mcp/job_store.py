"""Persistent job store for async MCP tools (Phase 2).

`sdd_full` returns immediately with a job_id; the caller polls
`get_sdd_full_status` until status moves to success / failed / timeout.
State lives under workspace/output/.sys/.mcp-jobs/ so it survives
server restarts and is visible to multiple MCP sessions.

File layout per job:
    .mcp-jobs/{job_id}.json     state envelope
    .mcp-jobs/{job_id}.stdout   captured stdout (append-only)
    .mcp-jobs/{job_id}.stderr   captured stderr (append-only)

Status transitions:
    queued -> running -> {success | failed | timeout}
    queued -> failed   (spawn error)
"""
from __future__ import annotations

import json
import os
import secrets
import signal
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.paths import iso_now_ms, repo_root  # noqa: E402


JobStatus = Literal["queued", "running", "success", "failed", "timeout"]


@dataclass
class JobState:
    job_id: str
    command: str
    feat_number: int | None
    status: JobStatus
    pid: int | None = None
    started_at: str = field(default_factory=iso_now_ms)
    ended_at: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    stdout_path: str = ""
    stderr_path: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def jobs_dir(root: Path | None = None) -> Path:
    """Resolve the .mcp-jobs directory and ensure it exists."""
    base = (root or repo_root()) / "workspace" / "output" / ".sys" / ".mcp-jobs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def new_job_id() -> str:
    """Short hex id, collision-resistant for ~thousands of concurrent jobs."""
    return secrets.token_hex(6)  # 12 hex chars


def state_path(job_id: str, root: Path | None = None) -> Path:
    return jobs_dir(root) / f"{job_id}.json"


def stdout_path(job_id: str, root: Path | None = None) -> Path:
    return jobs_dir(root) / f"{job_id}.stdout"


def stderr_path(job_id: str, root: Path | None = None) -> Path:
    return jobs_dir(root) / f"{job_id}.stderr"


def write_state(state: JobState, root: Path | None = None) -> None:
    """Atomic write: temp file then replace, so partial writes never appear."""
    target = state_path(state.job_id, root)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, target)


def read_state(job_id: str, root: Path | None = None) -> JobState | None:
    target = state_path(job_id, root)
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return JobState(**data)


def list_jobs(root: Path | None = None) -> list[JobState]:
    """Return all job states sorted by started_at descending (most recent first)."""
    out: list[JobState] = []
    for f in jobs_dir(root).glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append(JobState(**data))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    return sorted(out, key=lambda s: s.started_at, reverse=True)


def update_status_from_pid(state: JobState, root: Path | None = None) -> JobState:
    """Refresh a `running` state by polling the PID; persist if changed.

    Returns the updated state. No-op if status is already terminal.
    """
    if state.status not in ("queued", "running"):
        return state
    if state.pid is None:
        return state
    if not _is_pid_alive(state.pid):
        # Process exited but we missed the SIGCHLD — mark unknown / failed.
        state.status = "failed"
        state.ended_at = iso_now_ms()
        state.error = state.error or "Process exited; exit code unknown (polled post-mortem)"
        write_state(state, root)
    return state


def finalize(
    state: JobState,
    exit_code: int,
    duration_ms: int,
    timed_out: bool = False,
    root: Path | None = None,
) -> JobState:
    """Mark a job terminal and persist."""
    state.status = "timeout" if timed_out else ("success" if exit_code == 0 else "failed")
    state.exit_code = exit_code
    state.duration_ms = duration_ms
    state.ended_at = iso_now_ms()
    write_state(state, root)
    return state


def tail_text(path: Path, max_bytes: int = 8192) -> str:
    """Return the last N bytes of a file as text (utf-8, replace errors)."""
    if not path.is_file():
        return ""
    size = path.stat().st_size
    offset = max(0, size - max_bytes)
    with path.open("rb") as f:
        f.seek(offset)
        chunk = f.read()
    return chunk.decode("utf-8", errors="replace")


def _is_pid_alive(pid: int) -> bool:
    """Cross-platform liveness probe — no signal sent on POSIX, kernel-only check."""
    if pid <= 0:
        return False
    if os.name == "nt":
        # Best-effort on Windows: rely on subprocess.Popen poll() upstream; if
        # the caller lost the handle, treat as alive only if a process with the
        # PID exists. Use OpenProcess via ctypes for robustness.
        try:
            import ctypes  # noqa: PLC0415

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            STILL_ACTIVE = 259
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            return bool(ok) and exit_code.value == STILL_ACTIVE
        except Exception:  # pragma: no cover — defensive
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but we can't signal — still alive
    return True


def cancel(state: JobState, root: Path | None = None) -> JobState:
    """Attempt to terminate a running job. Best-effort, cross-platform."""
    if state.status not in ("queued", "running") or state.pid is None:
        return state
    try:
        if os.name == "nt":
            os.kill(state.pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.kill(state.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    state.status = "failed"
    state.ended_at = iso_now_ms()
    state.error = "Cancelled by client (mcp cancel_job)"
    write_state(state, root)
    return state
