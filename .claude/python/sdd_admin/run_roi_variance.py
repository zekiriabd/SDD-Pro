#!/usr/bin/env python3
"""SDD_Pro PoC ROI variance helper (v7.0.0 release-critical, 2026-05-20).

Calcule la variance des métriques ROI sur N runs d'une même FEAT M
matérialisée. Critère release v7.0.0 (cf. docs/roadmap-v7-v8.md §3) :
variance ≤ 15 % sur wall-clock + tokens + coût USD.

Ce script **ne lance PAS** les `/sdd-full` lui-même — Claude Code slash
commands sont user-triggered. Il agrège les `runs` déjà persistés dans
`console.db` pour une FEAT donnée et calcule la variance.

Procédure utilisateur :

  1. Choisir une FEAT M (ex. FEAT 2 — 3 US fullstack).
  2. Optionnel : `rm -rf workspace/output/src/{Backend|App}Name/` pour
     forcer un cold start (cache vide, données représentatives).
  3. Lancer 3× la slash command :
     /sdd-full 2
     /sdd-full 2 --rebuild-arch
     /sdd-full 2 --rebuild-arch
     (entre chaque run, `sleep 30` pour éviter le cache prompt 5min)
  4. Lancer ce script :
     python -m sdd_admin.run_roi_variance --feat 2

Le script :
  - Lit les N derniers runs `/sdd-full` pour la FEAT depuis `runs`
  - Agrège tokens depuis `token_usage` (scoped run_id grâce au fix
    v7.0.0 record_token_usage.py)
  - Calcule médiane + variance pour : wall_clock_ms, cost_usd,
    input_tokens, output_tokens, cache_hit_rate
  - Émet un verdict release ELIGIBLE / NOT_ELIGIBLE selon seuil 15 %
  - Persiste le rapport dans
    `workspace/output/qa/roi-variance-feat-{n}.{md,json}`

Usage:
    python -m sdd_admin.run_roi_variance --feat {n} [--n-runs 3]
                                          [--threshold-pct 15]
                                          [--json]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect_ro  # noqa: E402
from sdd_lib.paths import iso_now_ms, repo_root  # noqa: E402

# Pricing table (mirror report_roi.py + preflight_cost_cap.py — keep in sync)
PRICING = {
    "claude-opus-4-7":    {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_creation": 18.75},
    "claude-sonnet-4-6":  {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-haiku-4-5":   {"input":  1.00, "output":  5.00, "cache_read": 0.10, "cache_creation":  1.25},
}
FALLBACK_PRICING = PRICING["claude-sonnet-4-6"]


def _compute_cost(rows: list[Any]) -> float:
    total = 0.0
    for r in rows:
        model = r["model"] or ""
        p = PRICING.get(model, FALLBACK_PRICING)
        total += (r["input_tokens"] or 0) * p["input"] / 1_000_000
        total += (r["output_tokens"] or 0) * p["output"] / 1_000_000
        total += (r["cache_creation_tokens"] or 0) * p["cache_creation"] / 1_000_000
        total += (r["cache_read_tokens"] or 0) * p["cache_read"] / 1_000_000
    return total


def _variance_pct(values: list[float]) -> float:
    """Coefficient of variation = stddev / mean × 100."""
    if not values or len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0
    return statistics.stdev(values) / mean * 100


def collect_runs(feat_n: int, n_runs: int) -> list[dict[str, Any]]:
    """Collect last `n_runs` /sdd-full runs for FEAT, with aggregated metrics."""
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT run_id, started_at, ended_at, status FROM runs "
            "WHERE feat_n = ? AND command LIKE '%sdd-full%' "
            "ORDER BY started_at DESC LIMIT ?",
            (feat_n, n_runs),
        )
        run_rows = cur.fetchall()
        if not run_rows:
            return []

        runs = []
        for r in run_rows:
            run_id = r["run_id"]
            # Aggregate token_usage by exact run_id (v7.0.0 column)
            cur.execute(
                "SELECT model, input_tokens, output_tokens, "
                "       cache_creation_tokens, cache_read_tokens "
                "FROM token_usage WHERE run_id = ?",
                (run_id,),
            )
            tok_rows = cur.fetchall()
            sum_in    = sum((t["input_tokens"] or 0) for t in tok_rows)
            sum_out   = sum((t["output_tokens"] or 0) for t in tok_rows)
            sum_cread = sum((t["cache_read_tokens"] or 0) for t in tok_rows)
            sum_ccrea = sum((t["cache_creation_tokens"] or 0) for t in tok_rows)
            cost = _compute_cost(tok_rows)
            # Wall-clock
            from datetime import datetime
            try:
                started = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
                ended   = datetime.fromisoformat((r["ended_at"] or r["started_at"]).replace("Z", "+00:00"))
                wall_ms = int((ended - started).total_seconds() * 1000)
            except Exception:
                wall_ms = 0
            # Cache hit rate
            denom = sum_in + sum_cread
            cache_hit_pct = (sum_cread / denom * 100) if denom > 0 else 0.0

            runs.append({
                "run_id": run_id,
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "status": r["status"],
                "wall_clock_ms": wall_ms,
                "tokens_input": sum_in,
                "tokens_output": sum_out,
                "tokens_cache_read": sum_cread,
                "tokens_cache_creation": sum_ccrea,
                "cost_usd": cost,
                "cache_hit_pct": cache_hit_pct,
                "agent_calls": len(tok_rows),
            })
    return runs


def compute_variance(runs: list[dict[str, Any]], threshold_pct: float) -> dict[str, Any]:
    metrics = ("wall_clock_ms", "cost_usd", "tokens_input", "tokens_output", "cache_hit_pct")
    summary: dict[str, Any] = {"n_runs": len(runs), "threshold_pct": threshold_pct, "metrics": {}}

    eligible = True
    for m in metrics:
        values = [r[m] for r in runs if r[m] is not None]
        median = statistics.median(values) if values else 0
        var_pct = _variance_pct(values) if len(values) >= 2 else None
        passes = (var_pct is None) or (var_pct <= threshold_pct)
        if var_pct is not None and var_pct > threshold_pct:
            eligible = False
        summary["metrics"][m] = {
            "values": values,
            "median": median,
            "variance_pct": var_pct,
            "passes": passes,
        }
    summary["eligible_v7_release"] = eligible and len(runs) >= 3
    return summary


def render_markdown(feat_n: int, runs: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    out = []
    out.append(f"# SDD_Pro ROI Variance — FEAT {feat_n} (v7.0.0 release-critical)")
    out.append("")
    out.append(f"Generated : `{iso_now_ms()}`")
    out.append(f"Runs collected : {summary['n_runs']}")
    out.append(f"Threshold variance : {summary['threshold_pct']}%")
    out.append("")
    out.append("## Runs détail")
    out.append("")
    out.append("| # | run_id | wall_clock | tokens billed | cost USD | cache hit | status |")
    out.append("|---|---|---:|---:|---:|---:|---|")
    for i, r in enumerate(runs, 1):
        wall_min = r["wall_clock_ms"] / 60_000
        billed = r["tokens_input"] + r["tokens_output"] + r["tokens_cache_read"] + r["tokens_cache_creation"]
        out.append(
            f"| {i} | `{r['run_id'][:8]}` | {wall_min:.1f}min | "
            f"{billed:,} | ${r['cost_usd']:.2f} | "
            f"{r['cache_hit_pct']:.1f}% | {r['status']} |"
        )

    out.append("")
    out.append("## Variance par métrique")
    out.append("")
    out.append("| Métrique | Médiane | Variance % | Seuil | Verdict |")
    out.append("|---|---:|---:|---:|:---:|")
    for m, data in summary["metrics"].items():
        var = data["variance_pct"]
        if var is None:
            verdict = "n/a (need ≥ 2 runs)"
            var_str = "n/a"
        else:
            verdict = "OK" if data["passes"] else "FAIL"
            var_str = f"{var:.1f}%"
        out.append(f"| {m} | {data['median']:.2f} | {var_str} | {summary['threshold_pct']}% | {verdict} |")

    out.append("")
    out.append("## Verdict release v7.0.0")
    out.append("")
    if summary["eligible_v7_release"]:
        out.append("**ELIGIBLE** — toutes métriques sous seuil variance + ≥ 3 runs.")
        out.append("Tag v7.0.0 final autorisé (sous réserve revue 2 mainteneurs).")
    else:
        if summary["n_runs"] < 3:
            out.append(f"**NOT_ELIGIBLE** — seulement {summary['n_runs']} run(s), critère release exige ≥ 3.")
        else:
            out.append("**NOT_ELIGIBLE** — au moins une métrique dépasse le seuil variance.")
        out.append("Action : lancer des runs supplémentaires OU investiguer l'outlier.")
    return "\n".join(out) + "\n"


def main() -> int:
    # Windows console : force UTF-8 to avoid charmap crash on emoji/symbols
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--feat", type=int, required=True)
    p.add_argument("--n-runs", type=int, default=3)
    p.add_argument("--threshold-pct", type=float, default=15.0)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    runs = collect_runs(args.feat, args.n_runs)
    if not runs:
        print(f"ERROR : aucun run /sdd-full trouvé pour FEAT {args.feat}", file=sys.stderr)
        return 1

    summary = compute_variance(runs, args.threshold_pct)

    if args.json:
        print(json.dumps({"feat_n": args.feat, "runs": runs, "summary": summary},
                         indent=2, default=str))
    else:
        md = render_markdown(args.feat, runs, summary)
        out_path = repo_root() / "workspace" / "output" / "qa" / f"roi-variance-feat-{args.feat}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(md)
        print(f"\nReport saved : {out_path.as_posix()}")

    return 0 if summary["eligible_v7_release"] else 2


if __name__ == "__main__":
    sys.exit(main())
