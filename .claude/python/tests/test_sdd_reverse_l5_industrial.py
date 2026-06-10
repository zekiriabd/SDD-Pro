"""test_sdd_reverse_l5_industrial.py — L5 industrialization.

Covers deterministic FEAT pre-allocation (enables parallel Phase 3), the
extraction cache, and the back-side completeness reviewer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.reverse_cache import (  # noqa: E402
    compute_unit_evidence_hash,
    is_unit_cached,
    save_unit,
)
from sdd_reverse_scripts.check_feat_completeness import assess  # noqa: E402
from sdd_reverse_scripts.preallocate_feats import preallocate  # noqa: E402


def _inventory(units):
    return {"schemaVersion": 1, "units": units, "_featAllocations": {}, "_allocatedNames": {}}


# --------------------------------------------------------------------------- #
# pre-allocation
# --------------------------------------------------------------------------- #

def test_preallocate_assigns_unique_numbers_and_names(tmp_path):
    inv = _inventory([
        {"id": "U-1", "suggestedName": "Login"},
        {"id": "U-2", "suggestedName": "Orders"},
    ])
    allocs, names, unit_name = preallocate(inv, tmp_path)
    assert allocs == {"U-1": 1, "U-2": 2}
    assert unit_name["U-1"] == "Login"
    assert names["Login"] == "U-1"
    # numbers unique
    assert len(set(allocs.values())) == 2


def test_preallocate_collision_gets_legacy_suffix(tmp_path):
    # an existing human FEAT already owns "Login"
    (tmp_path / "5-Login.md").write_text("x", encoding="utf-8")
    inv = _inventory([{"id": "U-1", "suggestedName": "Login"}])
    allocs, names, unit_name = preallocate(inv, tmp_path)
    assert unit_name["U-1"] == "Login-Legacy"
    assert allocs["U-1"] != 5  # must not reuse the taken number


def test_preallocate_idempotent(tmp_path):
    inv = _inventory([{"id": "U-1", "suggestedName": "Login"},
                      {"id": "U-2", "suggestedName": "Orders"}])
    a1, n1, _ = preallocate(inv, tmp_path)
    inv["_featAllocations"] = a1
    inv["_allocatedNames"] = n1
    a2, n2, _ = preallocate(inv, tmp_path)
    assert a1 == a2 and n1 == n2


# --------------------------------------------------------------------------- #
# completeness reviewer
# --------------------------------------------------------------------------- #

def test_completeness_flags_unmentioned_repository():
    unit = {
        "id": "U-1",
        "classes": [
            {"name": "OrderRepository", "role": "repository", "file": "R.cs", "lines": "1-9"},
            {"name": "OrderService", "role": "service", "file": "S.cs", "lines": "1-5"},
        ],
        "dataAccess": {"queries": [{"tables": ["Invoices"]}], "storedProcedureCalls": []},
    }
    feat = "## Functional Needs\nSFD-1 the OrderService places records."
    report = assess(unit, feat)
    items = {g["item"] for g in report["gaps"]}
    assert "OrderRepository" in items   # repository not mentioned → gap
    assert "OrderService" not in items  # mentioned → no gap
    assert "Invoices" in items          # table not mentioned → gap
    assert report["verdict"].endswith("incomplete")  # serious gap present


def test_completeness_green_when_all_mentioned():
    unit = {
        "id": "U-1",
        "classes": [{"name": "AuthService", "role": "service", "file": "A.cs", "lines": "1-3"}],
        "dataAccess": {"queries": [], "storedProcedureCalls": []},
    }
    report = assess(unit, "AuthService validates credentials")
    assert report["gaps"] == []
    assert report["verdict"].endswith("complete")


# --------------------------------------------------------------------------- #
# extraction cache
# --------------------------------------------------------------------------- #

def test_cache_hit_only_when_evidence_unchanged_and_feat_exists(tmp_path):
    project = tmp_path / "old" / "Proj"
    (project / ".sys").mkdir(parents=True)
    src = project / "A.cs"
    src.write_text("class A {}", encoding="utf-8")
    feats = tmp_path / "input" / "feats"
    feats.mkdir(parents=True)

    unit = {"id": "U-1", "evidenceFiles": ["A.cs"]}
    h = compute_unit_evidence_hash(project, unit)

    # no cache yet
    assert not is_unit_cached(project, unit, feats)
    # save cache but FEAT missing → still not cached
    save_unit(project, "U-1", h, 1, "Alpha")
    assert not is_unit_cached(project, unit, feats)
    # create FEAT → now cached
    (feats / "1-Alpha.md").write_text("feat", encoding="utf-8")
    assert is_unit_cached(project, unit, feats)
    # edit evidence → hash changes → cache invalidated
    src.write_text("class A { void M(){} }", encoding="utf-8")
    assert not is_unit_cached(project, unit, feats)
