"""Unit tests for ingest_plans.py — plan markdown parser.

Covers (audit CTO 2026-06-09 Major #7 partial closure) :
    - parse_plan: extract us_id, family, schema_version, strict_ready, us_hash
    - parse_plan handles v1 (legacy, no frontmatter) and v2 (strict-ready)
    - parse_plan counts entries in `## Files` section
    - parse_plan rejects non-matching filenames (returns None)
    - now_iso consolidation : alias of sdd_lib.paths.iso_now
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import ingest_plans as ip_  # noqa: E402


def _write_plan(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_parse_plan_v2_strict_ready(tmp_path, monkeypatch):
    """parse_plan extracts v2 frontmatter (schema 2, strict-ready, us-hash)."""
    monkeypatch.setattr(ip_, "ROOT", tmp_path)
    body = """---
us: 1-1-Login
family: backend
generated-at: 2026-06-09T10:00:00Z
plan-schema-version: 2
us-hash: sha256:abc123def456
strict-ready: true
capabilities-triggered: pdf,excel
---

# Plan technique backend — 1-1-Login

## Files

- path: src/Services/AuthService.cs
- path: src/Endpoints/AuthEndpoints.cs
- path: src/DTOs/LoginRequest.cs
"""
    fp = _write_plan(tmp_path, "1-1-Login.back.md", body)
    out = ip_.parse_plan(fp)

    # parse_plan captures `family` from filename suffix `.back.md` / `.front.md`
    # → values are "back" / "front" (not "backend" / "frontend")
    assert out["plan_id"] == "1-1-back"
    assert out["us_id"] == "1-1"
    assert out["family"] == "back"
    assert out["schema_version"] == 2
    assert out["strict_ready"] == 1
    assert out["us_hash"] == "sha256:abc123def456"
    assert out["file_count"] == 3
    assert "pdf" in out["capabilities_json"]


def test_parse_plan_v1_legacy(tmp_path, monkeypatch):
    """parse_plan defaults schema_version=1 + strict_ready=0 when v2 fields absent."""
    monkeypatch.setattr(ip_, "ROOT", tmp_path)
    body = """---
us: 2-3-Reset
family: frontend
---

## Files

- path: src/pages/Reset.tsx
"""
    fp = _write_plan(tmp_path, "2-3-Reset.front.md", body)
    out = ip_.parse_plan(fp)

    assert out["plan_id"] == "2-3-front"
    assert out["us_id"] == "2-3"
    assert out["family"] == "front"
    assert out["schema_version"] == 1
    assert out["strict_ready"] == 0
    assert out["us_hash"] == ""
    assert out["file_count"] == 1


def test_parse_plan_rejects_bad_filename(tmp_path, monkeypatch):
    """parse_plan returns None for non-matching filenames."""
    monkeypatch.setattr(ip_, "ROOT", tmp_path)
    fp = _write_plan(tmp_path, "not-a-plan.md", "# header\n")
    assert ip_.parse_plan(fp) is None


def test_parse_plan_handles_invalid_schema_version(tmp_path, monkeypatch):
    """Non-int schema-version falls back to 1 (defensive)."""
    monkeypatch.setattr(ip_, "ROOT", tmp_path)
    body = """---
us: 4-1-Test
family: backend
plan-schema-version: not-a-number
---

## Files

- path: a.cs
"""
    fp = _write_plan(tmp_path, "4-1-Test.back.md", body)
    out = ip_.parse_plan(fp)
    assert out["schema_version"] == 1


def test_now_iso_consolidated_alias():
    """`now_iso` MUST be the consolidated import from sdd_lib.paths.iso_now
    (audit CTO 2026-06-09 #15 closure — no local wrapper duplication)."""
    from sdd_lib.paths import iso_now
    assert ip_.now_iso is iso_now
    ts = ip_.now_iso()
    assert ts.endswith("Z")
    assert "T" in ts
