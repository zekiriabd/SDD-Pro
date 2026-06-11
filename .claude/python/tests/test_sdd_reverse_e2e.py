"""test_sdd_reverse_e2e.py — End-to-end smoke for reverse Phase 1 pipeline.

Exercises scan + inventory + db-schema against the legacy-webforms-minimal
fixture. La fixture est copiée en tmp (module scope) avant exécution —
les scripts reverse écrivent `.sys/` dans le projet cible et ne doivent
jamais muter `tests/fixtures/` (audit 2026-06-11).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixture_utils import copy_legacy_fixture

PROJECT_ROOT = Path(__file__).parent.parent  # .claude/python/


def _run_inventory(project: Path) -> dict:
    """Run reverse_inventory CLI and return JSON output."""
    result = subprocess.run(
        [sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
         "--project", str(project), "--json"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"reverse_inventory failed: {result.stderr}"
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def webforms(tmp_path_factory) -> tuple[Path, dict]:
    """Copie isolée de legacy-webforms-minimal + rapport Phase 1 initial."""
    project = copy_legacy_fixture(
        "legacy-webforms-minimal", tmp_path_factory.mktemp("reverse-e2e")
    )
    report = _run_inventory(project)
    return project, report


def test_e2e_phase1_smoke(webforms):
    """Phase 1 produces inventory.json + db-schema.json with expected shape."""
    _, report = webforms
    assert report["ok"] is True
    assert report["project"] == "legacy-webforms-minimal"
    assert report["primaryLanguage"] == "aspx-webforms"
    assert report["unitsDetected"] >= 2, "expected at least 2 units (Login + Default)"
    assert report["entitiesDetected"] >= 1, "expected User entity from CreateSchema.sql"
    assert report["filesScanned"] >= 5


def test_e2e_inventory_schema_v04_keys(webforms):
    """inventory.json contains ADV-23 mandatory keys."""
    project, _ = webforms
    inv = json.loads((project / ".sys" / "inventory.json").read_text(encoding="utf-8"))
    assert inv["schemaVersion"] == 1
    assert "_allocatedNames" in inv, "ADV-23: _allocatedNames must be initialized"
    assert "_featAllocations" in inv, "ADV-23: _featAllocations must be initialized"
    assert "legacyMtimeMax" in inv, "ADV-1: legacyMtimeMax must be present"
    assert isinstance(inv["_allocatedNames"], dict)
    assert isinstance(inv["_featAllocations"], dict)


def test_e2e_db_schema_users_entity(webforms):
    """db-schema.json detects Users + UserRoles entities + the FK relation."""
    project, _ = webforms
    schema = json.loads((project / ".sys" / "db-schema.json").read_text(encoding="utf-8"))
    assert schema["schemaVersion"] == 1
    assert schema["completeness"] == "basic"
    assert schema["databaseType"] == "SqlServer"
    entity_names = {e["name"] for e in schema["entities"]}
    assert "Users" in entity_names
    assert "UserRoles" in entity_names
    # FK should be detected
    assert any(r["from"]["entity"] == "UserRoles" for r in schema["relations"]), \
        "Expected FK relation UserRoles → Users"


def test_e2e_un_stability_cross_runs(webforms):
    """Re-run inventory produces the same U-N IDs."""
    project, _ = webforms
    inv_path = project / ".sys" / "inventory.json"
    inv1 = json.loads(inv_path.read_text(encoding="utf-8"))
    units1 = {u["suggestedName"]: u["id"] for u in inv1["units"]}
    # Re-run
    _run_inventory(project)
    inv2 = json.loads(inv_path.read_text(encoding="utf-8"))
    units2 = {u["suggestedName"]: u["id"] for u in inv2["units"]}
    assert units1 == units2, f"U-N drift: {units1} != {units2}"
