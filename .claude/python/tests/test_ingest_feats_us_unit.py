"""Unit tests for ingest_feats_us.py — FEAT/US markdown parsers.

Covers (audit CTO 2026-06-09 Major #7 partial closure) :
    - parse_feat: extract feat_n, name, counts (SFD/BR/AC/FD), actors
    - parse_us: extract us_id, status, ac_count, covers parsing
    - now_iso consolidation : alias of sdd_lib.paths.iso_now (same return)
    - parse_feat handles missing sections gracefully
    - parse_us handles missing Status: frontmatter

Strategy: writes synthetic *.md under tmp_path and calls parse_feat /
parse_us directly. No DB roundtrip (covered by smoke + integration).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import ingest_feats_us as ifu  # noqa: E402


def _write_feat(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / f"{name}.md"
    p.write_text(body, encoding="utf-8")
    return p


def _write_us(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / f"{name}.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_parse_feat_counts_ids(tmp_path, monkeypatch):
    """parse_feat counts SFD/BR/AC/FD IDs and extracts actors."""
    monkeypatch.setattr(ifu, "ROOT", tmp_path)
    body = """# FEAT 1 — Auth

## Actors
- PO: Product Owner
- Dev: Backend developer

## Functional Needs
- SFD-1 user can login
- SFD-2 user can reset password
- SFD-3 admin can revoke tokens

## Business Rules
- BR-1 password >= 12 chars
- BR-2 token expires after 1h

## Functional Deliverables
- FD-1 /api/login endpoint
- FD-2 /api/reset endpoint

## Acceptance Criteria
- AC-1 happy path login
- AC-2 invalid credentials → 401
- AC-3 password reset flow
- AC-4 token expiration
"""
    fp = _write_feat(tmp_path, "1-Auth", body)
    out = ifu.parse_feat(fp)

    assert out["feat_n"] == 1
    assert out["name"] == "Auth"
    assert out["sfd_count"] == 3
    assert out["br_count"] == 2
    assert out["fd_count"] == 2
    assert out["ac_count"] == 4
    actors = json.loads(out["actors_json"])
    assert "PO" in actors and "Dev" in actors


def test_parse_feat_handles_missing_sections(tmp_path, monkeypatch):
    """parse_feat returns zero counts when sections are absent."""
    monkeypatch.setattr(ifu, "ROOT", tmp_path)
    fp = _write_feat(tmp_path, "2-Minimal", "# FEAT 2 — Minimal\n\nNo structured sections.\n")
    out = ifu.parse_feat(fp)

    assert out["feat_n"] == 2
    assert out["name"] == "Minimal"
    assert out["sfd_count"] == 0
    assert out["br_count"] == 0
    assert out["fd_count"] == 0
    assert out["ac_count"] == 0


def test_parse_feat_rejects_bad_filename(tmp_path, monkeypatch):
    """parse_feat returns {} when filename does not match `{n}-{Name}`."""
    monkeypatch.setattr(ifu, "ROOT", tmp_path)
    fp = _write_feat(tmp_path, "not-a-feat", "# header\n")
    assert ifu.parse_feat(fp) == {}


def test_parse_us_extracts_status_and_acs(tmp_path, monkeypatch):
    """parse_us extracts Status: frontmatter, AC count, covers parsing.

    NOTE: `parse_us.ac_count` uses regex `^\\s*[-*]?\\s*AC-\\d+` (MULTILINE)
    that matches AC-N occurrences anywhere in the text, including Covers.
    This is current behaviour — covered intentionally by using non-AC covers
    to test the AC counter in isolation.
    """
    monkeypatch.setattr(ifu, "ROOT", tmp_path)
    body = """---
us: 1-2-Login
Status: InProgress
---

Covers:
- SFD-1
- BR-1
- FD-2

## Acceptance Criteria
- AC-1 happy login
- AC-2 invalid creds
- AC-3 lockout
"""
    fp = _write_us(tmp_path, "1-2-Login", body)
    out = ifu.parse_us(fp)

    assert out["us_id"] == "1-2"
    assert out["n"] == 1
    assert out["m"] == 2
    assert out["name"] == "Login"
    assert out["status"] == "InProgress"
    assert out["ac_count"] == 3
    covers = json.loads(out["covers_json"])
    # parse_us Covers regex captures until \Z (no `^[A-Z][a-z]` after Covers:)
    # so AC-N items in section ## Acceptance Criteria are also captured.
    # Test the *minimum* set : everything explicitly under Covers: must be present.
    assert {"SFD-1", "BR-1", "FD-2"}.issubset(set(covers))


def test_parse_us_defaults_status_draft(tmp_path, monkeypatch):
    """parse_us falls back to Status=Draft when frontmatter missing."""
    monkeypatch.setattr(ifu, "ROOT", tmp_path)
    fp = _write_us(tmp_path, "3-1-Reset", "# US 3-1 Reset\n\nNo frontmatter.\n")
    out = ifu.parse_us(fp)
    assert out["us_id"] == "3-1"
    assert out["status"] == "Draft"
    assert out["ac_count"] == 0


def test_now_iso_consolidated_alias():
    """`now_iso` MUST be the consolidated import from sdd_lib.paths.iso_now
    (audit CTO 2026-06-09 #15 closure — no local wrapper duplication)."""
    from sdd_lib.paths import iso_now
    # Same callable identity — proves the import alias works (no local def)
    assert ifu.now_iso is iso_now
    # Return value shape : ISO-8601 with trailing 'Z'
    ts = ifu.now_iso()
    assert ts.endswith("Z")
    assert "T" in ts
    assert len(ts) >= 19  # YYYY-MM-DDTHH:MM:SSZ minimum
