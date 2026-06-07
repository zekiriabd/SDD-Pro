"""Internal helpers for sdd_review.py — verdict compute + persist + render (M2 split v7.0.0).

Extracted from sdd_review.py to keep the orchestrator <300L. Depends on
_review_fetch.py for Finding + SEVERITY_* constants.
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import (  # noqa: E402
    connect,
    ensure_initialized,
    insert_validation_report,
    replace_validation_reports,
)

from sdd_scripts._review_fetch import (
    Finding,
    SEVERITY_ORDER,
    SEVERITY_RANK,
    deduplicate_findings,
)
from sdd_scripts.triage_issues import classify_path, load_project_names


VERDICT_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


#: Issue classes that ALWAYS force verdict 🔴 RED regardless of agent-emitted
#: severity OR Project Config `*FailOn` threshold (audit 2026-06-06 RUPT-3).
#:
#: Source of truth : `rules/error-classification.md §1.10 §1.11 §1.13` +
#: `python/security_patterns.yaml` `hard_blocking: true` entries.
#:
#: Rationale : these classes encode invariants that **cannot** be bypassed
#: by lowering thresholds (e.g. `SecurityFailOn: critical` shouldn't allow
#: SQL injection to slip through). Without this list, `_review_report.py`
#: relied ONLY on `severity in {critical, blocker}` — if an agent emitted a
#: known-critical class at `serious` severity by mistake, the verdict
#: degraded silently to YELLOW.
#:
#: Add new entries here when extending the taxonomy. Keep in sync with
#: `error-classification.md §1.11` table (`hard-blocking systématique`).
HARD_BLOCKING_CLASSES: frozenset[str] = frozenset({
    # Security (OWASP Top 10 — 8 classes per §1.11)
    "SEC_SECRET_HARDCODED",       # A02/A07 CWE-798
    "SEC_SQL_INJECTION",          # A03 CWE-89
    "SEC_COMMAND_INJECTION",      # A03 CWE-78
    "SEC_BROKEN_AUTHZ",           # A01 CWE-862
    "SEC_BROKEN_AUTHN",           # A07 CWE-287
    "SEC_DESERIALIZATION_UNSAFE", # A08 CWE-502
    "SEC_JWT_MISCONFIG",          # A07 CWE-1004
    "SEC_SSRF_RISK",              # A10 CWE-918
    # Spec compliance (§1.13 — feat-validate STEP 4.5.3/4.5.4)
    "SPEC_COMPLIANCE_REQUIRED",
    "SPEC_COMPLIANCE_RED",
    "SPEC_COMPLIANCE_PARSE_ERROR",
    # Code review (§1.10 — code-reviewer.md §7.3 hard-blocking override)
    "FRONTEND_BACKEND_CONTRACT_GAP",
})


def _is_hard_blocking(finding: Finding) -> bool:
    """Return True if `finding.issue_class` is in HARD_BLOCKING_CLASSES.

    Strip leading `[` and trailing `]` if the agent emitted the bracketed
    form (defensive — the canonical Finding.issue_class is unbracketed).
    """
    cls = (finding.issue_class or "").strip()
    if cls.startswith("[") and cls.endswith("]"):
        cls = cls[1:-1]
    return cls in HARD_BLOCKING_CLASSES


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


def compute_report(
    feat_n: int, findings: list[Finding], missing: list[str], fail_on: str
) -> ReviewReport:
    names = load_project_names()
    # Apply owner
    for f in findings:
        f.owner = classify_path(f.file_path or "", names)

    # v7.0.0 audit §6.10 — cross-source dedup before counting/verdict
    findings, dedup_suppressed = deduplicate_findings(findings)

    counts_by_owner    = dict(Counter(f.owner for f in findings))
    counts_by_source   = dict(Counter(f.source for f in findings))
    counts_by_severity = dict(Counter(f.severity for f in findings))
    counts_by_class    = dict(Counter(f.issue_class for f in findings))

    # Verdict (audit 2026-06-06 RUPT-3 — hard_blocking override)
    threshold = SEVERITY_RANK.get(fail_on, SEVERITY_RANK["serious"])
    triggering = [f for f in findings if SEVERITY_RANK.get(f.severity, 0) >= threshold]

    # Hard-blocking classes force RED regardless of severity or fail_on
    # threshold. This catches the case where an agent emits a known-critical
    # class (e.g. [SEC_SQL_INJECTION]) at `serious` severity by mistake —
    # without this check, a `SecurityFailOn: critical` project would silently
    # downgrade to YELLOW. Promotes the YAML `hard_blocking: true` metadata
    # from declarative to enforced.
    hard_blocked = [f for f in findings if _is_hard_blocking(f)]

    # Audit 2026-06-06 D4 — aggregate-volume escalation YELLOW → RED.
    # Rationale : the legacy verdict logic stayed YELLOW regardless of HOW
    # MANY sub-threshold findings accumulated. 30 `moderate` findings (under
    # `serious` threshold) → YELLOW, pipeline continues without alerting the
    # operator. New thresholds tuned conservatively to avoid false positives
    # on healthy codebases while catching pathological accumulation :
    #   - 5+ `serious` findings (sub-threshold) → RED
    #   - 15+ `moderate` findings → RED
    #   - 30+ total findings (any severity except `minor`) → RED
    # The `minor`/`info` severities don't count individually toward escalation
    # (they're often style-only). Project-level override via Project Config
    # `ReviewAggregateMode` (planned v7.2 — for now constants are inline).
    aggregate_red = False
    n_serious  = counts_by_severity.get("serious", 0)
    n_moderate = counts_by_severity.get("moderate", 0)
    n_nonminor = sum(counts_by_severity.get(s, 0)
                     for s in ("blocker", "critical", "serious", "moderate"))
    if n_serious >= 5 or n_moderate >= 15 or n_nonminor >= 30:
        aggregate_red = True

    if hard_blocked:
        verdict = "red"
        # Treat hard-blocked findings as "triggering" so they appear in the
        # detail section of the report (alongside threshold-triggered ones).
        for f in hard_blocked:
            if f not in triggering:
                triggering.append(f)
    elif any(f.severity in ("critical", "blocker") for f in findings):
        verdict = "red"
    elif triggering:
        verdict = "red"
    elif aggregate_red:
        verdict = "red"
    elif findings:
        verdict = "yellow"
    else:
        verdict = "green"

    report = ReviewReport(
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
    # Attach dedup stat as side-channel (not in dataclass to preserve API)
    setattr(report, "_dedup_suppressed", dedup_suppressed)
    return report


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
