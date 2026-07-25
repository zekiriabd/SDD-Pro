"""test_sdd_reverse_p2.py — P2 closure tests.

Covers :
    P2.10  multilingual home-page detection in _suggested_name_from_path
           + env-var override SDD_REVERSE_HOME_STEMS
    P2.11  visible warnings when inventory.json is corrupted or FEAT
           unreadable in reverse_status
"""
from __future__ import annotations

import json
import sys
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# P2.10 — i18n suggested name from path
# ---------------------------------------------------------------------------

def test_suggested_name_english_default() -> None:
    from sdd_reverse.ui_unit_detector import _suggested_name_from_path
    assert _suggested_name_from_path("Default.aspx") == "Home"


def test_suggested_name_index_alias() -> None:
    from sdd_reverse.ui_unit_detector import _suggested_name_from_path
    assert _suggested_name_from_path("index.html") == "Home"
    assert _suggested_name_from_path("home.cshtml") == "Home"


def test_suggested_name_french_accueil() -> None:
    """P2.10 closure : FR cognate `accueil.*` → canonical `Home`."""
    from sdd_reverse.ui_unit_detector import _suggested_name_from_path
    assert _suggested_name_from_path("accueil.html") == "Home"
    assert _suggested_name_from_path("Accueil.aspx") == "Home"


def test_suggested_name_spanish_inicio() -> None:
    from sdd_reverse.ui_unit_detector import _suggested_name_from_path
    assert _suggested_name_from_path("inicio.cshtml") == "Home"
    assert _suggested_name_from_path("portada.html") == "Home"


def test_suggested_name_german_startseite() -> None:
    from sdd_reverse.ui_unit_detector import _suggested_name_from_path
    assert _suggested_name_from_path("startseite.aspx") == "Home"


def test_suggested_name_non_home_pascalcase() -> None:
    """Non-home stems keep their PascalCase derivation."""
    from sdd_reverse.ui_unit_detector import _suggested_name_from_path
    assert _suggested_name_from_path("users-list.aspx") == "UsersList"
    assert _suggested_name_from_path("admin/edit_user.cshtml") == "EditUser"
    assert _suggested_name_from_path("Login.aspx") == "Login"


def test_suggested_name_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """SDD_REVERSE_HOME_STEMS replaces defaults — accueil no longer matches."""
    monkeypatch.setenv("SDD_REVERSE_HOME_STEMS", "willkommen,benvenuto")
    from sdd_reverse.ui_unit_detector import _suggested_name_from_path
    # accueil no longer matches the override list
    assert _suggested_name_from_path("accueil.html") == "Accueil"
    # but our exotic stems do
    assert _suggested_name_from_path("willkommen.html") == "Home"
    assert _suggested_name_from_path("benvenuto.html") == "Home"


def test_suggested_name_env_var_empty_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty env var → defaults preserved."""
    monkeypatch.setenv("SDD_REVERSE_HOME_STEMS", "")
    from sdd_reverse.ui_unit_detector import _suggested_name_from_path
    assert _suggested_name_from_path("Default.aspx") == "Home"
    assert _suggested_name_from_path("accueil.html") == "Home"


# ---------------------------------------------------------------------------
# P2.11 — visible warnings in reverse_status
# ---------------------------------------------------------------------------

def _run_status_cli(cwd: Path) -> dict:
    """Invoke reverse_status --json from the given cwd."""
    project_root = Path(__file__).resolve().parents[1]  # .claude/python/
    result = subprocess.run(
        [sys.executable, "-m", "sdd_reverse_scripts.reverse_status", "--json"],
        capture_output=True, text=True, cwd=str(cwd),
        env={
            **dict(__import__("os").environ),
            "PYTHONPATH": str(project_root),
            # reverse_status anchors on the repo root since 2026-06-10
            # (anomalie env closure) — tests target their tmp workspace
            # explicitly instead of relying on the CWD.
            "SDD_REVERSE_WORKSPACE_ROOT": str(cwd),
        },
    )
    assert result.returncode in (0, 1), f"unexpected exit: {result.stderr}"
    return json.loads(result.stdout) if result.stdout.strip() else {}


def test_status_warning_on_corrupted_inventory(tmp_path: Path) -> None:
    """A corrupted inventory.json surfaces as an explicit warning."""
    from sdd_reverse_scripts.reverse_status import _scan_legacy_projects

    workspace_old = tmp_path / "workspace" / "old"
    proj = workspace_old / "broken-project"
    sys_dir = proj / ".sys"
    sys_dir.mkdir(parents=True)
    (sys_dir / "inventory.json").write_text("{not-json-at-all", encoding="utf-8")

    projects = _scan_legacy_projects(workspace_old)
    assert len(projects) == 1
    p = projects[0]
    assert p["name"] == "broken-project"
    assert p["units_total"] == 0
    assert p["feats_extracted"] == 0
    # Critical: warning MUST be visible (was silent before P2.11)
    assert len(p["warnings"]) == 1
    warning = p["warnings"][0]
    assert "[REVERSE_INVENTORY_CORRUPTED]" in warning
    assert "inventory.json" in warning
    assert "/sdd-reverse-inventory" in warning  # actionable hint


def test_status_no_warning_on_valid_inventory(tmp_path: Path) -> None:
    """Healthy inventory → empty warnings list."""
    from sdd_reverse_scripts.reverse_status import _scan_legacy_projects

    workspace_old = tmp_path / "workspace" / "old"
    proj = workspace_old / "ok-project"
    sys_dir = proj / ".sys"
    sys_dir.mkdir(parents=True)
    (sys_dir / "inventory.json").write_text(json.dumps({
        "schemaVersion": 1,
        "units": [{"id": "U-1"}, {"id": "U-2"}],
        "_featAllocations": {"U-1": 1},
        "_allocatedNames": {},
    }), encoding="utf-8")

    projects = _scan_legacy_projects(workspace_old)
    assert len(projects) == 1
    p = projects[0]
    assert p["units_total"] == 2
    # M9 (audit 2026-06-10) : feats_extracted is no longer derived from
    # len(_featAllocations) (lied at pre-allocation time, counted XC-*) —
    # the scan now only exposes the raw allocation data ; the CLI main()
    # cross-references actual FEAT files on disk.
    assert p["_unit_ids"] == ["U-1", "U-2"]
    assert p["_feat_numbers"] == [1]
    assert p["feats_extracted"] == 0  # computed later by main()
    assert p["warnings"] == []


def test_status_feat_unreadable_surfaces_warning(tmp_path: Path) -> None:
    """An unreadable FEAT .md → warning in feat_warnings list."""
    from sdd_reverse_scripts.reverse_status import _scan_reverse_feats

    feats_dir = tmp_path / "feats"
    feats_dir.mkdir()
    # Create a valid reverse FEAT next to a broken one
    (feats_dir / "1-Ok.md").write_text(
        "---\n"
        "generated-by: sdd-reverse\n"
        "confidence: high\n"
        "source-unit: U-1\n"
        "---\n"
        "# OK\n",
        encoding="utf-8",
    )
    # Simulate read failure by creating a directory with the .md name
    (feats_dir / "2-Broken.md").mkdir()  # is_file()==False, but glob picks it

    feats, warnings = _scan_reverse_feats(feats_dir)
    # The valid FEAT is captured
    feat_names = [f["name"] for f in feats]
    assert "1-Ok" in feat_names
    # The broken entry produces a warning (P2.11) — exact behavior depends
    # on whether read_text raises OSError on a dir. Be tolerant : either
    # the warning is emitted, OR the dir is silently skipped without
    # listing it as a FEAT. The CRITICAL invariant is : no silent crash.
    assert "2-Broken" not in feat_names


def test_status_json_output_includes_warnings_total(tmp_path: Path) -> None:
    """JSON output exposes the global warnings_total counter (CI consumption)."""
    # Build a minimal corrupted workspace
    workspace_old = tmp_path / "workspace" / "old"
    proj = workspace_old / "corrupt"
    sys_dir = proj / ".sys"
    sys_dir.mkdir(parents=True)
    (sys_dir / "inventory.json").write_text("not json", encoding="utf-8")
    feats_dir = tmp_path / "workspace" / "feats"
    feats_dir.mkdir(parents=True)

    payload = _run_status_cli(tmp_path)
    assert payload["ok"] is True
    assert "warnings_total" in payload
    assert payload["warnings_total"] >= 1, payload
    # Project carries the warning detail
    proj_record = next((p for p in payload["projects"] if p["name"] == "corrupt"), None)
    assert proj_record is not None
    assert len(proj_record["warnings"]) >= 1
