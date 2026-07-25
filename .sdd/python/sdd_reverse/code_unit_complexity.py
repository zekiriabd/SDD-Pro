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
    model_for(unit: dict, rung: str) -> model-id
    complexity_signals(unit: dict) -> dict   # explainability (why simple/complex)
"""

from __future__ import annotations

from typing import Any

OPUS = "claude-opus-4-8"
SONNET = "claude-sonnet-4-6"

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


def model_for(unit: dict, rung: str) -> str:
    """Model id for a ladder rung given the unit's complexity.

    rung ∈ {'3a', '3b', '3c'}. 3b is always Sonnet (altitude-lift, D2 of the
    spec-ladder ADR). 3a/3c are Sonnet for `simple` units, Opus for `complex`.
    Unknown rung → Opus (fail-safe).
    """
    if rung == "3b":
        return SONNET
    if rung in ("3a", "3c"):
        return SONNET if classify_unit(unit) == "simple" else OPUS
    return OPUS
