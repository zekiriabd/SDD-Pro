"""test_sdd_reverse_l2_units.py — L2 code-driven unit detection.

Verifies that backend/API-only legacies (no UI page) produce functional units
(controllers + orphan modules), and that page-based legacies don't gain
spurious code units for classes already covered by a page.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.code_graph_builder import build_code_graph  # noqa: E402
from sdd_reverse.code_unit_detector import detect_code_units  # noqa: E402

from tests.fixture_utils import copy_legacy_fixture  # noqa: E402

# Lecture seule uniquement (build_code_graph) — les tests qui exécutent
# reverse_inventory (écriture .sys/) passent par copy_legacy_fixture.
API_FIXTURE = Path(__file__).parent / "fixtures" / "legacy-api-minimal"


class _FakeLang:
    def __init__(self, files):
        self.files = files


class _FakeScan:
    def __init__(self, files, primary="csharp"):
        self.languages = [_FakeLang(files)]
        self.primary_language = primary


def _api_scan():
    files = list(API_FIXTURE.rglob("*.cs"))
    return _FakeScan(files)


def test_controller_becomes_api_unit_with_closure():
    cg = build_code_graph(API_FIXTURE, _api_scan())
    units = detect_code_units(cg, existing_units=[])
    api_units = [u for u in units if u["kind"] == "api"]
    assert len(api_units) == 1
    u = api_units[0]
    assert u["suggestedName"] == "Orders"
    # seed is the controller file
    assert any("OrdersController.cs" in f for f in u["evidenceFiles"])


def test_orphan_module_unit_for_unreached_backend_class():
    cg = build_code_graph(API_FIXTURE, _api_scan())
    units = detect_code_units(cg, existing_units=[])
    module_units = [u for u in units if u["kind"] == "module"]
    names = {u["suggestedName"] for u in module_units}
    assert "Jobs" in names, "NightlyCleanupJob is orphan → its own module unit"


def test_no_code_units_when_classes_already_covered_by_page():
    # Simulate a page unit whose seed already reaches every behavioural class.
    cg = build_code_graph(API_FIXTURE, _api_scan())
    # A page that 'owns' the controller file → its closure covers service/repo/dto.
    existing = [{
        "suggestedName": "OrdersPage",
        "seedEvidenceFiles": ["Controllers/OrdersController.cs"],
        "evidenceFiles": ["Controllers/OrdersController.cs"],
    }]
    units = detect_code_units(cg, existing_units=existing)
    # OrdersController is covered → no api unit for it; only the orphan Job remains.
    kinds = {u["kind"] for u in units}
    assert "api" not in kinds
    assert {u["suggestedName"] for u in units} == {"Jobs"}


def test_empty_graph_yields_no_code_units():
    assert detect_code_units({"classes": []}, existing_units=[]) == []


def test_e2e_api_only_fixture_produces_units(tmp_path):
    """Full Phase 1 on a backend-only project produces >= 2 units (was 0 pre-L2)."""
    project = copy_legacy_fixture("legacy-api-minimal", tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
         "--project", str(project), "--json"],
        capture_output=True, text=True, cwd=str(PY_ROOT),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["unitsDetected"] >= 2
    inv = json.loads((project / ".sys" / "inventory.json").read_text(encoding="utf-8"))
    kinds = {u["kind"] for u in inv["units"]}
    assert "api" in kinds
    assert "module" in kinds


def test_webforms_does_not_gain_spurious_code_units(tmp_path):
    """Page-based fixture keeps exactly its 2 page units (DataAccess covered)."""
    project = copy_legacy_fixture("legacy-webforms-minimal", tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
         "--project", str(project), "--json"],
        capture_output=True, text=True, cwd=str(PY_ROOT),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["unitsDetected"] == 2
