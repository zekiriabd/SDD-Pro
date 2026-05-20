#!/usr/bin/env python3
"""SDD_Pro: sonar-like quality scan (deterministic, 0 token).

Scans `workspace/output/src/{App|Backend|Lib}/` for:
- TODO / FIXME / XXX / HACK markers (errors)
- console.log / Console.WriteLine / print debug calls (warnings)
- Hex hardcoded outside theme.css (warnings)
- Methods > 50 lines (warnings, heuristic)
- Commented-out code blocks > 5 lines (info)
- Magic numbers (info, heuristic)

Produces `workspace/output/qa/feat-{n}/quality.json`.

Usage:
    python quality_scan.py --feat-number 1

Migrated from .claude/scripts/quality-scan.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import (  # noqa: E402
    connect, ensure_initialized, insert_qa_quality_batch, replace_qa_quality_for_feat,
)
from sdd_lib.paths import normalize, repo_root  # noqa: E402


SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".cs", ".razor", ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".kt", ".kts",
)

EXCLUDE_DIRS: tuple[str, ...] = (
    "bin", "obj", "node_modules", ".vs", "dist", "build", "coverage",
    "TestResults", ".angular", "wwwroot/_framework",
)

TEST_PATTERNS: tuple[str, ...] = (
    ".Tests/", "__tests__/", ".test.", ".FEAT.", "test_", "_test.",
    "Test.kt", "FEAT.kt",
)

DEBUG_PATTERNS: dict[str, str] = {
    r"console\.log":            "js-debug",
    r"console\.error":          "js-debug",
    r"console\.warn":           "js-debug",
    r"Console\.WriteLine":      "cs-debug",
    r"Debug\.Print":            "cs-debug",
    r"System\.out\.println":    "java-kotlin-debug",
    r"(?m)^\s*print\s*\(":      "py-debug",
    r"println\!":               "rust-debug",
}

METHOD_PATTERNS: tuple[str, ...] = (
    r"public\s+\w+\s+\w+\s*\([^)]*\)\s*\{",
    r"private\s+\w+\s+\w+\s*\([^)]*\)\s*\{",
    r"protected\s+\w+\s+\w+\s*\([^)]*\)\s*\{",
    r"function\s+\w+\s*\([^)]*\)\s*\{",
    r"fun\s+\w+\s*\([^)]*\)",
    r"def\s+\w+\s*\([^)]*\)\s*:",
)

MAGIC_NUMBER_SKIP: re.Pattern[str] = re.compile(
    r"^(200|201|204|301|302|400|401|403|404|500|503|"
    r"1000|1024|2048|4096|8080|8443|3306|5432|27017)$"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--feat-number", type=int, required=True)
    return p.parse_args()


def is_excluded(rel_path: str) -> bool:
    for d in EXCLUDE_DIRS:
        if re.search(re.escape(d), rel_path):
            return True
    for p in TEST_PATTERNS:
        if re.search(re.escape(p), rel_path):
            return True
    return False


def line_at(content: str, index: int) -> int:
    """1-based line number for a byte offset in content."""
    return content.count("\n", 0, index) + 1


def scan_file(path: Path, rel_path: str, results: dict[str, list]) -> None:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if not content:
        return

    is_theme_css = bool(re.search(r"/theme\.(css|scss)$", rel_path))

    # 1. TODO / FIXME / XXX / HACK
    for m in re.finditer(r"(?im)\b(TODO|FIXME|XXX|HACK)\b[^\r\n]*", content):
        results["errors"].append({
            "category": "todo",
            "severity": "error",
            "file": rel_path,
            "line": line_at(content, m.start()),
            "tag": m.group(1).upper(),
            "message": re.sub(r"\s+", " ", m.group(0).strip())[:200],
        })

    # 2. Debug output left in prod
    for pat, tag in DEBUG_PATTERNS.items():
        for m in re.finditer(pat, content):
            results["warnings"].append({
                "category": "debug-output",
                "severity": "warning",
                "file": rel_path,
                "line": line_at(content, m.start()),
                "tag": tag,
                "message": "Debug output left in production code",
            })

    # 3. Hex hardcoded hors theme.css
    if not is_theme_css and re.search(r"\.(css|scss|razor|tsx|jsx|vue)$", rel_path):
        for m in re.finditer(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b", content):
            results["warnings"].append({
                "category": "hardcoded-hex",
                "severity": "warning",
                "file": rel_path,
                "line": line_at(content, m.start()),
                "tag": "hex-outside-theme",
                "message": f"Hex value {m.group(0)} hardcoded outside theme.css - use CSS var or token",
            })

    # 4. Long methods (heuristic)
    if re.search(r"\.(cs|kt|ts|tsx|js|jsx|py)$", rel_path):
        for pat in METHOD_PATTERNS:
            for m in re.finditer(pat, content):
                start_line = line_at(content, m.start())
                remaining = content[m.start():]
                method_lines = remaining.split("\n")[:100]
                depth = 0
                started = False
                close_line = -1
                for i, line in enumerate(method_lines):
                    if "{" in line:
                        depth += 1
                        started = True
                    if "}" in line:
                        depth -= 1
                        if started and depth <= 0:
                            close_line = i
                            break
                if close_line > 50:
                    results["warnings"].append({
                        "category": "long-method",
                        "severity": "warning",
                        "file": rel_path,
                        "line": start_line,
                        "tag": "method-over-50-lines",
                        "message": f"Method spans approximately {close_line} lines - consider refactoring",
                    })

    # 5. Commented-out code blocks
    if re.search(r"\.(cs|kt|ts|tsx|js|jsx|py|razor)$", rel_path):
        lines = content.split("\n")
        block_count = 0
        block_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            is_comment = bool(
                re.match(r"^\s*//", line)
                or re.match(r"^\s*#", line)
                or re.match(r"^\s*\*", line)
                or re.match(r"^\s*<!--", line)
            )
            has_content = bool(re.search(r"\b\w+\s*[\(\=\;\.]", stripped))
            if is_comment and has_content:
                if block_count == 0:
                    block_start = i + 1
                block_count += 1
            else:
                if block_count >= 5:
                    results["info"].append({
                        "category": "commented-code",
                        "severity": "info",
                        "file": rel_path,
                        "line": block_start,
                        "tag": "commented-out-code",
                        "message": f"Block of {block_count} commented-out code lines - consider removing",
                    })
                block_count = 0

    # 6. Magic numbers (heuristic)
    if re.search(r"\.(cs|kt|ts|tsx|js|jsx|py)$", rel_path):
        reported: set[str] = set()
        for m in re.finditer(r"[^_a-zA-Z0-9]([0-9]{3,})[^_a-zA-Z0-9]", content):
            val = m.group(1)
            line_n = line_at(content, m.start())
            key = f"{rel_path}::{line_n}"
            if key in reported:
                continue
            reported.add(key)
            if MAGIC_NUMBER_SKIP.match(val):
                continue
            results["info"].append({
                "category": "magic-number",
                "severity": "info",
                "file": rel_path,
                "line": line_n,
                "tag": "literal-numeric",
                "message": f"Magic number '{val}' - consider extracting to a named constant",
            })


def main() -> int:
    args = parse_args()
    root = repo_root()
    src_dir = root / "workspace" / "output" / "src"

    if not src_dir.is_dir():
        print(f"Source directory not found: {src_dir}")
        print("Skipping quality scan (no code to analyze).")
        return 0

    source_files: list[Path] = []
    for ext in SOURCE_EXTENSIONS:
        for f in src_dir.rglob(f"*{ext}"):
            if not f.is_file():
                continue
            rel = normalize(f.relative_to(root))
            if is_excluded(rel):
                continue
            source_files.append(f)

    if not source_files:
        print("No source files found to scan.")
        return 0

    results: dict[str, list] = {"errors": [], "warnings": [], "info": []}

    for f in source_files:
        rel = normalize(f.relative_to(root))
        scan_file(f, rel, results)

    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_issues = results["errors"] + results["warnings"] + results["info"]

    # Write to console.db (single source of truth) — replaces former quality.json.
    ensure_initialized()
    with connect() as conn:
        replace_qa_quality_for_feat(conn, args.feat_number)
        insert_qa_quality_batch(
            conn, feat_n=args.feat_number, extracted_at=extracted_at,
            issues=all_issues,
        )

    print("Quality scan complete:")
    print(f"  Files scanned : {len(source_files)}")
    print(f"  Errors        : {len(results['errors'])}")
    print(f"  Warnings      : {len(results['warnings'])}")
    print(f"  Info          : {len(results['info'])}")
    print(f"  Target        : console.db (table qa_quality), feat_n={args.feat_number}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
