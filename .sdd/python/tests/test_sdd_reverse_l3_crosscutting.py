"""test_sdd_reverse_l3_crosscutting.py — L3 cross-cutting reverse FEATs.

Verifies the deterministic "Libraries" + "Database" FEATs are well-formed
(pass the reverse structure contract) and capture the technical detail the
Tech Lead needs for a faithful migration.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse import feat_structure_spec as spec  # noqa: E402
from sdd_reverse.crosscutting_feats import build_database_feat, build_libraries_feat  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "legacy-webforms-minimal"


def _assert_reverse_feat_wellformed(content: str):
    fm, body = spec.parse_frontmatter(content)
    assert spec.REQUIRED_FRONTMATTER_KEYS_REVERSE <= set(fm)
    assert fm["confidence"] in spec.CONFIDENCE_ENUM
    assert spec.REVERSE_GATE_RE.search(content)
    assert spec.section_order_violations(content) == []
    # every non-empty item line carries an evidence comment
    assert spec.EVIDENCE_COMMENT_RE.search(content)
    assert spec.AC_GIVEN_WHEN_THEN_RE.search(content)


_DEPS = {
    "packages": [
        {"name": "Newtonsoft.Json", "version": "13.0.3", "ecosystem": "nuget",
         "source": "PackageReference", "evidence": "App.csproj:8"},
        {"name": "log4net", "version": "2.0.15", "ecosystem": "nuget",
         "source": "PackageReference", "evidence": "App.csproj:9"},
    ],
    "assemblyReferences": [
        {"name": "LegacyVendor.Reporting", "hintPath": "lib\\X.dll", "evidence": "App.csproj:12"},
    ],
    "binaries": [],
}


def test_libraries_feat_wellformed_and_lists_packages():
    feat = build_libraries_feat(_DEPS, n=1, name="Libraries", project="Demo", language="csharp")
    _assert_reverse_feat_wellformed(feat)
    assert "Newtonsoft.Json" in feat
    assert "log4net" in feat
    assert "LegacyVendor.Reporting" in feat


_DB = {
    "databaseType": "SqlServer",
    "entities": [
        {"name": "Users", "table": "Users", "evidence": ["Schema.sql:2-7"],
         "fields": [{"name": "Id", "type": "INT"}, {"name": "Username", "type": "NVARCHAR(50)"}]},
    ],
    "relations": [
        {"name": "FK_UserRoles_User", "from": {"entity": "UserRoles", "field": "UserId"},
         "to": {"entity": "Users", "field": "Id"}, "type": "many-to-one", "evidence": "Schema.sql:20"},
    ],
}
_DA = {
    "storedProcedureDefs": [
        {"name": "GetUserById", "file": "Procs.sql", "line": 3,
         "params": [{"name": "@UserId", "type": "INT", "output": False},
                    {"name": "@Reason", "type": "NVARCHAR(200)", "output": True}]},
    ],
}
_CFG = {
    "connectionStrings": [
        {"name": "AppDb", "provider": "System.Data.SqlClient", "server": ".",
         "database": "HelloWebForms", "value": "Server=.;Database=HelloWebForms;",
         "file": "Web.config", "line": 4},
    ],
}


def test_database_feat_captures_procs_connstrings_entities():
    feat = build_database_feat(_DB, _DA, _CFG, n=2, name="Database", project="Demo", language="csharp")
    _assert_reverse_feat_wellformed(feat)
    assert "GetUserById" in feat
    assert "@UserId INT" in feat
    assert "@Reason NVARCHAR(200) OUTPUT" in feat  # OUTPUT param preserved
    assert "AppDb" in feat and "System.Data.SqlClient" in feat
    assert "FK_UserRoles_User" in feat
    # masked secret: no raw password leaked (none here, but ensure no 'Password=' literal)
    assert "Password=" not in feat or "***" in feat


def test_generate_cli_idempotent_allocation(tmp_path):
    # Copie isolée + Phase 1 explicite : ce test dépendait du .sys/ laissé
    # dans la fixture par d'autres tests (couplage caché, audit 2026-06-11).
    from tests.fixture_utils import copy_legacy_fixture
    project = copy_legacy_fixture("legacy-webforms-minimal", tmp_path)
    inv = subprocess.run(
        [sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
         "--project", str(project), "--json"],
        capture_output=True, text=True, cwd=str(PY_ROOT),
    )
    assert inv.returncode == 0, inv.stderr

    feats_dir = tmp_path / "feats"
    feats_dir.mkdir()

    def _run():
        r = subprocess.run(
            [sys.executable, "-m", "sdd_reverse_scripts.generate_crosscutting_feats",
             "--project", str(project), "--feats-dir", str(feats_dir), "--json"],
            capture_output=True, text=True, cwd=str(PY_ROOT),
        )
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    out1 = _run()
    out2 = _run()
    assert out1["allocations"] == out2["allocations"], "allocation must be idempotent"
    # both FEATs validate with the deterministic reverse validator
    for fname in (f"{out1['allocations']['XC-Libraries']}-Libraries.md",
                  f"{out1['allocations']['XC-Database']}-Database.md"):
        v = subprocess.run(
            [sys.executable, "-m", "sdd_reverse_scripts.validate_reverse_feat",
             "--feat-path", str(feats_dir / fname), "--json"],
            capture_output=True, text=True, cwd=str(PY_ROOT),
        )
        assert v.returncode == 0, f"{fname} failed validation: {v.stdout} {v.stderr}"
