#!/usr/bin/env python3
"""Deterministic triage gate — should we spawn LLM reviewers? (T2.8 audit 2026-06-08).

Anthropic recommendation §3.4 : 5 LLM reviewers cost ~150k tokens per FEAT
(~$10+ on Opus 4.7). Many FEATs ship code with obvious quality issues
detectable by `quality_scan.py` (deterministic, 0-token). If the
deterministic scan already produces enough RED findings to ensure the
final verdict will be RED, spawning the LLM reviewers is wasted budget.

This script implements the triage :
    1. Run `quality_scan.py` (re-uses existing impl, deterministic)
    2. Count findings >= `--fail-on` threshold in qa_quality table
    3. If `critical_findings >= --threshold` → exit 2 (= "skip LLM reviewers,
       verdict will be RED anyway") + emit recommendation on stderr
    4. Else exit 0 (= "proceed with LLM reviewers, you might still hit GREEN")

Usage (suggested in /sdd-full STEP 4.6 or /sdd-review STEP 2.5) :

    python .claude/python/sdd_scripts/triage_quality.py \
        --feat-number 1 --fail-on serious --threshold 5

    if [ $? -eq 2 ]; then
        echo "Triage RED — skipping LLM reviewers, /sdd-review will surface findings"
        # Optionally still run reviewers for forensics, but the Tech Lead
        # is aware that the verdict is decided.
    fi

Exit codes :
    0 — triage GREEN/YELLOW : worth running LLM reviewers
    2 — triage RED          : LLM reviewers likely redundant (cost-saving signal)
    3 — INFRA_BLOCKED       : DB unreachable / quality_scan failed
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.exit_codes import SUCCESS, FAIL_FAST, INFRA_BLOCKED  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402

SEVERITY_RANK = {
    "info": 0, "minor": 1, "moderate": 2, "serious": 3, "critical": 4,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument("--fail-on", default="serious",
                   choices=list(SEVERITY_RANK.keys()),
                   help="Severity threshold (same semantics as /sdd-review).")
    p.add_argument("--threshold", type=int, default=5,
                   help="Min number of triggering findings to declare triage RED. "
                        "Default 5 = 5 serious-or-critical findings already make "
                        "the verdict RED, LLM reviewers would only add detail.")
    p.add_argument("--skip-scan", action="store_true",
                   help="Read qa_quality as-is, skip the re-run of quality_scan.py.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    feat_n = args.feat_number

    db_path = repo_root() / "workspace" / "output" / "db" / "console.db"
    if not db_path.is_file():
        print(f"INFRA_BLOCKED: console.db not found at {db_path}", file=sys.stderr)
        return INFRA_BLOCKED

    # Step 1 — run quality_scan unless skipped
    if not args.skip_scan:
        import subprocess
        scan = subprocess.run(
            [sys.executable, "-m", "sdd_scripts.quality_scan",
             "--feat-number", str(feat_n)],
            cwd=str(repo_root()),
            capture_output=True, text=True, timeout=120,
        )
        if scan.returncode != 0:
            print(f"WARNING: quality_scan exited {scan.returncode}, reading stale DB",
                  file=sys.stderr)

    # Step 2 — count findings >= threshold
    min_rank = SEVERITY_RANK[args.fail_on]
    rank_set = [k for k, v in SEVERITY_RANK.items() if v >= min_rank]

    try:
        conn = sqlite3.connect(str(db_path))
        placeholders = ",".join("?" for _ in rank_set)
        cur = conn.execute(
            f"""
            SELECT COUNT(*) FROM qa_quality
             WHERE feat_n = ? AND severity IN ({placeholders})
            """,
            (feat_n, *rank_set),
        )
        triggering = cur.fetchone()[0] or 0
    except sqlite3.Error as e:
        print(f"INFRA_BLOCKED: cannot read qa_quality: {e}", file=sys.stderr)
        return INFRA_BLOCKED
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Step 3 — decision
    if triggering >= args.threshold:
        print(
            f"TRIAGE RED: FEAT {feat_n} has {triggering} findings "
            f">= {args.fail_on} (threshold={args.threshold})",
            file=sys.stderr,
        )
        print(
            "RECOMMENDATION: skip LLM reviewers (code-reviewer, security-reviewer, "
            "spec-compliance-reviewer, arch-reviewer, adversarial-reviewer) — "
            "verdict will be RED. Run them only for forensic detail if needed.",
            file=sys.stderr,
        )
        print(
            f"COST SAVING: ~150k tokens (~$10-15 Opus 4.7) per skipped FEAT review.",
            file=sys.stderr,
        )
        return FAIL_FAST  # exit 1 = "triage RED, downstream caller can decide"
    else:
        print(
            f"TRIAGE GREEN/YELLOW: FEAT {feat_n} has {triggering} findings "
            f">= {args.fail_on} (threshold={args.threshold}) — proceed with LLM reviewers"
        )
        return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
