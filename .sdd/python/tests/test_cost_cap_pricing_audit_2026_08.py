"""Regression tests for the C2 cost-cap findings (audit 2026-08-29).

Three distinct defects, one theme — the cost cap silently under-counted and
its own safety valve could not fire:

C2(a) `sdd_lib/pricing.py` knew no current-generation model id, so a runtime
      `claude-opus-5` fell through to `FALLBACK_PRICING` (Sonnet rates).
C2(b) every `token_usage` row in the live console.db had `model IS NULL`,
      because the Agent hook payload carries no `model` field.
C2(c) `preflight_cost_cap._compute_run_cost` guarded with
      `if model and not has_known_pricing(model)` — NULL short-circuits the
      truthy test, so `[PRICING_UNKNOWN]` never fired on the exact population
      (NULL models) it exists to protect.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".sdd" / "python"))

from sdd_hooks import preflight_cost_cap as pcc  # noqa: E402
from sdd_hooks import record_token_usage as rtu  # noqa: E402
from sdd_lib import pricing  # noqa: E402


# --------------------------------------------------------------------------
# C2(a) — current-generation models must price exactly, never via fallback
# --------------------------------------------------------------------------

CURRENT_GEN_MODELS = [
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
]


@pytest.mark.parametrize("model_id", CURRENT_GEN_MODELS)
def test_current_generation_models_have_exact_pricing(model_id):
    assert pricing.has_known_pricing(model_id), (
        f"{model_id} has no pricing entry — get_pricing() would silently "
        f"return Sonnet FALLBACK_PRICING and under-count the run"
    )
    assert model_id in pricing.PRICING
    p = pricing.get_pricing(model_id)
    assert p is not pricing.FALLBACK_PRICING
    for key in ("input", "output", "cache_read", "cache_creation"):
        assert p[key] > 0


@pytest.mark.parametrize("model_id", CURRENT_GEN_MODELS)
def test_current_generation_models_price_with_context_suffix(model_id):
    """Claude Code reports e.g. `claude-opus-5[1m]` at runtime."""
    assert pricing.has_known_pricing(f"{model_id}[1m]")
    assert pricing.get_pricing(f"{model_id}[1m]") == pricing.PRICING[model_id]


def test_opus_5_is_not_priced_as_sonnet():
    """The exact 5x-class under-count the audit found."""
    assert pricing.get_pricing("claude-opus-5") != pricing.get_pricing("claude-sonnet-4-6")


# --------------------------------------------------------------------------
# C2(c) — a NULL/empty model must trip [PRICING_UNKNOWN], not slip through
# --------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_a, **_kw):
        return self

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


#: An agent SDD_Pro actually declares (`.sdd/agents/dev-backend.md` exists) —
#: the population the fail-closed guard is meant to cover.
SDD_AGENT = "dev-backend"


def _row(model, inp=1000, outp=500, cc=0, cr=0, agent=SDD_AGENT):
    """One `token_usage` row, in the column order the hook SELECTs."""
    return (model, inp, outp, cc, cr, agent)


def _run_cost_with_rows(rows):
    pcc._COST_CACHE.clear()
    with patch("sdd_lib.console_db.connect_ro", lambda *a, **k: _FakeConn(rows)), \
         patch("sdd_lib.console_db.default_db_path") as dbp, \
         patch.object(pcc, "get_or_create_run_id", lambda: "run-test-0001"):
        dbp.return_value.exists.return_value = True
        return pcc._compute_run_cost()


def test_null_model_rows_are_flagged_unknown_pricing():
    """Regression — the live console.db has `model IS NULL` on every row."""
    _cost, _n, _scope, unknown, _foreign = _run_cost_with_rows([_row(None)])
    assert unknown, (
        "a NULL model must trip [PRICING_UNKNOWN] — it was priced at Sonnet "
        "FALLBACK_PRICING with no signal at all before this fix"
    )


def test_empty_string_model_rows_are_flagged_unknown_pricing():
    _cost, _n, _scope, unknown, _foreign = _run_cost_with_rows([_row("   ")])
    assert unknown


def test_unknown_named_model_still_flagged():
    _cost, _n, _scope, unknown, _foreign = _run_cost_with_rows(
        [_row("gpt-nonexistent-9", 10, 10)])
    assert "gpt-nonexistent-9" in unknown


def test_known_model_rows_are_not_flagged():
    _cost, _n, _scope, unknown, _foreign = _run_cost_with_rows([_row("claude-opus-5")])
    assert unknown == ()


def test_unknown_is_deduplicated_across_rows():
    rows = [_row(None, 1, 1), _row(None, 1, 1), _row("", 1, 1)]
    _cost, _n, _scope, unknown, _foreign = _run_cost_with_rows(rows)
    assert len(unknown) == 1


# --------------------------------------------------------------------------
# C-1 (2026-08-30) — the fail-closed DENY is scoped to the SDD registry
#
# Claude Code's built-in subagents are recorded in `token_usage` like any
# other spawn and carry `model IS NULL` (no `.sdd/agents/{name}.md`, so the
# tier fallback resolves nothing). Denying a CI run over a spawn the
# framework neither routes nor prices protects nothing.
# --------------------------------------------------------------------------

FOREIGN_AGENTS = ["Explore", "general-purpose", "claude-code-guide"]


@pytest.mark.parametrize("agent", FOREIGN_AGENTS)
def test_unpriced_row_from_non_sdd_agent_does_not_block(agent):
    _cost, _n, _scope, unknown, foreign = _run_cost_with_rows(
        [_row(None, agent=agent)])
    assert unknown == (), (
        f"{agent} is not in the SDD registry — its unpriced row must not be "
        f"able to DENY a CI run"
    )
    assert foreign == ("<unrecorded>",), (
        "the out-of-registry row must still be reported, not swallowed"
    )


def test_non_sdd_agent_tokens_are_still_priced_into_the_total():
    """Exempt from the DENY is not exempt from the cap."""
    cost, _n, _scope, _unknown, _foreign = _run_cost_with_rows(
        [_row(None, 1_000_000, 1_000_000, agent="Explore")])
    assert cost > 0


def test_sdd_agent_still_blocks_when_mixed_with_foreign_rows():
    """A foreign row must not launder an SDD row's unknown pricing."""
    rows = [_row(None, agent="Explore"), _row(None, agent=SDD_AGENT)]
    _cost, _n, _scope, unknown, foreign = _run_cost_with_rows(rows)
    assert unknown == ("<unrecorded>",)
    assert foreign == ("<unrecorded>",)


@pytest.mark.parametrize("agent", [None, "", "unknown", "PostToolUse.Agent", "SubagentStop"])
def test_unattributed_rows_stay_fail_closed(agent):
    """An unnamed spawn COULD be an SDD agent — the guard stays closed."""
    _cost, _n, _scope, unknown, _foreign = _run_cost_with_rows([_row(None, agent=agent)])
    assert unknown == ("<unrecorded>",)


def test_unreadable_registry_stays_fail_closed():
    """An unreadable registry must never widen the exemption."""
    with patch.object(pcc, "_sdd_agent_registry", lambda: None):
        _cost, _n, _scope, unknown, _foreign = _run_cost_with_rows(
            [_row(None, agent="Explore")])
    assert unknown == ("<unrecorded>",)


def test_sdd_registry_contains_the_framework_agents():
    registry = pcc._sdd_agent_registry()
    assert registry is not None, ".sdd/agents/ unreadable from the test run"
    assert {"dev-backend", "arch", "qa"} <= registry
    assert "Explore" not in registry


# --------------------------------------------------------------------------
# C2(b) — `model` must be resolvable even when the payload carries none
# --------------------------------------------------------------------------

def test_find_model_reads_payload_first():
    payload = {"tool_response": {"model": "claude-opus-5[1m]"}}
    assert rtu._find_model(payload, "dev-backend") == "claude-opus-5"


def test_find_model_falls_back_to_env():
    with patch.dict(os.environ, {"SDD_AGENT_MODEL": "claude-sonnet-5"}, clear=False):
        assert rtu._find_model({}, None) == "claude-sonnet-5"


def test_find_model_falls_back_to_agent_tier():
    """Regression — payload has no model field, so NULL was written forever.

    `dev-backend` declares `model_tier: deep`; the anthropic provider maps
    `deep` to a concrete id. The resolved value must be a *priced* model, so
    the cost cap stops treating the row as unknown.
    """
    for var in rtu._MODEL_ENV_VARS:
        os.environ.pop(var, None)
    resolved = rtu._find_model({}, "dev-backend")
    assert resolved, "agent-tier fallback returned nothing — model stays NULL"
    assert pricing.has_known_pricing(resolved), (
        f"tier fallback resolved {resolved!r}, which has no pricing entry"
    )


def test_find_model_returns_none_for_unknown_agent():
    """No guessing : an unknown agent yields None (loud NULL), not a default."""
    for var in rtu._MODEL_ENV_VARS:
        os.environ.pop(var, None)
    assert rtu._find_model({}, "no-such-agent-xyz") is None


def test_find_model_never_raises_on_garbage():
    for var in rtu._MODEL_ENV_VARS:
        os.environ.pop(var, None)
    assert rtu._find_model({"tool_response": None}, None) is None
    assert rtu._find_model({}, "../../etc/passwd") is None
