"""P0.4 — Orchestrateur des 20 runs go/no-go (plan §9 tâches 0.4-0.5).

Question : « Codex sait-il émuler l'orchestration de sous-agents isolés
dont dépendent 26 commandes SDD-Pro, de façon assez fiable ? »
Critère chiffré (plan §9 tâche 0.5) : GO si >= 95 % de complétions
parseables sur 20 runs de tâches synthétiques représentatives.

Usage (une fois `codex` installé et authentifié — cf. README.md) :
    python .sdd/experiments/p04-codex-subagent/run_experiment.py
Options : --runs 20 --max-parallel 2 --codex-bin codex --model <m>
          --timeout-s 180 --threshold 0.95

Écrit results/p04-report-{timestamp}.{json,md} + imprime le verdict.
Exit code : 0 = GO, 1 = NO-GO, 2 = erreur d'orchestration.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from spawn_agent_codex import CodexConfig, spawn_agent  # noqa: E402

DEFAULT_RUNS = 20
DEFAULT_THRESHOLD = 0.95
DEFAULT_MAX_PARALLEL = 2   # parallélisme borné — item (c) du plan §9 t.0.4


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def load_fixtures(fixtures_dir: Path) -> list:
    fixtures = []
    for path in sorted(fixtures_dir.glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            fx = json.load(fh)
        for key in ("id", "system_prompt", "task", "schema"):
            if key not in fx:
                raise ValueError(f"Fixture invalide {path.name}: clé "
                                 f"'{key}' absente")
        fixtures.append(fx)
    if not fixtures:
        raise ValueError(f"Aucune fixture *.json dans {fixtures_dir}")
    return fixtures


def plan_runs(fixtures: list, total_runs: int) -> list:
    """Affecte les runs aux fixtures en round-robin (20 runs / 4 fixtures
    = 5 runs chacune)."""
    return [fixtures[i % len(fixtures)] for i in range(total_runs)]


# ---------------------------------------------------------------------------
# Agrégation / verdict (pur, testé unitairement)
# ---------------------------------------------------------------------------

def compute_verdict(results: list, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Calcule le verdict go/no-go à partir des résultats spawn_agent.

    results : liste de dicts {fixture_id, ok, latency_ms, error_class, ...}
    """
    total = len(results)
    ok_count = sum(1 for r in results if r["ok"])
    rate = (ok_count / total) if total else 0.0

    latencies = sorted(r["latency_ms"] for r in results)
    median_latency = statistics.median(latencies) if latencies else 0

    error_distribution: dict = {}
    for r in results:
        if r["error_class"]:
            error_distribution[r["error_class"]] = (
                error_distribution.get(r["error_class"], 0) + 1)

    per_fixture: dict = {}
    for r in results:
        stats = per_fixture.setdefault(
            r["fixture_id"], {"runs": 0, "ok": 0})
        stats["runs"] += 1
        stats["ok"] += 1 if r["ok"] else 0

    return {
        "total_runs": total,
        "parseable_ok": ok_count,
        "parseable_rate": round(rate, 4),
        "threshold": threshold,
        "verdict": "GO" if rate >= threshold else "NO-GO",
        "median_latency_ms": median_latency,
        "error_distribution": error_distribution,
        "per_fixture": per_fixture,
    }


# ---------------------------------------------------------------------------
# Rapports
# ---------------------------------------------------------------------------

def render_md(summary: dict, results: list, cfg: CodexConfig,
              max_parallel: int) -> str:
    v = summary["verdict"]
    icon = "🟢" if v == "GO" else "🔴"
    lines = [
        "# P0.4 — Rapport go/no-go : émulation sous-agents Codex",
        "",
        f"- Date : {datetime.now(timezone.utc).isoformat()}",
        f"- Binaire : `{cfg.codex_bin}` — modèle : "
        f"`{cfg.model or '(défaut codex)'}` — timeout : {cfg.timeout_s}s "
        f"— parallélisme borné : {max_parallel}",
        "",
        f"## Verdict : {icon} **{v}** "
        f"({summary['parseable_ok']}/{summary['total_runs']} complétions "
        f"parseables = {summary['parseable_rate'] * 100:.1f} % ; "
        f"seuil {summary['threshold'] * 100:.0f} %)",
        "",
        f"Latence médiane par spawn : **{summary['median_latency_ms']} ms**",
        "",
        "## Distribution des classes d'erreur",
        "",
    ]
    if summary["error_distribution"]:
        lines += ["| Classe | Occurrences |", "|---|---:|"]
        for cls, n in sorted(summary["error_distribution"].items(),
                             key=lambda kv: -kv[1]):
            lines.append(f"| `{cls}` | {n} |")
    else:
        lines.append("Aucune erreur.")
    lines += ["", "## Par fixture", "", "| Fixture | OK / runs |", "|---|---|"]
    for fid, st in sorted(summary["per_fixture"].items()):
        lines.append(f"| {fid} | {st['ok']}/{st['runs']} |")
    lines += ["", "## Runs détaillés", "",
              "| # | Fixture | ok | latence (ms) | error_class |",
              "|---:|---|:---:|---:|---|"]
    for i, r in enumerate(results, 1):
        lines.append(f"| {i} | {r['fixture_id']} | "
                     f"{'✅' if r['ok'] else '❌'} | {r['latency_ms']} | "
                     f"{r['error_class'] or '—'} |")
    lines += [
        "",
        "## Décision (plan §9 t.0.5)",
        "",
        "- **GO** → `spawn_mode: emulated` viable ; Phase 3 (adaptateur "
        "Codex) peut être engagée après P1/P2.",
        "- **NO-GO** → périmètre Codex réduit à « commandes mono-agent » "
        "(dégradation affichée) + re-priorisation Gemini.",
        "",
        "Annexer ce verdict à l'ADR "
        "`.sdd/docs/adrs/ADR-20260724T164529-harness-and-provider-"
        "abstraction.md` (section go/no-go P0.4).",
        "",
    ]
    return "\n".join(lines)


def write_reports(summary: dict, results: list, cfg: CodexConfig,
                  max_parallel: int, results_dir: Path) -> tuple:
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = results_dir / f"p04-report-{ts}.json"
    md_path = results_dir / f"p04-report-{ts}.md"

    payload = {
        "experiment": "p04-codex-subagent",
        "generated": datetime.now(timezone.utc).isoformat(),
        "config": {"codex_bin": cfg.codex_bin, "model": cfg.model,
                   "timeout_s": cfg.timeout_s, "sandbox": cfg.sandbox,
                   "max_parallel": max_parallel},
        "summary": summary,
        "runs": [{k: r[k] for k in
                  ("fixture_id", "ok", "latency_ms", "error_class")}
                 for r in results],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        render_md(summary, results, cfg, max_parallel), encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_experiment(fixtures: list, cfg: CodexConfig, total_runs: int,
                   max_parallel: int, spawn=spawn_agent) -> list:
    """Exécute `total_runs` spawns (pool borné à `max_parallel`) et
    retourne les résultats annotés fixture_id, dans l'ordre des runs."""
    planned = plan_runs(fixtures, total_runs)

    def one(idx_fx):
        idx, fx = idx_fx
        res = spawn(fx["system_prompt"], fx["task"], fx["schema"], cfg)
        res["fixture_id"] = fx["id"]
        print(f"  run {idx + 1:>2}/{total_runs} [{fx['id']}] "
              f"{'OK' if res['ok'] else res['error_class']} "
              f"({res['latency_ms']} ms)", flush=True)
        return idx, res

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        indexed = list(pool.map(one, enumerate(planned)))
    return [res for _, res in sorted(indexed, key=lambda x: x[0])]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="P0.4 — 20 runs go/no-go émulation sous-agents Codex")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--max-parallel", type=int,
                        default=DEFAULT_MAX_PARALLEL)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--codex-bin",
                        default=os.environ.get("SDD_CODEX_BIN", "codex"))
    parser.add_argument("--model",
                        default=os.environ.get("SDD_CODEX_MODEL") or None)
    parser.add_argument("--timeout-s", type=float,
                        default=float(os.environ.get("SDD_CODEX_TIMEOUT_S",
                                                     "180")))
    parser.add_argument("--fixtures-dir", type=Path,
                        default=HERE / "fixtures")
    parser.add_argument("--results-dir", type=Path, default=HERE / "results")
    args = parser.parse_args(argv)

    try:
        fixtures = load_fixtures(args.fixtures_dir)
    except (ValueError, OSError) as exc:
        print(f"ERROR: chargement fixtures impossible\n"
              f"CAUSE: [NOT_FOUND] {exc}\n"
              f"FIX: vérifier {args.fixtures_dir}", file=sys.stderr)
        return 2

    cfg = CodexConfig(codex_bin=args.codex_bin, model=args.model,
                      timeout_s=args.timeout_s)

    print(f"[P0.4] {args.runs} runs × {len(fixtures)} fixtures — "
          f"binaire `{cfg.codex_bin}`, parallélisme {args.max_parallel}, "
          f"timeout {cfg.timeout_s}s")
    results = run_experiment(fixtures, cfg, args.runs, args.max_parallel)
    summary = compute_verdict(results, args.threshold)
    json_path, md_path = write_reports(summary, results, cfg,
                                       args.max_parallel, args.results_dir)

    icon = "🟢" if summary["verdict"] == "GO" else "🔴"
    print(f"\n{icon} VERDICT {summary['verdict']} "
          f"(≥{args.threshold * 100:.0f}% requis) — "
          f"{summary['parseable_ok']}/{summary['total_runs']} parseables "
          f"({summary['parseable_rate'] * 100:.1f} %), "
          f"latence médiane {summary['median_latency_ms']} ms")
    if summary["error_distribution"]:
        print(f"   erreurs : {summary['error_distribution']}")
    print(f"   rapports : {json_path}\n              {md_path}")
    return 0 if summary["verdict"] == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
