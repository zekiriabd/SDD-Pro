#!/usr/bin/env python3
"""SDD_Pro — JSON-Schema validator for merged Project Config (v7.0.0-alpha).

Validates the merged Project Config (3-layer hierarchy from layered_config.py)
against `.claude/templates/project-config.schema.json`. Catches :
  - Typo keys not in schema (when `--strict-unknown` is passed)
  - Wrong enum values (e.g. `QAMode: of` instead of `off`)
  - Out-of-range scalars (e.g. `CoverageMin: 150`)
  - Wrong types (e.g. `MaxParallel: "three"`)

Usage:
    python validate_project_config.py [--json] [--strict-unknown]

Exit codes (sdd_lib/exit_codes.py):
    0 = SUCCESS    — config validates
    1 = FAIL_FAST  — config contains invalid keys/values
    3 = INFRA_BLOCKED — schema file unreadable, layered_config unreachable
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import SUCCESS, FAIL_FAST, INFRA_BLOCKED  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402


def _load_schema(repo: Path) -> dict[str, Any]:
    p = repo / ".claude" / "templates" / "project-config.schema.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _resolve_definition(schema: dict, ref: str) -> dict:
    """Resolve $ref pointing into #/definitions/X."""
    if not ref.startswith("#/definitions/"):
        return {}
    name = ref.split("/", 2)[-1]
    return schema.get("definitions", {}).get(name, {})


def _validate_value(key: str, value: Any, prop_schema: dict, schema: dict,
                    errors: list[dict]) -> None:
    """Validate `value` against `prop_schema` (with $ref resolution)."""
    if "$ref" in prop_schema:
        prop_schema = _resolve_definition(schema, prop_schema["$ref"])

    expected_type = prop_schema.get("type")
    enum = prop_schema.get("enum")

    # Type check (canonical JSON-Schema types)
    type_ok = True
    if expected_type == "string":
        type_ok = isinstance(value, str)
    elif expected_type == "integer":
        type_ok = isinstance(value, bool) is False and isinstance(value, int)
    elif expected_type == "number":
        type_ok = isinstance(value, bool) is False and isinstance(value, (int, float))
    elif expected_type == "boolean":
        type_ok = isinstance(value, bool)

    if expected_type and not type_ok:
        errors.append({
            "key": key,
            "code": "TYPE_MISMATCH",
            "message": f"expected type '{expected_type}', got {type(value).__name__} ({value!r})",
        })
        return

    # Enum
    if enum is not None and value not in enum:
        errors.append({
            "key": key,
            "code": "ENUM_VIOLATION",
            "message": f"value {value!r} not in {enum}",
        })
        return

    # Range (integer / number)
    if expected_type in ("integer", "number"):
        minimum = prop_schema.get("minimum")
        maximum = prop_schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append({
                "key": key,
                "code": "BELOW_MINIMUM",
                "message": f"value {value} < minimum {minimum}",
            })
        if maximum is not None and value > maximum:
            errors.append({
                "key": key,
                "code": "ABOVE_MAXIMUM",
                "message": f"value {value} > maximum {maximum}",
            })


def validate_config(config: dict[str, Any], schema: dict,
                    strict_unknown: bool = False) -> list[dict]:
    """Return a list of finding dicts. Empty list = valid."""
    findings: list[dict] = []
    props = schema.get("properties", {})

    for key, value in config.items():
        if key in props:
            _validate_value(key, value, props[key], schema, findings)
        elif strict_unknown:
            findings.append({
                "key": key,
                "code": "UNKNOWN_KEY",
                "message": f"key not in project-config.schema.json (typo or extension?)",
            })

    return findings


def _load_merged_config() -> dict[str, Any] | None:
    """Best-effort load of the merged 3-layer config via sdd_lib.layered_config.

    v7.0.0-alpha : enables `coerce=True` so int/float/bool keys arrive as
    native Python types — required for the JSON-Schema validation below
    (a `'80'` string would falsely fail TYPE_MISMATCH on `CoverageMin`).
    """
    try:
        from sdd_lib.layered_config import read_layered_config
        return read_layered_config(coerce=True)
    except Exception as e:
        sys.stderr.write(f"WARN: read_layered_config failed: {e}\n")
        return None


def main() -> int:
    p = argparse.ArgumentParser(description="Validate merged Project Config.")
    p.add_argument("--json", action="store_true", help="emit JSON findings on stdout")
    p.add_argument("--strict-unknown", action="store_true",
                   help="treat unknown keys (not in schema) as errors")
    args = p.parse_args()

    root = repo_root()
    try:
        schema = _load_schema(root)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"ERROR: schema unreadable: {e}\n")
        return INFRA_BLOCKED

    cfg = _load_merged_config()
    if cfg is None:
        return INFRA_BLOCKED

    findings = validate_config(cfg, schema, strict_unknown=args.strict_unknown)

    if args.json:
        print(json.dumps({
            "config_keys": len(cfg),
            "findings": findings,
            "summary": {
                "errors": len(findings),
                "valid": not findings,
            },
        }, indent=2, ensure_ascii=False))
    else:
        if not findings:
            print(f"[OK] Project Config valid ({len(cfg)} keys validated)")
        else:
            print(f"[ERROR] Project Config has {len(findings)} issue(s):")
            for f in findings:
                print(f"  {f['code']:20s}  {f['key']:30s}  {f['message']}")

    return FAIL_FAST if findings else SUCCESS


if __name__ == "__main__":
    sys.exit(main())
