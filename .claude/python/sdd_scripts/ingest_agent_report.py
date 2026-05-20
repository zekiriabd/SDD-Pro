#!/usr/bin/env python3
"""SDD_Pro v6.10 — Ingest LLM agent reports into console.db.

Bridge between LLM auditor agents (which produce structured JSON) and
the SQLite source-of-truth. After the agent finishes, this script:
    1. reads the JSON report
    2. inserts the parsed entries into the appropriate qa_* table
    3. deletes the JSON file (no stats/logs persist on FS)

Supported report types:
    - a11y           → qa_a11y                (workspace/output/qa/feat-{n}/a11y-report.json)
    - code-review    → qa_code_review         (workspace/output/.sys/.validation/{n}-code-review.json)
    - security-scan  → qa_security (mode=scan)         (workspace/output/.sys/.validation/{n}-security-scan.json)
    - threat-model   → qa_security (mode=threat-model) (workspace/output/.sys/.validation/{n}-threat-model.json)
    - performance    → qa_performance         (workspace/output/qa/feat-{n}/perf-report.json)
    - spec-compliance→ qa_spec_compliance     (workspace/output/.sys/.validation/{n}-spec-compliance.json)
    - api-tests      → qa_api_tests (+ qa_api_endpoints)  (workspace/output/qa/feat-{n}/api-tests.json)

Usage:
    python -m sdd_scripts.ingest_agent_report --type a11y --feat 1
    python -m sdd_scripts.ingest_agent_report --type code-review --feat 1 --keep-json
    python -m sdd_scripts.ingest_agent_report --type security-scan --feat 1 --path /custom/path.json

By default the source JSON is DELETED after a successful ingest.
Use --keep-json to retain it (debugging only).

Exit codes:
    0 = ingest succeeded
    1 = report file missing
    2 = JSON parse error
    3 = unsupported report type / unknown schema
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import (  # noqa: E402
    connect, ensure_initialized,
    insert_qa_a11y_batch, insert_qa_code_review_batch,
    insert_qa_security_batch, insert_qa_performance_batch,
    insert_qa_spec_compliance_batch, insert_qa_api_tests,
    replace_qa_auditor_for_feat, replace_qa_api_tests_for_feat,
)
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


REPORT_TYPES = (
    "a11y", "code-review", "security-scan", "threat-model",
    "performance", "spec-compliance", "api-tests",
    "arch-review",
)


def default_path(report_type: str, feat: int, root: Path) -> Path:
    """Canonical path per report type (matches the conventions the agents use)."""
    qa = root / "workspace" / "output" / "qa" / f"feat-{feat}"
    val = root / "workspace" / "output" / ".sys" / ".validation"
    mapping = {
        "a11y":            qa / "a11y-report.json",
        "code-review":     val / f"{feat}-code-review.json",
        "security-scan":   val / f"{feat}-security-scan.json",
        "threat-model":    val / f"{feat}-threat-model.json",
        "performance":     qa / "perf-report.json",
        "spec-compliance": val / f"{feat}-spec-compliance.json",
        "api-tests":       qa / "api-tests.json",
        "arch-review":     val / f"{feat}-arch-review.json",
    }
    return mapping[report_type]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(_err_block(
            "ingest_agent_report: JSON parse error",
            f"[QA_OUTPUT_INVALID] {path}: {e.msg} (line {e.lineno})",
            "regenerate the report or fix the JSON manually",
            code=2,
        ))


def _err_block(error: str, cause: str, fix: str, code: int = 1) -> str:
    sys.stderr.write(f"ERROR: {error}\nCAUSE: {cause}\nFIX: {fix}\n")
    return ""  # SystemExit picks up the int passed below


def _verdict_of(report: dict) -> str | None:
    """Best-effort: agents tag a verdict (green/warn/red) at summary or root."""
    s = report.get("summary") or {}
    return s.get("verdict") or report.get("verdict")


def _flatten_issues(node: Any) -> list[dict[str, Any]]:
    """Flatten the auditor nested-issues shape (`{severity: {items: [...]}}`) into
    a single list. If the node is already a list, return it. The severity from
    the outer key is injected into each item when the items themselves don't
    expose it."""
    if isinstance(node, list):
        return [it for it in node if isinstance(it, dict)]
    if not isinstance(node, dict):
        return []
    out: list[dict[str, Any]] = []
    # Recognize the canonical {critical|serious|moderate|minor} shape
    severities = ("critical", "serious", "moderate", "minor")
    if any(k in node for k in severities):
        for sev in severities:
            block = node.get(sev)
            if not isinstance(block, dict):
                continue
            items = block.get("items") or []
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                it = dict(it)
                it.setdefault("severity", sev)
                out.append(it)
        return out
    # Fallback: collect any nested list of dicts.
    for v in node.values():
        if isinstance(v, list):
            out.extend(it for it in v if isinstance(it, dict))
        elif isinstance(v, dict):
            out.extend(_flatten_issues(v))
    return out


def ingest_a11y(report: dict, feat: int) -> int:
    issues = _flatten_issues(report.get("issues") or report.get("findings"))
    verdict = _verdict_of(report)
    with connect() as conn:
        replace_qa_auditor_for_feat(conn, "qa_a11y", feat)
        return insert_qa_a11y_batch(conn, feat_n=feat, verdict=verdict, issues=issues)


def ingest_code_review(report: dict, feat: int) -> int:
    issues = _flatten_issues(report.get("issues") or report.get("findings"))
    verdict = _verdict_of(report)
    with connect() as conn:
        replace_qa_auditor_for_feat(conn, "qa_code_review", feat)
        return insert_qa_code_review_batch(conn, feat_n=feat, verdict=verdict, issues=issues)


def ingest_security(report: dict, feat: int, mode: str) -> int:
    """mode = 'scan' | 'threat-model'."""
    if mode == "threat-model":
        # threats live at root in a flat list
        raw = report.get("threats") or report.get("findings") or []
        issues = [it for it in raw if isinstance(it, dict)]
        # Map STRIDE category -> stride column
        for it in issues:
            if "category" in it and "stride" not in it:
                it["stride"] = it["category"]
            it.setdefault("issue_class", f"SEC_THREAT_{(it.get('id') or 'UNK').upper()}")
            it.setdefault("severity", "moderate")
            it.setdefault("message", it.get("scenario") or it.get("description"))
    else:
        issues = _flatten_issues(report.get("issues") or report.get("findings"))
    verdict = _verdict_of(report)
    with connect() as conn:
        replace_qa_auditor_for_feat(conn, "qa_security", feat, mode=mode)
        return insert_qa_security_batch(conn, feat_n=feat, mode=mode, verdict=verdict, issues=issues)


def ingest_performance(report: dict, feat: int) -> int:
    issues = _flatten_issues(report.get("issues") or report.get("findings"))
    verdict = _verdict_of(report)
    with connect() as conn:
        replace_qa_auditor_for_feat(conn, "qa_performance", feat)
        return insert_qa_performance_batch(conn, feat_n=feat, verdict=verdict, issues=issues)


def ingest_spec_compliance(report: dict, feat: int) -> int:
    """Flatten us[].acs[] into one row per AC."""
    rows: list[dict[str, Any]] = []
    for us in (report.get("us") or []):
        us_id = us.get("us_id")
        if not us_id:
            continue
        for ac in (us.get("acs") or []):
            ev = ac.get("evidence") or {}
            rows.append({
                "us_id":         us_id,
                "ac_id":         ac.get("ac_id"),
                "verdict":       ac.get("status"),
                "severity":      ac.get("severity"),
                "evidence_file": ev.get("file"),
                "evidence_line": (ev.get("lines") or [None])[0]
                                  if isinstance(ev.get("lines"), list) else ev.get("line"),
                "message":       ac.get("ac_text"),
            })
    with connect() as conn:
        replace_qa_auditor_for_feat(conn, "qa_spec_compliance", feat)
        return insert_qa_spec_compliance_batch(conn, feat_n=feat, entries=rows)


def ingest_api_tests(report: dict, feat: int) -> int:
    summary = report.get("summary") or {}
    endpoints = report.get("endpoints") or []
    # Support both schema variants ('passed'/'failed' or 'tests_passed'/'tests_failed')
    tests_passed = int(summary.get("tests_passed", summary.get("passed", 0)) or 0)
    tests_failed = int(summary.get("tests_failed", summary.get("failed", 0)) or 0)
    with connect() as conn:
        replace_qa_api_tests_for_feat(conn, feat)
        insert_qa_api_tests(
            conn, feat_n=feat,
            gate_passed=bool(summary.get("gate_passed", False)),
            endpoints_total=int(summary.get("endpoints_total", len(endpoints))),
            tests_total=int(summary.get("tests_total", 0)),
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            endpoints=endpoints,
        )
    return len(endpoints)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingest_agent_report",
        description="Ingest LLM agent JSON report into console.db, then delete JSON.",
    )
    parser.add_argument("--type", required=True, choices=REPORT_TYPES)
    parser.add_argument("--feat", type=int, required=True)
    parser.add_argument("--path", type=Path, default=None,
                        help="Override default JSON path for this report type")
    parser.add_argument("--keep-json", action="store_true",
                        help="Do not delete the JSON after successful ingest")
    args = parser.parse_args(argv)

    root = repo_root()
    path = args.path or default_path(args.type, args.feat, root)

    if not path.is_file():
        sys.stderr.write(
            f"ERROR: ingest_agent_report: report not found\n"
            f"CAUSE: [QA_PRECONDITION_FAILED] {path}\n"
            f"FIX: ensure the agent {args.type} wrote its JSON before ingest\n"
        )
        return 1

    ensure_initialized()
    try:
        report = _load_json(path)
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 2

    if not isinstance(report, dict):
        sys.stderr.write(
            "ERROR: ingest_agent_report: report must be a JSON object\n"
            f"CAUSE: [QA_OUTPUT_INVALID] root is not an object in {path}\n"
            "FIX: regenerate the report\n"
        )
        return 3

    try:
        if args.type == "a11y":
            n = ingest_a11y(report, args.feat)
        elif args.type == "code-review":
            n = ingest_code_review(report, args.feat)
        elif args.type == "security-scan":
            n = ingest_security(report, args.feat, mode="scan")
        elif args.type == "threat-model":
            n = ingest_security(report, args.feat, mode="threat-model")
        elif args.type == "performance":
            n = ingest_performance(report, args.feat)
        elif args.type == "spec-compliance":
            n = ingest_spec_compliance(report, args.feat)
        elif args.type == "api-tests":
            n = ingest_api_tests(report, args.feat)
        elif args.type == "arch-review":
            # arch-reviewer writes into qa_code_review with ARCH_* issue_class
            # (reuses existing table, distinguishable via WHERE issue_class LIKE 'ARCH_%')
            n = ingest_code_review(report, args.feat)
        else:
            sys.stderr.write(f"ERROR: unsupported type {args.type}\n")
            return 3
    except Exception as exc:
        sys.stderr.write(
            "ERROR: ingest_agent_report: DB insert failed\n"
            f"CAUSE: [QA_OUTPUT_INVALID] {exc}\n"
            "FIX: inspect the JSON schema vs DB expected fields\n"
        )
        return 3

    if not args.keep_json:
        try:
            path.unlink()
        except OSError as exc:
            warn(f"WARN: ingested but failed to delete {path}: {exc}")

    print(f"OK ingest_agent_report: type={args.type} feat={args.feat} rows={n} "
          f"({'kept' if args.keep_json else 'deleted'}: {path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
