#!/usr/bin/env python3
"""SDD_Pro: parse multi-stack coverage outputs to normalized JSON.

Reads native coverage outputs from various stacks and produces
`workspace/output/qa/feat-{n}/coverage.json` following the schema in
`rules/quality.md §2`.

Supported formats:
- Cobertura XML  (`coverage.cobertura.xml`)  — .NET coverlet, Python coverage.py, JS
- lcov.info      (`lcov.info`)               — Vitest/c8/Jest/Karma
- JaCoCo XML     (`jacocoTestReport.xml`, `jacoco.xml`) — Kotlin/Java
- Istanbul JSON  (`coverage-summary.json`)   — Angular/Karma

Usage:
    python parse_coverage.py --feat-number 1 [--coverage-min 80]

Exit codes:
    0 = parse OK
    1 = no coverage files found
    2 = parse error

Migrated from .claude/scripts/parse-coverage.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import (  # noqa: E402
    connect, ensure_initialized, insert_qa_coverage, replace_qa_coverage_for_feat,
)
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument("--coverage-min", type=int, default=80)
    return p.parse_args()


def _round2(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def parse_cobertura(path: Path) -> dict[str, Any]:
    """Parse Cobertura XML (`coverage.cobertura.xml`)."""
    tree = ET.parse(path)
    root = tree.getroot()
    covered = int(root.get("lines-covered", 0))
    total = int(root.get("lines-valid", 0))
    bcovered = int(root.get("branches-covered", 0))
    btotal = int(root.get("branches-valid", 0))

    files: list[dict[str, Any]] = []
    for cls in root.iter("class"):
        filename = cls.get("filename")
        line_rate = cls.get("line-rate")
        if filename and line_rate:
            try:
                pct = round(float(line_rate) * 100, 2)
            except ValueError:
                continue
            files.append({"path": filename, "lines_pct": pct})

    return {"covered": covered, "total": total, "bcovered": bcovered, "btotal": btotal, "files": files}


def parse_lcov(path: Path) -> dict[str, Any]:
    """Parse `lcov.info` (Vitest/c8/Jest/Karma)."""
    covered = 0
    total = 0
    files: list[dict[str, Any]] = []
    current_file: str | None = None
    file_lf = 0
    file_lh = 0

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"covered": 0, "total": 0, "bcovered": 0, "btotal": 0, "files": []}

    for line in text.splitlines():
        if line.startswith("SF:"):
            current_file = line[3:].strip()
            file_lf = 0
            file_lh = 0
        elif line.startswith("LF:"):
            try:
                file_lf = int(line[3:].strip())
            except ValueError:
                file_lf = 0
        elif line.startswith("LH:"):
            try:
                file_lh = int(line[3:].strip())
            except ValueError:
                file_lh = 0
        elif line.startswith("end_of_record"):
            if current_file and file_lf > 0:
                covered += file_lh
                total += file_lf
                files.append({
                    "path": current_file,
                    "lines_pct": round((file_lh / file_lf) * 100, 2),
                })
            current_file = None

    return {"covered": covered, "total": total, "bcovered": 0, "btotal": 0, "files": files}


def parse_jacoco(path: Path) -> dict[str, Any]:
    """Parse JaCoCo XML (`jacocoTestReport.xml` / `jacoco.xml`)."""
    tree = ET.parse(path)
    root = tree.getroot()
    covered = 0
    total = 0
    bcovered = 0
    btotal = 0

    for counter in root.findall("counter"):
        ctype = counter.get("type")
        missed = int(counter.get("missed", 0))
        cov = int(counter.get("covered", 0))
        if ctype == "LINE":
            covered = cov
            total = missed + cov
        elif ctype == "BRANCH":
            bcovered = cov
            btotal = missed + cov

    files: list[dict[str, Any]] = []
    for package in root.findall("package"):
        pkg_name = package.get("name", "")
        for sourcefile in package.findall("sourcefile"):
            sf_name = sourcefile.get("name", "")
            for counter in sourcefile.findall("counter"):
                if counter.get("type") != "LINE":
                    continue
                sf_missed = int(counter.get("missed", 0))
                sf_cov = int(counter.get("covered", 0))
                sf_total = sf_missed + sf_cov
                if sf_total > 0:
                    files.append({
                        "path": f"{pkg_name}/{sf_name}",
                        "lines_pct": round((sf_cov / sf_total) * 100, 2),
                    })
                break

    return {"covered": covered, "total": total, "bcovered": bcovered, "btotal": btotal, "files": files}


def parse_istanbul(path: Path) -> dict[str, Any]:
    """Parse `coverage-summary.json` (Istanbul/Karma/Angular)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {"covered": 0, "total": 0, "bcovered": 0, "btotal": 0, "files": []}

    covered = 0
    total = 0
    files: list[dict[str, Any]] = []

    total_block = data.get("total") if isinstance(data, dict) else None
    if isinstance(total_block, dict) and "lines" in total_block:
        lines_block = total_block.get("lines") or {}
        covered = int(lines_block.get("covered", 0))
        total = int(lines_block.get("total", 0))

    if isinstance(data, dict):
        for key, value in data.items():
            if key == "total" or not isinstance(value, dict):
                continue
            lines_block = value.get("lines")
            if not isinstance(lines_block, dict):
                continue
            fc = int(lines_block.get("covered", 0))
            ft = int(lines_block.get("total", 0))
            if ft > 0:
                files.append({"path": key, "lines_pct": round((fc / ft) * 100, 2)})

    return {"covered": covered, "total": total, "bcovered": 0, "btotal": 0, "files": files}


def build_stack_entry(parsed: dict[str, Any], stack_id: str, tool: str) -> dict[str, Any]:
    branches_block: dict[str, Any] | None = None
    if parsed["btotal"] > 0:
        branches_block = {
            "covered": parsed["bcovered"],
            "total":   parsed["btotal"],
            "percent": _round2(parsed["bcovered"], parsed["btotal"]),
        }
    return {
        "stack": stack_id,
        "tool": tool,
        "toolVersion": "",
        "tests": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
        "coverage": {
            "lines": {
                "covered": parsed["covered"],
                "total":   parsed["total"],
                "percent": _round2(parsed["covered"], parsed["total"]),
            },
            "branches": branches_block,
        },
        "files": parsed["files"],
    }


def detect_coverage_min(stack_md: Path, default: int) -> int:
    """Read CoverageMin from a stack.md file.

    v6.7.4: if `stack_md` matches the canonical workspace path
    (`workspace/input/stack/stack.md`), prefer `read_layered_config()`
    (so team.yml policy is honored). Otherwise (tests / explicit
    paths), preserve v6.6.x behavior — read only the given file.
    """
    # v6.7.4: layered config only for canonical workspace stack.md
    try:
        from sdd_lib.layered_config import read_layered_config
        from sdd_lib.project_config import stack_md_path
        if stack_md.resolve() == stack_md_path().resolve():
            cfg = read_layered_config(keys=("CoverageMin",))
            raw = cfg.get("CoverageMin")
            if raw:
                try:
                    return int(raw)
                except ValueError:
                    pass
    except Exception:  # noqa: BLE001
        pass

    if not stack_md.is_file():
        return default
    try:
        text = stack_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return default
    m = re.search(r"(?ms)CoverageMin\s*:\s*(\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return default
    return default


def find_feat_name(feats_dir: Path, feat_number: int) -> str | None:
    if not feats_dir.is_dir():
        return None
    for f in sorted(feats_dir.glob(f"{feat_number}-*.md")):
        m = re.match(rf"^{feat_number}-(.+)$", f.stem)
        if m:
            return m.group(1)
    return None


def main() -> int:
    args = parse_args()
    root = repo_root()
    src_dir = root / "workspace" / "output" / "src"
    stack_md = root / "workspace" / "input" / "stack" / "stack.md"
    feats_dir = root / "workspace" / "input" / "feats"

    feat_name = find_feat_name(feats_dir, args.feat_number)
    coverage_min = detect_coverage_min(stack_md, args.coverage_min)

    stacks_found: list[dict[str, Any]] = []

    if not src_dir.is_dir():
        print(f"No source directory: {src_dir}")
        return FAIL_FAST

    # 1. Cobertura XML
    for f in src_dir.rglob("coverage.cobertura.xml"):
        try:
            parsed = parse_cobertura(f)
            stack_id = "qa-dotnet-xunit" if ".Tests" in str(f) else "qa-cobertura"
            tool = "coverlet" if stack_id == "qa-dotnet-xunit" else "cobertura"
            stacks_found.append(build_stack_entry(parsed, stack_id, tool))
        except ET.ParseError as e:
            warn(f"WARN: cobertura parse failed for {f}: {e}")

    # 2. lcov.info
    for f in src_dir.rglob("lcov.info"):
        try:
            parsed = parse_lcov(f)
            stack_id = (
                "qa-angular-jasmine" if re.search(r"angular|karma", str(f), re.IGNORECASE)
                else "qa-node-vitest"
            )
            tool = "istanbul" if stack_id == "qa-angular-jasmine" else "c8"
            stacks_found.append(build_stack_entry(parsed, stack_id, tool))
        except Exception as e:  # noqa: BLE001
            warn(f"WARN: lcov parse failed for {f}: {e}")

    # 3. JaCoCo XML
    for filename in ("jacocoTestReport.xml", "jacoco.xml"):
        for f in src_dir.rglob(filename):
            try:
                parsed = parse_jacoco(f)
                stacks_found.append(build_stack_entry(parsed, "qa-kotlin-junit", "JaCoCo"))
            except ET.ParseError as e:
                warn(f"WARN: JaCoCo parse failed for {f}: {e}")

    # 4. Istanbul JSON
    for f in src_dir.rglob("coverage-summary.json"):
        try:
            parsed = parse_istanbul(f)
            stacks_found.append(build_stack_entry(parsed, "qa-angular-jasmine", "istanbul"))
        except Exception as e:  # noqa: BLE001
            warn(f"WARN: istanbul parse failed for {f}: {e}")

    if not stacks_found:
        print(f"No coverage files found under {src_dir} (recursive).")
        print(
            "Looked for: coverage.cobertura.xml, lcov.info, jacocoTestReport.xml, "
            "coverage-summary.json"
        )
        return FAIL_FAST

    total_covered = sum(s["coverage"]["lines"]["covered"] for s in stacks_found)
    total_total = sum(s["coverage"]["lines"]["total"] for s in stacks_found)
    total_tests = sum(s["tests"]["total"] for s in stacks_found)
    total_passed = sum(s["tests"]["passed"] for s in stacks_found)
    total_failed = sum(s["tests"]["failed"] for s in stacks_found)
    total_skipped = sum(s["tests"]["skipped"] for s in stacks_found)

    global_pct = _round2(total_covered, total_total)

    # Audit 2026-06-06 D6 — per-stack threshold enforcement.
    # The LOC-weighted global_pct dilutes per-stack signal : back 50%/10k LOC
    # + front 95%/100 LOC → global ≈ 50.4% → 🔴 RED on the global, while front
    # is excellent. The reverse is also possible : back 95%/10k LOC + front
    # 40%/100 LOC → global ≈ 94.5% → 🟢 GREEN, hiding a poor front coverage.
    #
    # Strict policy : `passed` requires BOTH the LOC-weighted global AND every
    # individual stack to meet the threshold. This catches the per-stack
    # regression that the LOC-weighted average otherwise masks. Per-stack
    # coverage_passed remains attached to each `qa_coverage` row (single
    # source of truth for downstream consumers).
    per_stack_passes: list[bool] = []
    for s in stacks_found:
        stack_lines = s.get("coverage", {}).get("lines", {})
        stack_total = int(stack_lines.get("total", 0) or 0)
        if stack_total == 0:
            # Empty stack (no LOC measured) — treat as N/A, do not penalize.
            per_stack_passes.append(True)
            continue
        stack_pct = float(stack_lines.get("percent") or 0.0)
        per_stack_passes.append(stack_pct >= coverage_min)

    all_stacks_pass = all(per_stack_passes)
    global_pass = global_pct >= coverage_min
    passed = global_pass and all_stacks_pass

    feat_label = f"{args.feat_number}-{feat_name}" if feat_name else str(args.feat_number)
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Write to console.db (single source of truth) — replaces former coverage.json.
    ensure_initialized()
    with connect() as conn:
        replace_qa_coverage_for_feat(conn, args.feat_number)
        for s in stacks_found:
            cov = s.get("coverage") or {}
            lines = cov.get("lines") or {}
            branches = cov.get("branches") or {}
            tests = s.get("tests") or {}
            insert_qa_coverage(
                conn,
                feat_n=args.feat_number,
                stack=s.get("stack") or "",
                extracted_at=extracted_at,
                tool=s.get("tool") or None,
                tool_version=s.get("toolVersion") or None,
                tests_total=int(tests.get("total", 0) or 0),
                tests_passed=int(tests.get("passed", 0) or 0),
                tests_failed=int(tests.get("failed", 0) or 0),
                tests_skipped=int(tests.get("skipped", 0) or 0),
                lines_covered=int(lines.get("covered", 0) or 0),
                lines_total=int(lines.get("total", 0) or 0),
                lines_pct=float(lines.get("percent")) if lines.get("percent") is not None else None,
                branches_covered=(int(branches.get("covered", 0))
                                  if branches and branches.get("total", 0) else None),
                branches_total=(int(branches.get("total", 0))
                                if branches and branches.get("total", 0) else None),
                branches_pct=(float(branches.get("percent"))
                              if branches and branches.get("percent") is not None else None),
                coverage_min=coverage_min,
                coverage_passed=passed,
                files=s.get("files") or [],
            )

    print(f"Coverage parsed: global={global_pct}% (min: {coverage_min}%) "
          f"passed={passed} (global_pass={global_pass}, all_stacks_pass={all_stacks_pass})")
    if not all_stacks_pass:
        for s, ok in zip(stacks_found, per_stack_passes):
            if not ok:
                stack_pct = float(s.get("coverage", {}).get("lines", {}).get("percent") or 0.0)
                print(f"  ⚠ stack '{s.get('stack', '?')}' below threshold : "
                      f"{stack_pct}% < {coverage_min}%")
    print(f"Stacks: {len(stacks_found)}")
    print(f"FEAT: {feat_label} -> console.db (table qa_coverage)")

    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
