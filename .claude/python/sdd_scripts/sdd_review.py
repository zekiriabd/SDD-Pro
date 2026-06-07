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

**v7.0.0 M2 refactor** : helpers extracted to `_review_fetch.py` (DB +
dedup) and `_review_report.py` (compute + render + persist). Public
API re-exported here for backward-compat with existing tests.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402

# Re-export internal helpers (backward-compat with tests/callers that
# import from sdd_scripts.sdd_review).
from sdd_scripts._review_fetch import (  # noqa: E402,F401
    QUALITY_SEV_MAP,
    SEVERITY_ORDER,
    SEVERITY_RANK,
    Finding,
    _norm_sev,
    _normalize_path,
    deduplicate_findings,
    fetch_findings,
    run_quality_scan,
)
from sdd_scripts._review_report import (  # noqa: E402,F401
    VERDICT_ICON,
    ReviewReport,
    compute_report,
    persist_report,
    render_markdown,
)


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
    """Return True iff ArchReviewMode is `full` in layered config (base ← team ← project).

    Uses `read_layered_config` to honor team-level policies. A project that
    downgrades `ArchReviewMode` below the team baseline raises `ConfigError`
    `[CONFIG_SECURITY_DOWNGRADE]` which is re-raised here (no silent swallow).
    """
    from sdd_lib.layered_config import ConfigError, read_layered_config
    try:
        cfg = read_layered_config(keys=("ArchReviewMode",))
    except ConfigError:
        raise  # [CONFIG_SECURITY_DOWNGRADE] must surface
    except Exception:
        return False
    return (cfg.get("ArchReviewMode") or "").strip().lower() == "full"


def resolve_fail_on(cli_value: str | None) -> str:
    """Resolve --fail-on threshold from CLI or layered config (base ← team ← project).

    A project that relaxes `ReviewFailOn` below the team baseline raises
    `ConfigError` `[CONFIG_SECURITY_DOWNGRADE]` which is re-raised here
    (no silent swallow). Other I/O errors fall back to default 'serious'.
    """
    if cli_value:
        return cli_value.strip().lower()
    from sdd_lib.layered_config import ConfigError, read_layered_config
    try:
        cfg = read_layered_config(keys=("ReviewFailOn",))
    except ConfigError:
        raise  # [CONFIG_SECURITY_DOWNGRADE] must surface
    except Exception:
        return "serious"
    v = (cfg.get("ReviewFailOn") or "").strip().lower()
    if v in SEVERITY_RANK:
        return v
    return "serious"


def _auto_ingest_orphan_jsons(feat_n: int) -> list[str]:
    """Defensive auto-ingest of agent JSON reports if DB rows are missing.

    Sprint 1.2 fix (2026-06-06) — code-reviewer and security-reviewer agents
    sometimes finish writing their JSON reports but the SubagentStop hook
    that triggers `ingest_agent_report.py` misses (background completion,
    timeout, race condition). Result : `sdd-review` aggregates findings
    only from `qa_quality` and emits a false 🟢/🟡 verdict.

    This function scans the well-known JSON paths under
    `workspace/output/qa/feat-{n}/` and triggers ingest for each report
    type whose corresponding DB table is empty for this FEAT. Idempotent
    (no-op when ingests already done).

    Returns a list of human-readable log lines for `scans_run` (e.g.
    ["ingested code-review (3 rows)", ...]).
    """
    import sqlite3
    import subprocess
    logs: list[str] = []
    root = repo_root()
    qa_dir = root / "workspace" / "output" / "qa" / f"feat-{feat_n}"
    if not qa_dir.is_dir():
        return logs

    db_path = root / "workspace" / "output" / "db" / "console.db"
    if not db_path.is_file():
        return logs

    # (json filename pattern, ingest --type value, DB table to test)
    candidates = [
        ("code-review.json",     "code-review",     "qa_code_review"),
        ("security-scan.json",   "security-scan",   "qa_security"),
        ("spec-compliance.json", "spec-compliance", "qa_spec_compliance"),
        ("a11y.json",            "a11y",            "qa_a11y"),
        ("perf.json",            "perf",            "qa_performance"),
        ("adversarial.json",     "adversarial",     "validation_reports"),  # special
    ]
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return logs

    for fname, type_arg, table in candidates:
        path = qa_dir / fname
        if not path.is_file():
            continue
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE feat_n=?", (feat_n,))
            existing = cur.fetchone()[0]
        except sqlite3.Error:
            continue
        if existing > 0:
            continue  # already ingested — idempotent skip

        # Trigger ingest. Use subprocess to keep the orchestrator's import
        # graph clean (ingest_agent_report has its own argparse).
        # Invoke the script by absolute path (PYTHONPATH not configured at
        # repo root — `.claude/python/sdd_scripts` is not on sys.path for
        # subprocess by default).
        ingest_script = root / ".claude" / "python" / "sdd_scripts" / "ingest_agent_report.py"
        try:
            result = subprocess.run(
                [sys.executable, str(ingest_script),
                 "--type", type_arg, "--feat", str(feat_n),
                 "--path", str(path), "--keep-json"],
                cwd=str(root),
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "PYTHONPATH": str(root / ".claude" / "python")},
            )
            if result.returncode == 0:
                logs.append(f"auto-ingest {type_arg}")
            else:
                # Best-effort : log on stderr but don't fail sdd-review
                print(f"WARNING: auto-ingest {type_arg} failed: {result.stderr.strip()[:200]}",
                      file=sys.stderr)
        except (subprocess.SubprocessError, OSError) as e:
            print(f"WARNING: auto-ingest {type_arg} subprocess error: {e}",
                  file=sys.stderr)

    conn.close()
    return logs


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
        return 2  # legacy exit code preserved — see sdd_lib/exit_codes.py docstring

    scans_run: list[str] = []

    # STEP 3 — re-run deterministic scans
    if not args.skip_scans:
        ok, tail = run_quality_scan(feat_n)
        scans_run.append("quality_scan.py")
        if not ok:
            print(f"WARNING: quality_scan failed, continuing on stale DB.\n{tail}",
                  file=sys.stderr)

    # STEP 3.5 — auto-ingest stale JSONs (Sprint 1.2 fix 2026-06-06)
    # If an agent ran but ingest_agent_report wasn't invoked (e.g. SubagentStop
    # hook missed, background timeout), .json files exist on disk but DB rows
    # are empty → verdict aggregates 0 findings from those sources (false 🟢).
    # Defensive auto-ingest before fetch : scan well-known JSON paths and
    # pipe through ingest_agent_report.py if the corresponding DB table is empty.
    if not args.skip_scans:
        ingest_logs = _auto_ingest_orphan_jsons(feat_n)
        if ingest_logs:
            scans_run.extend(ingest_logs)

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
            return 3  # legacy exit code preserved — ensure-scans sources missing

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

    return FAIL_FAST if report.verdict == "red" else SUCCESS


if __name__ == "__main__":
    sys.exit(main())
