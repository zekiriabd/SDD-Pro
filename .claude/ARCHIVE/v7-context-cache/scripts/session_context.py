"""SDD_Pro session context — Niveau 5 (Persistent Sessions, v6.10.5).

Reifies a "persistent session" from existing console.db tables. The
`run_id` allocated by ``sdd_state.py`` at the start of ``/sdd-full {n}``
serves as the session identity. All sub-agents invoked during this run
(po, arch, dev-*, qa, dashboard, auditors) share it via the orchestrator.

This module composes a compact **session digest** (~3-8 KB) from :
    - runs               (header : run_id, feat_n, status, current_phase)
    - run_phases         (timeline : phase, status, started/ended)
    - events             (last N : gate decisions, fallbacks, errors)
    - context_budget     (per-agent token usage on this run)
    - token_usage        (real cost per agent + cache hit ratio)

Consumed by agents at STEP 0 (post-context-registry, before re-reading
heavy sources) to know "what happened so far in this run" — enabling :
    - skipping work already done by a prior agent in this session
    - resuming after a fail without re-deducing context
    - cross-agent decision coherence (no contradiction with earlier
      build_loop iterations or QA verdicts)

Today's Claude Code subagent model is stateless ; this module provides
the **orchestrator-side state** that agents can voluntarily Read. The
v7 design (native Claude session-id passthrough) is described in
``ADR-{ts}-governance-major-persistent-sessions``.
"""
from __future__ import annotations

import json
from typing import Any

from sdd_lib.console_db import connect_ro


def latest_run(feat_n: int | None = None) -> dict | None:
    """Return the most-recent run row (filtered by feat_n if given)."""
    try:
        with connect_ro() as conn:
            if feat_n is not None:
                row = conn.execute(
                    """
                    SELECT * FROM runs WHERE feat_n = ?
                    ORDER BY started_at DESC LIMIT 1
                    """,
                    (feat_n,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
            return dict(row) if row else None
    except FileNotFoundError:
        return None


def run_phases(run_id: str) -> list[dict]:
    try:
        with connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT phase, status, started_at, ended_at, payload_json
                  FROM run_phases WHERE run_id = ? ORDER BY id
                """,
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]
    except FileNotFoundError:
        return []


def recent_events(run_id: str, limit: int = 30) -> list[dict]:
    try:
        with connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT ts, event_type, agent, phase, us_id, payload_json
                  FROM events WHERE run_id = ? ORDER BY id DESC LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
    except FileNotFoundError:
        return []


def run_token_usage(run_id: str) -> dict[str, dict]:
    """Aggregate token_usage rows by agent for this run."""
    out: dict[str, dict] = {}
    try:
        with connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT agent,
                       SUM(input_tokens)          AS input_tokens,
                       SUM(output_tokens)         AS output_tokens,
                       SUM(cache_read_tokens)     AS cache_read_tokens,
                       SUM(cache_creation_tokens) AS cache_creation_tokens,
                       COUNT(*)                   AS calls
                  FROM token_usage WHERE run_id = ? GROUP BY agent
                """,
                (run_id,),
            ).fetchall()
            for r in rows:
                d = dict(r)
                input_tot = d.get("input_tokens") or 0
                cache_read = d.get("cache_read_tokens") or 0
                d["cache_hit_ratio"] = (
                    round(cache_read / (input_tot + cache_read), 3)
                    if (input_tot + cache_read) > 0 else 0.0
                )
                out[d["agent"]] = d
            return out
    except FileNotFoundError:
        return {}


def run_context_budget(run_id_or_feat: dict) -> list[dict]:
    """Context budget rows filtered by feat_n (no run_id column in this
    table — schema legacy)."""
    feat_n = run_id_or_feat.get("feat_n")
    if feat_n is None:
        return []
    try:
        with connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT ts, agent, us_id, tokens_used, tokens_budget, passed
                  FROM context_budget WHERE feat_n = ?
                  ORDER BY id DESC LIMIT 50
                """,
                (feat_n,),
            ).fetchall()
            return [dict(r) for r in rows]
    except FileNotFoundError:
        return []


def build_session_digest(
    *,
    run_id: str | None = None,
    feat_n: int | None = None,
    events_limit: int = 20,
) -> dict[str, Any]:
    """Compose a compact session view for the latest (or specified) run.

    Returns ``None`` if no matching run exists.
    """
    if run_id is None:
        run = latest_run(feat_n=feat_n)
    else:
        try:
            with connect_ro() as conn:
                row = conn.execute(
                    "SELECT * FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                run = dict(row) if row else None
        except FileNotFoundError:
            run = None

    if run is None:
        return {
            "available": False,
            "reason": "no_run_found",
            "hint": (
                "Aucun run /sdd-full enregistré dans console.db. "
                "Lance /sdd-full {n} d'abord OU pré-initialise via "
                "sdd_state.py."
            ),
        }

    run_id = run["run_id"]
    phases = run_phases(run_id)
    events = recent_events(run_id, limit=events_limit)
    tokens = run_token_usage(run_id)
    budgets = run_context_budget(run)

    # Compute aggregate cache hit ratio across all agents on this run.
    total_input = sum((t.get("input_tokens") or 0) for t in tokens.values())
    total_cache_read = sum((t.get("cache_read_tokens") or 0) for t in tokens.values())
    overall_cache_hit = (
        round(total_cache_read / (total_input + total_cache_read), 3)
        if (total_input + total_cache_read) > 0 else 0.0
    )

    return {
        "available": True,
        "session_id": run_id,
        "feat_n": run.get("feat_n"),
        "feat_name": run.get("feat_name"),
        "command": run.get("command"),
        "status": run.get("status"),
        "current_phase": run.get("current_phase"),
        "started_at": run.get("started_at"),
        "updated_at": run.get("updated_at"),
        "phases": phases,
        "recent_events": events,
        "token_usage_by_agent": tokens,
        "context_budget_recent": budgets[:10],  # last 10 entries
        "summary": {
            "total_phases": len(phases),
            "phases_done": sum(1 for p in phases if p.get("status") in ("success", "skipped")),
            "phases_failed": sum(1 for p in phases if p.get("status") == "failed"),
            "total_input_tokens": total_input,
            "total_cache_read_tokens": total_cache_read,
            "overall_cache_hit_ratio": overall_cache_hit,
            "agents_active": len(tokens),
        },
    }


def render_session_digest_md(digest: dict) -> str:
    """Render the session digest as a compact Markdown document
    suitable for direct injection into an agent system prompt."""
    if not digest.get("available"):
        return (
            "# Session Digest — SDD_Pro v6.10.5\n\n"
            "> Aucun run actif. Le digest sera matérialisé dès le "
            "premier `/sdd-full {n}`.\n\n"
            f"Raison : {digest.get('reason', 'unknown')}\n"
        )

    lines: list[str] = []
    lines.append("# Session Digest — SDD_Pro v6.10.5")
    lines.append("")
    lines.append("> Reified persistent session (Niveau 5) from console.db tables.")
    lines.append("> Stable for the duration of a single `/sdd-full` run ; refreshed")
    lines.append("> at each phase transition. Cache key : `cache_005`.")
    lines.append("")
    lines.append("## Session header")
    lines.append("")
    lines.append(f"- **run_id** : `{digest['session_id']}`")
    lines.append(f"- **feat** : {digest['feat_n']}-{digest['feat_name']}")
    lines.append(f"- **command** : `{digest['command']}`")
    lines.append(f"- **status** : `{digest['status']}`")
    lines.append(f"- **current_phase** : `{digest['current_phase']}`")
    lines.append(f"- **started_at** : {digest['started_at']}")
    lines.append(f"- **updated_at** : {digest['updated_at']}")
    lines.append("")

    summary = digest["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Métrique | Valeur |")
    lines.append(f"|---|---:|")
    lines.append(f"| Phases totales | {summary['total_phases']} |")
    lines.append(f"| Phases done | {summary['phases_done']} |")
    lines.append(f"| Phases failed | {summary['phases_failed']} |")
    lines.append(f"| Agents actifs (run) | {summary['agents_active']} |")
    lines.append(f"| Input tokens cumulés | {summary['total_input_tokens']:,} |")
    lines.append(f"| Cache read tokens cumulés | {summary['total_cache_read_tokens']:,} |")
    lines.append(f"| **Cache hit ratio global** | **{summary['overall_cache_hit_ratio']:.1%}** |")
    lines.append("")

    if digest["phases"]:
        lines.append("## Timeline phases")
        lines.append("")
        lines.append("| Phase | Status | Started | Ended |")
        lines.append("|---|---|---|---|")
        for ph in digest["phases"]:
            lines.append(
                f"| `{ph['phase']}` | {ph['status']} | "
                f"{ph.get('started_at') or '—'} | "
                f"{ph.get('ended_at') or '—'} |"
            )
        lines.append("")

    if digest["token_usage_by_agent"]:
        lines.append("## Token usage par agent")
        lines.append("")
        lines.append("| Agent | Calls | Input | Cache read | Cache hit | Output |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for agent, t in sorted(digest["token_usage_by_agent"].items()):
            lines.append(
                f"| `{agent}` | {t.get('calls') or 0} | "
                f"{(t.get('input_tokens') or 0):,} | "
                f"{(t.get('cache_read_tokens') or 0):,} | "
                f"{t.get('cache_hit_ratio', 0):.1%} | "
                f"{(t.get('output_tokens') or 0):,} |"
            )
        lines.append("")

    if digest["recent_events"]:
        lines.append(f"## {len(digest['recent_events'])} derniers events")
        lines.append("")
        for ev in digest["recent_events"][:10]:
            agent_str = f"`{ev['agent']}`" if ev.get('agent') else "—"
            phase_str = f"phase=`{ev['phase']}`" if ev.get('phase') else ""
            lines.append(
                f"- `{ev['ts']}` · `{ev['event_type']}` · {agent_str} {phase_str}"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*Digest régénérable : `compile_session_digest.py` (idempotent). "
        "Le `run_id` est la clé session naturelle reifiée depuis "
        "`sdd_state.py`.*"
    )
    return "\n".join(lines) + "\n"
