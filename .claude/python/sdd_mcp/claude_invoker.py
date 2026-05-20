"""Claude Code CLI invoker — Option A from MCP-SERVER.md §2.2.

Wraps `claude -p <prompt> --print` subprocess calls so Phase 2 MCP tools
can drive the user's local Claude Code session without re-implementing
agent logic. The user's auth, hooks, and Project Config travel with the
CLI naturally — no API key handling here.

Test fakes
----------
Set env var `SDD_MCP_FAKE_CLAUDE=1` (or `SDD_MCP_FAKE_CLAUDE_BIN=<path>`)
to short-circuit the real `claude` lookup. Used by pytest so the suite
runs offline and deterministically — never spawns a real LLM.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Sequence


CLAUDE_BIN_ENV = "SDD_MCP_CLAUDE_BIN"
FAKE_FLAG_ENV = "SDD_MCP_FAKE_CLAUDE"
FAKE_BIN_ENV = "SDD_MCP_FAKE_CLAUDE_BIN"


@dataclass(frozen=True)
class InvokeResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


def resolve_claude_bin() -> str | None:
    """Locate the `claude` executable. Returns None if not found and not faked.

    Precedence: explicit env var > fake mode > PATH lookup.
    """
    explicit = os.environ.get(CLAUDE_BIN_ENV)
    if explicit:
        return explicit
    if os.environ.get(FAKE_FLAG_ENV) == "1":
        return os.environ.get(FAKE_BIN_ENV) or _default_fake_command()
    return shutil.which("claude")


def _default_fake_command() -> str:
    """Return a path to a minimal stub that prints 'OK' and exits 0.

    Used when tests set `SDD_MCP_FAKE_CLAUDE=1` without providing their own
    binary. The stub is the current Python interpreter — we'll pass it
    `-c "print('OK')"` via argv reshaping in `invoke_sync`.
    """
    return sys.executable


def _build_argv(claude_bin: str, slash_command: str) -> list[str]:
    """Build the argv list. Fake mode reshapes to a stdlib python one-liner."""
    if os.environ.get(FAKE_FLAG_ENV) == "1" and claude_bin == sys.executable:
        # Echo back the slash command so callers can assert on it.
        return [
            claude_bin,
            "-c",
            f"import sys; sys.stdout.write('FAKE CLAUDE OK: {slash_command}')",
        ]
    return [claude_bin, "-p", slash_command, "--print"]


def invoke_sync(slash_command: str, timeout: float = 600.0) -> InvokeResult:
    """Run `claude -p <slash_command> --print` and wait for completion.

    Returns InvokeResult with exit code, stdout, stderr, duration. Raises
    FileNotFoundError if `claude` is not on PATH and not faked.
    """
    claude_bin = resolve_claude_bin()
    if not claude_bin:
        raise FileNotFoundError(
            "claude CLI not found on PATH. Install Claude Code or set "
            f"{CLAUDE_BIN_ENV} to override."
        )
    argv = _build_argv(claude_bin, slash_command)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return InvokeResult(
            exit_code=124,
            stdout=e.stdout or "",
            stderr=(e.stderr or "") + f"\nclaude CLI timed out after {timeout}s",
            duration_ms=int((time.monotonic() - started) * 1000),
            timed_out=True,
        )
    return InvokeResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def spawn_async(
    slash_command: str,
    stdout_path: str,
    stderr_path: str,
) -> subprocess.Popen[bytes]:
    """Start `claude -p <slash_command> --print` as a detached child.

    The caller is responsible for tracking the returned Popen (pid, poll) and
    for inspecting `stdout_path`/`stderr_path` to read incremental progress.
    Files are opened in append-binary mode so multiple polls can tail them.
    """
    claude_bin = resolve_claude_bin()
    if not claude_bin:
        raise FileNotFoundError(
            "claude CLI not found on PATH. Install Claude Code or set "
            f"{CLAUDE_BIN_ENV} to override."
        )
    argv = _build_argv(claude_bin, slash_command)
    out_fh = open(stdout_path, "ab")
    err_fh = open(stderr_path, "ab")
    return subprocess.Popen(
        argv,
        stdout=out_fh,
        stderr=err_fh,
        stdin=subprocess.DEVNULL,
    )


def claude_available() -> bool:
    """Lightweight check (used by `claude_check` tool / health endpoint)."""
    return resolve_claude_bin() is not None


def _safe_join_argv(argv: Sequence[str]) -> str:
    """Render argv for logs without exposing env vars (defense in depth)."""
    return " ".join(repr(a) if " " in a else a for a in argv)
