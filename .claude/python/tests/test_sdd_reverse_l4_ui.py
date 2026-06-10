"""test_sdd_reverse_l4_ui.py — L4 frontend fidelity.

Verifies the UI template parser now captures grid columns, data-binding,
the full set of form controls (dropdown/checkbox/textarea/select), navigation
targets, and that the palette extractor reads inline <style>/style="" too.
"""

from __future__ import annotations

import sys
from pathlib import Path

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.css_palette_extractor import extract_palette  # noqa: E402
from sdd_reverse.ui_template_parser import parse_template  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "legacy-webforms-grid"
USERS_ASPX = FIXTURE / "Users.aspx"


def test_grid_columns_are_extracted():
    parsed = parse_template(USERS_ASPX)
    grids = [g for g in parsed["grids"] if g.get("id") == "gvUsers"]
    assert grids, "GridView gvUsers must be detected"
    cols = grids[0]["columns"]
    headers = [c["header"] for c in cols]
    assert "Identifiant" in headers
    assert "Nom d'utilisateur" in headers
    assert "Actions" in headers  # TemplateField
    datafields = [c["dataField"] for c in cols if c["dataField"]]
    assert {"Id", "Username", "CreatedAt"} <= set(datafields)


def test_data_binding_fields_captured():
    parsed = parse_template(USERS_ASPX)
    # Eval("Id") in the TemplateField
    assert "Id" in parsed["bindings"]


def test_dropdown_with_options():
    parsed = parse_template(USERS_ASPX)
    selects = [e for e in parsed["elements"] if e["kind"] == "select"]
    assert selects, "asp:DropDownList must be parsed as a select"
    ddl = selects[0]
    texts = [o["text"] for o in ddl["options"]]
    assert "Administrateur" in texts
    assert "Utilisateur" in texts


def test_checkbox_parsed():
    parsed = parse_template(USERS_ASPX)
    checks = [e for e in parsed["elements"] if e["kind"] == "checkbox"]
    assert checks and checks[0]["text"] == "Actifs uniquement"


def test_navigation_targets_include_postbackurl():
    parsed = parse_template(USERS_ASPX)
    assert "Export.aspx" in parsed["navTargets"]


def test_palette_reads_inline_style():
    from sdd_reverse.scan_legacy import load_signatures, scan_project
    from sdd_reverse.paths import language_signatures_path
    sigs = load_signatures(language_signatures_path())
    scan = scan_project(FIXTURE, sigs)
    palette = extract_palette(FIXTURE, scan)
    hexes = {c["hex"] for c in palette["colors"]}
    # colours only present in the inline <style> / style="" of Users.aspx
    assert "#2563eb" in hexes or "#1e40af" in hexes or "#f8fafc" in hexes
    assert any("inline" in s for s in palette["css_sources"])


def test_wpf_branch_still_returns_new_keys():
    # WPF output shape must carry the new keys (empty) for consumer uniformity.
    wpf_fixture = Path(__file__).parent / "fixtures" / "legacy-wpf-minimal"
    xaml = next(wpf_fixture.rglob("*.xaml"), None)
    if xaml is None:
        return  # fixture variant without xaml — skip silently
    parsed = parse_template(xaml)
    assert "bindings" in parsed and "navTargets" in parsed
