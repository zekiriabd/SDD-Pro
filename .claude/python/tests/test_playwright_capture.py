"""Tests for sdd_reverse.playwright_capture — Phase 4 capture orchestration.

Covers :
- is_playwright_available (real check)
- assess_capture_size (size < threshold → CAPTURE_EMPTY)
- assess_status_code (401/403 → AUTH_REQUIRED warning, other → None)
- parse_css_color helpers via aggregate flow (covered by css_palette tests)
- capture_url orchestration with mocked async capture function :
  - playwright missing → REVERSE_UI_PLAYWRIGHT_MISSING
  - capture raises → REVERSE_UI_CAPTURE_FAILED
  - empty html → REVERSE_UI_CAPTURE_EMPTY
  - 401 status → warning only
  - happy path → ok=True
- write_capture_outputs (atomic write of HTML + palette JSON + PNG)
- load_auth_cookies (valid file, absent file, malformed schema)
- derive_route_from_unit_path (windows backslash, leading slash, empty)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sdd_reverse import playwright_capture as pc


# --------------------------------------------------------- availability


def test_is_playwright_available_returns_bool():
    """Real check : returns False in CI/dev without playwright installed."""
    result = pc.is_playwright_available()
    assert isinstance(result, bool)


def test_playwright_install_hint_mentions_pip_and_chromium():
    hint = pc.playwright_install_hint()
    assert "pip install playwright" in hint
    assert "chromium" in hint


# -------------------------------------------------------- size assessment


def test_assess_capture_size_returns_none_for_large_html():
    big_html = "<html>" + "x" * 1000 + "</html>"
    assert pc.assess_capture_size(big_html) is None


def test_assess_capture_size_returns_error_for_empty_html():
    err = pc.assess_capture_size("")
    assert err is not None
    assert err.code == "REVERSE_UI_CAPTURE_EMPTY"


def test_assess_capture_size_threshold_500():
    # Exactly under threshold
    small = "<html>" + "x" * 100 + "</html>"  # ~113 chars
    err = pc.assess_capture_size(small)
    assert err is not None
    assert "500 chars" in err.detail


# ------------------------------------------------------ status assessment


def test_assess_status_code_401_returns_auth_required():
    err = pc.assess_status_code(401)
    assert err is not None
    assert err.code == "REVERSE_UI_AUTH_REQUIRED"


def test_assess_status_code_403_returns_auth_required():
    err = pc.assess_status_code(403)
    assert err is not None
    assert err.code == "REVERSE_UI_AUTH_REQUIRED"


def test_assess_status_code_200_returns_none():
    assert pc.assess_status_code(200) is None


def test_assess_status_code_500_returns_none():
    """500 is NOT auth-required ; caller decides via raw_html assessment."""
    assert pc.assess_status_code(500) is None


def test_assess_status_code_none_returns_none():
    assert pc.assess_status_code(None) is None


# ----------------------------------------------------- capture_url paths


def test_capture_url_returns_error_when_playwright_missing():
    fake_unavailable = MagicMock(return_value=False)
    result = pc.capture_url(
        "http://127.0.0.1:5099", "/Default.aspx", "unit-001",
        _is_available_fn=fake_unavailable,
    )
    assert result.ok is False
    assert result.errors[0].code == "REVERSE_UI_PLAYWRIGHT_MISSING"
    assert "pip install playwright" in result.errors[0].fix


def test_capture_url_returns_error_when_capture_raises():
    async def boom(**kwargs):
        raise TimeoutError("networkidle timeout")

    def runner(coro):
        # Simulate asyncio.run by running the coroutine to exception
        try:
            coro.send(None)
        except StopIteration:
            pass
        except Exception:
            raise

    result = pc.capture_url(
        "http://127.0.0.1:5099", "/X.aspx", "unit-001",
        _is_available_fn=MagicMock(return_value=True),
        _capture_fn=boom,
        _asyncio_run=runner,
    )
    assert result.ok is False
    assert result.errors[0].code == "REVERSE_UI_CAPTURE_FAILED"
    assert "TimeoutError" in result.errors[0].detail


def test_capture_url_happy_path_returns_ok():
    async def fake_capture(**kwargs):
        return {
            "raw_html": "<html>" + "x" * 1000 + "</html>",
            "palette": {"colors": ["rgb(0,0,0)"], "fonts": ["Arial"]},
            "screenshot_bytes": b"PNG",
            "status_code": 200,
        }

    def runner(coro):
        return coro.send(None) if False else _drive(coro)

    result = pc.capture_url(
        "http://127.0.0.1:5099", "/Default.aspx", "unit-001",
        _is_available_fn=MagicMock(return_value=True),
        _capture_fn=fake_capture,
        _asyncio_run=_drive,
    )
    assert result.ok is True
    assert result.unit_id == "unit-001"
    assert result.html_size > 500
    assert result.status_code == 200
    assert result.palette["colors"] == ["rgb(0,0,0)"]
    assert result.screenshot_bytes == b"PNG"
    assert not result.errors


def test_capture_url_empty_html_marks_not_ok():
    async def fake_capture(**kwargs):
        return {
            "raw_html": "<html></html>",  # 13 chars
            "palette": {},
            "screenshot_bytes": b"",
            "status_code": 200,
        }

    result = pc.capture_url(
        "http://127.0.0.1:5099", "/X.aspx", "unit-001",
        _is_available_fn=MagicMock(return_value=True),
        _capture_fn=fake_capture,
        _asyncio_run=_drive,
    )
    assert result.ok is False
    assert any(e.code == "REVERSE_UI_CAPTURE_EMPTY" for e in result.errors)


def test_capture_url_401_status_attaches_warning_keeps_ok_if_html_substantive():
    big_html = "<html>" + "x" * 1000 + "</html>"

    async def fake_capture(**kwargs):
        return {
            "raw_html": big_html,
            "palette": {},
            "screenshot_bytes": b"",
            "status_code": 401,
        }

    result = pc.capture_url(
        "http://127.0.0.1:5099", "/Secure.aspx", "unit-099",
        _is_available_fn=MagicMock(return_value=True),
        _capture_fn=fake_capture,
        _asyncio_run=_drive,
    )
    # Substantive HTML : ok stays True, auth-required is just a warning
    assert result.ok is True
    assert any(w.code == "REVERSE_UI_AUTH_REQUIRED" for w in result.warnings)


# ------------------------------------------- write_capture_outputs


def test_write_capture_outputs_persists_all_artifacts(tmp_path):
    result = pc.CaptureResult(
        ok=True,
        unit_id="unit-005",
        url="http://x/y",
        raw_html="<html>test</html>",
        palette={"colors": ["rgb(0,0,0)"]},
        screenshot_bytes=b"PNGBYTES",
    )
    written = pc.write_capture_outputs(result, tmp_path)
    assert "html" in written
    assert "palette" in written
    assert "screenshot" in written
    assert (tmp_path / "unit-005.html").read_text(encoding="utf-8") == "<html>test</html>"
    palette_obj = json.loads((tmp_path / "unit-005-palette.json").read_text(encoding="utf-8"))
    assert palette_obj == {"colors": ["rgb(0,0,0)"]}
    assert (tmp_path / "unit-005.png").read_bytes() == b"PNGBYTES"


def test_write_capture_outputs_skips_screenshot_when_no_bytes(tmp_path):
    result = pc.CaptureResult(
        ok=True, unit_id="unit-006", raw_html="<html/>", palette={},
    )
    written = pc.write_capture_outputs(result, tmp_path)
    assert "screenshot" not in written
    assert not (tmp_path / "unit-006.png").is_file()


def test_write_capture_outputs_atomic_uses_tmp_suffix(tmp_path):
    """Verify tmp file is cleaned up (no .sddtmp leftover)."""
    result = pc.CaptureResult(
        ok=True, unit_id="unit-007", raw_html="<x/>", palette={},
    )
    pc.write_capture_outputs(result, tmp_path)
    leftovers = list(tmp_path.glob("*.sddtmp"))
    assert leftovers == []


# ----------------------------------------------- load_auth_cookies


def test_load_auth_cookies_absent_file_returns_empty(tmp_path):
    assert pc.load_auth_cookies(tmp_path / "missing.json") == []


def test_load_auth_cookies_valid_file_returns_list(tmp_path):
    payload = {
        "version": 1,
        "cookies": [
            {"name": "ASP.NET_SessionId", "value": "abc", "domain": "127.0.0.1", "path": "/"},
        ],
    }
    f = tmp_path / "auth.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    cookies = pc.load_auth_cookies(f)
    assert len(cookies) == 1
    assert cookies[0].name == "ASP.NET_SessionId"
    assert cookies[0].value == "abc"


def test_load_auth_cookies_invalid_schema_raises(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"version": 1}), encoding="utf-8")  # missing 'cookies'
    with pytest.raises(ValueError, match="cookies"):
        pc.load_auth_cookies(f)


def test_load_auth_cookies_wrong_version_raises(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"version": 99, "cookies": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        pc.load_auth_cookies(f)


def test_load_auth_cookies_missing_name_field_raises(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"version": 1, "cookies": [{"value": "v"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid cookie entry"):
        pc.load_auth_cookies(f)


# ----------------------------------------- derive_route_from_unit_path


def test_derive_route_empty_returns_root():
    assert pc.derive_route_from_unit_path("") == "/"


def test_derive_route_simple_path():
    assert pc.derive_route_from_unit_path("Default.aspx") == "/Default.aspx"


def test_derive_route_with_leading_slash():
    assert pc.derive_route_from_unit_path("/Default.aspx") == "/Default.aspx"


def test_derive_route_with_backslash():
    assert pc.derive_route_from_unit_path("Customers\\List.aspx") == "/Customers/List.aspx"


def test_derive_route_nested():
    assert pc.derive_route_from_unit_path("Customers/List.aspx") == "/Customers/List.aspx"


# --------------------------------------------- result_to_json_dict


def test_result_to_json_dict_strips_screenshot_bytes():
    result = pc.CaptureResult(
        ok=True, unit_id="u", raw_html="x", palette={"k": "v"},
        screenshot_bytes=b"PNGBYTES", status_code=200,
    )
    d = pc.result_to_json_dict(result)
    assert "screenshot_bytes" not in d
    # Other keys present
    assert d["ok"] is True
    assert d["palette"] == {"k": "v"}
    assert d["status_code"] == 200


# ----------------------------------------------------- async test helper


def _drive(coro):
    """Run a coroutine to completion without an event loop (for sync tests).

    Suitable only for coroutines that never yield control (i.e. that
    contain no await on real I/O). The async functions we inject here
    are pure-Python and return immediately.
    """
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise RuntimeError("coroutine yielded ; cannot drive synchronously")
