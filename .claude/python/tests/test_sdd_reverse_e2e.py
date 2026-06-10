"""test_sdd_reverse_e2e.py — End-to-end smoke for reverse Phase 1 pipeline.

Exercises scan + inventory + db-schema against the legacy-webforms-minimal fixture.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "legacy-webforms-minimal"
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


def test_e2e_phase1_smoke():
    """Phase 1 produces inventory.json + db-schema.json with expected shape."""
    report = _run_inventory(FIXTURE_ROOT)
    assert report["ok"] is True
    assert report["project"] == "legacy-webforms-minimal"
    assert report["primaryLanguage"] == "aspx-webforms"
    assert report["unitsDetected"] >= 2, "expected at least 2 units (Login + Default)"
    assert report["entitiesDetected"] >= 1, "expected User entity from CreateSchema.sql"
    assert report["filesScanned"] >= 5


def test_e2e_inventory_schema_v04_keys():
    """inventory.json contains ADV-23 mandatory keys."""
    inv_path = FIXTURE_ROOT / ".sys" / "inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    assert inv["schemaVersion"] == 1
    assert "_allocatedNames" in inv, "ADV-23: _allocatedNames must be initialized"
    assert "_featAllocations" in inv, "ADV-23: _featAllocations must be initialized"
    assert "legacyMtimeMax" in inv, "ADV-1: legacyMtimeMax must be present"
    assert isinstance(inv["_allocatedNames"], dict)
    assert isinstance(inv["_featAllocations"], dict)


def test_e2e_db_schema_users_entity():
    """db-schema.json detects Users + UserRoles entities + the FK relation."""
    schema_path = FIXTURE_ROOT / ".sys" / "db-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["schemaVersion"] == 1
    assert schema["completeness"] == "basic"
    assert schema["databaseType"] == "SqlServer"
    entity_names = {e["name"] for e in schema["entities"]}
    assert "Users" in entity_names
    assert "UserRoles" in entity_names
    # FK should be detected
    assert any(r["from"]["entity"] == "UserRoles" for r in schema["relations"]), \
        "Expected FK relation UserRoles → Users"


def test_e2e_un_stability_cross_runs():
    """Re-run inventory produces the same U-N IDs."""
    inv_path = FIXTURE_ROOT / ".sys" / "inventory.json"
    inv1 = json.loads(inv_path.read_text(encoding="utf-8"))
    units1 = {u["suggestedName"]: u["id"] for u in inv1["units"]}
    # Re-run
    _run_inventory(FIXTURE_ROOT)
    inv2 = json.loads(inv_path.read_text(encoding="utf-8"))
    units2 = {u["suggestedName"]: u["id"] for u in inv2["units"]}
    assert units1 == units2, f"U-N drift: {units1} != {units2}"
