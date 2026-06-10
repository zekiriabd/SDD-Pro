"""test_sdd_reverse_p1_8_regex.py — P1.8 closure : fragile regex fixes.

Covers :
    - HTML5 unquoted attributes  : ``<input type=text>``
    - HTML5 boolean attributes   : ``<input disabled>``
    - CSS hex8 alpha preservation : ``#aabbccdd`` keeps its alpha channel
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# HTML5 unquoted / boolean attributes (ui_template_parser._parse_attrs)
# ---------------------------------------------------------------------------

def test_parse_attrs_double_quoted() -> None:
    from sdd_reverse.ui_template_parser import _parse_attrs
    out = _parse_attrs(' id="txtFoo" type="text" ')
    assert out["id"] == "txtFoo"
    assert out["type"] == "text"


def test_parse_attrs_single_quoted() -> None:
    from sdd_reverse.ui_template_parser import _parse_attrs
    out = _parse_attrs(" id='txtFoo' name='bar' ")
    assert out["id"] == "txtFoo"
    assert out["name"] == "bar"


def test_parse_attrs_unquoted_html5() -> None:
    """HTML5 unquoted attribute values must be captured."""
    from sdd_reverse.ui_template_parser import _parse_attrs
    out = _parse_attrs(" id=txtFoo type=text maxlength=20 ")
    assert out["id"] == "txtFoo"
    assert out["type"] == "text"
    assert out["maxlength"] == "20"


def test_parse_attrs_boolean_html5() -> None:
    """HTML5 boolean attributes (disabled, readonly, required) detected."""
    from sdd_reverse.ui_template_parser import _parse_attrs
    out = _parse_attrs(" id=foo disabled required readonly ")
    assert "disabled" in out
    assert "required" in out
    assert "readonly" in out


def test_parse_attrs_mixed_styles() -> None:
    """A single tag can mix all 4 styles — all must be captured."""
    from sdd_reverse.ui_template_parser import _parse_attrs
    out = _parse_attrs(' id="myInput" type=email value=\'a@b\' disabled required ')
    assert out["id"] == "myInput"
    assert out["type"] == "email"
    assert out["value"] == "a@b"
    assert "disabled" in out
    assert "required" in out


def test_parse_attrs_no_false_positive_on_text_inside_quotes() -> None:
    """An attribute value containing '=' or words must not leak as new attrs."""
    from sdd_reverse.ui_template_parser import _parse_attrs
    out = _parse_attrs(' value="x = y + z" data-info="a b c" ')
    assert out["value"] == "x = y + z"
    assert out["data-info"] == "a b c"
    # No phantom 'y' or 'b' attribute
    assert "y" not in out
    assert "b" not in out


def test_parse_template_html5_unquoted(tmp_path: Path) -> None:
    """End-to-end : a real HTML5 template with unquoted attrs parses cleanly."""
    from sdd_reverse.ui_template_parser import parse_template
    page = tmp_path / "form.html"
    page.write_text(
        "<!doctype html>\n"
        "<html><head><title>Free Form</title></head>\n"
        "<body><form id=login method=post>\n"
        "  <input type=email name=email required>\n"
        "  <input type=password name=pw required>\n"
        "  <button type=submit disabled>Send</button>\n"
        "</form></body></html>\n",
        encoding="utf-8",
    )
    result = parse_template(page)
    assert result["template_family"] == "html"
    assert result["title"] == "Free Form"
    assert any(f["id"] == "login" for f in result["forms"])
    input_kinds = {e["kind"] for e in result["elements"]}
    assert "input" in input_kinds


# ---------------------------------------------------------------------------
# CSS hex8 alpha preservation (css_palette_extractor._normalize_hex)
# ---------------------------------------------------------------------------

def test_normalize_hex_3_digit_expands() -> None:
    from sdd_reverse.css_palette_extractor import _normalize_hex
    assert _normalize_hex("abc") == "#aabbcc"


def test_normalize_hex_6_digit_lowercases() -> None:
    from sdd_reverse.css_palette_extractor import _normalize_hex
    assert _normalize_hex("AaBbCc") == "#aabbcc"


def test_normalize_hex_8_digit_preserves_alpha() -> None:
    """Regression : alpha channel must be PRESERVED in canonical output."""
    from sdd_reverse.css_palette_extractor import _normalize_hex
    # Before P1.8 fix : h[:6] silently dropped 'dd' alpha
    assert _normalize_hex("AaBbCcDd") == "#aabbccdd"


def test_normalize_hex_4_digit_short_alpha_expands() -> None:
    """CSS3 short ``#rgba`` → expand to ``#rrggbbaa``."""
    from sdd_reverse.css_palette_extractor import _normalize_hex
    assert _normalize_hex("abcd") == "#aabbccdd"


def test_hex_strip_alpha_helper() -> None:
    """Caller can drop alpha for grouping while still having the canonical form."""
    from sdd_reverse.css_palette_extractor import _hex_strip_alpha, _normalize_hex
    canonical = _normalize_hex("AaBbCcDd")  # #aabbccdd
    rgb_only = _hex_strip_alpha(canonical)
    assert rgb_only == "#aabbcc"
    assert canonical == "#aabbccdd"  # original unchanged


def test_hex_strip_alpha_on_6_digit_is_noop() -> None:
    from sdd_reverse.css_palette_extractor import _hex_strip_alpha
    assert _hex_strip_alpha("#aabbcc") == "#aabbcc"
