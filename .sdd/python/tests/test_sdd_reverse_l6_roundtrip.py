"""test_sdd_reverse_l6_roundtrip.py — Reverse → (would-be /sdd-full) parity proxy.

We can't run the LLM pipeline in a unit test, so this asserts the DETERMINISTIC
contract: after Phase 1 + cross-cutting generation, the reverse output captures
every salient legacy feature needed to regenerate a functionally-equivalent app
on another stack — entities, stored procs, connection strings, libraries, the
deep repository class, and the inline SQL.

This is the end-to-end guarantee behind the user's goal:
    "drop a legacy app in old/ → get specs → /sdd-full → same app, other stack".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PY_ROOT = Path(__file__).parent.parent

from tests.fixture_utils import copy_legacy_fixture  # noqa: E402


def _run(module, *args):
    r = subprocess.run([sys.executable, "-m", module, *args],
                       capture_output=True, text=True, cwd=str(PY_ROOT))
    assert r.returncode == 0, f"{module} failed: {r.stderr}"
    return r


def test_roundtrip_parity_webforms(tmp_path):
    webforms = copy_legacy_fixture("legacy-webforms-minimal", tmp_path)
    feats = tmp_path / "feats"
    feats.mkdir()

    # Phase 1 (L0-L2) + cross-cutting FEATs (L3) — both deterministic.
    _run("sdd_reverse_scripts.reverse_inventory", "--project", str(webforms), "--json")
    _run("sdd_reverse_scripts.generate_crosscutting_feats",
         "--project", str(webforms), "--feats-dir", str(feats), "--json")

    sysd = webforms / ".sys"
    inv = json.loads((sysd / "inventory.json").read_text(encoding="utf-8"))
    db = json.loads((sysd / "db-schema.json").read_text(encoding="utf-8"))
    da = json.loads((sysd / "data-access.json").read_text(encoding="utf-8"))
    cfg = json.loads((sysd / "config.json").read_text(encoding="utf-8"))
    deps = json.loads((sysd / "dependencies.json").read_text(encoding="utf-8"))
    code_graph = json.loads((sysd / "code-graph.json").read_text(encoding="utf-8"))

    db_feat = next(feats.glob("*-Database.md")).read_text(encoding="utf-8")
    lib_feat = next(feats.glob("*-Libraries.md")).read_text(encoding="utf-8")

    # --- 1. Entities captured (schema + Database FEAT) ---
    entity_names = {e["name"] for e in db["entities"]}
    assert {"Users", "UserRoles"} <= entity_names
    assert "Users" in db_feat and "UserRoles" in db_feat

    # --- 2. Deep repository class captured (L0 transitive evidence) ---
    login = next(u for u in inv["units"] if u["suggestedName"] == "Login")
    assert "App_Code/DataAccess.cs" in login["evidenceFiles"], \
        "the deep repository must be in Login's evidence (L0 fix)"
    roles = {c["name"]: c["role"] for c in login["classes"]}
    assert roles.get("DataAccess") == "repository"

    # --- 3. Inline SQL captured + attached to the unit ---
    assert any("Users" in q.get("tables", []) for q in da["queries"])
    assert login["dataAccess"]["queries"], "Login unit must carry its SQL query"

    # --- 4. Stored procedures captured (defs + params + Database FEAT) ---
    proc_names = {p["name"] for p in da["storedProcedureDefs"]}
    assert {"GetUserById", "DeactivateUser"} <= proc_names
    assert "GetUserById" in db_feat
    assert "@UserId" in db_feat and "OUTPUT" in db_feat

    # --- 5. Connection string captured (config + Database FEAT) ---
    assert any(c["name"] == "AppDb" for c in cfg["connectionStrings"])
    assert "AppDb" in db_feat and "HelloWebForms" in db_feat

    # --- 6. Libraries captured (dependencies + Libraries FEAT) ---
    pkg_names = {p["name"] for p in deps["packages"]}
    assert {"Newtonsoft.Json", "log4net", "Dapper"} <= pkg_names
    for lib in ("Newtonsoft.Json", "log4net", "Dapper"):
        assert lib in lib_feat
    # assembly DLL reference too
    assert "LegacyVendor.Reporting" in lib_feat

    # --- 7. Class-role coverage (L0): the legacy's roles are all named ---
    assert code_graph["rolesSummary"].get("repository", 0) >= 1
    assert code_graph["rolesSummary"].get("code-behind", 0) >= 1
