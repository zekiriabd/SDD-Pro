"""test_reverse_evidence_resolution.py — audit C1 (2026-08-29) regression.

The reverse module's headline guarantee is that every FEAT / US / task claim
carries a `file:line` citation back into the legacy source. Until this fix the
CODE path only ever asked `bool(_EVIDENCE_RE.search(block))` — the HTML comment
was *present*, so the item passed. A fabricated `App_Code/Ghost.cs:34-38`, or a
real file cited at line 400 when it holds 12, was indistinguishable from a
verified citation. Only the DB path resolved anything, and only file existence.

These tests pin the three surfaces the fix wired up:
    - `sdd_reverse.evidence_resolver.resolve_evidence` (the shared SSoT)
    - `check_ladder_traceability.check` on the CODE ladder (FEAT items + tasks)
    - `validate_reverse_feat.validate_feat(..., legacy_root=...)`

and the fail-safe that matters as much as the check itself: with no legacy root
to resolve against, nothing is accused (tri-state None, never a fabricated gap).
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

clt = importlib.import_module("sdd_reverse_scripts.check_ladder_traceability")
vrf = importlib.import_module("sdd_reverse_scripts.validate_reverse_feat")
resolver = importlib.import_module("sdd_reverse.evidence_resolver")


# --------------------------------------------------------------------------- #
# The resolver itself
# --------------------------------------------------------------------------- #

class TestResolveEvidence:
    def test_missing_file_does_not_resolve(self, tmp_path):
        assert resolver.resolve_evidence(tmp_path, "App_Code/Ghost.cs:34-38") is False

    def test_placeholder_never_resolves(self, tmp_path):
        assert resolver.resolve_evidence(tmp_path, "unknown:1") is False

    def test_line_range_beyond_eof_does_not_resolve(self, tmp_path):
        (tmp_path / "Short.cs").write_text("\n".join(f"line {i}" for i in range(12)),
                                           encoding="utf-8")
        assert resolver.resolve_evidence(tmp_path, "Short.cs:34-38") is False

    def test_line_range_within_file_resolves(self, tmp_path):
        (tmp_path / "Login.aspx.cs").write_text(
            "\n".join(f"line {i}" for i in range(60)), encoding="utf-8")
        assert resolver.resolve_evidence(tmp_path, "Login.aspx.cs:34-38") is True

    def test_l_prefix_and_single_line_forms(self, tmp_path):
        (tmp_path / "a.cs").write_text("a\nb\nc\n", encoding="utf-8")
        assert resolver.resolve_evidence(tmp_path, "a.cs:L1-L3") is True
        assert resolver.resolve_evidence(tmp_path, "a.cs:2") is True
        assert resolver.resolve_evidence(tmp_path, "a.cs:L9") is False

    def test_first_ref_of_a_comma_list_is_the_load_bearing_one(self, tmp_path):
        (tmp_path / "a.cs").write_text("a\nb\nc\n", encoding="utf-8")
        assert resolver.resolve_evidence(tmp_path, "a.cs:1-2, b.cs:99") is True
        assert resolver.resolve_evidence(tmp_path, "gone.cs:1, a.cs:1") is False

    def test_no_project_root_is_undecidable_not_false(self, tmp_path):
        """Fail-safe: never accuse when we cannot verify."""
        assert resolver.resolve_evidence(None, "whatever.cs:1-2") is None

    def test_check_lines_false_keeps_db_ladder_semantics(self, tmp_path):
        (tmp_path / "s.sql").write_text("SELECT 1\n", encoding="utf-8")
        assert resolver.resolve_evidence(tmp_path, "s.sql:1-40", check_lines=False) is True
        assert resolver.resolve_evidence(tmp_path, "s.sql:1-40") is False


# --------------------------------------------------------------------------- #
# The CODE ladder — the surface the audit found unguarded
# --------------------------------------------------------------------------- #

_ANALYSIS = """---
confidence: high
---
# Analyse technique legacy — 3-Login

## Comportements observés (tasks techniques)
- T-1 : valide les credentials <!-- evidence: {t1_evidence} --> <!-- confidence: high -->
"""

_US = """---
confidence: high
---
# US-1: Connexion

ID: 3-1-Login
Parent FEAT: 3-Login

## Acceptance Criteria
- AC-1: Given credentials valides, when soumission, then session créée <!-- covers: T-1 --> <!-- confidence: high -->
"""

_FEAT = """---
generated-by: sdd-reverse
confidence: high
---
# FEAT 3 — Authentification

## Functional Needs
- SFD-1 : Permettre la connexion <!-- covers: US 3-1#AC-1 --> <!-- evidence: {feat_evidence} --> <!-- confidence: high -->
"""

_REAL_SOURCE = "Login.aspx.cs"
_REAL_LINES = 60


def _ladder(root: Path, *, feat_evidence: str, t1_evidence: str) -> Path:
    """3-rung ladder + a legacy project holding ONE real 60-line source file."""
    ws = root / "workspace"
    for sub in ("feats", "us", "plans"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    (ws / "feats" / "3-Login.md").write_text(
        _FEAT.format(feat_evidence=feat_evidence), encoding="utf-8")
    (ws / "us" / "3-1-Login.md").write_text(_US, encoding="utf-8")
    (ws / "plans" / "3-Login.analysis.md").write_text(
        _ANALYSIS.format(t1_evidence=t1_evidence), encoding="utf-8")

    project = ws / "old" / "Legacy"
    (project / ".sys").mkdir(parents=True, exist_ok=True)
    (project / _REAL_SOURCE).write_text(
        "\n".join(f"// line {i}" for i in range(_REAL_LINES)), encoding="utf-8")
    (project / ".sys" / "inventory.json").write_text(json.dumps({
        "_featAllocations": {"U-1": "3"},
        "_allocatedNames": {"Login": "U-1"},
        "units": [{"id": "U-1", "language": "csharp", "confidenceEstimate": "high",
                   "classes": [{"name": "LoginPage", "role": "page"}]}],
    }), encoding="utf-8")
    return project


def _evidence_gaps(report) -> list[str]:
    return [g for g in report["gaps"] if "REVERSE_EVIDENCE_MISSING" in g]


class TestCodeLadderResolvesEvidence:
    def test_truthful_citations_produce_no_evidence_gap(self, tmp_path, monkeypatch):
        monkeypatch.setattr(clt, "REPO_ROOT", tmp_path)
        project = _ladder(tmp_path,
                          feat_evidence=f"{_REAL_SOURCE}:34-45",
                          t1_evidence=f"{_REAL_SOURCE}:34-38")
        report = clt.check(project, "U-1", None)
        assert report["ran"] is True
        assert not _evidence_gaps(report), report["gaps"]

    def test_fabricated_feat_citation_is_rejected(self, tmp_path, monkeypatch):
        """A FEAT item pointing at a file that does not exist used to pass."""
        monkeypatch.setattr(clt, "REPO_ROOT", tmp_path)
        project = _ladder(tmp_path,
                          feat_evidence="App_Code/DataAccess.cs:34-38",
                          t1_evidence=f"{_REAL_SOURCE}:34-38")
        report = clt.check(project, "U-1", None)
        gaps = _evidence_gaps(report)
        assert any("SFD-1" in g and "does not resolve" in g for g in gaps), report["gaps"]

    def test_out_of_range_line_citation_is_rejected(self, tmp_path, monkeypatch):
        """The file is real; the cited range is past EOF — still a fabrication."""
        monkeypatch.setattr(clt, "REPO_ROOT", tmp_path)
        project = _ladder(tmp_path,
                          feat_evidence=f"{_REAL_SOURCE}:400-420",
                          t1_evidence=f"{_REAL_SOURCE}:34-38")
        report = clt.check(project, "U-1", None)
        assert any("SFD-1" in g and "does not resolve" in g
                   for g in _evidence_gaps(report)), report["gaps"]

    def test_fabricated_task_citation_is_rejected(self, tmp_path, monkeypatch):
        """The 3a task rung is where the ladder touches reality — check it too."""
        monkeypatch.setattr(clt, "REPO_ROOT", tmp_path)
        project = _ladder(tmp_path,
                          feat_evidence=f"{_REAL_SOURCE}:34-45",
                          t1_evidence="App_Code/Ghost.cs:1-9")
        report = clt.check(project, "U-1", None)
        assert any("T-1" in g and "does not resolve" in g
                   for g in _evidence_gaps(report)), report["gaps"]

    def test_feat_path_mode_stays_silent_no_false_accusation(self, tmp_path, monkeypatch):
        """Without --project there is no legacy root: undecidable, never a gap."""
        monkeypatch.setattr(clt, "REPO_ROOT", tmp_path)
        _ladder(tmp_path, feat_evidence="App_Code/Ghost.cs:34-38",
                t1_evidence="App_Code/Ghost.cs:1-9")
        report = clt.check(None, None, tmp_path / "workspace" / "feats" / "3-Login.md")
        assert report["ran"] is True
        assert not _evidence_gaps(report), report["gaps"]

    def test_gaps_stay_informational_exit_zero(self, tmp_path, monkeypatch):
        """[REVERSE_LADDER_TRACEABILITY_GAP] never blocks — exit code unchanged."""
        monkeypatch.setattr(clt, "REPO_ROOT", tmp_path)
        project = _ladder(tmp_path, feat_evidence="App_Code/Ghost.cs:34-38",
                          t1_evidence=f"{_REAL_SOURCE}:34-38")
        rc = clt.main(["--project", str(project), "--unit", "U-1", "--json"])
        assert rc == 0


# --------------------------------------------------------------------------- #
# validate_reverse_feat.py
# --------------------------------------------------------------------------- #

_VALIDATE_FEAT = """---
generated-by: sdd-reverse
legacy-sources: Login.aspx.cs
confidence: high
extraction-date: 2026-08-29
language-detected: csharp
source-unit: U-1
---
# FEAT 3 — Authentification

<!-- REVERSE-GATE: confidence=high; allow-sdd-full=true -->

## Actors
- Utilisateur

## Functional Needs
- SFD-1: Permettre la connexion <!-- evidence: {evidence} --> <!-- confidence: high -->

## Functional Deliverables
- FD-1: Page de connexion <!-- evidence: {evidence} --> <!-- confidence: high -->

## Business Rules
- BR-1: Le password est comparé contre PasswordHash <!-- evidence: {evidence} --> <!-- confidence: high -->

## Acceptance Criteria
- AC-1: Given credentials valides, when soumission, then session créée. <!-- evidence: {evidence} --> <!-- confidence: high -->

## Project Config
- Stack: legacy
"""


def _write_feat(tmp_path: Path, evidence: str) -> tuple[Path, Path]:
    legacy = tmp_path / "old" / "Legacy"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / _REAL_SOURCE).write_text(
        "\n".join(f"// line {i}" for i in range(_REAL_LINES)), encoding="utf-8")
    feat = tmp_path / "3-Login.md"
    feat.write_text(_VALIDATE_FEAT.format(evidence=evidence), encoding="utf-8")
    return feat, legacy


class TestValidateReverseFeatResolvesEvidence:
    def test_truthful_citation_validates_green(self, tmp_path):
        feat, legacy = _write_feat(tmp_path, f"{_REAL_SOURCE}:34-38")
        ok, errors, _ = vrf.validate_feat(feat, legacy)
        assert ok, errors

    def test_fabricated_citation_is_red_with_the_declared_class(self, tmp_path):
        feat, legacy = _write_feat(tmp_path, "App_Code/Ghost.cs:34-38")
        ok, errors, _ = vrf.validate_feat(feat, legacy)
        assert not ok
        offending = [e for e in errors if "[REVERSE_EVIDENCE_MISSING]" in e
                     and "does not resolve" in e]
        assert len(offending) == 4, errors  # SFD-1, FD-1, BR-1, AC-1

    def test_out_of_range_citation_is_red(self, tmp_path):
        feat, legacy = _write_feat(tmp_path, f"{_REAL_SOURCE}:400-420")
        ok, errors, _ = vrf.validate_feat(feat, legacy)
        assert not ok
        assert any("does not resolve" in e for e in errors), errors

    def test_without_legacy_root_behaviour_is_unchanged(self, tmp_path):
        """Backward compatibility: presence-only, as every existing caller expects."""
        feat, _ = _write_feat(tmp_path, "App_Code/Ghost.cs:34-38")
        ok, errors, _ = vrf.validate_feat(feat)
        assert ok, errors

    def test_cli_flag_wires_the_resolution_through(self, tmp_path, capsys):
        feat, legacy = _write_feat(tmp_path, "App_Code/Ghost.cs:34-38")
        rc = vrf.main(["--feat-path", str(feat), "--legacy-root", str(legacy), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert payload["evidence_resolved"] is True
        assert any("does not resolve" in e for e in payload["errors"])

    def test_cli_bad_legacy_root_degrades_instead_of_crashing(self, tmp_path, capsys):
        feat, _ = _write_feat(tmp_path, "App_Code/Ghost.cs:34-38")
        rc = vrf.main(["--feat-path", str(feat),
                       "--legacy-root", str(tmp_path / "nope"), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["evidence_resolved"] is False
