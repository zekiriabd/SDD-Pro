#!/usr/bin/env python3
"""SDD_Pro Context budget gate.

Makes .claude/loader.yml executable:
- expands `reads:` patterns per agent
- rejects unbounded globs (anti context bomb)
- enforces per-agent byte budget
- v6.10 BREAKING : writes to console.db (table `context_budget`) as the
  single source of truth. Legacy JSONL ledger at
  workspace/output/.sys/.audit/context-budget.jsonl is no longer the
  primary sink ; only emitted when `--out-file` is explicitly provided
  (backward-compat for tests / explicit overrides).

Migrated from .claude/scripts/context-budget.ps1 (2026-05-13).

Usage:
    python context_budget.py --agent po [--feat-number 1] [--us-id 1-2]
                             [--json] [--allow-unbounded-globs]

Exit codes:
    0 = pass (within budget, no errors)
    1 = errors (BUDGET_EXCEEDED, UNBOUNDED_GLOB)
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect, ensure_initialized, insert_context_budget  # noqa: E402
from sdd_lib.loader_yml import parse_agent_section  # noqa: E402
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.project_config import (  # noqa: E402  (legacy fallback)
    get_active_stack_paths,
    read_project_config,
)
from sdd_lib.layered_config import read_layered_config  # noqa: E402  (v6.7.3)
from sdd_lib.stderr import warn  # noqa: E402


#: Agents acceptable AS `--agent` CLI choice (current v7.0.0 surface).
#: Must stay in sync with `sdd_hooks.preflight_agent_budget.ALLOWED_AGENTS`.
#: Drift = hook would reject Agent spawns that this script accepts on CLI,
#: producing inconsistent budget signals.
CURRENT_AGENTS: tuple[str, ...] = (
    # Core + support (4 + 3)
    "po", "arch", "dev-backend", "dev-frontend",
    "qa", "elicitor", "constitutioner",
    # Auditors retained in v7.0.0 (4 + 1 opt-in)
    "code-reviewer",
    "security-reviewer",
    "spec-compliance-reviewer",
    "arch-reviewer",
    # Adversarial reviewer (R1 v7.2.0 opt-in, informational verdict).
    # Audit 2026-06-06 RUPT-1 — sync avec preflight_agent_budget.ALLOWED_AGENTS.
    "adversarial-reviewer",
)

#: Read-side compat list for historical `console.db` rows produced by
#: agents retired in v7.0.0 (governance-major-auditors-trim). Used by
#: `DEFAULT_BUDGETS` lookups and `recompute --backfill` only — NEVER as
#: argparse choice (a new `--agent dashboard` spawn must be rejected by
#: the hook, so it must also be rejected here for sanity).
RETIRED_AGENTS_V7: tuple[str, ...] = (
    "dashboard",
    "accessibility-auditor",
    "performance-auditor",
)

#: Legacy alias kept for any external script that imports this name.
#: Prefer `CURRENT_AGENTS` in new code. v7.1: remove this alias.
ALLOWED_AGENTS: tuple[str, ...] = CURRENT_AGENTS + RETIRED_AGENTS_V7

# Default byte budgets per agent (mirrors PowerShell defaults)
DEFAULT_BUDGETS: dict[str, int] = {
    "po":            60_000,
    "elicitor":      70_000,
    "arch":         180_000,
    "constitutioner":  90_000,   # security audit 2026-06-06 — manquant, KeyError sur invocation
    "dev-backend":  220_000,
    "dev-frontend": 240_000,
    "qa":           280_000,
    "dashboard":    180_000,
    # Auditors — les 5 reviewers cross-fichier scannent le code matérialisé
    # complet (workspace/output/src/{AppName,BackendName}/**) qui pèse
    # facilement 2-3 MB sur une FEAT moyenne. Budget calé à 4 MB (= ~1 Mtok)
    # pour absorber le scope réel. L'anti-context-bomb reste effectif via
    # [UNBOUNDED_GLOB] (refus des reads sans borne FEAT/US).
    # accessibility-auditor garde un budget serré : il ne lit que l'HTML/
    # markup (US + mockups), pas le code prod.
    "accessibility-auditor":     80_000,   # Haiku, scan WCAG déterministe (HTML/markup)
    "code-reviewer":          4_000_000,   # Sonnet, anti-patterns cross-fichier
    "arch-reviewer":          4_000_000,   # Sonnet, layer mapping + ADRs §6
    "security-reviewer":      4_000_000,   # Sonnet, OWASP scan + threat-model
    "performance-auditor":    4_000_000,   # Sonnet, CWV + SLO heuristiques
    "spec-compliance-reviewer": 4_000_000, # Sonnet, AC-by-AC re-lecture code
    # Audit 2026-06-06 RUPT-1 — adversarial-reviewer (R1 v7.2.0 opt-in).
    # Sonnet 4.6. Read-only sur workspace/output/qa/feat-{n}/ (consolidated
    # review reports) + workspace/output/src/{App,Backend}Name/** (code).
    # Verdict purement informational, jamais bloquant — mais consomme un
    # budget équivalent aux 4 autres reviewers (mêmes patterns de lecture).
    "adversarial-reviewer":   4_000_000,
}

# Exclude these from context budget
EXCLUDE_DIR_RE = re.compile(r"(^|/)(node_modules|bin|obj|TestResults|build|dist|coverage)(/|$)")
EXCLUDE_CSS_RE = re.compile(r"/wwwroot/css/(bootstrap|open-iconic)/")
EXCLUDE_EXT_RE = re.compile(r"\.(dll|exe|pdb|cache|map|woff|ttf|otf|eot|ico|png|jpg|jpeg|svg)$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SDD_Pro context budget gate")
    # v7.0.0 : CLI accepts only CURRENT_AGENTS (aligned with hook). Retired
    # agents (RETIRED_AGENTS_V7) keep their DEFAULT_BUDGETS entries for
    # `recompute --backfill` over historical console.db rows, but new CLI
    # invocations with `--agent dashboard|accessibility-auditor|
    # performance-auditor` are rejected with argparse's standard
    # "invalid choice" — matches the hook's REJECTED_AGENTS_V7 behavior.
    p.add_argument("--agent", required=True, choices=CURRENT_AGENTS)
    p.add_argument("--feat-number", type=int, default=0)
    p.add_argument("--us-id", default="")
    p.add_argument("--repo-root", default=None)
    p.add_argument("--run-id", default=None)
    p.add_argument("--out-file", default=None)
    p.add_argument("--json", action="store_true", help="Emit JSON record to stdout")
    p.add_argument("--allow-unbounded-globs", action="store_true")
    p.add_argument("--bytes-per-token", type=int, default=4)
    p.add_argument("--input-usd-per-million-tokens", type=float, default=3.0)
    return p.parse_args()


def is_excluded(rel_path: str) -> bool:
    return bool(
        EXCLUDE_DIR_RE.search(rel_path)
        or EXCLUDE_CSS_RE.search(rel_path)
        or EXCLUDE_EXT_RE.search(rel_path)
    )


def is_unbounded_glob(pattern: str) -> bool:
    """A glob is unbounded if it has wildcards AND no FEAT/US/Name placeholder."""
    if "*" not in pattern and "?" not in pattern:
        return False
    # Bounded by US, FEAT, or project context
    bounded_markers = (
        "{n}", "{n}-{m}", "feat-{n}", "{AppName}", "{BackendName}",
        "{LibName}", "{Project}",
    )
    if any(m in pattern for m in bounded_markers):
        return False
    # Whitelist: ADR-* sous .sys/.context/adrs/ (bounded by timestamp prefix)
    if pattern == "workspace/output/.sys/.context/adrs/ADR-*.md":
        return False
    return True


def resolve_pattern(
    pattern: str,
    config: dict[str, str],
    us_id: str,
    feat_number: int,
    root: Path,
) -> list[str]:
    """Expand `{n}`, `{n}-{m}`, `{AppName}`, `{cat}/{active}` placeholders."""
    if "{cat}/{active}" in pattern:
        return get_active_stack_paths(root)

    m = re.match(r"^\.claude/stacks/([^/]+)/\{active\}\.md$", pattern)
    if m:
        cat = m.group(1)
        return [p for p in get_active_stack_paths(root) if p.startswith(f".claude/stacks/{cat}/")]

    out = pattern
    if us_id:
        out = out.replace("{n}-{m}", us_id)
    if feat_number > 0:
        out = out.replace("{n}", str(feat_number))
    for key in ("AppName", "BackendName", "LibName"):
        if key in config:
            out = out.replace("{" + key + "}", config[key])

    # Multi-project expansion via {Project}
    if "{Project}" in out:
        results: list[str] = []
        for key in ("AppName", "BackendName", "LibName"):
            if config.get(key):
                results.append(out.replace("{Project}", config[key]))
        return results

    # If unresolved placeholders remain (other than {Project}), skip
    if re.search(r"\{[A-Za-z][A-Za-z0-9_]*\}", out):
        return []

    return [out]


# Dirs prunés AVANT descente lors d'un rglob — évite que workspace/output/src
# explose le scan (~170k fichiers node_modules sur le bench local 2.7GB).
# Audit perf 2026-06-06 : excludes étaient appliqués via fnmatch APRÈS rglob
# complet, donc la traversal coûtait le full I/O. Prune dirs à la racine ici
# pour réduire à ~50ms typique.
_PRUNE_DIRS: frozenset[str] = frozenset({
    "node_modules", ".git", "__pycache__", ".pytest_cache",
    ".cache", "dist", "build", "out", "target",
    "bin", "obj", ".next", ".nuxt", ".vite", ".turbo",
    ".gradle", ".idea", ".vscode", ".vs",
    "coverage", ".coverage", "htmlcov",
    ".venv", "venv", "env",
})


def _expand_braces(pattern: str) -> list[str]:
    """Expand `{a,b,c}` braces — fnmatch ne les supporte pas nativement.

    Exemple : `*.{back,front}.md` → ['*.back.md', '*.front.md']
    Récursif sur les braces multiples : `{a,b}/{c,d}.md` → 4 résultats.
    """
    m = re.search(r"\{([^{}]+)\}", pattern)
    if not m:
        return [pattern]
    alternatives = m.group(1).split(",")
    head = pattern[: m.start()]
    tail = pattern[m.end():]
    expanded: list[str] = []
    for alt in alternatives:
        expanded.extend(_expand_braces(head + alt.strip() + tail))
    return expanded


def _walk_pruned(base: Path):
    """Generator: yield only files, prune known noise dirs avant descente."""
    try:
        entries = list(base.iterdir())
    except (OSError, PermissionError):
        return
    for entry in entries:
        try:
            if entry.is_dir():
                if entry.name in _PRUNE_DIRS:
                    continue
                yield from _walk_pruned(entry)
            elif entry.is_file():
                yield entry
        except (OSError, PermissionError):
            continue


def expand_files(pattern: str, root: Path) -> list[Path]:
    """Resolve a (possibly glob) pattern against the repo root and return files."""
    # Expand braces first : loader.yml uses {back,front}, {n}-{m}-*, etc.
    sub_patterns = _expand_braces(pattern)
    if len(sub_patterns) > 1:
        out: list[Path] = []
        for sub in sub_patterns:
            out.extend(expand_files(sub, root))
        # Dédupliquer (préserver ordre)
        seen: set[Path] = set()
        deduped: list[Path] = []
        for p in out:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        return deduped

    full = root / pattern
    if "*" not in pattern and "?" not in pattern:
        if full.is_file():
            return [full]
        if full.is_dir():
            return [p for p in full.iterdir() if p.is_file()]
        return []

    # Manual rglob: find the longest non-wildcard prefix, scan recursively
    parts = pattern.split("/")
    fixed_parts: list[str] = []
    for part in parts:
        if "*" in part or "?" in part:
            break
        fixed_parts.append(part)
    base = root.joinpath(*fixed_parts) if fixed_parts else root
    while not base.exists() and len(fixed_parts) > 0:
        fixed_parts.pop()
        base = root.joinpath(*fixed_parts) if fixed_parts else root
    if not base.exists():
        return []

    if base.is_file():
        return [base]

    # Walk pruné (excludes AVANT descente) + fnmatch
    out: list[Path] = []
    for p in _walk_pruned(base):
        rel = normalize(p.relative_to(root))
        if fnmatch.fnmatch(rel, pattern):
            out.append(p)
    return out


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    root = Path(args.repo_root).resolve() if args.repo_root else repo_root()

    run_id = args.run_id or uuid.uuid4().hex
    # --out-file kept for backward-compat (tests / explicit overrides) but no
    # longer the default sink: telemetry now lives in console.db (table
    # context_budget). When --out-file is set, we also write JSONL for caller
    # debug, otherwise only the DB row is written.
    out_file = Path(args.out_file) if args.out_file else None

    reads = parse_agent_section(args.agent, "reads", root=root)
    # v6.7.3: layered config with legacy fallback
    try:
        config = read_layered_config(root=root)
    except Exception:  # noqa: BLE001
        config = read_project_config(root=root)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    expanded: list[dict[str, Any]] = []
    seen: set[str] = set()

    for read_pat in reads:
        if is_unbounded_glob(read_pat) and not args.allow_unbounded_globs:
            errors.append({
                "code": "UNBOUNDED_GLOB",
                "pattern": read_pat,
                "message": "Glob sans borne FEAT/US refuse",
            })
            continue

        resolved_paths = resolve_pattern(
            read_pat, config, args.us_id, args.feat_number, root
        )
        for resolved in resolved_paths:
            files = expand_files(resolved, root)
            if not files and ("*" not in resolved and "?" not in resolved):
                warnings.append({
                    "code": "READ_MISSING",
                    "pattern": resolved,
                    "message": "Read declare mais fichier absent",
                })
                continue
            for fp in files:
                try:
                    rel = normalize(fp.relative_to(root))
                except ValueError:
                    rel = normalize(fp)
                if rel in seen:
                    continue
                if is_excluded(rel):
                    continue
                try:
                    size = fp.stat().st_size
                except OSError:
                    continue
                seen.add(rel)
                expanded.append({
                    "path": rel,
                    "bytes": size,
                    "sourcePattern": read_pat,
                })

    total_bytes = sum(e["bytes"] for e in expanded)
    estimated_tokens = math.ceil(total_bytes / max(args.bytes_per_token, 1))
    budget_bytes = DEFAULT_BUDGETS[args.agent]
    budget_tokens = math.ceil(budget_bytes / max(args.bytes_per_token, 1))

    if total_bytes > budget_bytes:
        errors.append({
            "code": "BUDGET_EXCEEDED",
            "message": (
                f"Context bytes {total_bytes} > budget {budget_bytes} "
                f"for agent {args.agent}"
            ),
        })

    elapsed_ms = int((time.monotonic() - started) * 1000)
    cost = round((estimated_tokens / 1_000_000.0) * args.input_usd_per_million_tokens, 6)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runId": run_id,
        "agent": args.agent,
        "FeatNumber": args.feat_number if args.feat_number > 0 else None,
        "usId": args.us_id or None,
        "result": "pass" if not errors else "fail",
        "files": len(expanded),
        "bytes": total_bytes,
        "estimatedInputTokens": estimated_tokens,
        "budgetBytes": budget_bytes,
        "budgetTokens": budget_tokens,
        "estimatedInputCostUsd": cost,
        "elapsedMs": elapsed_ms,
        "errors": errors,
        "warnings": warnings,
    }

    # Primary sink: console.db (single source of truth).
    ensure_initialized()
    with connect() as conn:
        insert_context_budget(
            conn,
            agent=args.agent,
            tokens_used=estimated_tokens,
            tokens_budget=budget_tokens,
            passed=not errors,
            feat_n=args.feat_number if args.feat_number > 0 else None,
            us_id=args.us_id or None,
        )

    # Optional backward-compat JSONL (only when --out-file is explicitly passed).
    if out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    if args.json:
        print(json.dumps(record, indent=2))
    else:
        print(
            f"context-budget {args.agent}: {len(expanded)} files, "
            f"{total_bytes} bytes, ~{estimated_tokens} tokens / "
            f"budget ~{budget_tokens} tokens, USD {cost}"
        )
        for w in warnings:
            warn(f"WARN  {w['code']}: {w['pattern']}")
        for e in errors:
            warn(f"ERROR {e['code']}: {e['message']}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
