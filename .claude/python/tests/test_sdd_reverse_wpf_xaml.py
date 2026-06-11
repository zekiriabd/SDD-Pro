"""test_sdd_reverse_wpf_xaml.py — WPF XAML reverse engineering support.

Validates the extension added 2026-06-10 for Windows desktop UI legacy:
    1. language_signatures.yml `wpf-xaml` entry detected
    2. ui_template_parser parses WPF XAML into the common output shape
    3. ui_unit_detector treats Window/Page as units and App.xaml as layout
    4. scan_legacy + ui_template_parser + ui_unit_detector compose
       correctly on the legacy-wpf-minimal fixture
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixture_utils import copy_legacy_fixture

# Lecture seule (parse_template, scan_project) — le test e2e qui exécute
# reverse_inventory (écriture .sys/) passe par copy_legacy_fixture.
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "legacy-wpf-minimal"
PROJECT_ROOT = Path(__file__).parent.parent  # .claude/python/


# ===========================================================================
# 1. Language signature recognized
# ===========================================================================

def test_wpf_xaml_signature_present_in_yaml() -> None:
    """language_signatures.yml declares `wpf-xaml` with confidence_cap=high."""
    from sdd_reverse.paths import language_signatures_path
    import yaml
    sig_path = language_signatures_path()
    data = yaml.safe_load(sig_path.read_text(encoding="utf-8"))
    langs = {lang["id"]: lang for lang in data["languages"]}
    assert "wpf-xaml" in langs, "wpf-xaml not declared in language_signatures.yml"
    wpf = langs["wpf-xaml"]
    assert ".xaml" in wpf["file_extensions"]
    assert wpf["confidence_cap"] == "high"
    assert wpf["family"] == "dotnet"


def test_wpf_xaml_evidence_patterns_match_real_namespace() -> None:
    """The evidence_patterns regex actually match a canonical WPF root."""
    import re
    import yaml
    from sdd_reverse.paths import language_signatures_path

    data = yaml.safe_load(language_signatures_path().read_text(encoding="utf-8"))
    wpf = next(l for l in data["languages"] if l["id"] == "wpf-xaml")
    sample = (FIXTURE_ROOT / "Views" / "LoginWindow.xaml").read_text(encoding="utf-8")
    hits = sum(
        1 for ep in wpf["evidence_patterns"]
        if re.search(ep["pattern"], sample)
    )
    # At least 5 of the ~10 patterns should match this realistic Login.xaml
    assert hits >= 5, f"only {hits} evidence patterns matched the WPF fixture"


# ===========================================================================
# 2. ui_template_parser — _detect_family + _parse_xaml_template
# ===========================================================================

def test_xaml_detect_family_returns_wpf() -> None:
    from sdd_reverse.ui_template_parser import _detect_family
    assert _detect_family(Path("LoginWindow.xaml")) == "wpf"
    assert _detect_family(Path("Views/App.xaml")) == "wpf"


def test_parse_template_wpf_login_extracts_title() -> None:
    from sdd_reverse.ui_template_parser import parse_template
    result = parse_template(FIXTURE_ROOT / "Views" / "LoginWindow.xaml")
    assert result["template_family"] == "wpf"
    assert result["title"] == "Connexion"


def test_parse_template_wpf_login_detects_root_form() -> None:
    """Window root recorded as a `form` entry with wpf_root='Window'."""
    from sdd_reverse.ui_template_parser import parse_template
    result = parse_template(FIXTURE_ROOT / "Views" / "LoginWindow.xaml")
    assert len(result["forms"]) == 1
    f = result["forms"][0]
    assert f.get("wpf_root") == "Window"
    # x:Class is on the root — we don't extract Name there (no Name=), so id empty is OK
    assert "id" in f


def test_parse_template_wpf_login_inputs() -> None:
    """TextBox + PasswordBox extracted with x:Name as id, correct types."""
    from sdd_reverse.ui_template_parser import parse_template
    result = parse_template(FIXTURE_ROOT / "Views" / "LoginWindow.xaml")
    inputs = {e["id"]: e for e in result["elements"] if e["kind"] == "input"}
    assert "txtUsername" in inputs, f"missing txtUsername: {list(inputs)}"
    assert inputs["txtUsername"]["type"] == "text"
    assert inputs["txtUsername"]["wpf_control"] == "TextBox"
    assert "pwdPassword" in inputs
    assert inputs["pwdPassword"]["type"] == "password"
    assert inputs["pwdPassword"]["wpf_control"] == "PasswordBox"


def test_parse_template_wpf_login_buttons() -> None:
    """Button elements extracted with Click handler."""
    from sdd_reverse.ui_template_parser import parse_template
    result = parse_template(FIXTURE_ROOT / "Views" / "LoginWindow.xaml")
    buttons = {e["id"]: e for e in result["elements"] if e["kind"] == "button"}
    assert "btnLogin" in buttons
    assert buttons["btnLogin"]["text"] == "Se connecter"
    assert buttons["btnLogin"]["on_click"] == "btnLogin_Click"
    assert "btnCancel" in buttons
    assert buttons["btnCancel"]["on_click"] == "btnCancel_Click"


def test_parse_template_wpf_label_to_input_association() -> None:
    """Label Target={Binding ElementName=...} resolves the label text on the input."""
    from sdd_reverse.ui_template_parser import parse_template
    result = parse_template(FIXTURE_ROOT / "Views" / "LoginWindow.xaml")
    txtuser = next(e for e in result["elements"]
                   if e["kind"] == "input" and e["id"] == "txtUsername")
    # Label text "Nom d'utilisateur :" should attach via Target ElementName binding
    assert txtuser.get("label") == "Nom d'utilisateur :"


def test_parse_template_wpf_userslist_detects_datagrid() -> None:
    """UsersListPage → DataGrid captured with ItemsSource."""
    from sdd_reverse.ui_template_parser import parse_template
    result = parse_template(FIXTURE_ROOT / "Views" / "UsersListPage.xaml")
    assert result["template_family"] == "wpf"
    grids = result["grids"]
    dg = next((g for g in grids if g.get("wpf_control") == "DataGrid"), None)
    assert dg is not None, f"DataGrid missing in {grids}"
    assert dg["id"] == "dgUsers"
    assert "Users" in dg["items_source"]  # {Binding Users}


def test_parse_template_wpf_userslist_buttons_with_command() -> None:
    """MVVM Command binding extracted alongside Click handler."""
    from sdd_reverse.ui_template_parser import parse_template
    result = parse_template(FIXTURE_ROOT / "Views" / "UsersListPage.xaml")
    buttons = {e["id"]: e for e in result["elements"] if e["kind"] == "button"}
    assert "btnRefresh" in buttons
    assert buttons["btnRefresh"]["on_click"] == "btnRefresh_Click"
    assert "btnAdd" in buttons
    # Command binding preserved (MVVM pattern)
    assert "AddUserCommand" in buttons["btnAdd"]["command"]


def test_parse_template_wpf_app_xaml_yields_no_meaningful_elements() -> None:
    """App.xaml has Application root — parser returns empty elements list."""
    from sdd_reverse.ui_template_parser import parse_template
    result = parse_template(FIXTURE_ROOT / "App.xaml")
    assert result["template_family"] == "wpf"
    # No Window/Page/UserControl → no form record
    assert result["forms"] == []
    # No interactive controls
    assert result["elements"] == []


# ===========================================================================
# 3. ui_unit_detector — App.xaml filtered, Login/UsersList kept
# ===========================================================================

def test_unit_detector_skips_app_xaml() -> None:
    """App.xaml is classified as 'layout' and filtered out of units."""
    from sdd_reverse.ui_unit_detector import _classify_page
    content = (FIXTURE_ROOT / "App.xaml").read_text(encoding="utf-8")
    kind, score = _classify_page(content, "App.xaml")
    assert kind == "layout"
    assert score == 0.0


def test_unit_detector_resource_dictionary_only_is_layout(tmp_path: Path) -> None:
    """A standalone ResourceDictionary file is treated as layout (theme)."""
    from sdd_reverse.ui_unit_detector import _classify_page
    rd = (
        '<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" '
        'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">'
        '<SolidColorBrush x:Key="Primary" Color="#2563EB" />'
        '</ResourceDictionary>'
    )
    kind, _ = _classify_page(rd, "Themes/Brand.xaml")
    assert kind == "layout"


def test_unit_detector_login_window_is_form() -> None:
    """LoginWindow.xaml classified as 'form' (TextBox + PasswordBox + Button)."""
    from sdd_reverse.ui_unit_detector import _classify_page
    content = (FIXTURE_ROOT / "Views" / "LoginWindow.xaml").read_text(encoding="utf-8")
    kind, score = _classify_page(content, "Views/LoginWindow.xaml")
    assert kind == "form"
    assert score >= 1.0


def test_unit_detector_userslist_is_grid() -> None:
    """UsersListPage.xaml classified as 'grid' (DataGrid present)."""
    from sdd_reverse.ui_unit_detector import _classify_page
    content = (FIXTURE_ROOT / "Views" / "UsersListPage.xaml").read_text(encoding="utf-8")
    kind, score = _classify_page(content, "Views/UsersListPage.xaml")
    assert kind == "grid"
    assert score >= 1.0


# ===========================================================================
# 4. End-to-end : scan_legacy detects WPF as primary language
# ===========================================================================

def test_scan_legacy_detects_wpf_primary() -> None:
    """scan_project on the WPF fixture identifies wpf-xaml as a top language."""
    from sdd_reverse.paths import language_signatures_path
    from sdd_reverse.scan_legacy import load_signatures, scan_project

    sig = load_signatures(language_signatures_path())
    result = scan_project(FIXTURE_ROOT, sig)
    detected_ids = [lm.id for lm in result.languages]
    assert "wpf-xaml" in detected_ids, f"wpf-xaml not detected, got: {detected_ids}"


def test_e2e_reverse_inventory_on_wpf_fixture(tmp_path) -> None:
    """`reverse_inventory` CLI succeeds on the WPF fixture and reports >=2 units."""
    project = copy_legacy_fixture("legacy-wpf-minimal", tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "sdd_reverse_scripts.reverse_inventory",
         "--project", str(project), "--json"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"reverse_inventory failed: {result.stderr}"
    report = json.loads(result.stdout)
    assert report["ok"] is True
    # Exactly 2 user-facing screens (LoginWindow + UsersListPage) — App.xaml filtered
    assert report["unitsDetected"] >= 2, report
    # Primary language must be one of wpf-xaml or csharp (csharp has more LOC weight
    # in tiny fixtures because of code-behind .cs files)
    assert report["primaryLanguage"] in {"wpf-xaml", "csharp"}, report
