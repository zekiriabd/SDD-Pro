#!/usr/bin/env python3
"""SDD_Pro: /sdd-review --fix dispatcher — Phase B auto-fix orchestrator.

⚠️  STATUT v7.0.0 : SCRIPT DORMANT — Phase B unreleased.
    `/sdd-review --fix` n'est PAS encore câblé (roadmap v7.2).
    Le code est conservé pour préserver le mapping fix-class ↔ recette
    + les tests `test_dispatch_fixes_unit.py`. Tech Lead arbitre les
    findings via le rapport `review.md` consolidé (sortie `/sdd-review`).


Read findings already aggregated by /sdd-review (sources : qa_quality,
qa_code_review, qa_security, qa_a11y, qa_performance, qa_spec_compliance),
filter to **auto-fixable** classes (conservative whitelist), group by
owner (backend / frontend / shared), and write per-owner issue-list JSON
files that the slash command `/sdd-review --fix` consumes to spawn the
appropriate dev-* agent.

**Strictly conservative whitelist** : only issue classes where a narrow
edit (≤ 10 lines per file, no scaffolding, no API change, no behavior
shift) is sufficient. LLM-level fixes (archi pattern, security critical,
contract drift) remain rapport-seul — Tech Lead arbitre.

**Does NOT apply fixes itself.** Pure dispatcher : reads → groups → writes
issue-lists → exits. The actual fixing is delegated to dev-backend /
dev-frontend agents spawned by the slash command with a tight prompt.

Usage :
    python dispatch_fixes.py --feat-number 1                # plan + write issue-lists
    python dispatch_fixes.py --feat-number 1 --json         # JSON output
    python dispatch_fixes.py --feat-number 1 --dry-run      # plan only, no FS write

Exit codes :
    0 → planned (issue-lists written or 0 fixes ready)
    1 → no auto-fixable findings (delegate to Tech Lead)
    2 → infra error (DB unreachable, FEAT not found)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect, ensure_initialized  # noqa: E402
from sdd_lib.exit_codes import INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402

from sdd_scripts.triage_issues import (  # noqa: E402
    classify_path, load_project_names,
)


# ---------------------------------------------------------------------------
# Conservative whitelist — issue classes safely fixable by narrow agent edit
# ---------------------------------------------------------------------------
# Format: { "issue_class_or_rule": (max_severity, hint) }
# - max_severity = the highest severity at which the fix is still considered
#   conservative. Findings above this severity are escalated to Tech Lead.
# - hint = one-line description of the fix the agent should apply.
# ---------------------------------------------------------------------------

FIXABLE_QUALITY_RULES = {
    "hex-hardcoded":      ("moderate", "Replace hex literal with existing token or add to index.css"),
    "ui-token-violation": ("moderate", "Replace hex/rgba arbitrary value with Tailwind token utility"),
    "commented-code":     ("info",     "Delete commented-out block (≥3 lines) if no intent comment"),
    "console-debug":      ("moderate", "Remove or replace console.log/Debug.Print with logger"),
    "js-debug":           ("moderate", "Remove console.log/error/warn statement"),
    "cs-debug":           ("moderate", "Remove Console.WriteLine / Debug.Print"),
    "py-debug":           ("moderate", "Remove top-level print() debug call"),
    "java-kotlin-debug":  ("moderate", "Remove System.out.println"),
    "unused-import":      ("minor",    "Delete unused import line"),
}

FIXABLE_CODE_REVIEW_CLASSES = {
    "[REVIEW_ANTI_PATTERN_KEY_INDEX]":      ("moderate", "Replace key={idx} with stable id from data"),
    "[REVIEW_ANTI_PATTERN_USEEFFECT_NO_DEPS]": ("serious", "Add explicit deps array to useEffect"),
    "[REVIEW_CONFUSING_NAMING]":            ("minor", "Rename to descriptive name (preserve callers)"),
}

FIXABLE_A11Y_CLASSES = {
    "[A11Y_MISSING_ALT]":          ("critical", "Add alt='' or descriptive alt attribute"),
    "[A11Y_BUTTON_NO_LABEL]":      ("serious",  "Add aria-label or visible text content"),
    "[A11Y_INPUT_NO_LABEL]":       ("critical", "Add <label htmlFor=...> or aria-label"),
    "[A11Y_LANG_MISSING]":         ("serious",  "Add lang='fr' (or 'en') on <html> root"),
    "[A11Y_TABINDEX_POSITIVE]":    ("serious",  "Replace tabindex='N>0' with tabindex='0' or remove"),
}

# NEVER auto-fix these — too risky / require Tech Lead judgment
ESCALATE_ONLY_CLASSES = {
    "[SEC_SECRET_HARDCODED]",          # security critical
    "[SEC_SQL_INJECTION]",
    "[SEC_COMMAND_INJECTION]",
    "[SEC_BROKEN_AUTHZ]",
    "[SEC_BROKEN_AUTHN]",
    "[SEC_JWT_MISCONFIG]",
    "[SEC_DESERIALIZATION_UNSAFE]",
    "[SEC_SSRF_RISK]",
    "[FRONTEND_BACKEND_CONTRACT_GAP]",  # signature change
    "[LAYER_VIOLATION]",                # architectural
    "[ARCH_PATTERN_VIOLATION]",         # architectural
    "[ARCH_LAYER_BYPASS]",              # architectural
    "[ARCH_ADR_DRIFT]",                 # decision drift, Tech Lead review
    "[SPEC_AC_NOT_VERIFIED]",           # spec drift, requires US re-read
    "[SPEC_AC_PARTIAL]",
}

SEVERITY_ORDER = ("info", "minor", "moderate", "serious", "critical", "blocker")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}


@dataclass
class FixableFinding:
    source:       str
    issue_class:  str
    rule:         str | None
    severity:     str
    file_path:    str
    line:         int | None
    message:      str | None
    hint:         str
    owner:        str = "unknown"


@dataclass
class DispatchPlan:
    feat_n:        int
    extracted_at:  str
    total_findings: int
    auto_fixable:   int
    escalated:      int
    skipped_unowned: int
    by_owner:      dict[str, list[FixableFinding]] = field(default_factory=dict)
    issue_list_paths: dict[str, str]               = field(default_factory=dict)


# ---------------------------------------------------------------------------
# STEP 1 — Pull findings from DB (same shape as sdd_review.fetch_findings)
# ---------------------------------------------------------------------------

def _is_class_fixable(issue_class: str, rule: str | None, severity: str) -> tuple[bool, str | None]:
    """Returns (is_fixable, hint). Conservative — when in doubt, return False."""
    cls = (issue_class or "").strip()
    rl = (rule or "").strip()
    sev = (severity or "info").lower()

    # Hard escalation list always wins
    if cls in ESCALATE_ONLY_CLASSES:
        return False, None

    # Quality scan rules (deterministic) — keyed on `rule`
    for key, (max_sev, hint) in FIXABLE_QUALITY_RULES.items():
        if key == rl or key == cls:
            if SEVERITY_RANK.get(sev, 0) <= SEVERITY_RANK[max_sev]:
                return True, hint
            return False, None

    # Code-reviewer classes
    if cls in FIXABLE_CODE_REVIEW_CLASSES:
        max_sev, hint = FIXABLE_CODE_REVIEW_CLASSES[cls]
        if SEVERITY_RANK.get(sev, 0) <= SEVERITY_RANK[max_sev]:
            return True, hint
        return False, None

    # A11y classes
    if cls in FIXABLE_A11Y_CLASSES:
        max_sev, hint = FIXABLE_A11Y_CLASSES[cls]
        if SEVERITY_RANK.get(sev, 0) <= SEVERITY_RANK[max_sev]:
            return True, hint
        return False, None

    return False, None


def fetch_fixable(feat_n: int) -> tuple[list[FixableFinding], int, int]:
    """Read DB, filter to whitelist, return (fixable, total_seen, escalated_count)."""
    total = 0
    escalated = 0
    fixable: list[FixableFinding] = []

    with connect() as conn:
        conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}

        queries = [
            ("quality",
             "SELECT severity, issue_class, rule, file_path, line, message "
             "FROM qa_quality WHERE feat_n=?"),
            ("code-review",
             "SELECT severity, issue_class, NULL as rule, file_path, line, message "
             "FROM qa_code_review WHERE feat_n=?"),
            ("a11y",
             "SELECT severity, issue_class, NULL as rule, file_path, line, message "
             "FROM qa_a11y WHERE feat_n=?"),
            # security/perf/spec → only ESCALATE (no fixable classes in those)
            ("security",
             "SELECT severity, issue_class, NULL as rule, file_path, line, message "
             "FROM qa_security WHERE feat_n=? AND (mode IS NULL OR mode='scan')"),
            ("perf",
             "SELECT severity, issue_class, NULL as rule, file_path, line, message "
             "FROM qa_performance WHERE feat_n=?"),
        ]

        for src, sql in queries:
            for row in conn.execute(sql, (feat_n,)):
                total += 1
                cls = (row["issue_class"] or "").strip()
                rule = (row["rule"] or "").strip()
                sev = (row["severity"] or "info").strip().lower()

                is_fix, hint = _is_class_fixable(cls, rule, sev)
                if not is_fix:
                    if cls in ESCALATE_ONLY_CLASSES:
                        escalated += 1
                    continue
                if not row["file_path"]:
                    continue  # cannot edit without a file path
                fixable.append(FixableFinding(
                    source=src,
                    issue_class=cls or (rule or "UNKNOWN"),
                    rule=rule or None,
                    severity=sev,
                    file_path=row["file_path"],
                    line=row["line"],
                    message=row["message"],
                    hint=hint or "",
                ))

    return fixable, total, escalated


# ---------------------------------------------------------------------------
# STEP 2 — Triage by owner + write per-owner issue-lists
# ---------------------------------------------------------------------------

FIXLIST_DIR = "workspace/output/.sys/.fixlist"


def build_plan(feat_n: int, dry_run: bool = False) -> DispatchPlan:
    fixable, total, escalated = fetch_fixable(feat_n)

    names = load_project_names()
    by_owner: dict[str, list[FixableFinding]] = defaultdict(list)
    skipped_unowned = 0

    for f in fixable:
        f.owner = classify_path(f.file_path, names)
        if f.owner == "unknown":
            skipped_unowned += 1
            continue
        by_owner[f.owner].append(f)

    plan = DispatchPlan(
        feat_n=feat_n,
        extracted_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_findings=total,
        auto_fixable=sum(len(v) for v in by_owner.values()),
        escalated=escalated,
        skipped_unowned=skipped_unowned,
        by_owner=dict(by_owner),
    )

    if not dry_run:
        out_dir = repo_root() / FIXLIST_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        # Clean stale fixlists for this feat
        for stale in out_dir.glob(f"{feat_n}-*.json"):
            try:
                stale.unlink()
            except OSError:
                pass

        for owner, items in by_owner.items():
            path = out_dir / f"{feat_n}-{owner}.json"
            payload = {
                "feat_n":       feat_n,
                "owner":        owner,
                "extracted_at": plan.extracted_at,
                "agent":        "dev-backend" if owner == "backend" else "dev-frontend" if owner == "frontend" else "manual",
                "constraints": [
                    "Only edit files listed in `items[].file_path`",
                    "Only fix the issues described in `items[].hint` for the given line",
                    "Do NOT scaffold new files, do NOT add new endpoints / components",
                    "Do NOT modify ACs of US, do NOT modify constitution, do NOT modify stack",
                    "Run the project build after fixes; if build fails, revert and STOP",
                    "Idempotent : if the issue is already absent, skip silently",
                ],
                "items":        [asdict(f) for f in items],
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                            encoding="utf-8")
            plan.issue_list_paths[owner] = str(path.as_posix())

    return plan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render_human(plan: DispatchPlan) -> str:
    lines: list[str] = []
    lines.append(f"=== /sdd-review --fix — FEAT {plan.feat_n} dispatch plan ===")
    lines.append("")
    lines.append(f"  Total findings (DB)        : {plan.total_findings}")
    lines.append(f"  Auto-fixable (whitelist)   : {plan.auto_fixable}")
    lines.append(f"  Escalated (Tech Lead only) : {plan.escalated}")
    lines.append(f"  Skipped (unowned path)     : {plan.skipped_unowned}")
    lines.append("")
    if plan.auto_fixable == 0:
        lines.append("  → No auto-fixable findings. Tech Lead arbitre.")
        return "\n".join(lines) + "\n"

    lines.append("  Dispatch par owner :")
    for owner, items in plan.by_owner.items():
        agent = (
            "dev-backend"  if owner == "backend"
            else "dev-frontend" if owner == "frontend"
            else "manual (shared lib — both agents possible)"
        )
        path = plan.issue_list_paths.get(owner, "(dry-run)")
        lines.append(f"    - {owner:8} : {len(items):3} fix(es) → agent `{agent}`")
        lines.append(f"                   fixlist={path}")
        # First 3 items as preview
        for f in items[:3]:
            loc = f"{f.file_path}:{f.line or '?'}"
            lines.append(f"                     · [{f.severity}] {f.issue_class} @ {loc}")
        if len(items) > 3:
            lines.append(f"                     · ... (+{len(items) - 3} more)")
    lines.append("")
    lines.append("Next : the slash command `/sdd-review {n} --fix` spawns each agent")
    lines.append("       with a tight prompt referencing its fixlist. After all agents")
    lines.append("       converge, `/sdd-review {n}` is re-run to verify.")
    return "\n".join(lines) + "\n"


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument("--json", action="store_true", help="Emit JSON plan on stdout")
    p.add_argument("--dry-run", action="store_true",
                   help="Plan only — do not write fixlist files")
    args = p.parse_args()

    try:
        ensure_initialized()
        plan = build_plan(args.feat_number, dry_run=args.dry_run)
    except Exception as exc:
        sys.stderr.write(f"ERROR: dispatch_fixes: {exc}\n")
        return INFRA_BLOCKED

    if args.json:
        # Serialize dataclasses to dict
        out = {
            "feat_n":        plan.feat_n,
            "extracted_at":  plan.extracted_at,
            "total":         plan.total_findings,
            "auto_fixable":  plan.auto_fixable,
            "escalated":     plan.escalated,
            "skipped_unowned": plan.skipped_unowned,
            "by_owner": {
                owner: [asdict(f) for f in items]
                for owner, items in plan.by_owner.items()
            },
            "issue_list_paths": plan.issue_list_paths,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(render_human(plan))

    # predicate: 0 if there are auto-fixable findings, 1 if none (not an error code)
    return SUCCESS if plan.auto_fixable else 1


if __name__ == "__main__":
    sys.exit(main())
