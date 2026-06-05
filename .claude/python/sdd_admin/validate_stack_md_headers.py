#!/usr/bin/env python3
"""SDD_Pro — validate Status: + Validation: headers on all stack .md files.

The agents (po, arch, dev-*) read these headers to decide :
  - `Status:` (Draft / Stable / Deprecated) — show maturity to Tech Lead
  - `Validation: 🟢 reference | 🟡 experimental | 🔴 deprecated` — drives
    `phase_planner.py` warnings when a "🟡 experimental" stack is used in
    production runs.

Headers MUST appear as **top-level lines** (not buried in a `> blockquote`).
A blockquoted `> Validation: ...` was the v6 convention but was rejected
in v7.0.0-alpha because some scripts greped for `^Validation:` and missed
those. This validator catches the drift.

Exit codes (sdd_lib/exit_codes.py) :
  0 SUCCESS       — all stacks have both headers (strict mode passes)
  1 FAIL_FAST     — at least one stack missing Status: OR Validation:
  3 INFRA_BLOCKED — stacks/ directory unreadable

Usage :
  python validate_stack_md_headers.py            # human-friendly report
  python validate_stack_md_headers.py --json     # JSON output (CI)
  python validate_stack_md_headers.py --strict   # exit 1 if any MISS

Scope :
  - .claude/stacks/{backend,frontend,ui,qa,auth,archi,fullstack,mobiles}/*.md
  - All stacks under .claude/stacks/ are considered active since v7.0.0+
    rollback of the _drafts/ quarantine mechanism.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows : the report contains 🟢/🟡/🔴
# badges which crash on cp1252 default encoding when invoked without
# `PYTHONIOENCODING=utf-8` (e.g. from framework_smoke without env override).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import SUCCESS, FAIL_FAST, INFRA_BLOCKED  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402


# Validation badges allowed in v7.0.0 — drift detector for typos
VALID_BADGES = ("🟢", "🟡", "🔴")

# v7.0.0-alpha (audit MIN-10, 2026-06-04) — `Validation:` header has 3
# coexisting syntaxes observed in the wild :
#   (a) `Validation: 🟢 reference (note)`         — TOP-LEVEL, canonical, this validator enforces
#   (b) `validation: experimental` (YAML META)    — lowercase, indented, accepted by preflight.py
#   (c) `> Validation: ...` (blockquote)          — rejected by this validator
# A future v7.1 cleanup could unify to a single format ; for v7.0.0 we
# tolerate (b) in legacy stacks to avoid mass-migration risk.
STATUS_RE = re.compile(r"^Status\s*:\s*(\S+)", re.M)
VALIDATION_RE = re.compile(r"^Validation\s*:\s*(\S+)", re.M)
BLOCKQUOTED_VALIDATION_RE = re.compile(r"^\s*>\s*Validation\s*:", re.M)


def find_stack_files(repo: Path) -> list[Path]:
    """Return all active stack .md files under .claude/stacks/.

    Excludes the top-level README.md (not a stack file). All category
    subdirectories are considered active since the v7.0.0+ rollback of
    the _drafts/ quarantine mechanism.
    """
    stacks_dir = repo / ".claude" / "stacks"
    if not stacks_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(stacks_dir.glob("**/*.md")):
        if p.parent == stacks_dir:
            continue
        out.append(p)
    return out


def audit_file(path: Path) -> dict:
    """Return {has_status, has_validation, blockquoted, badge, category}."""
    try:
        # Only inspect the head (first ~1 KB) — headers are always near top
        text = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError as e:
        return {
            "category": path.parent.name,
            "stack": path.stem,
            "error": str(e),
        }
    status_m = STATUS_RE.search(text)
    validation_m = VALIDATION_RE.search(text)
    blockquoted = bool(BLOCKQUOTED_VALIDATION_RE.search(text))
    badge = None
    if validation_m:
        # `Validation: 🟢 reference (...)`  →  badge = "🟢"
        badge_match = re.search(r"^Validation\s*:\s*(🟢|🟡|🔴)", text, re.M)
        badge = badge_match.group(1) if badge_match else "INVALID"
    return {
        "category":          path.parent.name,
        "stack":             path.stem,
        "has_status":        status_m is not None,
        "has_validation":    validation_m is not None,
        "blockquoted_only":  blockquoted and validation_m is None,
        "badge":             badge,
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Validate Status: + Validation: headers on stack .md files."
    )
    p.add_argument("--json", action="store_true", help="emit JSON output")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 if any stack is missing a header")
    args = p.parse_args()

    repo = repo_root()
    files = find_stack_files(repo)
    if not files:
        sys.stderr.write(f"ERROR: no stacks found under {repo}/.claude/stacks/\n")
        return INFRA_BLOCKED

    findings: list[dict] = []
    missing_status = 0
    missing_validation = 0
    blockquoted_only = 0
    invalid_badge = 0

    for path in files:
        r = audit_file(path)
        r["path"] = str(path.relative_to(repo)).replace("\\", "/")
        findings.append(r)
        if "error" in r:
            continue
        if not r["has_status"]:
            missing_status += 1
        if not r["has_validation"]:
            missing_validation += 1
        if r["blockquoted_only"]:
            blockquoted_only += 1
        if r["badge"] not in (None, "INVALID") and r["badge"] not in VALID_BADGES:
            invalid_badge += 1
        elif r["badge"] == "INVALID":
            invalid_badge += 1

    report = {
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stacks_count": len(files),
        "summary": {
            "missing_status": missing_status,
            "missing_validation": missing_validation,
            "blockquoted_only": blockquoted_only,
            "invalid_badge": invalid_badge,
            "ok": sum(
                1 for f in findings
                if "error" not in f
                and f["has_status"]
                and f["has_validation"]
                and f["badge"] in VALID_BADGES
            ),
        },
        "findings": findings,
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print()
        print("=== Stack headers audit ===")
        print(f"Scanned : {len(files)} stack(s)")
        s = report["summary"]
        print(f"OK                : {s['ok']}")
        print(f"Missing Status:   : {s['missing_status']}")
        print(f"Missing Validation: {s['missing_validation']}")
        print(f"Blockquoted only  : {s['blockquoted_only']} (legacy v6 format — must be top-level)")
        print(f"Invalid badge     : {s['invalid_badge']} (not 🟢/🟡/🔴)")
        bad = [f for f in findings
               if "error" not in f
               and (not f["has_status"]
                    or not f["has_validation"]
                    or f["blockquoted_only"]
                    or (f["badge"] not in (None, *VALID_BADGES)))]
        if bad:
            print()
            print("Issues :")
            for f in bad:
                issues = []
                if not f["has_status"]:
                    issues.append("missing Status:")
                if not f["has_validation"]:
                    issues.append("missing Validation:")
                if f["blockquoted_only"]:
                    issues.append("Validation: only in blockquote")
                if f["badge"] not in (None, *VALID_BADGES):
                    issues.append(f"invalid badge {f['badge']!r}")
                print(f"  [{f['category']:8s}] {f['stack']:24s}  → {', '.join(issues)}")
        else:
            print()
            print("[OK] All stacks have valid headers.")

    has_problems = (missing_status + missing_validation
                    + blockquoted_only + invalid_badge) > 0
    if args.strict and has_problems:
        return FAIL_FAST
    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
