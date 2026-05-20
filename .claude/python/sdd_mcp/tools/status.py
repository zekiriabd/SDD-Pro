"""Status / readiness MCP tools — read-only diagnostics.

Three tools, all wrap deterministic Python scripts under sdd_scripts/:

  sdd_status         -> sdd_state.py list-runs / get-run / show-run
  validate_readiness -> validate_readiness.py --feat-number N --json
  feat_validate      -> alias of validate_readiness (matches /feat-validate CLI naming)

These are pure observations of the workspace — they never write, never spawn
agents, never invoke an LLM.
"""
from __future__ import annotations

from typing import Any

from ..registry import Tool
from ..subprocess_helper import run_script


# --------------------------------------------------------------------------
# sdd_status
# --------------------------------------------------------------------------

_SDD_STATUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "run_id": {
            "type": "string",
            "description": "If provided, return full state of this run (show-run).",
        },
        "feat_number": {
            "type": "integer",
            "minimum": 1,
            "description": "Filter runs by FEAT number.",
        },
        "latest": {
            "type": "boolean",
            "default": False,
            "description": "When feat_number is set: return only the most recent run (get-run --latest).",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 10,
            "description": "Max runs to return when listing.",
        },
    },
    "additionalProperties": False,
}


def _handle_sdd_status(args: dict[str, Any]) -> dict[str, Any]:
    run_id = args.get("run_id")
    feat_number = args.get("feat_number")
    latest = bool(args.get("latest", False))
    limit = int(args.get("limit", 10))

    if run_id:
        return run_script("sdd_state", ["show-run", "--run-id", str(run_id)])
    if feat_number is not None and latest:
        return run_script(
            "sdd_state",
            ["get-run", "--feat-number", str(feat_number), "--latest"],
        )
    script_args = ["list-runs", "--limit", str(limit)]
    if feat_number is not None:
        script_args += ["--feat-number", str(feat_number)]
    return run_script("sdd_state", script_args)


# --------------------------------------------------------------------------
# validate_readiness  (and feat_validate alias)
# --------------------------------------------------------------------------

_VALIDATE_READINESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "feat_number": {
            "type": "integer",
            "minimum": 1,
            "description": "FEAT number to validate (e.g. 1 for FEAT 1-Auth).",
        },
    },
    "required": ["feat_number"],
    "additionalProperties": False,
}


def _handle_validate_readiness(args: dict[str, Any]) -> dict[str, Any]:
    feat_number = int(args["feat_number"])
    return run_script(
        "validate_readiness",
        ["--feat-number", str(feat_number), "--json"],
    )


TOOLS: list[Tool] = [
    Tool(
        name="sdd_status",
        description=(
            "Read the SDD_Pro pipeline state for one or more runs. "
            "Wraps sdd_state.py (list-runs / get-run / show-run). "
            "Pass `run_id` for full detail, `feat_number` to filter, "
            "`latest=true` to fetch only the most recent run for that FEAT."
        ),
        input_schema=_SDD_STATUS_SCHEMA,
        handler=_handle_sdd_status,
    ),
    Tool(
        name="validate_readiness",
        description=(
            "Run the Implementation Readiness Gate for a FEAT "
            "(deterministic, 0 LLM tokens). Returns GO / NO-GO with the "
            "list of blocking/warning checks. Equivalent to /feat-validate {n}."
        ),
        input_schema=_VALIDATE_READINESS_SCHEMA,
        handler=_handle_validate_readiness,
    ),
    Tool(
        name="feat_validate",
        description=(
            "Alias of `validate_readiness` matching the /feat-validate slash "
            "command naming. Same inputs, same output."
        ),
        input_schema=_VALIDATE_READINESS_SCHEMA,
        handler=_handle_validate_readiness,
    ),
]
