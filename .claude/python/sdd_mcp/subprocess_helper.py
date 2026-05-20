"""Subprocess helper — invoke sdd_scripts/*.py and shape the result for MCP.

All Phase 1 tools wrap an existing deterministic Python script. We never
re-implement logic in the MCP layer — drift between the script and the tool
would be a maintenance liability. The script is the source of truth.

Conventions for sdd_scripts/* invocation:
- `--json` flag emits a single machine-readable JSON object on stdout.
- Exit codes are documented per script (cf. each script's docstring).
- stderr carries human-readable WARN/ERROR blocks (`[CLASS]` taxonomy).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "sdd_scripts"


def script_path(name: str) -> Path:
    """Resolve sdd_scripts/{name}.py — raises if absent at startup time."""
    p = _SCRIPTS_DIR / f"{name}.py"
    if not p.is_file():
        raise FileNotFoundError(f"sdd_scripts/{name}.py not found at {p}")
    return p


def run_script(
    name: str,
    args: list[str],
    cwd: str | Path | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Invoke `python sdd_scripts/{name}.py {args}`, return MCP-shaped result.

    Result shape (MCP `tools/call` response content):
        {
          "content": [{"type": "text", "text": "..."}],
          "isError": bool,
          "_meta": {"exitCode": N, "json": <parsed-stdout-if-any>}
        }

    The `_meta` field is non-standard MCP but legal — clients ignore unknown
    keys. It lets test fixtures and power clients inspect the raw exit
    code and parsed JSON without re-parsing the `text` payload.
    """
    cmd = [sys.executable, str(script_path(name))] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _error_result(
            f"Script {name} timed out after {timeout}s",
            exit_code=124,
        )
    except OSError as e:
        return _error_result(f"Failed to spawn {name}: {e}", exit_code=-1)

    parsed: Any = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = None

    is_error = proc.returncode != 0
    text_body = proc.stdout if proc.stdout else proc.stderr
    if is_error and proc.stderr:
        text_body = f"{text_body}\n--- stderr ---\n{proc.stderr}".strip()

    return {
        "content": [{"type": "text", "text": text_body or "(no output)"}],
        "isError": is_error,
        "_meta": {"exitCode": proc.returncode, "json": parsed},
    }


def _error_result(msg: str, exit_code: int) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": msg}],
        "isError": True,
        "_meta": {"exitCode": exit_code, "json": None},
    }
