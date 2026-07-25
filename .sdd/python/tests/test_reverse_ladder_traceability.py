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
    feats = root / "workspace" / "feats"
    us = root / "workspace" / "us"
    plans = root / "workspace" / "plans"
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
    feats = tmp_path / "workspace" / "feats"
    feats.mkdir(parents=True, exist_ok=True)
    feat = feats / "3-Login.md"
    feat.write_text(_FEAT_OK, encoding="utf-8")
    report = mod.check(None, None, feat)  # no US / analysis
    assert report["ran"] is False
    assert report["verdict"] == "ladder-incomplete-artifacts"


def _scaffold_with_inventory(root: Path, *, language: str, estimate: str,
                             analysis_conf: str, n: str = "3", name: str = "Login") -> Path:
    """Scaffold a 3-rung ladder + a legacy project inventory for --project --unit mode."""
    _scaffold(
        root,
        feat_body=_FEAT_OK.replace("confidence: high", f"confidence: {analysis_conf}"),
        us_body=("---\nconfidence: %s\n---\n" % analysis_conf) + _US_OK,
        analysis_body=("---\nconfidence: %s\n---\n" % analysis_conf) + _ANALYSIS_OK,
        n=n, name=name,
    )
    project = root / "workspace" / "old" / "Proj"
    (project / ".sys").mkdir(parents=True, exist_ok=True)
    import json
    (project / ".sys" / "inventory.json").write_text(json.dumps({
        "_featAllocations": {"U-1": n},
        "_allocatedNames": {name: "U-1"},
        "units": [{"id": "U-1", "language": language, "confidenceEstimate": estimate}],
    }), encoding="utf-8")
    return project


def test_ladder_confidence_cap_violation_flagged(tmp_path, monkeypatch):
    """Regression for the 2026-06-12 audit fix (reverse-C2).

    A 3a analysis declaring `high` confidence on a `medium`-cap language
    (php-procedural) must be flagged: nothing previously checked the analysis
    against confidence_cap[language] — only relative monotonicity.
    """
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    mod._LANG_CAP_CACHE = None  # force reload against the real signatures file
    project = _scaffold_with_inventory(
        tmp_path, language="php-procedural", estimate="high", analysis_conf="high")
    report = mod.check(project, "U-1", None)
    assert report["ran"] is True
    assert any("confidence cap" in g and "php-procedural" in g for g in report["gaps"]), report["gaps"]
    assert report["confidence"]["language"] == "php-procedural"
    assert report["confidence"]["language_cap"] == "medium"


def test_ladder_confidence_cap_respected_no_gap(tmp_path, monkeypatch):
    """Analysis at `high` on a `high`-cap language (csharp) → no cap gap."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    mod._LANG_CAP_CACHE = None
    project = _scaffold_with_inventory(
        tmp_path, language="csharp", estimate="high", analysis_conf="high")
    report = mod.check(project, "U-1", None)
    assert report["ran"] is True
    assert not any("confidence cap" in g for g in report["gaps"]), report["gaps"]
    assert report["confidence"]["language_cap"] == "high"


def _scaffold_with_unit_fields(root: Path, *, unit_fields: dict, analysis_conf: str,
                               db_schema: dict | None = None,
                               n: str = "3", name: str = "Login") -> Path:
    """Scaffold a 3-rung ladder + inventory whose units[0] carries arbitrary fields
    (entities, classes, …) for the cap_db / extraction-depth checks."""
    import json
    _scaffold(
        root,
        feat_body=_FEAT_OK.replace("confidence: high", f"confidence: {analysis_conf}"),
        us_body=("---\nconfidence: %s\n---\n" % analysis_conf) + _US_OK,
        analysis_body=("---\nconfidence: %s\n---\n" % analysis_conf) + _ANALYSIS_OK,
        n=n, name=name,
    )
    project = root / "workspace" / "old" / "Proj"
    (project / ".sys").mkdir(parents=True, exist_ok=True)
    unit = {"id": "U-1", **unit_fields}
    (project / ".sys" / "inventory.json").write_text(json.dumps({
        "_featAllocations": {"U-1": n},
        "_allocatedNames": {name: "U-1"},
        "units": [unit],
    }), encoding="utf-8")
    if db_schema is not None:
        (project / ".sys" / "db-schema.json").write_text(
            json.dumps(db_schema), encoding="utf-8")
    return project


def test_ladder_cap_db_degraded_when_entities_not_ddl_backed(tmp_path, monkeypatch):
    """A1 (audit 2026-06-29): a csharp unit (lang cap=high) whose declared entity
    is NOT present in db-schema → cap_db tightens to medium → a `high` analysis
    is flagged. Closes the 'cap_db prompt-only' gap (rule §4)."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    mod._LANG_CAP_CACHE = None
    project = _scaffold_with_unit_fields(
        tmp_path,
        unit_fields={"language": "csharp", "confidenceEstimate": "high",
                     "entities": ["Ghost"]},
        analysis_conf="high",
        db_schema={"entities": [{"name": "Other"}]},  # 'Ghost' absent → deduced
    )
    report = mod.check(project, "U-1", None)
    assert report["ran"] is True
    assert report["confidence"]["language_cap"] == "medium", report["confidence"]
    assert any("confidence cap" in g for g in report["gaps"]), report["gaps"]


def test_ladder_cap_db_not_degraded_when_entity_backed(tmp_path, monkeypatch):
    """Entity present in db-schema → no db degradation → cap stays high."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    mod._LANG_CAP_CACHE = None
    project = _scaffold_with_unit_fields(
        tmp_path,
        unit_fields={"language": "csharp", "confidenceEstimate": "high",
                     "entities": ["User"]},
        analysis_conf="high",
        db_schema={"entities": [{"name": "User"}]},
    )
    report = mod.check(project, "U-1", None)
    assert report["confidence"]["language_cap"] == "high", report["confidence"]
    assert not any("confidence cap" in g for g in report["gaps"]), report["gaps"]


def test_ladder_extraction_depth_shallow_flagged(tmp_path, monkeypatch):
    """A2 (audit 2026-06-29): a non-.NET unit (java-ee, cap=high) with an empty
    class graph + confidence=high is flagged as shallow — reading-reliable ≠
    extraction-deep. No cap gap (java-ee cap is high), only an extraction-depth gap."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    mod._LANG_CAP_CACHE = None
    project = _scaffold_with_unit_fields(
        tmp_path,
        unit_fields={"language": "java-ee", "confidenceEstimate": "high",
                     "classes": []},  # graph ran, empty (non-.NET)
        analysis_conf="high",
    )
    report = mod.check(project, "U-1", None)
    assert report["ran"] is True
    assert report["extraction_depth"] == "shallow"
    assert any("extraction-depth" in g for g in report["gaps"]), report["gaps"]


def test_ladder_extraction_depth_deep_no_flag(tmp_path, monkeypatch):
    """A .NET unit with a non-empty class graph → deep, no extraction-depth gap."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    mod._LANG_CAP_CACHE = None
    project = _scaffold_with_unit_fields(
        tmp_path,
        unit_fields={"language": "csharp", "confidenceEstimate": "high",
                     "classes": [{"name": "AuthService", "role": "service"}]},
        analysis_conf="high",
    )
    report = mod.check(project, "U-1", None)
    assert report["extraction_depth"] == "deep"
    assert not any("extraction-depth" in g for g in report["gaps"]), report["gaps"]


def test_ladder_staleness_detected(tmp_path, monkeypatch):
    """A3 (audit 2026-06-29): 3a analysis newer than 3b US / 3c FEAT → stale
    findings ([REVERSE_LADDER_STALE]), separate from traceability gaps."""
    import os
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    feat = _scaffold(tmp_path, feat_body=_FEAT_OK, us_body=_US_OK, analysis_body=_ANALYSIS_OK)
    analysis = tmp_path / "workspace" / "plans" / "3-Login.analysis.md"
    us = tmp_path / "workspace" / "us" / "3-1-Login.md"
    # Make analysis clearly newer than US and FEAT (>1s tolerance).
    old = 1_700_000_000
    os.utime(feat, (old, old))
    os.utime(us, (old, old))
    os.utime(analysis, (old + 100, old + 100))
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert report["stale_findings"], "expected staleness findings"
    assert report["stale_class"] == "[REVERSE_LADDER_STALE]"


def test_ladder_no_staleness_when_synchronised(tmp_path, monkeypatch):
    """Near-simultaneous writes (sub-second) → no false-positive staleness."""
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    feat = _scaffold(tmp_path, feat_body=_FEAT_OK, us_body=_US_OK, analysis_body=_ANALYSIS_OK)
    report = mod.check(None, None, feat)
    assert report["ran"] is True
    assert not report["stale_findings"], report["stale_findings"]


def test_us_template_header_confidence_matches_conf_re():
    """Audit 2026-06-11 M2 : le template US 3b DOIT porter une ligne header
    Confidence: lisible par _CONF_RE, sinon la monotonie Q3 (US <= analyse,
    FEAT <= min(US)) est silencieusement skippee pour toutes les US."""
    template = Path(__file__).resolve().parent.parent / "sdd_reverse" / "us.reverse.template.md"
    text = template.read_text(encoding="utf-8").replace("{Confidence}", "medium")
    assert mod._frontmatter_confidence(text) == "medium"


def test_legacy_us_comment_confidence_fallback():
    """US 3b generees AVANT le fix M2 : confidence lisible via le commentaire
    de provenance (fallback _CONF_COMMENT_RE)."""
    legacy = (
        "# US-1: Login\n\nID: 1-1-Login\nStatus: Draft\n\n"
        "<!-- generated-by: sdd-reverse ; artifact: user-story ; source-unit: U-1 ; "
        "confidence: low ; extraction-date: 2026-06-01 -->\n"
    )
    assert mod._frontmatter_confidence(legacy) == "low"
