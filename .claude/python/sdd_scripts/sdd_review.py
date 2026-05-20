#!/usr/bin/env python3
"""SDD_Pro: /sdd-review orchestrator — Sonar-like audit per FEAT (Phase A).

Phase A scope (rapport seul, 0 auto-fix) :
1. Re-run deterministic scans (quality_scan.py) to refresh `qa_quality`.
2. Read all auditor findings already in `console.db` for this FEAT
   (qa_quality, qa_code_review, qa_security, qa_a11y, qa_performance,
   qa_spec_compliance).
3. Triage each finding by owner (backend|frontend|shared|unknown) via
   `triage_issues.classify_path()`.
4. Compute verdict 🟢/🟡/🔴 against `ReviewFailOn` config (default `serious`).
5. Persist a row in `validation_reports(report_type='review')` with full
   JSON payload (owner counts + issue class breakdown + sources).
6. Emit a human-readable Markdown report at
   `workspace/output/qa/feat-{n}/review.md`.

Usage :
    python sdd_review.py --feat-number 1
    python sdd_review.py --feat-number 1 --json
    python sdd_review.py --feat-number 1 --skip-scans         # skip re-run
    python sdd_review.py --feat-number 1 --fail-on critical   # override

Exit codes :
    0 → 🟢 GREEN (or YELLOW under FailOn threshold)
    1 → 🔴 RED (issues at/above FailOn)
    2 → infra error (missing FEAT, DB unreachable, bad args)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import (  # noqa: E402
    connect, ensure_initialized, insert_validation_report,
    replace_validation_reports,
)
from sdd_lib.paths import repo_root  # noqa: E402

from sdd_scripts.triage_issues import (  # noqa: E402
    classify_batch, classify_path, load_project_names, summarize_buckets,
)

# Severity ordering — same as accessibility-auditor / security-reviewer.
SEVERITY_ORDER = ("info", "minor", "moderate", "serious", "critical", "blocker")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}

# Map quality_scan severities → unified ordering
QUALITY_SEV_MAP = {
    "error":    "serious",
    "warning":  "moderate",
    "info":     "info",
    "blocker":  "blocker",
    "critical": "critical",
    "major":    "serious",
    "minor":    "minor",
}


@dataclass
class Finding:
    source: str           # "quality" | "code-review" | "security" | "a11y" | "perf" | "spec"
    issue_class: str      # [CLASS] préfixe, ex. REVIEW_*, SEC_*, A11Y_*
    severity: str         # normalisé sur SEVERITY_ORDER
    rule: str | None
    file_path: str | None
    line: int | None
    message: str | None
    owner: str = "unknown"


@dataclass
class ReviewReport:
    feat_n: int
    extracted_at: str
    verdict: str          # green | yellow | red
    fail_on: str
    counts_by_owner: dict[str, int]          = field(default_factory=dict)
    counts_by_source: dict[str, int]         = field(default_factory=dict)
    counts_by_severity: dict[str, int]       = field(default_factory=dict)
    counts_by_class: dict[str, int]          = field(default_factory=dict)
    triggering_findings: list[Finding]       = field(default_factory=list)
    all_findings: list[Finding]              = field(default_factory=list)
    scans_run: list[str]                     = field(default_factory=list)
    skipped_sources: list[str]               = field(default_factory=list)


# ---------------------------------------------------------------------------
# STEP 3 — Deterministic scans
# ---------------------------------------------------------------------------

def run_quality_scan(feat_n: int) -> tuple[bool, str]:
    """Re-run quality_scan.py for the given FEAT. Returns (ok, stdout-tail)."""
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / "quality_scan.py"),
        "--feat-number", str(feat_n),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (>120s)"
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    return proc.returncode == 0, "\n".join(tail[-6:])


# ---------------------------------------------------------------------------
# STEP 4 — Read findings from DB
# ---------------------------------------------------------------------------

def _norm_sev(s: str | None, src: str) -> str:
    if not s:
        return "info"
    s = s.strip().lower()
    if src == "quality":
        return QUALITY_SEV_MAP.get(s, "info")
    return s if s in SEVERITY_RANK else "info"


def fetch_findings(feat_n: int) -> tuple[list[Finding], list[str]]:
    """Pull all auditor findings for `feat_n` from console.db.

    Returns (findings, missing_sources). `missing_sources` is the list of
    auditor tables where 0 rows exist for this feat — informational, used
    by the Markdown report.
    """
    findings: list[Finding] = []
    sources_present: set[str] = set()

    with connect() as conn:
        conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}

        # qa_quality (deterministic scan)
        for row in conn.execute(
            "SELECT severity, issue_class, rule, file_path, line, message "
            "FROM qa_quality WHERE feat_n=?", (feat_n,)
        ):
            sources_present.add("quality")
            findings.append(Finding(
                source="quality",
                issue_class=row["issue_class"] or row["rule"] or "QUALITY",
                severity=_norm_sev(row["severity"], "quality"),
                rule=row["rule"],
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_code_review (LLM) — split by issue_class prefix:
        #   ARCH_* → source "arch" (emitted by arch-reviewer)
        #   *      → source "code-review" (emitted by code-reviewer)
        for row in conn.execute(
            "SELECT severity, issue_class, file_path, line, message "
            "FROM qa_code_review WHERE feat_n=?", (feat_n,)
        ):
            cls = (row["issue_class"] or "").strip()
            is_arch = cls.startswith("ARCH_") or cls.startswith("[ARCH_")
            src = "arch" if is_arch else "code-review"
            sources_present.add(src)
            findings.append(Finding(
                source=src,
                issue_class=cls or "REVIEW",
                severity=_norm_sev(row["severity"], src),
                rule=None,
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_security
        for row in conn.execute(
            "SELECT severity, issue_class, file_path, line, message, mode, owasp, cwe "
            "FROM qa_security WHERE feat_n=? AND (mode IS NULL OR mode='scan')", (feat_n,)
        ):
            sources_present.add("security")
            findings.append(Finding(
                source="security",
                issue_class=row["issue_class"],
                severity=_norm_sev(row["severity"], "security"),
                rule=row["owasp"] or row["cwe"],
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_a11y
        for row in conn.execute(
            "SELECT severity, issue_class, file_path, line, message, wcag "
            "FROM qa_a11y WHERE feat_n=?", (feat_n,)
        ):
            sources_present.add("a11y")
            findings.append(Finding(
                source="a11y",
                issue_class=row["issue_class"],
                severity=_norm_sev(row["severity"], "a11y"),
                rule=row["wcag"],
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_performance
        for row in conn.execute(
            "SELECT severity, issue_class, file_path, line, message, metric "
            "FROM qa_performance WHERE feat_n=?", (feat_n,)
        ):
            sources_present.add("perf")
            findings.append(Finding(
                source="perf",
                issue_class=row["issue_class"],
                severity=_norm_sev(row["severity"], "perf"),
                rule=row["metric"],
                file_path=row["file_path"],
                line=row["line"],
                message=row["message"],
            ))

        # qa_spec_compliance
        for row in conn.execute(
            "SELECT severity, us_id, ac_id, verdict, evidence_file, evidence_line, message "
            "FROM qa_spec_compliance WHERE feat_n=? AND verdict != 'verified'", (feat_n,)
        ):
            sources_present.add("spec")
            findings.append(Finding(
                source="spec",
                issue_class=f"SPEC_{(row['verdict'] or 'not_verified').upper()}",
                severity=_norm_sev(row["severity"], "spec"),
                rule=f"{row['us_id']}/{row['ac_id']}",
                file_path=row["evidence_file"],
                line=row["evidence_line"],
                message=row["message"],
            ))

    all_sources = {"quality", "code-review", "security", "a11y", "perf", "spec", "arch"}
    missing = sorted(all_sources - sources_present)
    return findings, missing


# ---------------------------------------------------------------------------
# STEP 5-6 — Triage + verdict
# ---------------------------------------------------------------------------

def compute_report(
    feat_n: int, findings: list[Finding], missing: list[str], fail_on: str
) -> ReviewReport:
    names = load_project_names()
    # Apply owner
    for f in findings:
        f.owner = classify_path(f.file_path or "", names)

    counts_by_owner    = dict(Counter(f.owner for f in findings))
    counts_by_source   = dict(Counter(f.source for f in findings))
    counts_by_severity = dict(Counter(f.severity for f in findings))
    counts_by_class    = dict(Counter(f.issue_class for f in findings))

    # Verdict
    threshold = SEVERITY_RANK.get(fail_on, SEVERITY_RANK["serious"])
    triggering = [f for f in findings if SEVERITY_RANK.get(f.severity, 0) >= threshold]

    if any(f.severity in ("critical", "blocker") for f in findings):
        verdict = "red"
    elif triggering:
        verdict = "red"
    elif findings:
        verdict = "yellow"
    else:
        verdict = "green"

    return ReviewReport(
        feat_n=feat_n,
        extracted_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        verdict=verdict,
        fail_on=fail_on,
        counts_by_owner=counts_by_owner,
        counts_by_source=counts_by_source,
        counts_by_severity=counts_by_severity,
        counts_by_class=counts_by_class,
        triggering_findings=triggering,
        all_findings=findings,
        skipped_sources=missing,
    )


# ---------------------------------------------------------------------------
# STEP 7 — Persist (DB) + STEP 8 — Markdown
# ---------------------------------------------------------------------------

def persist_report(report: ReviewReport, md_path: Path) -> None:
    payload: dict[str, Any] = {
        "verdict": report.verdict,
        "fail_on": report.fail_on,
        "counts": {
            "by_owner":    report.counts_by_owner,
            "by_source":   report.counts_by_source,
            "by_severity": report.counts_by_severity,
            "by_class":    report.counts_by_class,
            "total":       len(report.all_findings),
            "triggering":  len(report.triggering_findings),
        },
        "scans_run":       report.scans_run,
        "skipped_sources": report.skipped_sources,
        "top_classes":     dict(Counter(report.counts_by_class).most_common(10)),
    }
    ensure_initialized()
    with connect() as conn:
        replace_validation_reports(conn, feat_n=report.feat_n, report_type="review")
        insert_validation_report(
            conn,
            feat_n=report.feat_n,
            report_type="review",
            verdict=report.verdict.upper(),
            extracted_at=report.extracted_at,
            score=len(report.all_findings),
            summary=(
                f"{len(report.all_findings)} findings "
                f"({len(report.triggering_findings)} ≥ {report.fail_on}); "
                f"verdict={report.verdict.upper()}"
            ),
            payload=payload,
            file_path=str(md_path.as_posix()) if md_path else None,
        )


VERDICT_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def render_markdown(report: ReviewReport) -> str:
    """Human-readable consolidated review report."""
    lines: list[str] = []
    icon = VERDICT_ICON.get(report.verdict, "❓")
    lines.append(f"# /sdd-review — FEAT {report.feat_n}")
    lines.append("")
    lines.append(f"**Verdict** : {icon} `{report.verdict.upper()}` ")
    lines.append(f"**Extracted at** : `{report.extracted_at}` ")
    lines.append(f"**FailOn threshold** : `{report.fail_on}` ")
    lines.append(f"**Total findings** : {len(report.all_findings)} "
                 f"(triggering ≥ {report.fail_on} → {len(report.triggering_findings)})")
    lines.append("")

    if report.scans_run:
        lines.append(f"**Scans re-run** : {', '.join(report.scans_run)}")
        lines.append("")
    if report.skipped_sources:
        lines.append(f"**Sources sans données** (auditeur non lancé pour cette FEAT) : "
                     f"`{', '.join(report.skipped_sources)}`")
        lines.append("")

    # By owner
    lines.append("## Triage par owner")
    lines.append("")
    lines.append("| Owner | Findings | Agent à dispatcher (Phase B+) |")
    lines.append("|---|---:|---|")
    owner_agent = {
        "backend":  "`dev-backend`",
        "frontend": "`dev-frontend`",
        "shared":   "`dev-backend` + `dev-frontend`",
        "unknown":  "— (Tech Lead manuel)",
    }
    for owner in ("backend", "frontend", "shared", "unknown"):
        n = report.counts_by_owner.get(owner, 0)
        if n:
            lines.append(f"| {owner} | {n} | {owner_agent[owner]} |")
    lines.append("")

    # By source
    lines.append("## Par source d'audit")
    lines.append("")
    lines.append("| Source | Findings |")
    lines.append("|---|---:|")
    for src, n in sorted(report.counts_by_source.items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{src}` | {n} |")
    lines.append("")

    # By severity
    lines.append("## Par sévérité")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    for sev in reversed(SEVERITY_ORDER):
        n = report.counts_by_severity.get(sev, 0)
        if n:
            lines.append(f"| {sev} | {n} |")
    lines.append("")

    # Top issue classes
    lines.append("## Top 10 classes d'erreur")
    lines.append("")
    lines.append("| Issue class | Count |")
    lines.append("|---|---:|")
    for cls, n in Counter(report.counts_by_class).most_common(10):
        lines.append(f"| `{cls}` | {n} |")
    lines.append("")

    # Triggering findings detail (the ones that pushed verdict to red/yellow)
    if report.triggering_findings:
        lines.append(f"## Findings déclenchants (≥ {report.fail_on})")
        lines.append("")
        lines.append("| Severity | Source | Class | Owner | File:Line | Message |")
        lines.append("|---|---|---|---|---|---|")
        for f in sorted(
            report.triggering_findings,
            key=lambda x: -SEVERITY_RANK.get(x.severity, 0),
        )[:50]:
            loc = f"{f.file_path}:{f.line}" if f.file_path else "—"
            msg = (f.message or "").replace("|", "\\|")[:90]
            lines.append(f"| {f.severity} | {f.source} | `{f.issue_class}` "
                         f"| {f.owner} | {loc} | {msg} |")
        if len(report.triggering_findings) > 50:
            lines.append(f"| ... | ... | ... | ... | ... | (+{len(report.triggering_findings)-50} more) |")
        lines.append("")

    # Suite
    lines.append("## Suite (Phase B — auto-fix, à venir)")
    lines.append("")
    lines.append(
        "Phase A = rapport seul. Phase B branchera `dispatch_fixes.py` pour "
        "spawn `dev-backend:fix` / `dev-frontend:fix` sur les findings "
        "déterministes corrigeables (hex hardcoded, imports inutilisés, "
        "magic numbers triviaux). Issues LLM (archi, sécurité critique) "
        "restent rapport-seul — Tech Lead arbitre."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Source de vérité : `console.db.validation_reports "
                 f"WHERE feat_n={report.feat_n} AND report_type='review'`")
    lines.append("Re-run : `python .claude/python/sdd_scripts/sdd_review.py "
                 f"--feat-number {report.feat_n}`")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument("--skip-scans", action="store_true",
                   help="Do not re-run quality_scan (read DB as-is)")
    p.add_argument("--ensure-scans", action="store_true",
                   help="v7.0.0: exit non-zero (3) if any required auditor "
                        "source has 0 rows in console.db for this FEAT. "
                        "Sources required by default: quality, code-review, "
                        "security, spec. Optional (skipped on missing): "
                        "arch (only if ArchReviewMode=full), a11y/perf "
                        "(legacy — agents removed v7.0.0).")
    p.add_argument("--fail-on", default=None,
                   help="Severity threshold (info|minor|moderate|serious|critical). "
                        "Default: from Project Config ReviewFailOn, else 'serious'.")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON summary on stdout instead of human text")
    return p.parse_args()


# Sources required when --ensure-scans is set. a11y/perf are LEGACY in
# v7.0.0 (agents removed → no SDD_Pro agent emits them anymore — they
# only repopulate via future axe-core / Lighthouse CI ingest hooks).
# arch is gated on ArchReviewMode=full (cf. resolve_arch_required()).
ENSURE_SCANS_REQUIRED_DEFAULT = ("quality", "code-review", "security", "spec")
ENSURE_SCANS_OPTIONAL = ("arch", "a11y", "perf")


def resolve_arch_required() -> bool:
    """Return True iff ArchReviewMode is `full` in Project Config."""
    try:
        from sdd_lib.project_config import read_project_config
        cfg = read_project_config(keys=("ArchReviewMode",))
        return (cfg.get("ArchReviewMode") or "").strip().lower() == "full"
    except Exception:
        return False


def resolve_fail_on(cli_value: str | None) -> str:
    if cli_value:
        return cli_value.strip().lower()
    # Read from Project Config (best-effort, no failure if absent)
    try:
        from sdd_lib.project_config import read_project_config
        cfg = read_project_config(keys=("ReviewFailOn",))
        v = (cfg.get("ReviewFailOn") or "").strip().lower()
        if v in SEVERITY_RANK:
            return v
    except Exception:
        pass
    return "serious"


def main() -> int:
    # Windows console: force UTF-8 to avoid charmap codec on emoji/icons
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = parse_args()
    feat_n = args.feat_number
    fail_on = resolve_fail_on(args.fail_on)
    if fail_on not in SEVERITY_RANK:
        print(f"ERROR: invalid --fail-on '{fail_on}'", file=sys.stderr)
        return 2

    scans_run: list[str] = []

    # STEP 3 — re-run deterministic scans
    if not args.skip_scans:
        ok, tail = run_quality_scan(feat_n)
        scans_run.append("quality_scan.py")
        if not ok:
            print(f"WARNING: quality_scan failed, continuing on stale DB.\n{tail}",
                  file=sys.stderr)

    # STEP 4 — fetch
    findings, missing = fetch_findings(feat_n)

    # STEP 4.5 — --ensure-scans gate (v7.0.0, codex audit follow-up)
    if args.ensure_scans:
        required = set(ENSURE_SCANS_REQUIRED_DEFAULT)
        if resolve_arch_required():
            required.add("arch")
        truly_missing = [s for s in missing if s in required]
        if truly_missing:
            print(
                f"ERROR: /sdd-review --ensure-scans — required auditor "
                f"sources missing in console.db for FEAT {feat_n}",
                file=sys.stderr,
            )
            print(f"CAUSE: [REVIEW_SOURCES_MISSING] no rows for: "
                  f"{', '.join(truly_missing)}", file=sys.stderr)
            invoc_lines = []
            if "quality" in truly_missing:
                invoc_lines.append(
                    "  - quality        : python -m sdd_scripts.quality_scan "
                    f"--feat-number {feat_n}"
                )
            if "code-review" in truly_missing:
                invoc_lines.append(
                    "  - code-review    : Agent: code-reviewer "
                    f"(prompt: \"audit FEAT {feat_n}\")"
                )
            if "security" in truly_missing:
                invoc_lines.append(
                    "  - security       : Agent: security-reviewer "
                    f"(prompt: \"audit FEAT {feat_n}\")"
                )
            if "spec" in truly_missing:
                invoc_lines.append(
                    "  - spec-compliance: Agent: spec-compliance-reviewer "
                    f"(prompt: \"verify FEAT {feat_n}\")"
                )
            if "arch" in truly_missing:
                invoc_lines.append(
                    "  - arch           : Agent: arch-reviewer "
                    f"(prompt: \"audit pattern + ADRs FEAT {feat_n}\")"
                )
            print("FIX: re-run the missing scans then /sdd-review {n} "
                  "(without --ensure-scans, or with it).",
                  file=sys.stderr)
            for ln in invoc_lines:
                print(ln, file=sys.stderr)
            return 3

    # STEP 5-6 — triage + verdict
    report = compute_report(feat_n, findings, missing, fail_on)
    report.scans_run = scans_run

    # STEP 8 — Markdown emit (before persist so file_path is known)
    md_dir = repo_root() / "workspace" / "output" / "qa" / f"feat-{feat_n}"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / "review.md"
    md_path.write_text(render_markdown(report), encoding="utf-8")

    # STEP 7 — Persist DB
    persist_report(report, md_path)

    # Output
    if args.json:
        print(json.dumps({
            "feat_n": report.feat_n,
            "verdict": report.verdict,
            "fail_on": report.fail_on,
            "total": len(report.all_findings),
            "triggering": len(report.triggering_findings),
            "counts": {
                "by_owner":    report.counts_by_owner,
                "by_source":   report.counts_by_source,
                "by_severity": report.counts_by_severity,
            },
            "markdown_path": str(md_path.as_posix()),
        }, indent=2))
    else:
        icon = VERDICT_ICON.get(report.verdict, "❓")
        print(f"{icon} /sdd-review FEAT {feat_n}: "
              f"{len(report.all_findings)} findings "
              f"({len(report.triggering_findings)} ≥ {fail_on}) → "
              f"{report.verdict.upper()}")
        print(f"   owner: {report.counts_by_owner}")
        print(f"   source: {report.counts_by_source}")
        print(f"   markdown: {md_path.as_posix()}")

    return 1 if report.verdict == "red" else 0


if __name__ == "__main__":
    sys.exit(main())
