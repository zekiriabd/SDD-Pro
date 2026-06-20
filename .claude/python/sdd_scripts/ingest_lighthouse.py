#!/usr/bin/env python3
"""SDD_Pro v7.2.0 — Ingest Lighthouse JSON (CI artifact) into console.db.qa_performance.

CI ingest bridge for the performance-auditor agent retired in v7.0.0
(`governance-major-auditors-trim`). The class taxonomy `[PERF_*]` and the
qa_performance table schema were intentionally preserved for this
purpose (cf. `rules/error-classification-legacy.md §2`).

Pipeline:
    .github/workflows/quality.yml
        └─ npx @lhci/cli collect → .lighthouseci/lhr-*.json (N runs)
            └─ python .claude/python/sdd_scripts/ingest_lighthouse.py
                 --report .lighthouseci/ --feat {n}
                  └─ resolve LHR file(s) — pick median or aggregate
                  └─ extract Core Web Vitals + selected audits
                  └─ map to [PERF_*] classes against thresholds
                  └─ insert into qa_performance
                  └─ record_auditor_run(auditor='perf', verdict)

The script accepts either a single Lighthouse Result (LHR) JSON file
OR a directory containing one or more `lhr-*.json` files (the layout
produced by `lhci collect`). When multiple runs are present, metrics
are taken from the median run as recommended by Lighthouse CI.

Usage:
    python -m sdd_scripts.ingest_lighthouse --report lhr.json --feat 1
    python -m sdd_scripts.ingest_lighthouse --report .lighthouseci/ --feat 1
    python -m sdd_scripts.ingest_lighthouse --report lhr.json --feat 1 --json

Thresholds (default values from legacy `error-classification-legacy.md §2`):
    --lcp-ms      2500     LCP critical above
    --cls         0.10     CLS serious above
    --inp-ms      200      INP serious above
    --ttfb-ms     600      Server response time serious above
    --bundle-kb   1500     JS bundle size serious above (raw, not gzipped)

Exit codes:
    0 = ingest succeeded (verdict green or warn)
    1 = report file/directory missing or unreadable
    2 = JSON parse error
    3 = unsupported LHR schema (e.g. v5 legacy)
    4 = ingest succeeded but verdict RED (≥1 issue ≥ threshold)

Pass `--no-fail` to coerce exit 0 even on RED (telemetry-only mode).
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
    insert_qa_performance_batch, record_auditor_run,
    replace_qa_auditor_for_feat,
)
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.exit_codes import SUCCESS  # noqa: E402

# ============================================================
# Default thresholds (legacy)
# ============================================================

DEFAULTS = {
    "lcp_ms":   2500.0,
    "cls":         0.10,
    "inp_ms":    200.0,
    "ttfb_ms":   600.0,
    "bundle_kb_serious":  1500.0,   # raw JS+resources > 1500 KB → serious
    "bundle_kb_moderate":  500.0,   # raw 500-1500 KB → moderate
}

SEVERITY_RANK: dict[str, int] = {
    "critical": 4, "serious": 3, "moderate": 2, "minor": 1,
}

DEFAULT_THRESHOLD = "serious"


def _err(error: str, cause: str, fix: str, code: int) -> int:
    sys.stderr.write(f"ERROR: {error}\nCAUSE: {cause}\nFIX: {fix}\n")
    return code


# ============================================================
# LHR resolution — single file vs directory of N runs
# ============================================================

def _gather_lhr_files(path: Path) -> list[Path]:
    """Return the LHR JSON file(s) under `path`.

    - file → [path]
    - directory → all `lhr-*.json` (Lighthouse CI convention), sorted by name
    """
    if path.is_file():
        return [path]
    if path.is_dir():
        files = sorted(path.glob("lhr-*.json"))
        if not files:
            # Fall back to any *.json that looks like an LHR (must have `audits`)
            files = sorted(path.glob("*.json"))
        return files
    return []


def _pick_median_lhr(lhrs: list[dict[str, Any]]) -> dict[str, Any]:
    """When multiple runs exist, pick the one with the median performance
    score (per Lighthouse CI recommendation). Ties → first."""
    if len(lhrs) <= 1:
        return lhrs[0] if lhrs else {}
    scored = []
    for lhr in lhrs:
        cats = (lhr.get("categories") or {})
        perf = cats.get("performance") or {}
        score = perf.get("score")
        scored.append((float(score) if isinstance(score, (int, float)) else 0.0, lhr))
    scored.sort(key=lambda t: t[0])
    median_idx = len(scored) // 2
    return scored[median_idx][1]


# ============================================================
# Audit extraction → [PERF_*] issues
# ============================================================

def _audit_value(lhr: dict[str, Any], audit_id: str) -> float | None:
    audits = lhr.get("audits") or {}
    a = audits.get(audit_id)
    if not isinstance(a, dict):
        return None
    v = a.get("numericValue")
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _render_blocking_items(lhr: dict[str, Any]) -> list[dict[str, Any]]:
    audits = lhr.get("audits") or {}
    a = audits.get("render-blocking-resources") or {}
    details = a.get("details") or {}
    items = details.get("items") or []
    return [it for it in items if isinstance(it, dict)]


def extract_issues(lhr: dict[str, Any], thresholds: dict[str, float]) -> list[dict[str, Any]]:
    """Map LHR audits to [PERF_*] issue rows compatible with insert_qa_performance_batch."""
    issues: list[dict[str, Any]] = []
    url = (lhr.get("finalDisplayedUrl") or lhr.get("finalUrl")
           or lhr.get("requestedUrl") or "")

    # LCP — largest-contentful-paint (ms)
    lcp = _audit_value(lhr, "largest-contentful-paint")
    if lcp is not None and lcp > thresholds["lcp_ms"]:
        issues.append({
            "issue_class":  "PERF_LCP_TOO_HIGH",
            "severity":     "critical",
            "metric":       "LCP",
            "metric_value": round(lcp, 2),
            "metric_unit":  "ms",
            "threshold":    thresholds["lcp_ms"],
            "file_path":    url or None,
            "message":      f"LCP {round(lcp)}ms exceeds {thresholds['lcp_ms']}ms (WCAG/Core Web Vitals)",
        })

    # CLS — cumulative-layout-shift (unitless)
    cls = _audit_value(lhr, "cumulative-layout-shift")
    if cls is not None and cls > thresholds["cls"]:
        issues.append({
            "issue_class":  "PERF_CLS_TOO_HIGH",
            "severity":     "serious",
            "metric":       "CLS",
            "metric_value": round(cls, 3),
            "metric_unit":  None,
            "threshold":    thresholds["cls"],
            "file_path":    url or None,
            "message":      f"CLS {round(cls, 3)} exceeds {thresholds['cls']}",
        })

    # INP — interaction-to-next-paint (ms, replaces FID since 2024)
    # Lighthouse Lab exposes it under "interaction-to-next-paint" or
    # falls back to "max-potential-fid" / "total-blocking-time".
    inp = _audit_value(lhr, "interaction-to-next-paint")
    if inp is None:
        inp = _audit_value(lhr, "total-blocking-time")
        inp_metric = "TBT"
    else:
        inp_metric = "INP"
    if inp is not None and inp > thresholds["inp_ms"]:
        issues.append({
            "issue_class":  "PERF_INP_TOO_HIGH",
            "severity":     "serious",
            "metric":       inp_metric,
            "metric_value": round(inp, 1),
            "metric_unit":  "ms",
            "threshold":    thresholds["inp_ms"],
            "file_path":    url or None,
            "message":      f"{inp_metric} {round(inp)}ms exceeds {thresholds['inp_ms']}ms",
        })

    # TTFB — server-response-time (ms)
    ttfb = _audit_value(lhr, "server-response-time")
    if ttfb is not None and ttfb > thresholds["ttfb_ms"]:
        issues.append({
            "issue_class":  "PERF_TTFB_TOO_HIGH",
            "severity":     "serious",
            "metric":       "TTFB",
            "metric_value": round(ttfb, 1),
            "metric_unit":  "ms",
            "threshold":    thresholds["ttfb_ms"],
            "file_path":    url or None,
            "message":      f"TTFB {round(ttfb)}ms exceeds {thresholds['ttfb_ms']}ms",
        })

    # Bundle / total byte weight (bytes) — convert to KB raw
    total_bytes = _audit_value(lhr, "total-byte-weight")
    if total_bytes is not None:
        total_kb = total_bytes / 1024.0
        if total_kb > thresholds["bundle_kb_serious"]:
            issues.append({
                "issue_class":  "PERF_BUNDLE_TOO_LARGE",
                "severity":     "serious",
                "metric":       "bundle_size",
                "metric_value": round(total_kb, 1),
                "metric_unit":  "KB",
                "threshold":    thresholds["bundle_kb_serious"],
                "file_path":    url or None,
                "message":      f"Total payload {round(total_kb)}KB exceeds "
                                f"{int(thresholds['bundle_kb_serious'])}KB",
            })
        elif total_kb > thresholds["bundle_kb_moderate"]:
            issues.append({
                "issue_class":  "PERF_BUNDLE_LARGE",
                "severity":     "moderate",
                "metric":       "bundle_size",
                "metric_value": round(total_kb, 1),
                "metric_unit":  "KB",
                "threshold":    thresholds["bundle_kb_moderate"],
                "file_path":    url or None,
                "message":      f"Total payload {round(total_kb)}KB above "
                                f"{int(thresholds['bundle_kb_moderate'])}KB threshold",
            })

    # Render-blocking resources — 1 issue per blocking item
    for item in _render_blocking_items(lhr):
        item_url = item.get("url") or url
        wasted_ms = item.get("wastedMs")
        msg = f"render-blocking: {item_url}"
        if isinstance(wasted_ms, (int, float)):
            msg += f" (~{round(wasted_ms)}ms wasted)"
        issues.append({
            "issue_class":  "PERF_RENDER_BLOCKING",
            "severity":     "serious",
            "metric":       "render_blocking_ms",
            "metric_value": (float(wasted_ms) if isinstance(wasted_ms, (int, float))
                             else None),
            "metric_unit":  "ms",
            "threshold":    None,
            "file_path":    item_url,
            "message":      msg,
        })

    return issues


def compute_verdict(issues: list[dict[str, Any]], threshold: str) -> str:
    """Return 'green' | 'warn' | 'red' against severity threshold."""
    if not issues:
        return "green"
    thr_rank = SEVERITY_RANK.get(threshold.lower(), SEVERITY_RANK[DEFAULT_THRESHOLD])
    for it in issues:
        sev = (it.get("severity") or "moderate").lower()
        if SEVERITY_RANK.get(sev, 0) >= thr_rank:
            return "red"
    return "warn"


# ============================================================
# Main
# ============================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingest_lighthouse",
        description="Ingest Lighthouse JSON report(s) into console.db qa_performance.",
    )
    parser.add_argument("--report", type=Path, required=True,
                        help="Path to a Lighthouse Result (LHR) JSON file "
                             "OR a .lighthouseci/ directory containing lhr-*.json runs")
    parser.add_argument("--feat", type=int, required=True,
                        help="FEAT number this scan is associated with")
    parser.add_argument("--threshold", default=DEFAULT_THRESHOLD,
                        choices=tuple(SEVERITY_RANK.keys()),
                        help=f"Severity gate (default: {DEFAULT_THRESHOLD})")
    # Threshold overrides
    parser.add_argument("--lcp-ms",    type=float, default=DEFAULTS["lcp_ms"])
    parser.add_argument("--cls",       type=float, default=DEFAULTS["cls"])
    parser.add_argument("--inp-ms",    type=float, default=DEFAULTS["inp_ms"])
    parser.add_argument("--ttfb-ms",   type=float, default=DEFAULTS["ttfb_ms"])
    parser.add_argument("--bundle-kb", type=float, default=DEFAULTS["bundle_kb_serious"],
                        help="Bundle size threshold for SERIOUS verdict (KB raw)")
    parser.add_argument("--no-fail", action="store_true",
                        help="Always exit 0 (telemetry-only mode, no CI gating)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON summary on stdout instead of human text")
    args = parser.parse_args(argv)

    path = args.report
    if not path.is_absolute():
        path = (repo_root() / path).resolve()

    if not path.exists():
        return _err(
            "ingest_lighthouse: report not found",
            f"[QA_PRECONDITION_FAILED] {path}",
            "ensure the Lighthouse CI step ran and uploaded .lighthouseci/ artifacts",
            code=1,
        )

    files = _gather_lhr_files(path)
    if not files:
        return _err(
            "ingest_lighthouse: no LHR file resolved",
            f"[QA_PRECONDITION_FAILED] {path} contains no lhr-*.json",
            "ensure lhci collect ran and produced JSON results",
            code=1,
        )

    lhrs: list[dict[str, Any]] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return _err(
                "ingest_lighthouse: JSON parse error",
                f"[QA_OUTPUT_INVALID] {f}: {e.msg} (line {e.lineno})",
                "regenerate the Lighthouse run (artifact may be truncated)",
                code=2,
            )
        if not isinstance(data, dict):
            return _err(
                "ingest_lighthouse: unsupported LHR schema",
                f"[QA_OUTPUT_INVALID] {f}: root is not an object",
                "ensure Lighthouse ≥ v10 (single-object LHR shape)",
                code=3,
            )
        # Sanity check: must have 'audits' map
        if not isinstance(data.get("audits"), dict):
            return _err(
                "ingest_lighthouse: unsupported LHR schema",
                f"[QA_OUTPUT_INVALID] {f}: missing 'audits' object",
                "ensure Lighthouse ≥ v10 — older formats not supported",
                code=3,
            )
        lhrs.append(data)

    median_lhr = _pick_median_lhr(lhrs)

    thresholds = {
        "lcp_ms":             args.lcp_ms,
        "cls":                args.cls,
        "inp_ms":             args.inp_ms,
        "ttfb_ms":            args.ttfb_ms,
        "bundle_kb_serious":  args.bundle_kb,
        "bundle_kb_moderate": DEFAULTS["bundle_kb_moderate"],
    }
    issues = extract_issues(median_lhr, thresholds)
    verdict = compute_verdict(issues, args.threshold)

    # Performance score (median run) — for telemetry payload
    cats = (median_lhr.get("categories") or {})
    perf_cat = cats.get("performance") or {}
    perf_score = perf_cat.get("score")

    ensure_initialized()
    with connect() as conn:
        replace_qa_auditor_for_feat(conn, "qa_performance", args.feat)
        n = insert_qa_performance_batch(conn, feat_n=args.feat,
                                        verdict=verdict, issues=issues)
        record_auditor_run(
            conn, feat_n=args.feat, auditor="perf",
            findings_count=n, verdict=verdict,
            payload={
                "source": "lighthouse",
                "runs":   len(lhrs),
                "report": str(path),
                "performance_score": perf_score,
                "thresholds": thresholds,
            },
        )

    summary = {
        "feat":              args.feat,
        "source":            "lighthouse",
        "report":            str(path),
        "runs":              len(lhrs),
        "performance_score": perf_score,
        "issues":            n,
        "verdict":           verdict,
        "threshold":         args.threshold,
    }
    if args.json:
        sys.stdout.write(json.dumps(summary) + "\n")
    else:
        sys.stdout.write(
            f"OK ingest_lighthouse: feat={args.feat} runs={len(lhrs)} "
            f"issues={n} verdict={verdict} score={perf_score}\n"
        )

    if verdict == "red" and not args.no_fail:
        return 4
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
