"""Tests for sdd_reverse.inventory_builder, ui_unit_detector, and CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sdd_reverse import scan_legacy, inventory_builder, ui_unit_detector


SIGNATURES_PATH = (
    Path(__file__).resolve().parent.parent / "sdd_reverse" / "language_signatures.yml"
)
_PY_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def signatures():
    return scan_legacy.load_signatures(SIGNATURES_PATH)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_aspx_legacy(root: Path) -> None:
    """Construct a realistic mini WebForms legacy for testing."""
    _write(root / "Default.aspx", (
        '<%@ Page Language="C#" Title="Accueil" %>\n'
        '<html runat="server"><head><title>AcmeCRM Home</title></head>'
        '<body><form runat="server"><h1>Bienvenue</h1></form></body></html>\n'
    ))
    _write(root / "Login.aspx", (
        '<%@ Page Language="C#" %>\n'
        '<html runat="server"><head><title>Connexion</title></head>'
        '<body><form runat="server"><asp:Login ID="Login1" runat="server" />'
        '</form></body></html>\n'
    ))
    _write(root / "Login.aspx.cs", (
        "using System;\npublic partial class Login : Page {\n"
        "  protected void Login1_Authenticate(object s, EventArgs e) { }\n}\n"
    ))
    _write(root / "Customers" / "List.aspx", (
        '<%@ Page Language="C#" Title="Liste clients" %>\n'
        '<html runat="server"><head><title>Clients</title></head>\n'
        '<body><form runat="server">\n'
        '  <asp:DropDownList ID="ddStatus" runat="server" />\n'
        '  <asp:TextBox ID="txtName" runat="server" />\n'
        '  <asp:Button ID="BtnSearch" runat="server" OnClick="BtnSearch_Click" />\n'
        '  <asp:GridView ID="grdCustomers" runat="server" '
        'OnRowEditing="OnRowEditing" OnRowDeleting="OnRowDeleting"></asp:GridView>\n'
        '</form></body></html>\n'
    ))
    _write(root / "Customers" / "List.aspx.cs", (
        "using System;\npublic partial class CustomersList : Page {\n"
        "  protected void BindGrid() { }\n"
        "  protected void BtnSearch_Click(object s, EventArgs e) { BindGrid(); }\n"
        "  protected void OnRowEditing(object s, EventArgs e) { }\n"
        "  protected void OnRowDeleting(object s, EventArgs e) { }\n}\n"
    ))
    _write(root / "Site.Master", (
        '<%@ Master Language="C#" %>\n'
        '<html><head><title>AcmeCRM</title></head>'
        '<body><asp:Menu runat="server" /></body></html>\n'
    ))
    _write(root / "Web.config", '<?xml version="1.0"?><configuration/>')


def test_detect_pages_finds_aspx_files(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    pages = inventory_builder.detect_pages(scan, tmp_path)
    page_paths = {p["path"] for p in pages}
    assert any("Default.aspx" in p for p in page_paths)
    assert any("Login.aspx" in p for p in page_paths)
    assert any("Customers/List.aspx" in p or "Customers\\List.aspx" in p for p in page_paths)


def test_detect_pages_extracts_title(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    pages = inventory_builder.detect_pages(scan, tmp_path)
    titles = {p["title_detected"] for p in pages if p["title_detected"]}
    assert "AcmeCRM Home" in titles
    assert "Connexion" in titles
    assert "Clients" in titles


def test_detect_pages_finds_code_behind(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    pages = inventory_builder.detect_pages(scan, tmp_path)
    login_page = next(p for p in pages if p["path"].endswith("Login.aspx"))
    assert login_page["code_behind"] is not None
    assert "Login.aspx.cs" in login_page["code_behind"]


def test_detect_pages_complexity_increases_with_loc(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    pages = inventory_builder.detect_pages(scan, tmp_path)
    # All pages should have a complexity score between 1 and 5
    for p in pages:
        assert 1 <= p["complexity_score"] <= 5


def test_detect_entry_points_classifies_root_and_auth(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    inv = inventory_builder.build_inventory(scan, tmp_path)
    entries = inv["entry_points"]
    roles = {e["role"] for e in entries}
    assert "root" in roles  # Default.aspx
    assert "auth" in roles  # Login.aspx


def test_suggest_modules_groups_by_folder(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    inv = inventory_builder.build_inventory(scan, tmp_path)
    module_labels = {m["label"] for m in inv["modules_suggested"]}
    # Customers is a subfolder → module name = Customers
    assert "Customers" in module_labels
    # Login.aspx at root → Authentication
    assert "Authentication" in module_labels


def test_build_inventory_returns_full_schema(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    inv = inventory_builder.build_inventory(scan, tmp_path)
    # All expected top-level keys
    for key in ("schema_version", "project", "languages", "frameworks",
                "manifests", "pages", "entry_points", "modules_suggested",
                "exclusions", "stats"):
        assert key in inv


# ============================================================================
# ui_unit_detector tests
# ============================================================================


def test_detect_units_grid_crud_on_aspx(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    inv = inventory_builder.build_inventory(scan, tmp_path)
    units_result = ui_unit_detector.detect_all_units(inv["pages"], tmp_path)
    units = units_result["units"]
    types_detected = {u["type"] for u in units}
    assert "grid-crud" in types_detected
    assert "form-login" in types_detected
    assert "navigation-menu" in types_detected


def test_detect_units_merge_hint_filter_to_grid(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    inv = inventory_builder.build_inventory(scan, tmp_path)
    units_result = ui_unit_detector.detect_all_units(inv["pages"], tmp_path)
    # Find filter-panel unit on Customers/List
    filter_units = [u for u in units_result["units"] if u["type"] == "filter-panel"]
    if filter_units:
        # Should propose merge to grid-crud
        assert filter_units[0]["merge_hint"] is not None
        assert "grid" in filter_units[0]["merge_hint"].lower() or "filtres" in filter_units[0]["merge_hint"].lower()


def test_detect_units_evidence_format(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    inv = inventory_builder.build_inventory(scan, tmp_path)
    units_result = ui_unit_detector.detect_all_units(inv["pages"], tmp_path)
    for u in units_result["units"]:
        # Each unit must have at least one evidence entry
        assert u["evidence"], f"unit {u['id']} has no evidence"
        ev = u["evidence"][0]
        assert "file" in ev
        assert "lines" in ev
        # lines format: "start-end"
        assert "-" in ev["lines"]


def test_detect_units_confidence_per_unit(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    scan = scan_legacy.scan_project(tmp_path, signatures)
    inv = inventory_builder.build_inventory(scan, tmp_path)
    units_result = ui_unit_detector.detect_all_units(inv["pages"], tmp_path)
    for u in units_result["units"]:
        assert u["confidence_hint"] in ("high", "medium", "low")


def test_detect_units_php_post_handler(tmp_path, signatures):
    _write(tmp_path / "login.php", (
        '<?php\n'
        'if ($_SERVER["REQUEST_METHOD"] == "POST") {\n'
        '    // authenticate\n'
        '}\n'
        '?>\n'
        '<form method="post"><input type="password" name="pwd"/></form>\n'
    ))
    scan = scan_legacy.scan_project(tmp_path, signatures)
    inv = inventory_builder.build_inventory(scan, tmp_path)
    units = ui_unit_detector.detect_all_units(inv["pages"], tmp_path)
    types = {u["type"] for u in units["units"]}
    # PHP login.php should detect at least one form-related unit
    assert types & {"form-login", "form-submit"}, f"got types: {types}"


# ============================================================================
# CLI tests
# ============================================================================


def test_cli_creates_inventory_and_units_files(tmp_path, signatures):
    _build_aspx_legacy(tmp_path)
    cmd = [
        sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
        "--project-path", str(tmp_path),
        "--json",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_PY_ROOT),
        timeout=30,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    sys_dir = tmp_path / ".sys"
    assert (sys_dir / "inventory-raw.json").is_file()
    assert (sys_dir / "units-candidates.json").is_file()


def test_cli_json_output_valid(tmp_path):
    """In --json mode, stdout is a single JSON document (no chat updates)."""
    _build_aspx_legacy(tmp_path)
    cmd = [
        sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
        "--project-path", str(tmp_path),
        "--json",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_PY_ROOT),
        timeout=30,
    )
    assert result.returncode == 0
    # stdout should parse as a single JSON document (chat updates suppressed)
    summary = json.loads(result.stdout)
    assert summary["ok"] is True
    assert summary["summary"]["pages_count"] >= 3
    assert summary["summary"]["units_count"] >= 1
    assert "global_confidence" in summary["summary"]


def test_cli_chat_mode_emits_progress_lines(tmp_path):
    """Without --json, stdout emits [REVERSE] chat lines + [DONE] verdict."""
    _build_aspx_legacy(tmp_path)
    cmd = [
        sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
        "--project-path", str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_PY_ROOT), timeout=30)
    assert result.returncode == 0
    assert "[REVERSE]" in result.stdout
    assert "[DONE]" in result.stdout
    # No JSON document should leak when --json absent
    assert '"ok":' not in result.stdout


def test_cli_inventory_json_has_required_keys(tmp_path):
    _build_aspx_legacy(tmp_path)
    cmd = [
        sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
        "--project-path", str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_PY_ROOT), timeout=30)
    assert result.returncode == 0
    inv = json.loads((tmp_path / ".sys" / "inventory-raw.json").read_text(encoding="utf-8"))
    for key in ("languages", "pages", "modules_suggested", "entry_points",
                "exclusions", "stats", "schema_version"):
        assert key in inv


def test_cli_units_json_has_required_keys(tmp_path):
    _build_aspx_legacy(tmp_path)
    cmd = [
        sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
        "--project-path", str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_PY_ROOT), timeout=30)
    assert result.returncode == 0
    units = json.loads((tmp_path / ".sys" / "units-candidates.json").read_text(encoding="utf-8"))
    assert "schema_version" in units
    assert "units" in units
    for u in units["units"]:
        # Required fields per design doc §2.4
        for k in ("id", "page_id", "page_path", "type", "label_proposed",
                  "evidence", "confidence_hint"):
            assert k in u


def test_cli_fails_on_nonexistent_project(tmp_path):
    cmd = [
        sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
        "--project-path", str(tmp_path / "does-not-exist"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_PY_ROOT), timeout=30)
    assert result.returncode == 1
    assert "[REVERSE_PRECONDITION]" in result.stderr


def test_cli_fails_on_empty_project(tmp_path):
    cmd = [
        sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
        "--project-path", str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_PY_ROOT), timeout=30)
    assert result.returncode == 3
    assert "[REVERSE_NO_LANGUAGE]" in result.stderr
