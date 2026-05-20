"""US-level operations MCP tools.

Four tools, all wrap deterministic Python scripts under sdd_scripts/:

  set_us_status          -> set_us_status.py
  validate_us_deps       -> validate_us_deps.py
  compute_us_complexity  -> compute_us_complexity.py
  migrate_us_v1_to_v2    -> migrate_us_v1_to_v2.py

`set_us_status` is the only one that may write; it edits a single
`Status:` frontmatter line under workspace/output/us/{n}-{m}-*.md after
validating the transition is allowed (cf. set_us_status.py docstring).

`compute_us_complexity` with `apply=true` and `migrate_us_v1_to_v2`
without `dry_run=true` also write, but to a single US file each and only
in ways that are idempotent and reversible.
"""
from __future__ import annotations

from typing import Any

from ..registry import Tool
from ..subprocess_helper import run_script


_US_ID_PATTERN = r"^\d+-\d+$"
_VALID_STATUSES = [
    "Draft", "Ready", "InProgress", "Review", "Done", "Deferred", "Cancelled",
]


# --------------------------------------------------------------------------
# set_us_status
# --------------------------------------------------------------------------

_SET_US_STATUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "us": {
            "type": "string",
            "pattern": _US_ID_PATTERN,
            "description": "US short id, e.g. '1-2' (matched against workspace/output/us/1-2-*.md).",
        },
        "status": {
            "type": "string",
            "enum": _VALID_STATUSES,
            "description": "Target status. Transition is validated unless force=true.",
        },
        "get": {
            "type": "boolean",
            "default": False,
            "description": "Read-only: print current Status: of `us` and exit. Ignores `status` if set.",
        },
        "force": {
            "type": "boolean",
            "default": False,
            "description": "Bypass transition validation (legacy migration / terminal reopen).",
        },
    },
    "additionalProperties": False,
}


def _handle_set_us_status(args: dict[str, Any]) -> dict[str, Any]:
    us = args.get("us")
    if not us:
        return _bad_args("`us` is required (e.g. '1-2')")

    if args.get("get"):
        return run_script("set_us_status", ["--us", us, "--get"])

    status = args.get("status")
    if not status:
        return _bad_args("`status` is required unless get=true")

    script_args = ["--us", us, "--status", status]
    if args.get("force"):
        script_args.append("--force")
    return run_script("set_us_status", script_args)


# --------------------------------------------------------------------------
# validate_us_deps
# --------------------------------------------------------------------------

_VALIDATE_US_DEPS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "feat": {"type": "integer", "minimum": 1, "description": "FEAT number to scope."},
        "us": {
            "type": "string",
            "pattern": _US_ID_PATTERN,
            "description": "Single US id (e.g. '1-2'). Mutually exclusive with `feat`/`all`.",
        },
        "all": {
            "type": "boolean",
            "default": False,
            "description": "Validate every US under workspace/output/us/.",
        },
        "topo": {
            "type": "boolean",
            "default": False,
            "description": "Also print the topological order (one short id per line).",
        },
    },
    "additionalProperties": False,
}


def _handle_validate_us_deps(args: dict[str, Any]) -> dict[str, Any]:
    feat = args.get("feat")
    us = args.get("us")
    all_us = bool(args.get("all", False))
    selectors = sum(1 for v in (feat is not None, us is not None, all_us) if v)
    if selectors != 1:
        return _bad_args("Provide exactly one of: feat | us | all")

    script_args: list[str] = []
    if feat is not None:
        script_args += ["--feat", str(feat)]
    elif us is not None:
        script_args += ["--us-id", us]
    else:
        script_args.append("--all")
    if args.get("topo"):
        script_args.append("--topo")
    script_args.append("--json")
    return run_script("validate_us_deps", script_args)


# --------------------------------------------------------------------------
# compute_us_complexity
# --------------------------------------------------------------------------

_COMPUTE_COMPLEXITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "us": {
            "type": "string",
            "pattern": _US_ID_PATTERN,
            "description": "US short id, e.g. '1-2'.",
        },
        "apply": {
            "type": "boolean",
            "default": False,
            "description": "Persist score into the US `## Metadata` JSON block.",
        },
    },
    "required": ["us"],
    "additionalProperties": False,
}


def _handle_compute_us_complexity(args: dict[str, Any]) -> dict[str, Any]:
    script_args = ["--us", args["us"], "--json"]
    if args.get("apply"):
        script_args.append("--apply")
    return run_script("compute_us_complexity", script_args)


# --------------------------------------------------------------------------
# migrate_us_v1_to_v2
# --------------------------------------------------------------------------

_MIGRATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "us": {
            "type": "string",
            "pattern": _US_ID_PATTERN,
            "description": "Single US id to migrate. Mutually exclusive with `all`.",
        },
        "all": {
            "type": "boolean",
            "default": False,
            "description": "Migrate every US under workspace/output/us/ (idempotent).",
        },
        "dry_run": {
            "type": "boolean",
            "default": False,
            "description": "Preview changes without writing.",
        },
    },
    "additionalProperties": False,
}


def _handle_migrate_us_v1_to_v2(args: dict[str, Any]) -> dict[str, Any]:
    us = args.get("us")
    all_us = bool(args.get("all", False))
    if (us is None) == (not all_us):
        return _bad_args("Provide exactly one of: us | all")
    script_args: list[str] = ["--all"] if all_us else ["--us", us]  # type: ignore[list-item]
    if args.get("dry_run"):
        script_args.append("--dry-run")
    script_args.append("--json")
    return run_script("migrate_us_v1_to_v2", script_args)


def _bad_args(msg: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": f"ERROR: bad arguments — {msg}"}],
        "isError": True,
        "_meta": {"exitCode": 2, "json": None},
    }


TOOLS: list[Tool] = [
    Tool(
        name="set_us_status",
        description=(
            "Read or write the `Status:` line of a User Story file. "
            "7 statuses: Draft, Ready, InProgress, Review, Done, Deferred, "
            "Cancelled. Transitions are validated unless force=true."
        ),
        input_schema=_SET_US_STATUS_SCHEMA,
        handler=_handle_set_us_status,
    ),
    Tool(
        name="validate_us_deps",
        description=(
            "Validate the `## Dependencies` graph of User Stories: detect "
            "cycles (Tarjan SCC), missing refs, orphans. Optionally return "
            "topological order. Exit 3 = cycles, 4 = missing refs."
        ),
        input_schema=_VALIDATE_US_DEPS_SCHEMA,
        handler=_handle_validate_us_deps,
    ),
    Tool(
        name="compute_us_complexity",
        description=(
            "Compute deterministic 1-10 complexity score and S/M/L/XL effort "
            "estimate for a User Story from 6 measurable signals (no LLM). "
            "Optionally persist into `## Metadata` with apply=true."
        ),
        input_schema=_COMPUTE_COMPLEXITY_SCHEMA,
        handler=_handle_compute_us_complexity,
    ),
    Tool(
        name="migrate_us_v1_to_v2",
        description=(
            "Migrate User Stories from v1 (pre-6.8) to v2 schema: append "
            "`## Metadata` block + ensure Status: line. Idempotent and safe — "
            "never rewrites existing content."
        ),
        input_schema=_MIGRATE_SCHEMA,
        handler=_handle_migrate_us_v1_to_v2,
    ),
]
