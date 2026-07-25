"""Tests de harness_preflight — composition stack_config + impact_report + gate.

Vérifie le point d'entrée unique du combo actif (harnais × provider) : combo
de référence autorisé, combo UNTESTED bloqué sauf SDD_ALLOW_UNTESTED_HARNESS,
verdict structuré consommable par le pipeline.

Pur/offline (base=REPO_ROOT pour résoudre le foyer .sdd/).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

SDD_HOME = Path(__file__).resolve().parents[2]  # .sdd/
REPO_ROOT = SDD_HOME.parent

from sdd_lib.harness_preflight import (  # noqa: E402
    PreflightError,
    preflight_combo,
)
from sdd_lib.impact_report import ALLOW_UNTESTED_ENV  # noqa: E402


def _stack(text: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="-stack.md", delete=False, encoding="utf-8"
    )
    tmp.write(text)
    tmp.close()
    return Path(tmp.name)


def test_default_combo_is_reference_and_allowed():
    """Sans stack.md -> claude-code × anthropic, référence, autorisé sans env."""
    res = preflight_combo(None, env={}, base=REPO_ROOT)
    assert (res.harness, res.provider) == ("claude-code", "anthropic")
    assert res.report.is_reference is True
    assert res.allowed is True
    assert res.blocking_reason is None


def test_untested_combo_blocked_without_env():
    stack = _stack(
        "## Active Harness\nHarness: codex\n"
        "## Active Model Provider\nProvider: moonshot\n"
    )
    try:
        res = preflight_combo(stack, env={}, base=REPO_ROOT)
    finally:
        stack.unlink(missing_ok=True)
    assert (res.harness, res.provider) == ("codex", "moonshot")
    assert res.report.untested is True
    assert res.allowed is False
    assert "STACK_COMBO_UNTESTED" in (res.blocking_reason or "")


def test_untested_combo_allowed_with_env():
    stack = _stack("## Active Harness\nHarness: gemini-cli\n")
    try:
        res = preflight_combo(stack, env={ALLOW_UNTESTED_ENV: "1"}, base=REPO_ROOT)
    finally:
        stack.unlink(missing_ok=True)
    assert res.allowed is True
    assert res.blocking_reason is None


def test_render_contains_gate_verdict():
    stack = _stack("## Active Harness\nHarness: codex\n")
    try:
        res = preflight_combo(stack, env={}, base=REPO_ROOT)
    finally:
        stack.unlink(missing_ok=True)
    text = res.render()
    text.encode("cp1252")  # ASCII/cp1252-safe (pas de glyphe hors console Windows)
    assert "Gate combo" in text
    assert "HARNESS BUILD REPORT" in text


def test_missing_stack_raises():
    with pytest.raises(PreflightError):
        preflight_combo(Path("nope/stack.md"), env={}, base=REPO_ROOT)


def test_invalid_stack_value_raises():
    stack = _stack("## Active Harness\nHarness: bun-cli\n")
    try:
        with pytest.raises(PreflightError):
            preflight_combo(stack, env={}, base=REPO_ROOT)
    finally:
        stack.unlink(missing_ok=True)


def test_unknown_provider_raises():
    stack = _stack(
        "## Active Harness\nHarness: codex\n"
        "## Active Model Provider\nProvider: does-not-exist\n"
    )
    try:
        with pytest.raises(PreflightError):
            preflight_combo(stack, env={}, base=REPO_ROOT)
    finally:
        stack.unlink(missing_ok=True)
