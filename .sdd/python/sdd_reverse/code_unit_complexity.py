"""code_unit_complexity.py — Deterministic complexity router for the reverse code ladder.

ADR governance-reverse-complexity-ladder (2026-06-29). The 3-rung ladder
applies 2 Opus passes (3a + 3c) to EVERY unit regardless of complexity. This
classifier — the code-stream equivalent of build_proc_us.py's proc_complexity —
labels each unit `simple` or `complex` from the L0 signals already present in
inventory.json (0 token, stdlib only, D4-isolated). The reverse commands route
3a/3c to Sonnet for `simple` units, keeping Opus only where it earns its cost.
3b is Sonnet either way.

DECISION SCOPE (D2): model-routing ONLY. The ladder STRUCTURE is unchanged —
3 rungs, 3 artifacts, D3 traceability + confidence min-monotone all intact. This
is NOT the structural-collapse alternative (a fused single pass), which was
deferred as an opt-in V2 because it would reintroduce the decommissioned
mono-prompt (altitude bleed).

FAIL-SAFE: any missing / ambiguous signal yields `complex` — doubt costs an Opus,
never an under-analysis. In particular an EMPTY class graph (non-.NET units, where
code_graph_builder is unavailable) cannot positively confirm simplicity, so those
units stay `complex` (= Opus) in the MVP. Savings therefore accrue on the .NET
legacy where the graph exists; non-.NET routing is a deliberate follow-up once a
non-.NET depth signal exists.

Rubric SSoT: docs/rubrics/reverse-complexity-routing.md (this module is the
executable mirror — keep both in sync).

Public API:
    classify_unit(unit: dict) -> "simple" | "complex"
    tier_for(unit: dict, rung: str) -> "deep" | "balanced"   # PREFERRED
    model_for(unit: dict, rung: str) -> model-id             # legacy id-shaped view
    complexity_signals(unit: dict) -> dict   # explainability (why simple/complex)
"""

from __future__ import annotations

from typing import Any

# --- Model tiers (m5, audit 2026-08-29) --------------------------------------
# The agent system expresses model choice as a TIER (`model_tier: deep|balanced`
# in every `.sdd/agents/*.md` frontmatter; `db_tier_router.TIERS` on the DB
# stream), not as a concrete model id. This module used to hand callers a raw
# `claude-opus-4-8` / `claude-sonnet-4-6`, which drifts the day the roster moves
# and bypasses each agent's declared tier_floor / tier_ceiling. `tier_for()` is
# now the primary API; the id-shaped constants below survive only so the
# existing `model_for()` callers keep working.
TIER_DEEP = "deep"
TIER_BALANCED = "balanced"

#: Legacy id-shaped view of the two tiers. Prefer `tier_for()`.
OPUS = "claude-opus-4-8"
SONNET = "claude-sonnet-4-6"
_TIER_TO_MODEL = {TIER_DEEP: OPUS, TIER_BALANCED: SONNET}

# --- D1 rubric defaults (MVP, conservative). Calibrate on real legacy. ---------
SIMPLE_KINDS: frozenset[str] = frozenset({"form", "page", "grid", "api"})
MAX_CLASSES: int = 5
GOD_CLASS_ROLE: str = "complex"


def _has_dynamic_sql(data_access: Any) -> bool:
    """Best-effort dynamic-SQL signal over a unit's dataAccess block.

    Dynamic SQL (sp_executesql / EXEC(@sql) / string-built queries) means the
    behaviour is not statically observable → the unit deserves Opus scrutiny.
    Field is optional in the inventory schema; absence is treated as 'no dynamic'
    (most inline-SQL units never set it), so this never forces `complex` spuriously.
    """
    if not isinstance(data_access, dict):
        return False
    for key in ("queries", "storedProcedureCalls", "storedProcedures"):
        for item in data_access.get(key) or []:
            if isinstance(item, dict) and (
                item.get("dynamicSql") or item.get("dynamic")
            ):
                return True
    return bool(data_access.get("dynamicSql") or data_access.get("dynamic"))


def complexity_signals(unit: dict) -> dict:
    """Return the individual signals + the disqualifiers, for explainability."""
    if not isinstance(unit, dict):
        return {"reasons": ["unit is not a dict"], "is_simple": False}

    kind = unit.get("kind")
    classes = unit.get("classes")
    n_classes = len(classes) if isinstance(classes, list) else None
    roles = (
        {c.get("role") for c in classes if isinstance(c, dict)}
        if isinstance(classes, list)
        else set()
    )
    estimate = unit.get("confidenceEstimate")
    dynamic = _has_dynamic_sql(unit.get("dataAccess"))

    reasons: list[str] = []
    if kind not in SIMPLE_KINDS:
        reasons.append(f"kind={kind!r} not in simple kinds {sorted(SIMPLE_KINDS)}")
    # Require a POSITIVELY OBSERVED small graph: non-empty AND bounded.
    # Empty/absent graph (non-.NET) → cannot confirm simplicity → complex (fail-safe).
    if not isinstance(classes, list) or n_classes == 0:
        reasons.append("empty/absent class graph (cannot confirm simplicity — fail-safe)")
    elif n_classes > MAX_CLASSES:
        reasons.append(f"{n_classes} classes > MAX_CLASSES={MAX_CLASSES}")
    if GOD_CLASS_ROLE in roles:
        reasons.append(f"god-class present (role={GOD_CLASS_ROLE!r})")
    if dynamic:
        reasons.append("dynamic SQL present")
    if estimate != "high":
        reasons.append(f"confidenceEstimate={estimate!r} != 'high' (degraded)")

    return {
        "kind": kind,
        "n_classes": n_classes,
        "roles": sorted(r for r in roles if r),
        "confidenceEstimate": estimate,
        "dynamic_sql": dynamic,
        "reasons": reasons,
        "is_simple": not reasons,
    }


def classify_unit(unit: dict) -> str:
    """Return 'simple' or 'complex'. Fail-safe: doubt → 'complex'."""
    return "simple" if complexity_signals(unit).get("is_simple") else "complex"


def tier_for(unit: dict, rung: str) -> str:
    """Model TIER for a ladder rung given the unit's complexity.

    rung ∈ {'3a', '3b', '3c'}. 3b is always `balanced` (altitude-lift, D2 of the
    spec-ladder ADR). 3a/3c are `balanced` for `simple` units, `deep` for
    `complex`. Unknown rung → `deep` (fail-safe: doubt costs a deep pass, never
    an under-analysis).
    """
    if rung == "3b":
        return TIER_BALANCED
    if rung in ("3a", "3c"):
        return TIER_BALANCED if classify_unit(unit) == "simple" else TIER_DEEP
    return TIER_DEEP


def model_for(unit: dict, rung: str) -> str:
    """Legacy id-shaped view of `tier_for()` — kept for existing callers.

    Prefer `tier_for()`: the agent frontmatter speaks tiers, and a concrete id
    here silently overrides each agent's declared tier_floor / tier_ceiling.
    """
    return _TIER_TO_MODEL[tier_for(unit, rung)]


# --------------------------------------------------------------------------- #
# CLI — the routing entry point used by /sdd-reverse-analyze and
# /sdd-reverse-feat (M2, audit 2026-08-29).
#
# Both commands used to embed a `python -c` one-liner that globbed
# `workspace/old/*/.sys/inventory.json` and took `[0]` — ALWAYS the first legacy
# project on disk, discarding the project their own Action 1 had just resolved.
# With two projects checked out, unit `U-3` was routed against a stranger's
# inventory. Worse, the uncaught IndexError / StopIteration meant the documented
# "doubt → deep" fail-safe did not exist: a traceback surfaced where a tier was
# expected. Here the project is REQUIRED and every failure prints `deep`.
# --------------------------------------------------------------------------- #

def route_tier(project_root, unit_id: str, rung: str) -> tuple[str, str | None]:
    """Return (tier, failure_reason). Never raises — doubt yields TIER_DEEP.

    `failure_reason` is None on a real classification, else a one-line
    explanation the caller surfaces on stderr so a silent mis-route is
    impossible to confuse with a deliberate deep routing.
    """
    import json
    from pathlib import Path

    inv_path = Path(project_root) / ".sys" / "inventory.json"
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return TIER_DEEP, f"inventory unreadable ({inv_path}): {exc}"
    except json.JSONDecodeError as exc:
        return TIER_DEEP, f"inventory is not valid JSON ({inv_path}): {exc}"
    unit = next(
        (u for u in (data.get("units") or []) if isinstance(u, dict) and u.get("id") == unit_id),
        None,
    )
    if unit is None:
        return TIER_DEEP, f"unit {unit_id!r} absent from {inv_path}"
    return tier_for(unit, rung), None


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(
        prog="code_unit_complexity",
        description="Deterministic complexity routing for one reverse code unit "
                    "(prints a model tier: deep|balanced). Fail-safe: any error "
                    "prints 'deep' and explains why on stderr, exit 0.",
    )
    p.add_argument("--project", required=True,
                   help="Legacy project root — workspace/old/{P} (the project "
                        "the command's own Action 1 resolved, never a glob).")
    p.add_argument("--unit", required=True, help="Unit id, e.g. U-3")
    p.add_argument("--rung", default="3a", choices=["3a", "3b", "3c"])
    p.add_argument("--json", action="store_true",
                   help="Emit {tier, model, unit, rung, reason} instead of the bare tier.")
    args = p.parse_args(argv)

    tier, reason = route_tier(args.project, args.unit, args.rung)
    if reason:
        # ASCII only: this lands on a cp1252 Windows console (M10 convention).
        print(f"[REVERSE/WARN] complexity routing unavailable - {reason}. "
              f"Defaulting to tier '{TIER_DEEP}' (fail-safe).", file=sys.stderr)
    if args.json:
        import json as _json
        print(_json.dumps({
            "tier": tier, "model": _TIER_TO_MODEL[tier],
            "unit": args.unit, "rung": args.rung, "reason": reason,
        }, ensure_ascii=False))
    else:
        print(tier)
    return 0  # never blocking — the caller always receives a usable tier


if __name__ == "__main__":
    import sys

    sys.exit(main())
