"""db_tier_router.py — per-object model tier routing for db-reverse.

db-reverse used to route in binary: an object was either `simple` (deterministic
template, 0 token) or `complex` (the analyst agent, always at its `deep` tier).
Between a three-line CRUD accessor and a 400-line transactional orchestrator
with dynamic SQL there is a wide middle — legible business logic that a
mid-tier model reads perfectly well — and paying the deep tier for all of it is
waste, while paying a mid tier for the hard cases is worse than waste.

This module grades each SQL object into one of four lanes:

    none      nothing to read, or nothing an LLM would add   -> 0 token
    fast      short, legible, single-effect logic
    balanced  real business logic, statically readable
    deep      logic that requires reasoning about what is NOT written down

**It returns a tier name, never a model name.** The mapping tier -> model is the
provider's job (`.sdd/providers/*.yaml` `tier_map`), so the same rubric routes
to Opus / Sonnet / Haiku on Anthropic, Gemini Pro / Flash / Flash-Lite on
Google, and the OpenAI reasoning / general / mini lane on OpenAI, without this
module knowing any of them. The reverse module never imports `sdd_lib` (D4
isolation invariant), so the resolution happens in the harness, downstream.

The grade is returned WITH its reasons, so the orchestrator, the User Story
banner and the audit trail all agree on why a given tier was spent on a given
object.

Public API:
    tier_for(record)          -> (tier, reasons)
    clamp(tier, floor, ceiling) -> tier
    plan_tiers(records)       -> dict (per-object grades + cost-shape summary)
"""
from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = 1

TIERS = ("none", "fast", "balanced", "deep")
_RANK = {t: i for i, t in enumerate(TIERS)}

# Thresholds. Calibrated on synthetic corpora; expected to be revisited after
# the first run against a real database, like the clustering thresholds.
FAST_MAX_LINES = 40
BALANCED_MAX_LINES = 200
FAST_MAX_BRANCHES = 2
BALANCED_MAX_BRANCHES = 12
DEEP_FAN_IN = 6


def _at_least(current: str, candidate: str) -> str:
    return candidate if _RANK[candidate] > _RANK[current] else current


def tier_for(rec: dict[str, Any]) -> tuple[str, list[str]]:
    """Grade one SQL object, and say why.

    The rubric escalates: every signal can only push the tier UP, never down, so
    the order of the checks does not change the verdict — only the reasons read
    in a stable order.
    """
    reasons: list[str] = []

    # An encrypted body cannot be read by any model at any price. The pipeline
    # emits a deterministic low-confidence User Story with a banner instead of
    # paying a model to speculate.
    if rec.get("encrypted"):
        return "none", ["encrypted-body"]

    tier = "none"

    def bump(candidate: str, reason: str) -> None:
        nonlocal tier
        before = tier
        tier = _at_least(tier, candidate)
        if tier != before or reason not in reasons:
            reasons.append(reason)

    lines = rec.get("lineCount") or 0
    branches = rec.get("branches") or 0
    calls = rec.get("callsProcs") or []
    written = rec.get("tablesWritten") or []
    params = rec.get("params") or []

    # --- what makes an object worth reading at all -------------------------
    if branches:
        bump("fast" if branches <= FAST_MAX_BRANCHES else "balanced",
             f"branches={branches}")
    if rec.get("raises"):
        # A raised error is a business precondition, and preconditions are the
        # acceptance criteria a reader most often needs.
        bump("fast", "raises=" + ",".join(sorted(rec.get("raises") or [])[:3]))
    if lines > FAST_MAX_LINES:
        bump("balanced", f"lines={lines}")
    # Params alone are not a complexity signal: a getter/setter with 7 params but
    # zero branches, zero raises and zero calls is still trivially readable — the
    # 2026-08-26 run showed 6 Insert/Update procedures with 4-7 params that were
    # sent to Sonnet unnecessarily because of this check.
    if len(params) >= 4 and (branches or rec.get("raises") or calls or lines > FAST_MAX_LINES):
        bump("fast", f"params={len(params)}")
    if len(written) >= 2:
        bump("balanced", f"writes={len(written)}-tables")
    elif written and rec.get("hasTransaction"):
        bump("balanced", "transactional-write")

    # --- what requires reasoning beyond the text ---------------------------
    if rec.get("dynamicSql"):
        # The behaviour is assembled at runtime: the reader must reason about
        # what the string could become, which is exactly the deep lane.
        bump("deep", "dynamic-sql")
    if rec.get("cursors"):
        bump("deep", f"cursors={rec['cursors']}")
    if rec.get("recursive"):
        bump("deep", "recursive")
    if rec.get("unresolvedCallees"):
        bump("deep", "unresolved-callees="
             + ",".join(sorted(rec.get("unresolvedCallees") or [])[:3]))
    if len(calls) >= 2:
        # An orchestrator composes behaviour it does not contain. Composition is
        # what the pre-2026-08-26 rubric missed entirely.
        bump("deep", f"orchestrates={len(calls)}-calls")
    elif calls:
        bump("balanced", "calls=1")
    if lines > BALANCED_MAX_LINES:
        bump("deep", f"lines={lines}")
    if branches > BALANCED_MAX_BRANCHES:
        bump("deep", f"branches={branches}")
    if (rec.get("fanIn") or 0) >= DEEP_FAN_IN:
        # Load-bearing by usage: a wrong reading here is wrong in every caller.
        bump("deep", f"fan-in={rec['fanIn']}")

    return tier, reasons


def clamp(tier: str, floor: str = "none", ceiling: str = "deep") -> str:
    """Clamp a routed tier into an agent's declared bounds.

    Mirrors `sdd_lib.model_resolver.clamp_tier` in intent, re-implemented here
    because the reverse module must not import `sdd_lib` (D4). Unknown values
    fail safe upward: an unrecognised tier is treated as `deep`, never as `none`.
    """
    t = tier if tier in _RANK else "deep"
    f = floor if floor in _RANK else "none"
    c = ceiling if ceiling in _RANK else "deep"
    if _RANK[f] > _RANK[c]:
        f, c = c, f
    return TIERS[max(_RANK[f], min(_RANK[t], _RANK[c]))]


def plan_tiers(
    records: Iterable[dict[str, Any]],
    *,
    floor: str = "none",
    ceiling: str = "deep",
) -> dict[str, Any]:
    """Grade a whole object set and describe the resulting cost shape."""
    grades: dict[str, dict[str, Any]] = {}
    counts = dict.fromkeys(TIERS, 0)

    for rec in records:
        fq = str(rec.get("fqName") or rec.get("name") or "")
        if not fq:
            continue
        raw, reasons = tier_for(rec)
        tier = clamp(raw, floor, ceiling)
        grades[fq] = {
            "tier": tier,
            "routedTier": raw,
            "clamped": tier != raw,
            "reasons": reasons,
            "wave": rec.get("wave"),
        }
        counts[tier] += 1

    total = sum(counts.values()) or 1
    return {
        "schemaVersion": SCHEMA_VERSION,
        "grades": grades,
        "counts": counts,
        "stats": {
            "objects": sum(counts.values()),
            # The share that costs nothing is the number a Tech Lead reads first.
            "freeShare": round(counts["none"] / total, 3),
            "deepShare": round(counts["deep"] / total, 3),
            "clamped": sum(1 for g in grades.values() if g["clamped"]),
        },
    }
