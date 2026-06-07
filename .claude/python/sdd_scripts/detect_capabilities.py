#!/usr/bin/env python3
"""SDD_Pro deterministic workload: detect §2.4.b capabilities triggered by a US.

Reads the §2.4.b ON-DEMAND table from the active backend stack `.md`, matches
each capability's regex triggers against the US text + HTML mockup, and
returns a JSON structure consumed by dev-backend STEP 5.bis.

Replaces ~70 lines of LLM prose with a deterministic script (~0 token).

Usage:
    python detect_capabilities.py \\
        --us-path workspace/output/us/1-2-Bebes.md \\
        --stack-path .claude/stacks/backend/dotnet-minimalapi.md \\
        --project-config workspace/input/stack/stack.md \\
        [--html-path workspace/input/ui/1-2-Bebes.html] \\
        [--project-file workspace/output/src/AppName/AppName.csproj]

Migrated from .claude/scripts/detect-capabilities.ps1 (2026-05-13).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import SUCCESS  # noqa: E402

import argparse
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path


# v7.0.0-alpha (audit MAJ-11, 2026-06-04) — regex compilation cache +
# word-boundary wrapping. Before MAJ-11, every trigger was re.search'd
# uncompiled (re-parsed per call) and matched `re.IGNORECASE` literally
# — `excel` matched `excellent UX`. The cache + \b wrap fixes both.

@lru_cache(maxsize=256)
def _compile_trigger(pattern: str) -> re.Pattern[str] | None:
    """Return a compiled trigger or None on invalid regex.

    Wraps the user pattern with `\\b...\\b` boundaries IFF the pattern
    looks like a simple alphanumeric word (no metachars). Patterns
    containing regex metachars are compiled as-is — the catalog author
    has already crafted their own boundaries.
    """
    if not pattern:
        return None
    try:
        # Heuristic: bare alphanumeric token → wrap with \b for word match.
        # Token = letters/digits/dashes only, no regex metachars.
        if re.fullmatch(r"[A-Za-z0-9_-]+", pattern):
            return re.compile(rf"\b{re.escape(pattern)}\b", re.IGNORECASE)
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--us-path", required=True)
    p.add_argument("--stack-path", required=True,
                   help="Path to .claude/stacks/backend/{id}.md OR {id}.libs.json")
    p.add_argument("--project-config", required=True,
                   help="Path to workspace/input/stack/stack.md")
    p.add_argument("--html-path", default="")
    p.add_argument("--project-file", default="",
                   help="csproj/package.json/etc. to check 'already-installed' libs")
    return p.parse_args()


def safe_read(path: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_ondemand_from_libs_json(stack_path: str) -> list[dict[str, object]]:
    """Read §2.4.b ON-DEMAND capabilities from the stack `.libs.json` (SSOT).

    Accepts either the `.md` path (resolves to companion `.libs.json`) or
    the `.libs.json` directly. Falls back to empty list if catalog missing.

    The `.libs.json` is the source of truth since 2026-05-07 (cf.
    `stack-completeness.md §1.0`). The `.md` §2.4 table is regenerated
    from JSON via `sync_stack_md.py` — parsing the `.md` table was fragile
    (whitespace/format drift). This direct read eliminates that risk.
    """
    p = Path(stack_path)
    if p.suffix == ".md":
        libs_json = p.with_suffix(".libs.json")
    else:
        libs_json = p
    if not libs_json.is_file():
        return []
    try:
        catalog = json.loads(libs_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    versions: dict[str, str] = catalog.get("versions", {}) or {}
    capabilities: list[dict[str, object]] = []
    for lib in catalog.get("onDemand", []) or []:
        capability = lib.get("capability") or lib.get("id") or lib.get("module")
        triggers = lib.get("triggers") or []
        if not capability or not triggers:
            continue
        version_ref = lib.get("versionRef") or lib.get("ref")
        version = versions.get(version_ref, "") if version_ref else ""
        module = lib.get("module") or capability
        capabilities.append({
            "name": str(capability),
            "lib": str(module),
            "version": str(version),
            "triggers": [str(t) for t in triggers if t],
        })
    return capabilities


def parse_overrides(config: str) -> tuple[list[str], dict[str, str]]:
    """Extract `Capabilities: a, b, c` + `## Capabilities Override` map."""
    forced: list[str] = []
    overrides: dict[str, str] = {}

    m = re.search(r"(?im)^\s*Capabilities\s*:\s*([^\r\n]+)", config)
    if m:
        forced = [c.strip().lower() for c in m.group(1).split(",") if c.strip()]

    m_block = re.search(
        r"(?ims)##\s*Capabilities\s+Override\s*\r?\n((?:\s+\w+\s*:\s*\S+\s*\r?\n?)+)",
        config,
    )
    if m_block:
        for line in m_block.group(1).splitlines():
            mm = re.match(r"^\s*([a-zA-Z0-9_-]+)\s*:\s*([a-zA-Z0-9_.\-]+)", line)
            if mm:
                overrides[mm.group(1).strip().lower()] = mm.group(2).strip()

    return forced, overrides


def main() -> int:
    args = parse_args()

    us_text = safe_read(args.us_path)
    config_text = safe_read(args.project_config)
    html_text = safe_read(args.html_path) if args.html_path else ""
    project_text = safe_read(args.project_file) if args.project_file else ""

    capabilities = load_ondemand_from_libs_json(args.stack_path)
    forced_caps, override_map = parse_overrides(config_text)

    haystack = f"{us_text}\n{html_text}"
    results: list[dict[str, object]] = []

    for cap in capabilities:
        name_lc = str(cap["name"]).lower()
        is_forced = name_lc in forced_caps
        is_auto = False
        matched_triggers: list[str] = []

        if not is_forced:
            # v7.0.0-alpha (audit MAJ-11) : compiled cache + word-boundary
            # wrap for bare-word patterns ; eliminates `excel` matching
            # `excellent UX`. Cf. _compile_trigger above.
            for trigger in cap["triggers"]:  # type: ignore[union-attr]
                compiled = _compile_trigger(str(trigger or ""))
                if compiled is None:
                    continue
                if compiled.search(haystack):
                    is_auto = True
                    matched_triggers.append(trigger)

        lib_to_use = override_map.get(name_lc, cap["lib"])
        lib_already_present = (
            bool(project_text)
            and re.search(re.escape(str(cap["lib"])), project_text) is not None
        )

        if is_forced:
            status = "TRIGGERED-FORCED"
        elif is_auto and not lib_already_present:
            status = "TRIGGERED-AUTO"
        elif is_auto and lib_already_present:
            status = "USE-EXISTING"
        elif not is_auto and lib_already_present:
            status = "PRESENT-NO-TRIGGER"
        else:
            status = "SKIPPED-NO-TRIGGER"

        results.append({
            "capability": cap["name"],
            "lib": lib_to_use,
            "lib_default": cap["lib"],
            "version": cap["version"],
            "status": status,
            "triggers_matched": matched_triggers,
            "forced_via_config": is_forced,
            "override_applied": name_lc in override_map,
            "install_required": status in ("TRIGGERED-FORCED", "TRIGGERED-AUTO"),
        })

    summary = {
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "us_path": args.us_path,
        "stack_path": args.stack_path,
        "total": len(results),
        "to_install": sum(1 for r in results if r["install_required"]),
        "use_existing": sum(1 for r in results if r["status"] == "USE-EXISTING"),
        "skipped": sum(1 for r in results if r["status"] == "SKIPPED-NO-TRIGGER"),
        "present_unused": sum(1 for r in results if r["status"] == "PRESENT-NO-TRIGGER"),
    }

    print(json.dumps({"summary": summary, "capabilities": results}, indent=2))
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
