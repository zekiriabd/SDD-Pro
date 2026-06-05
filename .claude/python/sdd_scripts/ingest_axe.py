#!/usr/bin/env python3
"""SDD_Pro v7.2.0 — Ingest axe-core JSON (CI artifact) into console.db.qa_a11y.

CI ingest bridge for the accessibility-auditor agent retired in v7.0.0
(`governance-major-auditors-trim`). The class taxonomy `[A11Y_*]` and the
qa_a11y table schema were intentionally preserved for this purpose
(cf. `rules/error-classification-legacy.md §1`).

Pipeline:
    .github/workflows/quality.yml
        └─ npx @axe-core/cli  →  axe-report.json
            └─ python .claude/python/sdd_scripts/ingest_axe.py
                 --report axe-report.json --feat {n}
                  └─ map axe.violations[] → [A11Y_*] classes
                  └─ insert into qa_a11y
                  └─ record_auditor_run(auditor='a11y', verdict)

Usage:
    python -m sdd_scripts.ingest_axe --report axe-report.json --feat 1
    python -m sdd_scripts.ingest_axe --report axe-report.json --feat 1 --json
    python -m sdd_scripts.ingest_axe --report axe-report.json --feat 1 --threshold serious

Exit codes (per `sdd_lib.exit_codes` conventions):
    0 = ingest succeeded (verdict green or warn — non-bloquant)
    1 = report file missing or unreadable
    2 = JSON parse error
    3 = unsupported axe schema (e.g. v3 legacy, malformed)
    4 = ingest succeeded but verdict RED (≥1 violation ≥ threshold)

Exit 4 is the gating signal for CI: a project that wants A11yFailOn to
block PRs sets `continue-on-error: false` on the workflow step. Use
`--no-fail` to coerce exit 0 even on RED (telemetry-only mode).

Read-only on the source JSON by default (CI artifact, kept for upload).
Pass `--delete-json` to mimic ingest_agent_report behavior.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import (  # noqa: E402
    connect, ensure_initialized,
    insert_qa_a11y_batch, record_auditor_run,
    replace_qa_auditor_for_feat,
)
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.exit_codes import SUCCESS  # noqa: E402

# ============================================================
# axe-core rule id → SDD [A11Y_*] class mapping
# ============================================================
# Severity sourced from axe `impact` field, but we override for the
# canonical 10 classes to keep parity with the legacy auditor.
# WCAG inferred from `tags[]` when no specific class match.

# rule_id → (issue_class, default_severity, wcag)
AXE_RULE_MAP: dict[str, tuple[str, str, str]] = {
    # 1.1.1 — Images
    "image-alt":                 ("A11Y_MISSING_ALT",       "critical", "1.1.1"),
    "image-redundant-alt":       ("A11Y_MISSING_ALT",       "moderate", "1.1.1"),
    "input-image-alt":           ("A11Y_MISSING_ALT",       "critical", "1.1.1"),
    "area-alt":                  ("A11Y_MISSING_ALT",       "critical", "1.1.1"),
    "role-img-alt":              ("A11Y_MISSING_ALT",       "serious",  "1.1.1"),
    "svg-img-alt":               ("A11Y_MISSING_ALT",       "serious",  "1.1.1"),

    # 1.3.1 — Form labels & heading order
    "label":                     ("A11Y_INPUT_NO_LABEL",    "critical", "1.3.1"),
    "label-title-only":          ("A11Y_INPUT_NO_LABEL",    "serious",  "1.3.1"),
    "form-field-multiple-labels": ("A11Y_INPUT_NO_LABEL",   "moderate", "1.3.1"),
    "select-name":               ("A11Y_INPUT_NO_LABEL",    "critical", "1.3.1"),
    "heading-order":             ("A11Y_HEADING_SKIP",      "moderate", "1.3.1"),
    "empty-heading":             ("A11Y_HEADING_SKIP",      "minor",    "1.3.1"),
    "p-as-heading":              ("A11Y_HEADING_SKIP",      "serious",  "1.3.1"),

    # 2.4.3 — Tabindex / focus order
    "tabindex":                  ("A11Y_TABINDEX_POSITIVE", "serious",  "2.4.3"),
    "focus-order-semantics":     ("A11Y_TABINDEX_POSITIVE", "moderate", "2.4.3"),

    # 2.4.6 — Buttons / links accessible names
    "button-name":               ("A11Y_BUTTON_NO_LABEL",   "serious",  "2.4.6"),
    "link-name":                 ("A11Y_BUTTON_NO_LABEL",   "serious",  "2.4.6"),
    "input-button-name":         ("A11Y_BUTTON_NO_LABEL",   "serious",  "2.4.6"),
    "frame-title":               ("A11Y_BUTTON_NO_LABEL",   "serious",  "2.4.6"),

    # 3.1.1 — Page language
    "html-has-lang":             ("A11Y_LANG_MISSING",      "serious",  "3.1.1"),
    "html-lang-valid":           ("A11Y_LANG_MISSING",      "serious",  "3.1.1"),
    "html-xml-lang-mismatch":    ("A11Y_LANG_MISSING",      "moderate", "3.1.1"),
    "valid-lang":                ("A11Y_LANG_MISSING",      "serious",  "3.1.1"),

    # 3.3.2 — Form submit / labeling
    "form-submit":               ("A11Y_FORM_NO_SUBMIT",    "moderate", "3.3.2"),

    # 4.1.2 — ARIA / roles
    "aria-allowed-attr":         ("A11Y_ROLE_INCOMPLETE",   "serious",  "4.1.2"),
    "aria-allowed-role":         ("A11Y_ROLE_INCOMPLETE",   "moderate", "4.1.2"),
    "aria-required-attr":        ("A11Y_ROLE_INCOMPLETE",   "critical", "4.1.2"),
    "aria-required-children":    ("A11Y_ROLE_INCOMPLETE",   "critical", "4.1.2"),
    "aria-required-parent":      ("A11Y_ROLE_INCOMPLETE",   "critical", "4.1.2"),
    "aria-roles":                ("A11Y_ROLE_INCOMPLETE",   "serious",  "4.1.2"),
    "aria-valid-attr":           ("A11Y_ROLE_INCOMPLETE",   "critical", "4.1.2"),
    "aria-valid-attr-value":     ("A11Y_ROLE_INCOMPLETE",   "critical", "4.1.2"),
    "aria-hidden-focus":         ("A11Y_ROLE_INCOMPLETE",   "serious",  "4.1.2"),
    "aria-hidden-body":          ("A11Y_ROLE_INCOMPLETE",   "critical", "4.1.2"),
    "aria-input-field-name":     ("A11Y_ROLE_INCOMPLETE",   "serious",  "4.1.2"),
    "aria-toggle-field-name":    ("A11Y_ROLE_INCOMPLETE",   "serious",  "4.1.2"),
    "aria-command-name":         ("A11Y_ROLE_INCOMPLETE",   "serious",  "4.1.2"),
    "role-img-alt":              ("A11Y_ROLE_INCOMPLETE",   "serious",  "4.1.2"),

    # 4.1.3 — Status messages / live regions
    "aria-live-region":          ("A11Y_STATUS_NO_LIVE",    "moderate", "4.1.3"),

    # 2.5.5 — Target size (WCAG 2.2)
    "target-size":               ("A11Y_TARGET_TOO_SMALL",  "moderate", "2.5.5"),
}

# Severity ordinal — sort highest first; threshold compares >=.
SEVERITY_RANK: dict[str, int] = {
    "critical": 4, "serious": 3, "moderate": 2, "minor": 1,
}

DEFAULT_THRESHOLD = "serious"   # matches legacy A11yFailOn default

# WCAG SC tag : `wcag<P><G><C[C]>` where P=principle (1..4), G=guideline
# (single digit — WCAG 2.x has ≤9 guidelines per principle), C=criterion
# (1-2 digits). Examples: `wcag111` → 1.1.1, `wcag143` → 1.4.3,
# `wcag2510` → 2.5.10. Version tags like `wcag22aa` deliberately don't
# match (extra non-digit suffix); they describe conformance level, not SC.
WCAG_TAG_RE = re.compile(r"^wcag(\d)(\d)(\d{1,2})?$")


def _err(error: str, cause: str, fix: str, code: int) -> int:
    sys.stderr.write(f"ERROR: {error}\nCAUSE: {cause}\nFIX: {fix}\n")
    return code


def _infer_wcag_from_tags(tags: list[str]) -> str | None:
    """Extract a WCAG SC number (e.g. '1.1.1') from axe tags like 'wcag111'."""
    for tag in tags or []:
        m = WCAG_TAG_RE.match(str(tag).lower())
        if not m:
            continue
        parts = [m.group(1), m.group(2)]
        if m.group(3):
            parts.append(m.group(3))
        return ".".join(parts)
    return None


def _classify_violation(rule_id: str, axe_impact: str | None,
                        tags: list[str]) -> tuple[str, str, str | None]:
    """Return (issue_class, severity, wcag) for one axe violation."""
    if rule_id in AXE_RULE_MAP:
        cls, sev, wcag = AXE_RULE_MAP[rule_id]
        return cls, sev, wcag

    # Fallback: preserve rule id as suffix, use axe impact, infer WCAG from tags
    safe_id = re.sub(r"[^a-zA-Z0-9]", "_", rule_id).upper()
    cls = f"A11Y_RULE_{safe_id}"
    sev = (axe_impact or "moderate").lower()
    if sev not in SEVERITY_RANK:
        sev = "moderate"
    wcag = _infer_wcag_from_tags(tags)
    return cls, sev, wcag


def _node_target(node: dict[str, Any]) -> str | None:
    """Extract a CSS selector path from an axe node (best-effort)."""
    target = node.get("target")
    if isinstance(target, list) and target:
        # axe target can be nested arrays for iframe descent
        flat: list[str] = []
        for t in target:
            if isinstance(t, list):
                flat.extend(str(x) for x in t)
            else:
                flat.append(str(t))
        return " >> ".join(flat) if flat else None
    if isinstance(target, str):
        return target
    return None


def parse_axe_report(report: Any) -> list[dict[str, Any]]:
    """Normalize axe-core JSON (CLI: list[result], API: single result) into a
    flat list of issue dicts compatible with insert_qa_a11y_batch."""
    if isinstance(report, list):
        results = report
    elif isinstance(report, dict):
        results = [report]
    else:
        raise ValueError("axe report must be a JSON object or array of objects")

    issues: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        url = result.get("url") or ""
        violations = result.get("violations") or []
        if not isinstance(violations, list):
            continue

        for v in violations:
            if not isinstance(v, dict):
                continue
            rule_id = v.get("id") or "unknown"
            axe_impact = v.get("impact")
            tags = v.get("tags") or []
            cls, sev, wcag = _classify_violation(rule_id, axe_impact, tags)
            help_text = (v.get("help") or v.get("description") or "").strip()

            nodes = v.get("nodes") or []
            if not isinstance(nodes, list) or not nodes:
                # No nodes → still record a single row (URL-level issue)
                issues.append({
                    "issue_class": cls,
                    "severity":    sev,
                    "wcag":        wcag,
                    "file_path":   url or None,
                    "line":        None,
                    "message":     f"{rule_id}: {help_text}".strip(": "),
                })
                continue

            for node in nodes:
                if not isinstance(node, dict):
                    continue
                target = _node_target(node)
                fail_summary = (node.get("failureSummary") or "").strip()
                msg_parts = [rule_id]
                if help_text:
                    msg_parts.append(help_text)
                if target:
                    msg_parts.append(f"@{target}")
                if fail_summary:
                    # Keep summary short — first line only
                    first_line = fail_summary.splitlines()[0].strip()
                    if first_line:
                        msg_parts.append(first_line)
                issues.append({
                    "issue_class": cls,
                    "severity":    sev,
                    "wcag":        wcag,
                    "file_path":   url or target,
                    "line":        None,
                    "message":     " — ".join(msg_parts),
                })
    return issues


def compute_verdict(issues: list[dict[str, Any]], threshold: str) -> str:
    """Return 'green' | 'warn' | 'red' for the issue set vs threshold."""
    if not issues:
        return "green"
    thr_rank = SEVERITY_RANK.get(threshold.lower(), SEVERITY_RANK[DEFAULT_THRESHOLD])
    for it in issues:
        sev = (it.get("severity") or "moderate").lower()
        if SEVERITY_RANK.get(sev, 0) >= thr_rank:
            return "red"
    return "warn"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingest_axe",
        description="Ingest axe-core JSON report into console.db qa_a11y.",
    )
    parser.add_argument("--report", type=Path, required=True,
                        help="Path to axe-core JSON artifact (CI output)")
    parser.add_argument("--feat", type=int, required=True,
                        help="FEAT number this scan is associated with")
    parser.add_argument("--threshold", default=DEFAULT_THRESHOLD,
                        choices=tuple(SEVERITY_RANK.keys()),
                        help=f"Severity gate (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--no-fail", action="store_true",
                        help="Always exit 0 (telemetry-only mode, no CI gating)")
    parser.add_argument("--delete-json", action="store_true",
                        help="Delete source JSON after successful ingest "
                             "(default: keep — CI artifact)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON summary on stdout instead of human text")
    args = parser.parse_args(argv)

    path = args.report
    if not path.is_absolute():
        path = (repo_root() / path).resolve()

    if not path.is_file():
        return _err(
            "ingest_axe: axe-core report not found",
            f"[QA_PRECONDITION_FAILED] {path}",
            "ensure the axe-core CI step ran and wrote --save axe-report.json",
            code=1,
        )

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return _err(
            "ingest_axe: JSON parse error",
            f"[QA_OUTPUT_INVALID] {path}: {e.msg} (line {e.lineno})",
            "regenerate axe-report.json (the CI artifact may be truncated)",
            code=2,
        )

    try:
        issues = parse_axe_report(report)
    except ValueError as exc:
        return _err(
            "ingest_axe: unsupported axe schema",
            f"[QA_OUTPUT_INVALID] {path}: {exc}",
            "ensure axe-core CLI version ≥ 4.x (JSON shape: array of results)",
            code=3,
        )

    verdict = compute_verdict(issues, args.threshold)

    ensure_initialized()
    with connect() as conn:
        replace_qa_auditor_for_feat(conn, "qa_a11y", args.feat)
        n = insert_qa_a11y_batch(conn, feat_n=args.feat, verdict=verdict,
                                 issues=issues)
        record_auditor_run(
            conn, feat_n=args.feat, auditor="a11y",
            findings_count=n, verdict=verdict,
            payload={"source": "axe-core", "report": str(path),
                     "threshold": args.threshold},
        )

    if args.delete_json:
        try:
            path.unlink()
        except OSError:
            pass  # non-fatal — telemetry already persisted

    summary = {
        "feat":       args.feat,
        "source":     "axe-core",
        "report":     str(path),
        "issues":     n,
        "verdict":    verdict,
        "threshold":  args.threshold,
    }
    if args.json:
        sys.stdout.write(json.dumps(summary) + "\n")
    else:
        sys.stdout.write(
            f"OK ingest_axe: feat={args.feat} issues={n} verdict={verdict} "
            f"(threshold={args.threshold})\n"
        )

    if verdict == "red" and not args.no_fail:
        return 4
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
