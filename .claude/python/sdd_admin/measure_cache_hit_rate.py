#!/usr/bin/env python3
"""SDD_Pro cache hit-rate monitor (Levier 1b, v7.0.x).

Parses Claude Code session logs (`~/.claude/projects/<encoded-cwd>/*.jsonl`)
and computes the prompt-cache hit rate against the annotations declared
in `loader.yml`. Distinct from `cache_manifest.py` (which exports the
*intended* manifest): this script measures *actual* cache usage over a
recent window.

Why we can measure even without v7.1 harness wiring:
    Claude Code already requests prompt caching automatically. Anthropic
    populates `usage.cache_read_input_tokens` and
    `usage.cache_creation_input_tokens` on every assistant turn. The
    baseline reported in `docs/cache-strategy.md` (40.8% hit, 2026-05-20)
    was measured this way.

Usage::

    # Default (current SDD_Pro repo, last 7 days)
    python -m sdd_admin.measure_cache_hit_rate

    # Wider window
    python -m sdd_admin.measure_cache_hit_rate --days 30

    # Explicit logs dir (override auto-detect)
    python -m sdd_admin.measure_cache_hit_rate --logs-dir "C:/Users/.../c--DEV-SDD-Pro"

    # JSON output (CI / dashboards)
    python -m sdd_admin.measure_cache_hit_rate --json

Output (human)::

    === Cache hit rate (last 7 days, 142 turns) ===
    cache_read       :   312,450 tokens (38.2%)
    cache_creation   :    98,210 tokens (12.0%)
    input (no cache) :   406,120 tokens (49.7%)
                       ---------
    total input      :   816,780 tokens
    output           :    72,310 tokens

    Breakdown (cache_creation):
      ephemeral_5m   :    98,210 tokens (100%)
      ephemeral_1h   :         0 tokens (0%)

Exit codes:
  0 = SUCCESS — report produced
  1 = CORRECTIBLE — no logs found (give --logs-dir or check directory)
  2 = FAIL_FAST — invalid arg / malformed log
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402


@dataclass
class CacheStats:
    turns: int = 0
    input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    output_tokens: int = 0
    ephemeral_5m: int = 0
    ephemeral_1h: int = 0
    per_model: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total_input(self) -> int:
        return (
            self.input_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )

    @property
    def cache_hit_rate(self) -> float:
        t = self.total_input
        return (self.cache_read_input_tokens / t) if t else 0.0

    @property
    def cache_write_rate(self) -> float:
        t = self.total_input
        return (self.cache_creation_input_tokens / t) if t else 0.0


def encode_path_for_claude_logs(path: Path) -> str:
    """Mirror Claude Code's filesystem-safe encoding of project paths.

    Examples (Windows):
        C:\\DEV\\SDD-Pro       → c--DEV-SDD-Pro
        C:\\DEV\\compart\\SDD_Pro → c--DEV-compart-SDD_Pro
    """
    s = str(path.resolve())
    if not s:
        return s
    s = s[0].lower() + s[1:]
    return s.replace(":", "-").replace("\\", "-").replace("/", "-")


def auto_detect_logs_dir(repo: Path | None = None) -> Path | None:
    """Find the Claude Code logs directory for a given repo, by trying the
    expected encoding first, then scanning for matches by basename."""
    if repo is None:
        repo = repo_root()
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return None
    expected = projects / encode_path_for_claude_logs(repo)
    if expected.is_dir():
        return expected
    basename = repo.name
    candidates = [
        p for p in projects.iterdir()
        if p.is_dir() and basename.replace("_", "-").lower() in p.name.replace("_", "-").lower()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def iter_jsonl_files(logs_dir: Path) -> list[Path]:
    """Return every *.jsonl under logs_dir (recursive, includes subagents/)."""
    return sorted(logs_dir.rglob("*.jsonl"))


def parse_logs(logs_dir: Path, since_epoch: float | None = None) -> CacheStats:
    stats = CacheStats()
    for jsonl in iter_jsonl_files(logs_dir):
        if since_epoch is not None and jsonl.stat().st_mtime < since_epoch:
            continue
        try:
            with open(jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = obj.get("message")
                    if not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    stats.turns += 1
                    stats.input_tokens += int(usage.get("input_tokens", 0) or 0)
                    stats.cache_read_input_tokens += int(
                        usage.get("cache_read_input_tokens", 0) or 0
                    )
                    stats.cache_creation_input_tokens += int(
                        usage.get("cache_creation_input_tokens", 0) or 0
                    )
                    stats.output_tokens += int(usage.get("output_tokens", 0) or 0)
                    cc = usage.get("cache_creation") or {}
                    if isinstance(cc, dict):
                        stats.ephemeral_5m += int(cc.get("ephemeral_5m_input_tokens", 0) or 0)
                        stats.ephemeral_1h += int(cc.get("ephemeral_1h_input_tokens", 0) or 0)
                    model = msg.get("model")
                    if isinstance(model, str):
                        bucket = stats.per_model.setdefault(model, {
                            "turns": 0, "input": 0, "cache_read": 0,
                            "cache_creation": 0, "output": 0,
                        })
                        bucket["turns"] += 1
                        bucket["input"] += int(usage.get("input_tokens", 0) or 0)
                        bucket["cache_read"] += int(
                            usage.get("cache_read_input_tokens", 0) or 0
                        )
                        bucket["cache_creation"] += int(
                            usage.get("cache_creation_input_tokens", 0) or 0
                        )
                        bucket["output"] += int(usage.get("output_tokens", 0) or 0)
        except OSError:
            continue
    return stats


def format_report(stats: CacheStats, days: int) -> str:
    if stats.turns == 0:
        return "No assistant turns found in the time window."

    t = stats.total_input
    cr = stats.cache_read_input_tokens
    cc = stats.cache_creation_input_tokens
    raw = stats.input_tokens

    def pct(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole else "0.0%"

    lines = []
    lines.append(f"=== Cache hit rate (last {days} days, {stats.turns} turns) ===")
    lines.append(f"cache_read       : {cr:>11,} tokens ({pct(cr, t)})")
    lines.append(f"cache_creation   : {cc:>11,} tokens ({pct(cc, t)})")
    lines.append(f"input (no cache) : {raw:>11,} tokens ({pct(raw, t)})")
    lines.append(f"                   ---------")
    lines.append(f"total input      : {t:>11,} tokens")
    lines.append(f"output           : {stats.output_tokens:>11,} tokens")
    lines.append("")
    lines.append("Breakdown (cache_creation):")
    e5 = stats.ephemeral_5m
    e1 = stats.ephemeral_1h
    total_cc = e5 + e1
    lines.append(f"  ephemeral_5m   : {e5:>11,} tokens ({pct(e5, total_cc)})")
    lines.append(f"  ephemeral_1h   : {e1:>11,} tokens ({pct(e1, total_cc)})")

    if stats.per_model:
        lines.append("")
        lines.append("Per model:")
        for model, b in sorted(stats.per_model.items()):
            bt = b["input"] + b["cache_read"] + b["cache_creation"]
            lines.append(
                f"  {model:<32} turns={b['turns']:>4}  "
                f"hit={pct(b['cache_read'], bt):>6}  "
                f"write={pct(b['cache_creation'], bt):>6}"
            )

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Measure prompt-cache hit rate from Claude Code logs")
    p.add_argument("--logs-dir", help="Override auto-detected logs directory")
    p.add_argument("--days", type=int, default=7, help="Look-back window in days (default 7)")
    p.add_argument("--json", action="store_true", help="JSON output for CI / dashboards")
    args = p.parse_args()

    if args.logs_dir:
        logs_dir = Path(args.logs_dir)
        if not logs_dir.is_dir():
            print(f"FAIL: logs dir not found: {logs_dir}", file=sys.stderr)
            return FAIL_FAST
    else:
        logs_dir = auto_detect_logs_dir()
        if logs_dir is None:
            print(
                "FAIL: could not auto-detect Claude Code logs directory. "
                "Pass --logs-dir explicitly (e.g. ~/.claude/projects/c--DEV-SDD-Pro).",
                file=sys.stderr,
            )
            return CORRECTIBLE

    if args.days <= 0:
        print(f"FAIL: --days must be > 0 (got {args.days})", file=sys.stderr)
        return FAIL_FAST

    since = time.time() - args.days * 86400
    stats = parse_logs(logs_dir, since_epoch=since)

    if args.json:
        out = {
            "logs_dir": str(logs_dir),
            "days": args.days,
            "turns": stats.turns,
            "input_tokens": stats.input_tokens,
            "cache_read_input_tokens": stats.cache_read_input_tokens,
            "cache_creation_input_tokens": stats.cache_creation_input_tokens,
            "output_tokens": stats.output_tokens,
            "total_input_tokens": stats.total_input,
            "cache_hit_rate": round(stats.cache_hit_rate, 4),
            "cache_write_rate": round(stats.cache_write_rate, 4),
            "ephemeral_5m_input_tokens": stats.ephemeral_5m,
            "ephemeral_1h_input_tokens": stats.ephemeral_1h,
            "per_model": stats.per_model,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(format_report(stats, args.days))

    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
