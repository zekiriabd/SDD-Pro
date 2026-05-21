"""SDD_Pro — Verify console.db telemetry health (anti test pollution).

Background (post-mortem 2026-05-21)
-----------------------------------
The framework's test suite had `SDD_REPO_ROOT` env override silently
falling through to CWD walk when the override path didn't satisfy
`_looks_like_repo_root()` strict check. This caused 62/872 tests to
walk up from %TEMP% to the REAL repo and pollute its console.db with
test artifacts (fake commands `/x`, `/a`, `/cmd1`, etc., 100 % of
`token_usage.run_id` NULL because tests never set the env var).

The combo `paths.py` fix (trust override unconditionally) + test fixture
scaffolding (full `.claude/agents`+`.claude/commands`+`workspace/`)
prevents *future* pollution. This script detects the *signs* of pollution
in an existing DB and refuses to certify it as a source of truth for ROI
/ cost-cap / financial audit.

Run as a CI gate before any phase that depends on telemetry integrity
(report_roi.py, /sdd-review aggregation, cost-cap trust).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# bootstrap sdd_lib import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.console_db import connect_ro  # noqa: E402  (v7.0.0-alpha — WAL-safe RO)
from sdd_lib.exit_codes import OK, INFRA_BLOCKED  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402


# Heuristics : commands that should NEVER appear in production console.db
TEST_POLLUTION_COMMANDS = {"/x", "/a", "/b", "/cmd1", "/cmd2", "/y", "/z", "unknown"}

# Sanity floors for a real /sdd-full run (one-shot, FEAT 3 US ballpark)
MIN_REAL_INPUT_TOKENS_PER_RUN = 50_000   # < this : almost certainly fake
MIN_REAL_OUTPUT_TOKENS_PER_RUN = 10_000


def audit_db(db_path: Path) -> dict:
    """Return a structured health report for the given DB.

    v7.0.0-alpha (2026-05-21) — uses ``connect_ro`` (WAL-safe + portable URI
    + immutable fallback) instead of raw ``sqlite3.connect`` to survive the
    "unable to open database file" failure mode reported when a concurrent
    writer holds the ``-wal``/``-shm`` files (Windows lock semantics).
    """
    report: dict = {
        "db_path": str(db_path),
        "exists": db_path.exists(),
        "checks": [],
        "verdict": "UNKNOWN",
    }
    if not db_path.exists():
        report["verdict"] = "ABSENT"
        report["checks"].append({"name": "db_present", "status": "FAIL",
                                 "detail": "console.db missing"})
        return report

    # Use connect_ro for WAL safety. Wrap in a class to keep the cursor /
    # check helper API stable for the body below.
    try:
        ro_ctx = connect_ro(db_path)
        conn = ro_ctx.__enter__()
    except (sqlite3.Error, OSError) as e:
        report["verdict"] = "UNREADABLE"
        report["checks"].append({
            "name": "db_open",
            "status": "FAIL",
            "detail": f"cannot open DB: {e}",
        })
        return report

    cur = conn.cursor()

    def check(name: str, status: str, detail: str) -> None:
        report["checks"].append({"name": name, "status": status, "detail": detail})

    # v7.0.0-alpha — SQLite reveals DB corruption (malformed magic bytes,
    # truncated page header, etc.) only at the first query, not at open.
    # If the DB exists but is corrupt, we want verdict=UNREADABLE rather
    # than a half-filled report that misleads the operator.
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
    except sqlite3.DatabaseError as e:
        report["verdict"] = "UNREADABLE"
        report["checks"].append({
            "name": "db_open",
            "status": "FAIL",
            "detail": f"DB exists but unreadable: {e}",
        })
        try:
            ro_ctx.__exit__(None, None, None)
        except Exception:
            pass
        return report
    required = {"runs", "token_usage", "events", "context_budget"}
    missing = required - tables
    if missing:
        check("schema", "FAIL", f"missing tables: {sorted(missing)}")
    else:
        check("schema", "PASS", f"{len(tables)} tables present")

    # 2. Test pollution by command name
    if "runs" in tables:
        cur.execute(
            f"SELECT command, COUNT(*) FROM runs WHERE command IN "
            f"({','.join('?' * len(TEST_POLLUTION_COMMANDS))}) GROUP BY command",
            tuple(TEST_POLLUTION_COMMANDS),
        )
        rows = cur.fetchall()
        if rows:
            check("test_pollution_commands", "FAIL",
                  f"found test-artifact commands: {dict(rows)}")
        else:
            check("test_pollution_commands", "PASS",
                  "no test-artifact commands detected")

    # 3. NULL run_id rate in token_usage
    if "token_usage" in tables:
        cur.execute("SELECT COUNT(*) FROM token_usage WHERE run_id IS NULL")
        nulls = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM token_usage")
        total = cur.fetchone()[0]
        if total == 0:
            check("token_usage_present", "WARN",
                  "table empty — no telemetry yet (run /sdd-full to baseline)")
        else:
            pct = 100.0 * nulls / total
            if pct > 50:
                check("token_usage_run_id_null_rate", "FAIL",
                      f"{nulls}/{total} ({pct:.1f}%) rows have NULL run_id — "
                      f"pre-v7.0.1 fix or test pollution")
            elif pct > 10:
                check("token_usage_run_id_null_rate", "WARN",
                      f"{nulls}/{total} ({pct:.1f}%) rows have NULL run_id")
            else:
                check("token_usage_run_id_null_rate", "PASS",
                      f"{nulls}/{total} ({pct:.1f}%) rows have NULL run_id")

        # 4. Sanity floor on per-run token volumes
        cur.execute(
            "SELECT run_id, SUM(input_tokens), SUM(output_tokens) "
            "FROM token_usage WHERE run_id IS NOT NULL GROUP BY run_id"
        )
        suspicious = []
        for run_id, sum_in, sum_out in cur.fetchall():
            if (sum_in or 0) < MIN_REAL_INPUT_TOKENS_PER_RUN and \
               (sum_out or 0) < MIN_REAL_OUTPUT_TOKENS_PER_RUN:
                suspicious.append({"run_id": run_id, "in": sum_in, "out": sum_out})
        if suspicious:
            check("token_volume_sanity", "WARN",
                  f"{len(suspicious)} runs below realistic token floors "
                  f"(in<{MIN_REAL_INPUT_TOKENS_PER_RUN} AND "
                  f"out<{MIN_REAL_OUTPUT_TOKENS_PER_RUN}) — likely test data")

    try:
        ro_ctx.__exit__(None, None, None)
    except Exception:
        pass  # best-effort RO context closure

    # Final verdict
    statuses = {c["status"] for c in report["checks"]}
    if "FAIL" in statuses:
        report["verdict"] = "POLLUTED"
    elif "WARN" in statuses:
        report["verdict"] = "SUSPECT"
    else:
        report["verdict"] = "CLEAN"
    return report


def main() -> int:
    p = argparse.ArgumentParser(
        description="Verify console.db telemetry health (anti test pollution)"
    )
    p.add_argument("--db", default=None,
                   help="DB path (default: workspace/output/db/console.db)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--fail-on", choices=("polluted", "suspect"), default="polluted",
                   help="Exit non-zero if verdict matches (default: polluted)")
    args = p.parse_args()

    db_path = Path(args.db) if args.db else \
        repo_root() / "workspace" / "output" / "db" / "console.db"
    report = audit_db(db_path)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"DB: {report['db_path']}")
        print(f"Verdict: {report['verdict']}")
        for c in report["checks"]:
            print(f"  [{c['status']}] {c['name']}: {c['detail']}")

    fail_set = {"polluted", "suspect"} if args.fail_on == "suspect" else {"polluted"}
    return OK if report["verdict"].lower() not in fail_set else INFRA_BLOCKED


if __name__ == "__main__":
    sys.exit(main())
