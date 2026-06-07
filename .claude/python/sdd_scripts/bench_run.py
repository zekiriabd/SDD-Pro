#!/usr/bin/env python3
"""SDD_Pro: bench_run — snapshot-based ROI measurement (v7.0.0+).

Capture l'etat console.db + sdd_state avant/apres un /sdd-full, calcule
les deltas tokens/cout/temps/qualite et produit un rapport JSON conforme
au protocole `docs/benchmarks/README.md`.

Resout la critique audit v7.0.0-alpha §4.1 :
    « 100 % des cellules <TBD> dans roi-baseline.md — la valeur business
      n'est pas quantifiee. »

Usage:
    # Avant /sdd-full
    python bench_run.py --snapshot-before --bench-id bench-s-dotnet-run-1

    # Apres /sdd-full
    python bench_run.py --snapshot-after \\
        --bench-id bench-s-dotnet-run-1 \\
        --wallclock-min 11.7 \\
        --feat-n 1 \\
        --output docs/benchmarks/runs/bench-s-dotnet-run-1.json

Snapshots stocked sous workspace/output/.sys/.bench/snapshots/{bench_id}.json.

Exit codes:
    0  success (snapshot ou rapport produit)
    1  missing console.db (TokenUsageMode != record probablement)
    2  invalid args (bench-id, paths)
    3  snapshot-before manquant pour snapshot-after
    4  IO error

Pricing applique (dollars per million tokens, v7.0.0) :
    sonnet-4-6 :  input $3.00, output $15.00, cache_read $0.30
    opus-4-7   :  input $15.00, output $75.00, cache_read $1.50
    haiku-4-5  :  input $1.00, output $5.00,  cache_read $0.10
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.atomic_write import atomic_write_text  # noqa: E402
from sdd_lib.pricing import PRICING, get_pricing  # noqa: E402

# ---------------------------------------------------------------------------
# Pricing — SSoT delegated to sdd_lib.pricing (audit CTO 2026-06-07).
# Pre-fix, this module redefined a local PRICING dict with short aliases
# (`sonnet`, `opus`, `haiku`) which drifted from sdd_lib SSoT. Any Anthropic
# price change required two PRs. Now we import the canonical table and use
# `get_pricing(model)` which falls back to Sonnet pricing on unknown ids.
# ---------------------------------------------------------------------------


def _console_db_path() -> Path:
    """Console DB location (v6.10+ : workspace/output/db/console.db).

    Fallback to legacy workspace/console/console.db for old projects.
    """
    primary = repo_root() / "workspace" / "output" / "db" / "console.db"
    if primary.is_file():
        return primary
    return repo_root() / "workspace" / "console" / "console.db"


def _bench_dir() -> Path:
    d = repo_root() / "workspace" / "output" / ".sys" / ".bench" / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_path(bench_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in bench_id)
    return _bench_dir() / f"{safe}.json"


def _iso_now() -> str:
    """Thin wrapper around `sdd_lib.paths.iso_now` — kept as `_iso_now`
    for backward-compat with internal callers (audit consolidé 2026-06-07
    Sprint 2 : factorisation 5 impls iso_now → 1 SSoT)."""
    from sdd_lib.paths import iso_now
    return iso_now()


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    cur = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


# Whitelist of all identifiers (column + table names) that may be interpolated
# into f-string SQL in this module. Defense-in-depth: even though `cols` comes
# from `PRAGMA table_info(token_usage)` (DB-driven, not user input), explicit
# whitelisting makes any future code modification fail-fast on unknown idents.
# Audit P0-doc 2026-06-05.
_SAFE_SQL_IDENTS: frozenset[str] = frozenset({
    # token_usage columns
    "model", "model_name",
    "input_tokens", "tokens_input",
    "output_tokens", "tokens_output",
    "cache_read_input_tokens", "cache_read_tokens",
    # qa_* tables
    "qa_coverage", "qa_quality", "qa_api_gate", "qa_code_review",
    "qa_security", "qa_spec_compliance", "qa_arch_review", "qa_a11y", "qa_performance",
    # other tables
    "context_budget", "token_usage",
})


def _safe_ident(name: str) -> str:
    """Return `name` if it's in the whitelist, else raise ValueError.

    Use whenever interpolating an identifier into f-string SQL. Prevents
    even hypothetical SQL injection via a future code path that lets user
    input reach this site.
    """
    if name not in _SAFE_SQL_IDENTS:
        raise ValueError(f"unsafe SQL identifier: {name!r} (not in whitelist)")
    return name


def _query_token_usage(con: sqlite3.Connection) -> dict:
    """Aggregate token_usage table : counts per model + total."""
    if not _table_exists(con, "token_usage"):
        return {"rows": 0, "by_model": {}, "total_rows": 0}

    # Get column names dynamically (schema may evolve)
    cols = {row[1] for row in con.execute("PRAGMA table_info(token_usage)")}
    model_col = "model" if "model" in cols else ("model_name" if "model_name" in cols else None)
    input_col = "input_tokens" if "input_tokens" in cols else "tokens_input"
    output_col = "output_tokens" if "output_tokens" in cols else "tokens_output"
    cache_col = (
        "cache_read_input_tokens"
        if "cache_read_input_tokens" in cols
        else ("cache_read_tokens" if "cache_read_tokens" in cols else None)
    )

    if model_col is None:
        return {"rows": 0, "by_model": {}, "total_rows": 0, "note": "schema mismatch"}

    # Belt + braces: ensure every identifier we interpolate is in the whitelist
    model_col = _safe_ident(model_col)
    input_col = _safe_ident(input_col)
    output_col = _safe_ident(output_col)
    if cache_col is not None:
        cache_col = _safe_ident(cache_col)

    cache_select = f", COALESCE(SUM({cache_col}), 0)" if cache_col else ", 0"
    sql = (
        f"SELECT {model_col}, COUNT(*), "
        f"COALESCE(SUM({input_col}), 0), COALESCE(SUM({output_col}), 0){cache_select} "
        "FROM token_usage GROUP BY 1"
    )

    by_model = {}
    total_rows = 0
    for row in con.execute(sql):
        model, count, t_in, t_out, t_cache = row
        by_model[model or "unknown"] = {
            "invocations": count,
            "input": int(t_in),
            "output": int(t_out),
            "cache_read": int(t_cache),
        }
        total_rows += count
    return {"by_model": by_model, "total_rows": total_rows}


def _query_qa_tables(con: sqlite3.Connection) -> dict:
    """Pull row counts from qa_* tables (auditor results)."""
    qa_tables = (
        "qa_coverage",
        "qa_quality",
        "qa_api_gate",
        "qa_code_review",
        "qa_security",
        "qa_spec_compliance",
        "qa_arch_review",
    )
    out = {}
    for t in qa_tables:
        if _table_exists(con, t):
            safe_t = _safe_ident(t)  # belt + braces (t is already hardcoded above)
            (count,) = con.execute(f"SELECT COUNT(*) FROM {safe_t}").fetchone()
            out[t] = count
    return out


def _query_context_budget(con: sqlite3.Connection) -> dict:
    if not _table_exists(con, "context_budget"):
        return {"rows": 0}
    (count,) = con.execute("SELECT COUNT(*) FROM context_budget").fetchone()
    return {"rows": count}


def _read_sdd_state_runs() -> list[dict]:
    """List sdd_state.run-*.json files with basic metadata."""
    state_dir = repo_root() / "workspace" / "output" / ".sys" / ".state"
    if not state_dir.is_dir():
        return []
    runs = []
    for f in sorted(state_dir.glob("run-*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            runs.append({
                "file": f.name,
                "run_id": data.get("run_id"),
                "started_at": data.get("started_at"),
                "ended_at": data.get("ended_at"),
                "status": data.get("status"),
                "feat_number": data.get("feat_number"),
                "phases": list((data.get("phases") or {}).keys()),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return runs


def _count_validation_reports(feat_n: int | None) -> dict:
    """Count auditor reports for a specific FEAT."""
    if feat_n is None:
        return {}
    val_dir = repo_root() / "workspace" / "output" / ".sys" / ".validation"
    qa_dir = repo_root() / "workspace" / "output" / "qa" / f"feat-{feat_n}"
    out = {}
    if val_dir.is_dir():
        out["code_review"] = bool((val_dir / f"{feat_n}-code-review.json").is_file())
        out["security_scan"] = bool((val_dir / f"{feat_n}-security-scan.json").is_file())
        out["spec_compliance"] = bool((val_dir / f"{feat_n}-spec-compliance.json").is_file())
        out["arch_review"] = bool((val_dir / f"{feat_n}-arch-review.json").is_file())
        out["readiness"] = bool((val_dir / f"{feat_n}-readiness.md").is_file())
    if qa_dir.is_dir():
        out["coverage"] = (qa_dir / "coverage.json").is_file()
        out["quality"] = (qa_dir / "quality.json").is_file()
        out["api_tests"] = (qa_dir / "api-tests.json").is_file()
    return out


def _extract_verdicts(feat_n: int | None) -> dict:
    """Parse auditor JSON for verdicts (GREEN/WARN/RED)."""
    if feat_n is None:
        return {}
    val_dir = repo_root() / "workspace" / "output" / ".sys" / ".validation"
    qa_dir = repo_root() / "workspace" / "output" / "qa" / f"feat-{feat_n}"
    out = {}
    files = {
        "code_review": val_dir / f"{feat_n}-code-review.json",
        "security_scan": val_dir / f"{feat_n}-security-scan.json",
        "spec_compliance": val_dir / f"{feat_n}-spec-compliance.json",
        "arch_review": val_dir / f"{feat_n}-arch-review.json",
        "coverage": qa_dir / "coverage.json",
        "api_tests": qa_dir / "api-tests.json",
    }
    for name, path in files.items():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            verdict = data.get("verdict") or data.get("status") or data.get("summary", {}).get("verdict")
            out[name] = verdict
        except (OSError, json.JSONDecodeError):
            out[name] = "PARSE_ERROR"
    return out


def _compute_cost(by_model: dict) -> dict:
    """Compute USD cost per model + total.

    Uses sdd_lib.pricing.get_pricing which falls back to Sonnet pricing on
    unknown model ids (audit CTO 2026-06-07 — removed local PRICING dup).
    """
    out = {"by_model": {}, "total_usd": 0.0}
    for model, tokens in by_model.items():
        price = get_pricing(model)
        cost = (
            tokens["input"] * price["input"] / 1_000_000
            + tokens["output"] * price["output"] / 1_000_000
            + tokens["cache_read"] * price["cache_read"] / 1_000_000
        )
        out["by_model"][model] = {"cost_usd": round(cost, 4)}
        out["total_usd"] += cost
    out["total_usd"] = round(out["total_usd"], 4)
    return out


def _capture_state(bench_id: str) -> dict:
    """Capture full current state for snapshot."""
    db_path = _console_db_path()
    if not db_path.is_file():
        return {
            "bench_id": bench_id,
            "captured_at": _iso_now(),
            "db_present": False,
            "note": "console.db absent - TokenUsageMode probably 'off'",
        }
    state: dict = {
        "bench_id": bench_id,
        "captured_at": _iso_now(),
        "db_present": True,
    }
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            state["token_usage"] = _query_token_usage(con)
            state["qa_tables"] = _query_qa_tables(con)
            state["context_budget"] = _query_context_budget(con)
    except sqlite3.Error as exc:
        state["db_error"] = str(exc)
    state["sdd_state_runs"] = _read_sdd_state_runs()
    return state


def _delta(before: dict, after: dict) -> dict:
    """Compute delta (after - before) for aggregated counts."""
    delta = {"by_model": {}, "total_invocations": 0}
    b_models = before.get("token_usage", {}).get("by_model", {})
    a_models = after.get("token_usage", {}).get("by_model", {})
    all_models = set(b_models) | set(a_models)
    for m in all_models:
        b = b_models.get(m, {"invocations": 0, "input": 0, "output": 0, "cache_read": 0})
        a = a_models.get(m, {"invocations": 0, "input": 0, "output": 0, "cache_read": 0})
        delta["by_model"][m] = {
            "invocations": a["invocations"] - b["invocations"],
            "input": a["input"] - b["input"],
            "output": a["output"] - b["output"],
            "cache_read": a["cache_read"] - b["cache_read"],
        }
        delta["total_invocations"] += delta["by_model"][m]["invocations"]
    return delta


def _build_report(
    before: dict, after: dict, bench_id: str, wallclock_min: float | None, feat_n: int | None
) -> dict:
    delta_tokens = _delta(before, after)
    cost = _compute_cost(delta_tokens["by_model"])

    # Identify the run_id triggered between before and after
    b_runs = {r.get("run_id") for r in before.get("sdd_state_runs", [])}
    a_runs = after.get("sdd_state_runs", [])
    new_runs = [r for r in a_runs if r.get("run_id") and r.get("run_id") not in b_runs]

    report = {
        "bench_id": bench_id,
        "captured_at": _iso_now(),
        "wallclock_min": wallclock_min,
        "feat_number": feat_n,
        "snapshot_before_at": before.get("captured_at"),
        "snapshot_after_at": after.get("captured_at"),
        "tokens_delta": delta_tokens,
        "cost": cost,
        "qa_outputs": _count_validation_reports(feat_n),
        "verdicts": _extract_verdicts(feat_n),
        "new_runs": new_runs,
        "summary": {
            "wallclock_min": wallclock_min,
            "total_cost_usd": cost["total_usd"],
            "total_invocations": delta_tokens["total_invocations"],
            "auditor_artifacts_present": sum(
                1 for v in _count_validation_reports(feat_n).values() if v
            ),
        },
    }
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot-based bench measurement for /sdd-full runs")
    parser.add_argument("--snapshot-before", action="store_true", help="capture pre-run state")
    parser.add_argument("--snapshot-after", action="store_true", help="capture post-run + emit report")
    parser.add_argument("--bench-id", required=True, help="e.g. bench-s-dotnet-run-1")
    parser.add_argument("--wallclock-min", type=float, default=None, help="wall-clock duration in minutes")
    parser.add_argument("--feat-n", type=int, default=None, help="FEAT number for validation lookup")
    parser.add_argument("--output", type=Path, default=None, help="report JSON output path (snapshot-after)")
    args = parser.parse_args()

    if args.snapshot_before == args.snapshot_after:
        parser.error("specify exactly one of --snapshot-before / --snapshot-after")

    if args.snapshot_before:
        state = _capture_state(args.bench_id)
        path = _snapshot_path(args.bench_id)
        atomic_write_text(path, json.dumps(state, indent=2, ensure_ascii=False, default=str))
        print(f"[OK] snapshot-before saved: {path.relative_to(repo_root())}")
        if not state.get("db_present"):
            print("[WARN] console.db missing - TokenUsageMode likely 'off' ; bench will lack token data")
            return FAIL_FAST
        return SUCCESS
    # snapshot-after path
    before_path = _snapshot_path(args.bench_id)
    if not before_path.is_file():
        print(f"[FAIL] snapshot-before not found: {before_path}", file=sys.stderr)
        print("       Run with --snapshot-before first.", file=sys.stderr)
        return INFRA_BLOCKED
    try:
        before = json.loads(before_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] cannot read snapshot-before: {exc}", file=sys.stderr)
        return 4

    after = _capture_state(args.bench_id)
    report = _build_report(before, after, args.bench_id, args.wallclock_min, args.feat_n)

    # Persist after-snapshot too (for forensic re-runs)
    after_path = _bench_dir() / f"{args.bench_id}.after.json"
    atomic_write_text(after_path, json.dumps(after, indent=2, ensure_ascii=False, default=str))

    # Write report
    out_path = args.output or (_bench_dir().parent / "reports" / f"{args.bench_id}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_path, json.dumps(report, indent=2, ensure_ascii=False, default=str))

    print(f"[OK] report saved: {out_path.relative_to(repo_root())}")
    print(f"     wallclock_min   : {report['summary']['wallclock_min']}")
    print(f"     total_cost_usd  : {report['summary']['total_cost_usd']}")
    print(f"     invocations     : {report['summary']['total_invocations']}")
    print(f"     auditor outputs : {report['summary']['auditor_artifacts_present']}")
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
