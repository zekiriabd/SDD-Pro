#!/usr/bin/env python3
"""SDD_Pro stack matcher — maps scan_repo output to SDD stack ids.

Takes the scan-report JSON produced by `scan_repo.py` and the SDD_Pro
stack catalog (`.claude/stacks/*/{stack-id}.libs.json`), then scores
each stack against the detected indicators. Outputs ranked candidates
per category (backend / frontend / ui / database / auth).

Score is in [0, 100]. Confidence levels:
    >= 80 : high confidence (auto-suggest)
    50-79 : medium (ask user to confirm)
    < 50  : low (mention but don't suggest)

Usage:
    python match_stack_catalog.py --scan-report PATH [--json]
    python match_stack_catalog.py --scope DIR [--json]   # runs scan first

The script is **deterministic** (no LLM). The mapping rules are
declarative below. To extend support for a new stack, add an entry in
STACK_RULES.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.combos import get_component_level  # noqa: E402
from sdd_lib.paths import iso_now  # noqa: E402
from sdd_lib.exit_codes import CORRECTIBLE, SUCCESS  # noqa: E402

try:
    from sdd_scripts.scan_repo import scan as scan_repo_func
except ImportError:
    scan_repo_func = None  # type: ignore[assignment]


# v7.0.0-alpha (audit CRIT-6, 2026-06-04) — validation level no longer
# hardcoded per entry below (was `"validation": "🟢"` on every stack, a
# drift source vs the SSoT in `.claude/templates/combos.json`). The
# `validation` field of each output candidate is now derived at runtime
# via `sdd_lib.combos.get_component_level(category, stack_id)`.
_LEVEL_TO_EMOJI: dict[str, str] = {
    "validated":    "🟢",
    "experimental": "🟡",
    "untested":     "🔴",
    "missing":      "⊘",
}


# Stack matching rules. Each entry maps a stack id to required + bonus indicators.
# Score = (required_hits / len(required)) * 70 + (bonus_hits / len(bonus)) * 30
# A stack is a candidate only if all required indicators are present.
STACK_RULES: dict[str, dict[str, Any]] = {
    # --- Backend stacks ---
    "dotnet-minimalapi": {
        "category": "backend",
        "required": {
            "languages": ["dotnet"],
            "frameworks": ["aspnetcore-minimal"],
        },
        "bonus": {
            "frameworks": ["aspnetcore"],
        },
    },
    "kotlin-spring-boot": {
        "category": "backend",
        "required": {
            "languages": ["kotlin"],
            "frameworks": ["spring-boot"],
        },
        "bonus": {
            "frameworks": ["kotlin-jvm"],
        },
    },
    "python-fastapi": {
        "category": "backend",
        "required": {
            "languages": ["python"],
            "frameworks": ["fastapi"],
        },
        "bonus": {},
    },
    "node-express": {
        "category": "backend",
        "required": {
            "languages": ["javascript"],
            "frameworks": ["express"],
        },
        "bonus": {
            "languages": ["typescript"],
        },
    },

    # --- Frontend stacks ---
    "react": {
        "category": "frontend",
        "required": {
            "frameworks": ["react"],
        },
        "bonus": {
            "frameworks": ["vite"],
            "languages": ["typescript"],
        },
    },
    "vue": {
        "category": "frontend",
        "required": {
            "frameworks": ["vue"],
        },
        "bonus": {
            "frameworks": ["vite"],
        },
    },
    "angular": {
        "category": "frontend",
        "required": {
            "frameworks": ["angular"],
        },
        "bonus": {
            "languages": ["typescript"],
        },
    },
    "blazor-webassembly": {
        "category": "frontend",
        "required": {
            "frameworks": ["blazor-webassembly"],
        },
        "bonus": {
            "languages": ["dotnet"],
        },
    },

    # --- UI design systems ---
    "shadcn": {
        "category": "ui",
        "required": {
            "ui_indicators": ["shadcn"],
        },
        "bonus": {
            "ui_indicators": ["tailwind", "radix-ui"],
        },
    },
    "vuetify": {
        "category": "ui",
        "required": {
            "ui_indicators": ["vuetify"],
        },
        "bonus": {},
    },
    "radzen-blazor": {
        "category": "ui",
        "required": {
            "ui_indicators": ["radzen-blazor"],
        },
        "bonus": {
            "frameworks": ["blazor-webassembly"],
        },
    },
}

# Database stack mappings (Project Config `DatabaseType:`)
DATABASE_MAPPING: dict[str, str] = {
    "sqlserver": "SqlServer",
    "postgresql": "PostgreSql",
    "mysql": "MySql",
    "sqlite": "Sqlite",
    "mongodb": "MongoDb",
    "jpa": "SqlServer",  # JPA hint but actual driver unknown; default SqlServer
}

# Auth stack mappings (`.claude/stacks/auth/`)
AUTH_MAPPING: dict[str, str] = {
    "azure-ad": "azure-ad",
    "oauth2-resource-server": "azure-ad",
    "spring-security": "auth-local",
    "auth-library": "auth-local",
    "jwt-local": "auth-local",
}


def _intersect_count(needed: list[str], found: list[str]) -> tuple[int, list[str]]:
    matched = [x for x in needed if x in found]
    return len(matched), matched


def _score_stack(rules: dict[str, Any], scan_report: dict[str, Any]) -> dict[str, Any]:
    """Score one stack against the scan report.

    Returns dict with score (0-100), required_met (bool), and evidence lists.
    """
    required_total = 0
    required_hit = 0
    required_evidence: list[str] = []

    for axis, needed in rules.get("required", {}).items():
        found = scan_report.get(axis, [])
        hits, matched = _intersect_count(needed, found)
        required_total += len(needed)
        required_hit += hits
        for m in matched:
            required_evidence.append(f"{axis}:{m}")

    required_met = required_total == required_hit if required_total > 0 else False

    bonus_total = 0
    bonus_hit = 0
    bonus_evidence: list[str] = []
    for axis, needed in rules.get("bonus", {}).items():
        found = scan_report.get(axis, [])
        hits, matched = _intersect_count(needed, found)
        bonus_total += len(needed)
        bonus_hit += hits
        for m in matched:
            bonus_evidence.append(f"{axis}:{m}")

    if required_total == 0:
        score = 0
    else:
        req_pct = required_hit / required_total
        bonus_pct = (bonus_hit / bonus_total) if bonus_total > 0 else 0
        score = round(req_pct * 70 + bonus_pct * 30)

    # v7.0.0-alpha (audit CRIT-6) : validation derived at runtime from
    # combos.json SSoT instead of duplicated per-entry. `category` field
    # is forwarded so the `match()` loop can resolve the level.
    return {
        "score":             score,
        "required_met":      required_met,
        "required_evidence": required_evidence,
        "bonus_evidence":    bonus_evidence,
    }


def _confidence_label(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def match(scan_report: dict[str, Any]) -> dict[str, Any]:
    """Match scan_report against STACK_RULES; return categorized candidates."""
    candidates: dict[str, list[dict[str, Any]]] = {
        "backend": [], "frontend": [], "ui": [],
    }

    for stack_id, rules in STACK_RULES.items():
        score_info = _score_stack(rules, scan_report)
        if not score_info["required_met"]:
            continue  # skip stacks whose required indicators aren't all present
        category = rules["category"]
        # v7.0.0-alpha (audit CRIT-6) : look up level from combos.json SSoT.
        level = get_component_level(category, stack_id)
        candidates.setdefault(category, []).append({
            "stack_id":          stack_id,
            "score":             score_info["score"],
            "confidence":        _confidence_label(score_info["score"]),
            "validation":        _LEVEL_TO_EMOJI.get(level, "⊘"),
            "validation_level":  level,  # raw string (validated|experimental|untested|missing)
            "required_evidence": score_info["required_evidence"],
            "bonus_evidence":    score_info["bonus_evidence"],
        })

    # Sort by score desc
    for cat in candidates:
        candidates[cat].sort(key=lambda c: -c["score"])

    # Database detection (single value)
    db_inds = scan_report.get("database_indicators", [])
    database: str | None = None
    for ind in db_inds:
        mapped = DATABASE_MAPPING.get(ind)
        if mapped:
            database = mapped
            break

    # Auth detection
    auth_inds = scan_report.get("auth_indicators", [])
    auth: str | None = None
    for ind in auth_inds:
        mapped = AUTH_MAPPING.get(ind)
        if mapped:
            auth = mapped
            break

    # Build warnings
    warnings: list[str] = list(scan_report.get("warnings", []))
    if not any(candidates[c] for c in ("backend", "frontend")):
        warnings.append(
            "[DISCOVER_NO_MATCH] aucun stack backend ni frontend reconnu"
        )
    elif candidates.get("backend") and not candidates.get("frontend"):
        warnings.append("[DISCOVER_PARTIAL] backend détecté, frontend absent (projet API-only ?)")
    elif candidates.get("frontend") and not candidates.get("backend"):
        warnings.append("[DISCOVER_PARTIAL] frontend détecté, backend absent (SPA standalone ?)")

    if candidates.get("backend") and len(candidates["backend"]) > 1:
        warnings.append(
            f"[DISCOVER_AMBIGUOUS] {len(candidates['backend'])} backends reconnus — "
            "le Tech Lead doit choisir"
        )
    if candidates.get("frontend") and len(candidates["frontend"]) > 1:
        warnings.append(
            f"[DISCOVER_AMBIGUOUS] {len(candidates['frontend'])} frontends reconnus — "
            "le Tech Lead doit choisir"
        )

    return {
        "matched_at": iso_now(),
        "scope_dir": scan_report.get("scope_dir"),
        "candidates": candidates,
        "database": database,
        "auth": auth,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="match_stack_catalog",
        description="Map scan_repo output to SDD_Pro stack ids.",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--scan-report",
        type=Path,
        help="Path to a JSON file produced by scan_repo.py",
    )
    g.add_argument(
        "--scope",
        type=Path,
        help="Directory to scan first (calls scan_repo internally)",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.scan_report:
        try:
            scan_report = json.loads(args.scan_report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write(f"ERROR loading scan report: {e}\n")
            return CORRECTIBLE
    else:
        if scan_repo_func is None:
            sys.stderr.write("ERROR: scan_repo module not importable\n")
            return CORRECTIBLE
        scan_report = scan_repo_func(args.scope)

    result = match(scan_report)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    sys.stdout.write(text + "\n")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
