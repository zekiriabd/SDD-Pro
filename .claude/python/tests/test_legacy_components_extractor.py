"""Tests for sdd_reverse.legacy_components_extractor — Phase 4 UI heuristics.

Covers :
- detect_components_in_html : grid, form, nav, modal, pagination, filter
- threshold respect (< MIN values → no detection)
- deduplication of same-kind detections
- empty HTML / malformed HTML
- GlobalInventory.aggregate_by_kind
- emit_inventory_markdown (table format, sorted by occurrences)
- write_components_inventory (atomic write)
- build_inventory_from_captures (convenience helper)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from sdd_reverse import legacy_components_extractor as lce


# ----------------------------------------------- detect : grids


def test_detect_grid_with_min_rows():
    html = (
        "<table>"
        + "<thead><tr><th>A</th></tr></thead>"
        + "<tbody>"
        + "".join("<tr><td>x</td></tr>" for _ in range(5))
        + "</tbody>"
        + "</table>"
    )
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "grid" for c in components)


def test_detect_grid_with_class_datatable():
    """A small table with class='datatable' should be detected even if few rows."""
    html = (
        "<table class='datatable display'>"
        "<tr><td>1</td></tr>"
        "<tr><td>2</td></tr>"
        "</table>"
    )
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "grid" for c in components)


def test_detect_grid_uses_id_in_label():
    html = (
        "<table id='tbl' class='datatable'>"
        "<tr><td>1</td></tr>"
        "</table>"
    )
    components = lce.detect_components_in_html(html)
    grid = next(c for c in components if c.kind == "grid")
    assert "tbl" in grid.label


def test_no_grid_for_small_plain_table():
    """A table with < MIN rows and no class match should NOT be detected."""
    html = "<table><tr><td>a</td></tr></table>"
    components = lce.detect_components_in_html(html)
    assert not any(c.kind == "grid" for c in components)


# ----------------------------------------------- detect : forms


def test_detect_form_with_min_inputs_and_button():
    html = (
        "<form>"
        "<input type='text' name='a'/>"
        "<input type='text' name='b'/>"
        "<select name='c'><option>x</option></select>"
        "<button type='submit'>OK</button>"
        "</form>"
    )
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "form" for c in components)


def test_no_form_without_button():
    """A form with inputs but no submit button is not a CRUD form."""
    html = (
        "<form>"
        "<input/><input/><input/>"
        "</form>"
    )
    components = lce.detect_components_in_html(html)
    assert not any(c.kind == "form" for c in components)


def test_no_form_below_min_inputs():
    html = (
        "<form>"
        "<input/>"
        "<button>Go</button>"
        "</form>"
    )
    components = lce.detect_components_in_html(html)
    assert not any(c.kind == "form" for c in components)


# ----------------------------------------------- detect : nav


def test_detect_nav_with_min_links():
    html = (
        "<nav>"
        "<a href='/a'>A</a>"
        "<a href='/b'>B</a>"
        "<a href='/c'>C</a>"
        "</nav>"
    )
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "nav" for c in components)


def test_no_nav_with_too_few_links():
    html = "<nav><a href='/a'>A</a></nav>"
    components = lce.detect_components_in_html(html)
    assert not any(c.kind == "nav" for c in components)


# ----------------------------------------------- detect : modal


def test_detect_modal_with_class():
    html = "<div class='modal fade'>content</div>"
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "modal" for c in components)


def test_detect_modal_with_aria_modal():
    html = "<div aria-modal='true'>content</div>"
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "modal" for c in components)


def test_detect_modal_dialog_class():
    html = "<div class='dialog open'>content</div>"
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "modal" for c in components)


def test_no_modal_without_match():
    html = "<div class='regular-div'>content</div>"
    components = lce.detect_components_in_html(html)
    assert not any(c.kind == "modal" for c in components)


# ----------------------------------------------- detect : pagination


def test_detect_pagination_ul_class():
    html = "<ul class='pagination'><li>1</li><li>2</li></ul>"
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "pagination" for c in components)


def test_detect_pagination_nav_class():
    html = "<nav class='pager'><a>1</a></nav>"
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "pagination" for c in components)


# ----------------------------------------------- detect : filter


def test_detect_filter_panel_with_search_button_french():
    html = (
        "<div>"
        "<input type='text' name='q'/>"
        "<select><option>All</option></select>"
        "<button type='submit'>Rechercher</button>"
        "</div>"
    )
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "filter" for c in components)


def test_detect_filter_panel_with_search_button_english():
    html = (
        "<div>"
        "<input type='text'/>"
        "<input type='text'/>"
        "<button>Search</button>"
        "</div>"
    )
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "filter" for c in components)


def test_detect_filter_panel_with_input_value_search():
    """Detects when the submit button is <input type=submit value='Rechercher'>."""
    html = (
        "<form>"
        "<input type='text'/>"
        "<input type='text'/>"
        "<input type='submit' value='Rechercher'/>"
        "</form>"
    )
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "filter" for c in components)


def test_no_filter_without_button_label():
    html = (
        "<div>"
        "<input type='text'/>"
        "<input type='text'/>"
        "<button>Submit</button>"  # generic, not a filter label
        "</div>"
    )
    components = lce.detect_components_in_html(html)
    assert not any(c.kind == "filter" for c in components)


# ----------------------------------------------- deduplication


def test_multiple_grids_collapsed_to_single_detection_with_occurrences():
    html = (
        "<table id='t1' class='datatable'><tr><td>1</td></tr></table>"
        "<table id='t2' class='datatable'><tr><td>2</td></tr></table>"
    )
    components = lce.detect_components_in_html(html)
    grids = [c for c in components if c.kind == "grid"]
    assert len(grids) == 1
    assert grids[0].occurrences == 2


def test_empty_html_returns_no_components():
    assert lce.detect_components_in_html("") == []


def test_malformed_html_doesnt_crash():
    """html.parser is tolerant ; we should not raise on bad input."""
    result = lce.detect_components_in_html("<div><span>unclosed")
    assert isinstance(result, list)


# ----------------------------------------------- GlobalInventory


def test_global_inventory_aggregate_by_kind():
    inv = lce.GlobalInventory(
        pages=[
            lce.PageInventory(
                unit_id="unit-001",
                page_path="/Default.aspx",
                components=[
                    lce.DetectedComponent(kind="grid", label="Grille", suggestion="Table", occurrences=1),
                ],
            ),
            lce.PageInventory(
                unit_id="unit-002",
                page_path="/Other.aspx",
                components=[
                    lce.DetectedComponent(kind="grid", label="Grille", suggestion="Table", occurrences=2),
                    lce.DetectedComponent(kind="form", label="Form", suggestion="Form", occurrences=1),
                ],
            ),
        ]
    )
    agg = inv.aggregate_by_kind()
    assert agg["grid"]["total_occurrences"] == 3
    assert agg["grid"]["pages"] == ["/Default.aspx", "/Other.aspx"]
    assert agg["form"]["total_occurrences"] == 1


def test_global_inventory_dedup_pages_list():
    """If same page detected twice, it appears only once in pages list."""
    inv = lce.GlobalInventory(
        pages=[
            lce.PageInventory(
                unit_id="u1",
                page_path="/A.aspx",
                components=[
                    lce.DetectedComponent(kind="grid", label="Grille", suggestion="Table", occurrences=1),
                    lce.DetectedComponent(kind="grid", label="Grille", suggestion="Table", occurrences=1),
                ],
            ),
        ]
    )
    agg = inv.aggregate_by_kind()
    assert agg["grid"]["pages"] == ["/A.aspx"]


# ----------------------------------------------- emit_inventory_markdown


def test_emit_inventory_markdown_header_and_table():
    inv = lce.GlobalInventory(
        pages=[
            lce.PageInventory(
                unit_id="u1",
                page_path="/A",
                components=[
                    lce.DetectedComponent(kind="grid", label="Grille X", suggestion="<Table>"),
                ],
            ),
        ]
    )
    md = lce.emit_inventory_markdown(inv, project_name="AspxDemo", extraction_date="2026-06-10")
    assert "AspxDemo" in md
    assert "2026-06-10" in md
    assert "| Grille X |" in md
    assert "<Table>" in md


def test_emit_inventory_markdown_empty_inventory():
    md = lce.emit_inventory_markdown(lce.GlobalInventory(), project_name="Empty")
    assert "Aucun composant" in md


def test_emit_inventory_markdown_sorted_by_occurrences():
    inv = lce.GlobalInventory(
        pages=[
            lce.PageInventory(
                unit_id="u1", page_path="/A",
                components=[
                    lce.DetectedComponent(kind="form", label="Form", suggestion="X", occurrences=1),
                    lce.DetectedComponent(kind="grid", label="Grille", suggestion="Y", occurrences=10),
                ],
            ),
        ]
    )
    md = lce.emit_inventory_markdown(inv, project_name="Sorted")
    # Grille should appear before Form (higher occurrences)
    grid_idx = md.find("Grille")
    form_idx = md.find("Form")
    assert grid_idx < form_idx


def test_emit_inventory_markdown_truncates_long_pages_list():
    """If > 5 pages, suffix '(+N)' should appear."""
    pages = [
        lce.PageInventory(
            unit_id=f"u{i}", page_path=f"/p{i}.aspx",
            components=[lce.DetectedComponent(kind="grid", label="G", suggestion="T")],
        )
        for i in range(7)
    ]
    inv = lce.GlobalInventory(pages=pages)
    md = lce.emit_inventory_markdown(inv, project_name="x")
    assert "(+2)" in md  # 7 pages, shows 5 + (+2)


# ----------------------------------------------- write_components_inventory


def test_write_components_inventory_persists_atomically(tmp_path):
    inv = lce.GlobalInventory(
        pages=[
            lce.PageInventory(
                unit_id="u1", page_path="/A",
                components=[lce.DetectedComponent(kind="grid", label="G", suggestion="T")],
            ),
        ]
    )
    target = tmp_path / "components-inventory.md"
    lce.write_components_inventory(inv, target, project_name="X", extraction_date="2026-06-10")
    assert target.is_file()
    assert "| G |" in target.read_text(encoding="utf-8")
    # No tmp leftover
    assert list(tmp_path.glob("*.sddtmp")) == []


# ----------------------------------------------- build_inventory_from_captures


def test_build_inventory_from_captures_single_page():
    html = (
        "<table id='employees' class='datatable'><tr><td>x</td></tr></table>"
    )
    inv = lce.build_inventory_from_captures([("u1", "/Default.aspx", html)])
    assert len(inv.pages) == 1
    assert inv.pages[0].unit_id == "u1"
    assert inv.pages[0].page_path == "/Default.aspx"
    assert any(c.kind == "grid" for c in inv.pages[0].components)


def test_build_inventory_from_captures_multiple_pages():
    captures = [
        ("u1", "/A.aspx", "<table id='t1' class='grid'><tr><td>x</td></tr></table>"),
        ("u2", "/B.aspx", "<form><input/><input/><input/><button>Go</button></form>"),
        ("u3", "/C.aspx", "<nav><a>1</a><a>2</a><a>3</a></nav>"),
    ]
    inv = lce.build_inventory_from_captures(captures)
    assert len(inv.pages) == 3
    kinds_total = {c.kind for page in inv.pages for c in page.components}
    assert "grid" in kinds_total
    assert "form" in kinds_total
    assert "nav" in kinds_total


# ----------------------------------------------- aspx-flavored html


def test_aspx_gridview_detected_as_grid():
    """Real-ish ASPX server rendering output."""
    html = """
    <table id="ContentPlaceHolder1_GridView1" class="gridview" cellspacing="0">
        <tr><th>Id</th><th>Name</th><th>Email</th></tr>
        <tr><td>1</td><td>Alice</td><td>a@x</td></tr>
        <tr><td>2</td><td>Bob</td><td>b@x</td></tr>
        <tr><td>3</td><td>Carol</td><td>c@x</td></tr>
        <tr><td>4</td><td>Dave</td><td>d@x</td></tr>
        <tr><td>5</td><td>Eve</td><td>e@x</td></tr>
    </table>
    """
    components = lce.detect_components_in_html(html)
    grids = [c for c in components if c.kind == "grid"]
    assert len(grids) == 1
    assert "ContentPlaceHolder1_GridView1" in grids[0].label


def test_master_nav_with_aspx_menu():
    """ASPX Site.Master typically renders a nav with multiple anchor tags."""
    html = """
    <header>
        <nav>
            <a href="/Default.aspx">Employees</a>
            <a href="/Products.aspx">Products</a>
            <a href="/Posts.aspx">Posts</a>
            <a href="/UsersServer.aspx">Users</a>
        </nav>
    </header>
    """
    components = lce.detect_components_in_html(html)
    assert any(c.kind == "nav" for c in components)
