#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Skill / Task) — Auto-invoke complexity_router.

Audit P3 A + A.bis (2026-06-08) — when `ComplexityRouterMode=auto` is set
in Project Config AND the user is about to invoke `/sdd-full`, `/sdd-poc`,
or `/dev-run`, this hook proactively runs `sdd_scripts/complexity_router.py`
as a subprocess BEFORE the LLM starts the slash command.

Outputs are persisted to `workspace/output/.sys/.routing/{n}-complexity.{json,md}`.
The slash command then reads these files for routing guidance.

A.bis idempotent guard : skip subprocess if a fresh report (≤ 1h) already
exists for this FEAT. Avoids re-running on every retry of the same command.

Default mode is `manual` (not invoked auto). To activate :
    `ComplexityRouterMode: auto` in Project Config.

Bypass :
  - `ComplexityRouterMode: off` → never invoked (default behavior unchanged)
  - `ComplexityRouterMode: manual` → never invoked from this hook (explicit Python invocation only)
  - `SDD_DISABLE_AUTO_ROUTER=1` env var → one-shot bypass

The hook NEVER blocks the user command — it's additive. On any failure
(script crash, FEAT unparseable, disk error), the hook emits a WARN and
exits 0 (allow). The slash command proceeds without routing guidance.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW  # noqa: E402
from sdd_lib.hook_input import get_nested, read_hook_input  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402


#: Slash commands that should trigger pre-routing
_ROUTING_COMMANDS = frozenset({
    "sdd-full",
    "sdd-poc",
    "dev-run",
})

#: A.bis idempotent guard — skip if report newer than this many seconds
_REPORT_FRESHNESS_SECONDS = 3600  # 1 hour


def _extract_command_name(payload: dict) -> str | None:
    """Extract the slash command name from a Skill/Task tool call.

    Claude Code passes slash command invocations through the Skill tool
    with `tool_input.skill` (or `tool_input.command`) carrying the
    command name (e.g. `sdd-full`).
    """
    for key in ("skill", "command", "skill_name", "command_name"):
        v = get_nested(payload, "tool_input", key)
        if isinstance(v, str) and v.strip():
            # Strip leading slash if present
            return v.strip().lstrip("/")
    return None


def _extract_feat_number(payload: dict) -> int | None:
    """Extract FEAT number from the slash command args."""
    # Try tool_input.args first
    for key in ("args", "arguments", "input"):
        v = get_nested(payload, "tool_input", key)
        if isinstance(v, str):
            m = re.search(r"\b(\d+)\b", v)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    continue
    return None


def _resolve_router_mode(root: Path) -> str:
    """Read ComplexityRouterMode from layered config. Default 'manual'."""
    try:
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config(root=root, keys=("ComplexityRouterMode",))
        v = (cfg.get("ComplexityRouterMode") or "manual").strip().lower()
        if v in ("off", "manual", "auto"):
            return v
    except Exception:
        pass
    return "manual"


def _routing_report_fresh(feat_n: int, root: Path) -> bool:
    """A.bis idempotent guard — True if routing JSON < 1h fresh exists."""
    report = (
        root / "workspace" / "output" / ".sys" / ".routing"
        / f"{feat_n}-complexity.json"
    )
    if not report.is_file():
        return False
    try:
        age = time.time() - report.stat().st_mtime
    except OSError:
        return False
    return age < _REPORT_FRESHNESS_SECONDS


def main() -> int:
    # Defensive : never block on hook failure.
    # Audit P3 C3 (2026-06-08) narrow scope — let KeyboardInterrupt/MemoryError
    # propagate, catch only payload/IO recoverable errors.
    import json as _json
    try:
        payload = read_hook_input()
    except (_json.JSONDecodeError, OSError, UnicodeError, ValueError):
        return HOOK_ALLOW

    cmd = _extract_command_name(payload)
    if not cmd or cmd not in _ROUTING_COMMANDS:
        return HOOK_ALLOW

    if os.environ.get("SDD_DISABLE_AUTO_ROUTER") == "1":
        return HOOK_ALLOW

    root = repo_root()
    mode = _resolve_router_mode(root)
    if mode != "auto":
        # `off` or `manual` — no auto-invoke
        return HOOK_ALLOW

    feat_n = _extract_feat_number(payload)
    if feat_n is None:
        sys.stderr.write(
            f"[AUTO_ROUTER_SKIP] /{cmd} invoked but FEAT number cannot be "
            f"extracted from args — routing skipped. Pass `--feat-number N` "
            f"or `{{n}}` positional to enable auto-routing.\n"
        )
        return HOOK_ALLOW

    # A.bis : idempotent guard
    if _routing_report_fresh(feat_n, root):
        sys.stderr.write(
            f"[AUTO_ROUTER_FRESH] routing report for FEAT {feat_n} is fresh "
            f"(< 1h) — reusing existing workspace/output/.sys/.routing/"
            f"{feat_n}-complexity.json. To force re-run, delete it.\n"
        )
        return HOOK_ALLOW

    # Invoke the deterministic Python script as subprocess
    script = root / ".claude" / "python" / "sdd_scripts" / "complexity_router.py"
    if not script.is_file():
        sys.stderr.write(
            f"WARN [AUTO_ROUTER_SCRIPT_MISSING] {script.relative_to(root).as_posix()} "
            f"not found — skipping auto-route for FEAT {feat_n}.\n"
        )
        return HOOK_ALLOW

    try:
        result = subprocess.run(
            [sys.executable, "-m", "sdd_scripts.complexity_router",
             "--feat-number", str(feat_n)],
            cwd=str(root),
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "PYTHONPATH": str(root / ".claude" / "python")},
        )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as exc:
        sys.stderr.write(
            f"WARN [AUTO_ROUTER_FAILED] subprocess error for FEAT {feat_n}: {exc}. "
            f"Slash command continues without routing guidance.\n"
        )
        return HOOK_ALLOW

    if result.returncode == 0:
        # Success — emit a 1-line summary to stderr (visible to user)
        summary = (result.stdout.strip().splitlines() or ["(no output)"])[0]
        sys.stderr.write(
            f"[AUTO_ROUTER] {summary} (auto-invoked via ComplexityRouterMode=auto)\n"
        )
    else:
        sys.stderr.write(
            f"WARN [AUTO_ROUTER_EXIT_{result.returncode}] complexity_router.py "
            f"failed for FEAT {feat_n} : {result.stderr.strip()[:200]}\n"
        )

    return HOOK_ALLOW  # Never block — additive only


if __name__ == "__main__":
    sys.exit(main())
