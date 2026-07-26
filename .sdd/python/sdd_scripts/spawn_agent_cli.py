#!/usr/bin/env python3
"""spawn_agent_cli — CLI wrapper around `sdd_lib.spawn_agent` (audit R4, 2026-07-26).

This script is the **wiring point** that closes the gap identified in the
2026-07-26 multi-harness audit : `spawn_agent.py` provided the isolated
sub-agent emulation but no command under `.sdd/commands/` invoked it, so
Codex / Gemini prompts fell back to treating `Task(subagent_type=X)` as
narrative guidance instead of a mechanical spawn.

Usage — from a Codex prompt or Gemini command body :

    python .sdd/python/sdd_scripts/spawn_agent_cli.py \\
        --agent dev-backend \\
        --task-file workspace/us/1-1-Login.md \\
        [--harness codex] [--provider openai] \\
        [--schema-file .sdd/schemas/dev-backend-output.json] \\
        [--timeout-s 300]

The default `--harness` and `--provider` are resolved from
`workspace/stack/stack.md` (§ Active Harness / Active Model Provider) via
``sdd_lib.stack_config`` — same source of truth as the rest of the
framework. Explicit CLI flags override.

Output : the sub-agent JSON on stdout (canonical dumps.indent=2) — safe
to pipe to `jq` or persist for auditability.

Exit codes (convention `sdd_lib.exit_codes`) :
  0 SUCCESS          — sub-agent returned valid JSON matching schema
  1 FAIL_FAST        — validation failed after retries, bad args, etc.
  3 INFRA_BLOCKED    — CLI binary absent, API key missing, stack.md unreadable
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Repo-root-relative import path (script must be runnable both from repo root
# and from a checked-out façade under .codex/ or .gemini/).
_HERE = Path(__file__).resolve().parent  # .sdd/python/sdd_scripts/
_PYTHON_ROOT = _HERE.parent               # .sdd/python/
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib.exit_codes import SUCCESS, FAIL_FAST, INFRA_BLOCKED  # noqa: E402
from sdd_lib.spawn_agent import (  # noqa: E402
    AgentSpec,
    SpawnConfig,
    spawn_agent,
)


# Minimal default schema — used when the caller doesn't specify --schema-file.
# The purpose of the default is to force at least ONE JSON key of contract so
# the LLM knows we expect structured output; specialized commands should pass
# their real schema via --schema-file.
_DEFAULT_SCHEMA: dict = {
    "type": "object",
    "required": ["result"],
    "properties": {
        "result": {"type": "string"},
        "notes": {"type": "string"},
    },
}


def _load_json_file(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"ERROR: --{label} file not found: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"ERROR: --{label} file is not valid JSON: {path} ({e})")


def _load_agent_prompt(agent_name: str) -> str:
    """Load `.sdd/agents/{name}.md` body as the sub-agent system prompt.

    Fails INFRA_BLOCKED if the agent .md is missing — this is the
    load-bearing SSoT for sub-agent behavior across harnesses.
    """
    try:
        from sdd_lib.paths import agents_dir
        agent_path = agents_dir() / f"{agent_name}.md"
    except Exception as e:
        print(f"ERROR: cannot resolve agents_dir: {e}", file=sys.stderr)
        sys.exit(INFRA_BLOCKED)
    if not agent_path.is_file():
        print(
            f"ERROR: [INFRA_BLOCKED] agent .md not found: {agent_path}",
            file=sys.stderr,
        )
        print(
            f"FIX: verify `.sdd/agents/` contains {agent_name}.md — the SSoT for "
            f"sub-agent behavior (byte-identical across harness façades).",
            file=sys.stderr,
        )
        sys.exit(INFRA_BLOCKED)
    return agent_path.read_text(encoding="utf-8")


def _resolve_defaults_from_stack_md() -> tuple[str, str]:
    """Read `workspace/stack/stack.md` and extract (harness, provider).

    Returns fallback ("claude-code", "anthropic") on any error — same
    rétrocompat as `stack_config.parse()`.
    """
    try:
        from sdd_lib.stack_config import load_stack_config
        cfg = load_stack_config()
        return cfg.harness, cfg.provider
    except Exception:
        return "claude-code", "anthropic"


def _resolve_model_id(harness: str, provider: str, tier: str) -> str | None:
    """Resolve the concrete model id for the given (provider, tier)."""
    try:
        from sdd_lib.model_resolver import resolve_model_id
        return resolve_model_id(tier, provider)
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spawn_agent_cli",
        description="Emulated sub-agent spawn for multi-harness SDD_Pro. "
                    "Loads the agent .md as system prompt, executes the task "
                    "in an isolated sub-process, validates the JSON contract.",
    )
    p.add_argument("--agent", required=True,
                   help="Agent name (e.g. `dev-backend`, `po`, `qa`) — must exist under .sdd/agents/")
    task_group = p.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task", help="Task instructions (inline text)")
    task_group.add_argument("--task-file", help="Task instructions loaded from a file")
    p.add_argument("--harness", default=None,
                   help="Harness to emulate (codex|gemini-cli|antigravity|claude-code). "
                        "Default: resolved from stack.md")
    p.add_argument("--provider", default=None,
                   help="Model provider (anthropic|openai|google|moonshot). "
                        "Default: resolved from stack.md")
    p.add_argument("--tier", default="balanced", choices=("deep", "balanced", "fast"),
                   help="Model tier (default: balanced)")
    p.add_argument("--schema-file", default=None,
                   help="JSON schema the sub-agent output must satisfy. "
                        "Default: minimal { result: string } schema")
    p.add_argument("--timeout-s", type=float, default=300.0,
                   help="Sub-process timeout in seconds (default: 300)")
    p.add_argument("--no-schema-retry", action="store_true",
                   help="Disable the 1 automatic retry on JSON schema mismatch")
    p.add_argument("--label", default="",
                   help="Optional label for the spawn (persisted in logs)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 1) Resolve harness + provider
    default_harness, default_provider = _resolve_defaults_from_stack_md()
    harness = args.harness or default_harness
    provider = args.provider or default_provider

    # 2) Load agent system prompt (SSoT = .sdd/agents/<name>.md)
    system_prompt = _load_agent_prompt(args.agent)

    # 3) Load task text
    if args.task:
        task_text = args.task
    else:
        try:
            task_text = Path(args.task_file).read_text(encoding="utf-8")
        except Exception as e:
            print(f"ERROR: cannot read --task-file: {e}", file=sys.stderr)
            return FAIL_FAST

    # 4) Load output schema
    if args.schema_file:
        schema = _load_json_file(Path(args.schema_file), "schema-file")
    else:
        schema = _DEFAULT_SCHEMA

    # 5) Resolve concrete model id from tier + provider (best-effort)
    model_id = _resolve_model_id(harness, provider, args.tier)

    # 6) Build config + spec
    cfg = SpawnConfig(
        harness=harness,
        model=model_id,
        timeout_s=args.timeout_s,
        schema_retry=not args.no_schema_retry,
    )
    spec = AgentSpec(
        system_prompt=system_prompt,
        task=task_text,
        output_schema=schema,
        label=args.label or f"{args.agent}",
    )

    # 7) Invoke the sub-agent (spawn_agent returns a dict — see spawn_agent.py)
    try:
        result = spawn_agent(spec, cfg)
    except FileNotFoundError as e:
        print(
            f"ERROR: [INFRA_BLOCKED] harness binary not found for `{harness}`: {e}",
            file=sys.stderr,
        )
        print(
            f"FIX: install the CLI ({harness}) or override with --harness. "
            f"See .sdd/docs/multi-llm-getting-started.md §1.",
            file=sys.stderr,
        )
        return INFRA_BLOCKED

    # 8) Emit + exit code
    payload = {
        "ok": bool(result.get("ok")),
        "agent": args.agent,
        "harness": harness,
        "provider": provider,
        "model": model_id,
        "parsed": result.get("parsed"),
        "raw": result.get("raw"),
        "error_class": result.get("error_class"),
        "schema_errors": result.get("schema_errors", []),
        "attempts": result.get("attempts", 1),
        "latency_ms": result.get("latency_ms"),
        "label": result.get("label", ""),
    }
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")

    return SUCCESS if payload["ok"] else FAIL_FAST


if __name__ == "__main__":
    sys.exit(main())
