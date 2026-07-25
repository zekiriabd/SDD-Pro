"""test_reverse_complexity_routing.py — ADR governance-reverse-complexity-ladder.

Covers the deterministic complexity classifier that routes the reverse code
ladder's 3a/3c rungs to Sonnet for `simple` units (Opus stays for `complex`).
Fail-safe behaviour (doubt → complex) is the load-bearing contract.
"""
from __future__ import annotations

import importlib

mod = importlib.import_module("sdd_reverse.code_unit_complexity")


def _simple_unit(**over) -> dict:
    u = {
        "id": "U-1",
        "kind": "form",
        "confidenceEstimate": "high",
        "classes": [
            {"name": "Login", "role": "code-behind"},
            {"name": "AuthService", "role": "service"},
        ],
        "dataAccess": {"queries": [{"tables": ["Users"]}]},
    }
    u.update(over)
    return u


# --- happy path -------------------------------------------------------------

def test_simple_unit_is_simple_and_routes_to_sonnet():
    u = _simple_unit()
    assert mod.classify_unit(u) == "simple"
    assert mod.model_for(u, "3a") == mod.SONNET
    assert mod.model_for(u, "3c") == mod.SONNET
    assert mod.model_for(u, "3b") == mod.SONNET  # always Sonnet


# --- disqualifiers → complex (each in isolation) ----------------------------

def test_complex_kind():
    assert mod.classify_unit(_simple_unit(kind="module")) == "complex"
    assert mod.classify_unit(_simple_unit(kind="wizard")) == "complex"
    assert mod.classify_unit(_simple_unit(kind="job")) == "complex"


def test_complex_too_many_classes():
    classes = [{"name": f"C{i}", "role": "service"} for i in range(6)]
    assert mod.classify_unit(_simple_unit(classes=classes)) == "complex"


def test_complex_god_class():
    classes = [{"name": "God", "role": "complex"}, {"name": "X", "role": "service"}]
    assert mod.classify_unit(_simple_unit(classes=classes)) == "complex"


def test_complex_dynamic_sql():
    da = {"queries": [{"tables": ["Users"], "dynamicSql": True}]}
    assert mod.classify_unit(_simple_unit(dataAccess=da)) == "complex"
    da2 = {"storedProcedureCalls": [{"name": "usp_X", "dynamic": True}]}
    assert mod.classify_unit(_simple_unit(dataAccess=da2)) == "complex"


def test_complex_degraded_confidence():
    assert mod.classify_unit(_simple_unit(confidenceEstimate="medium")) == "complex"
    assert mod.classify_unit(_simple_unit(confidenceEstimate="low")) == "complex"


# --- fail-safe: empty / absent graph (non-.NET) → complex -------------------

def test_empty_class_graph_is_complex_failsafe():
    """Non-.NET units have no class graph → cannot confirm simplicity → complex."""
    assert mod.classify_unit(_simple_unit(classes=[])) == "complex"
    u = _simple_unit()
    del u["classes"]
    assert mod.classify_unit(u) == "complex"


def test_non_dict_unit_is_complex():
    assert mod.classify_unit(None) == "complex"  # type: ignore[arg-type]
    assert mod.classify_unit("nope") == "complex"  # type: ignore[arg-type]


# --- model routing for complex ----------------------------------------------

def test_complex_unit_keeps_opus_on_3a_3c():
    u = _simple_unit(kind="module")  # complex
    assert mod.classify_unit(u) == "complex"
    assert mod.model_for(u, "3a") == mod.OPUS
    assert mod.model_for(u, "3c") == mod.OPUS
    assert mod.model_for(u, "3b") == mod.SONNET


def test_unknown_rung_is_opus_failsafe():
    assert mod.model_for(_simple_unit(), "3z") == mod.OPUS


# --- explainability ---------------------------------------------------------

def test_signals_explain_why_complex():
    sig = mod.complexity_signals(_simple_unit(kind="module", confidenceEstimate="low"))
    assert sig["is_simple"] is False
    assert any("kind" in r for r in sig["reasons"])
    assert any("confidenceEstimate" in r for r in sig["reasons"])


def test_signals_simple_has_no_reasons():
    sig = mod.complexity_signals(_simple_unit())
    assert sig["is_simple"] is True
    assert sig["reasons"] == []
    assert sig["n_classes"] == 2
