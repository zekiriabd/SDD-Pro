"""Audit CTO 2026-06-09 #25 closure : session_start banner constant.

`INVARIANTS.yml` claims that `session_start` emits a "byte-identical banner
(cache-friendly v7.0.0+)" at startup|resume|clear|compact, declaring the
13 commands + 12 LLM agents + 1 rubric. The cache benefit relies on the
banner being a constant string — if any timestamp, run-id, or dynamic
data leaks in, the prompt cache prefix breaks every session.

This test runs `session_start.emit()` 5 times and verifies the additional
context payload is byte-identical across invocations. Catch regressions
where someone adds e.g. `datetime.now()` to the banner.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_hooks import session_start  # noqa: E402


def _extract_context(payload: dict) -> str:
    return (payload.get("hookSpecificOutput", {}) or {}).get("additionalContext", "")


def test_banner_is_byte_identical_across_5_calls():
    """5 consecutive emit() must return the exact same banner string.

    Defensive : if a future maintainer slips a `datetime.now()` or `uuid.uuid4()`
    into the banner template, this test fails and forces them to either
    (a) move the dynamic data elsewhere, or (b) explicitly accept the
    cache-prefix invalidation and update INVARIANTS.yml.
    """
    snapshots = [_extract_context(session_start.emit()) for _ in range(5)]
    assert len(snapshots) == 5
    first = snapshots[0]
    assert first, "additionalContext is empty — banner emission broken"
    for i, snap in enumerate(snapshots[1:], start=2):
        assert snap == first, (
            f"Banner drift on emit #{i}: first emission was "
            f"{len(first)} chars, this one is {len(snap)} chars. "
            f"Cache prefix invariant broken."
        )


def test_banner_declares_12_agents_llm_and_rubric():
    """Audit CTO 2026-06-09 Bug #18 closure : the banner must reflect the
    new wording '12 agents LLM + 1 rubric' (not the legacy '13 agents')."""
    payload = session_start.emit()
    ctx = _extract_context(payload)
    assert "12 agents LLM" in ctx or "12 LLM agents" in ctx, (
        f"Banner must declare '12 agents LLM' (not '13 agents'). "
        f"First 300 chars: {ctx[:300]!r}"
    )
    assert "rubric" in ctx.lower(), "Banner must mention the deterministic rubric"


def test_banner_does_not_contain_dynamic_markers():
    """Sanity : no obviously dynamic string in the banner."""
    payload = session_start.emit()
    ctx = _extract_context(payload)
    # Patterns qui suggéreraient une injection dynamique
    forbidden_substrings = [
        # ISO timestamp prefix
        "2026-",
        "T0",   # un timestamp T0X:XX
        "T1",
        "T2",
        # UUID hex chunk
        "-4",   # ne devrait pas apparaître mais le « pipeline » mention OK
    ]
    # Cette liste est volontairement souple : on autorise « v7.0.0+ », « Phase 0 »,
    # etc. On cherche surtout des patterns timestamp-like. Test soft : on inspecte
    # mais on ne fail que sur des patterns ISO timestamp évidents.
    # Détection plus stricte : un timestamp ISO complet « YYYY-MM-DDTHH:MM:SS »
    import re
    iso_ts_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
    matches = iso_ts_pattern.findall(ctx)
    assert not matches, (
        f"Banner contains ISO timestamp(s) {matches} — cache prefix will "
        f"invalidate every minute. Move dynamic data out of the banner."
    )
