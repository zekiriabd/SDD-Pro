"""test_reverse_ladder_traceability.py — D3 enforcer coverage (ADR reverse-spec-ladder).

Exercises check_ladder_traceability.check() on a synthetic 3-rung ladder
(3a analysis + 3b US + 3c FEAT) by monkeypatching the module REPO_ROOT to a
tmp workspace. Covers the happy complete chain and a few gap cases.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

mod = importlib.import_module("sdd_reverse_scripts.check_ladder_traceability")


def _scaffold(root: Path, *, feat_body: str, us_body: str, analysis_body: str,
              n: str = "3", name: str = "Login") -> Path:
    feats = root / "workspace" / "input" / "feats"
    us = root / "workspace" / "output" / "us"
    plans = root / "workspace" / "output" / "plans"
    for d in (feats, us, plans):
        d.mkdir(parents=True, exist_ok=True)
    feat = feats / f"{n}-{name}.md"
    feat.write_text(feat_body, encoding="utf-8")
    (us / f"{n}-1-{name}.md").write_text(us_body, encoding="utf-8")
    (plans / f"{n}-{name}.analysis.md").write_text(analysis_body, encoding="utf-8")
    return feat


_ANALYSIS_OK = """# Analyse technique legacy — 3-Login

## Comportements observés (tasks techniques)
- T-1 : valide les credentials <!-- evidence: Login.aspx.cs:34-38 --> <!-- confidence: high -->
- T-2 : crée la session <!-- evidence: Login.aspx.cs:40-45 --> <!-- confidence: high -->
"""

_US_OK = """# US-1: Connexion

ID: 3-1-Login
Parent FEAT: 3-Login

## Acceptance Criteria
- AC-1: Given credentials valides, when soumission, then session créée <!-- covers: T-1, T-2 --> <!-- confidence: high -->
"""

_FEAT_OK = """---
generated-by: sdd-reverse
confidence: high
---
# FEAT 3 — Authentification

## Functional Needs
- SFD-1 : Permettre la connexion <!-- covers: US 3-1#AC-1 --> <!-- evidence: Login.aspx.cs:34-45 --> <!-- confidence: high -->

## Acceptance Criteria
- AC-1 : Given credentials valides, when soumission, then session <!-- covers: US 3-1#AC-1 --> <!-- evidence: Login.aspx.cs:40-45 --> <!-- confidence: high -->
"""


def test_ladder_complete_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    feat = _scaffold(tmp_path, feat_body=_FEAT_OK, us_body=_US_OK, analysis_body=_ANALYSIS_OK)
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert report["verdict"] == "ladder-complete", report["gaps"]
    assert report["gap_count"] == 0


def test_ladder_dangling_feat_covers(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    # FEAT covers a US AC that does not exist
    feat_bad = _FEAT_OK.replace("US 3-1#AC-1", "US 3-9#AC-7")
    feat = _scaffold(tmp_path, feat_body=feat_bad, us_body=_US_OK, analysis_body=_ANALYSIS_OK)
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert report["verdict"] in ("partial", "incomplete")
    assert any("dangling" in g for g in report["gaps"])


def test_ladder_us_ac_without_task_covers(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    us_bad = _US_OK.replace(" <!-- covers: T-1, T-2 -->", "")
    feat = _scaffold(tmp_path, feat_body=_FEAT_OK, us_body=us_bad, analysis_body=_ANALYSIS_OK)
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert any("no `covers:` to any task" in g for g in report["gaps"])


_ANALYSIS_WITH_CONF = """---
confidence: medium
---
""" + _ANALYSIS_OK

_US_WITH_CONF = """---
confidence: medium
---
""" + _US_OK


def test_ladder_confidence_min_monotone_ok(tmp_path, monkeypatch):
    """FEAT(medium) ≤ min(US)(medium) ≤ analysis(medium) → no uprank gap."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    feat_med = _FEAT_OK.replace("confidence: high", "confidence: medium")
    feat = _scaffold(tmp_path, feat_body=feat_med, us_body=_US_WITH_CONF,
                     analysis_body=_ANALYSIS_WITH_CONF)
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert not any("uprank" in g for g in report["gaps"]), report["gaps"]
    assert report["confidence"]["analysis"] == "medium"
    assert report["confidence"]["feat"] == "medium"


def test_ladder_confidence_uprank_feat_over_analysis(tmp_path, monkeypatch):
    """FEAT(high) > analysis(medium) → min-monotone Q3 gap reported."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    feat = _scaffold(tmp_path, feat_body=_FEAT_OK, us_body=_US_WITH_CONF,
                     analysis_body=_ANALYSIS_WITH_CONF)  # FEAT=high, analysis=medium
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert any("uprank" in g and "FEAT" in g for g in report["gaps"]), report["gaps"]


def test_ladder_confidence_uprank_us_over_analysis(tmp_path, monkeypatch):
    """US(high) > analysis(medium) → min-monotone Q3 gap reported."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    us_high = _US_WITH_CONF.replace("confidence: medium", "confidence: high")
    feat_med = _FEAT_OK.replace("confidence: high", "confidence: medium")
    feat = _scaffold(tmp_path, feat_body=feat_med, us_body=us_high,
                     analysis_body=_ANALYSIS_WITH_CONF)
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert any("uprank" in g and "US" in g for g in report["gaps"]), report["gaps"]


def test_ladder_confidence_absent_is_tolerated(tmp_path, monkeypatch):
    """Barreaux sans frontmatter confidence (3a/3b legacy) → aucune comparaison."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    feat = _scaffold(tmp_path, feat_body=_FEAT_OK, us_body=_US_OK,
                     analysis_body=_ANALYSIS_OK)
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert not any("uprank" in g for g in report["gaps"]), report["gaps"]


def test_ladder_missing_artifacts_is_informational(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    feats = tmp_path / "workspace" / "input" / "feats"
    feats.mkdir(parents=True, exist_ok=True)
    feat = feats / "3-Login.md"
    feat.write_text(_FEAT_OK, encoding="utf-8")
    report = mod.check(None, None, feat)  # no US / analysis
    assert report["ran"] is False
    assert report["verdict"] == "ladder-incomplete-artifacts"
