"""Phase 4 E2E tests — orchestration legacy_runner + playwright_capture + extractors.

These tests run the FULL Sprint 2-3 pipeline end-to-end on synthetic legacy
fixtures, with Playwright mocked (since it's an opt-in dependency).

Coverage scope :
- legacy_runner.launch_legacy + playwright_capture.capture_url + persistence
- css_palette_extractor on multi-page captured palettes → tokens.css
- legacy_components_extractor on multi-page captured HTMLs → inventory.md
- Idempotence : re-run with same palette sources → skip
- Isolation contract : no writes outside authorized paths

NOT covered (out of E2E scope, covered by individual module tests) :
- Network HTTP (legacy_runner.wait_ready real urlopen)
- Real Playwright Chromium launch
- Subprocess.Popen real launches
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sdd_reverse import (
    css_palette_extractor as cpe,
    legacy_components_extractor as lce,
    legacy_runner,
    playwright_capture as pc,
)


# ---------------------------------------------------------- fixtures


@pytest.fixture
def fake_aspx_project(tmp_path):
    """Synthesize a minimal ASP.NET WebForms legacy under tmp_path."""
    project = tmp_path / "FakeAspxApp"
    project.mkdir()
    (project / "Default.aspx").write_text(
        '<%@ Page Language="C#" %><html runat="server"><body>'
        '<table id="tbl"><tr><th>Name</th></tr></table>'
        "</body></html>",
        encoding="utf-8",
    )
    (project / "Site.Master").write_text(
        '<%@ Master Language="C#" %><html><head/><body>'
        '<nav><a href="/">Home</a><a href="/About">About</a><a href="/Contact">Contact</a></nav>'
        "</body></html>",
        encoding="utf-8",
    )
    sys_dir = project / ".sys"
    sys_dir.mkdir()
    return project


@pytest.fixture
def signatures():
    sigs_path = Path(__file__).resolve().parent.parent / "sdd_reverse" / "runner_signatures.yml"
    return legacy_runner.load_signatures(sigs_path)


@pytest.fixture
def captured_aspx_html_runtime():
    """Realistic post-JS-injection ASPX page (DataTable filled by JS)."""
    return """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Liste des employes</title>
    <input type="hidden" name="__VIEWSTATE" value="encoded-viewstate-blob"/>
    <input type="hidden" name="__EVENTVALIDATION" value="encoded"/>
</head>
<body>
    <header>
        <nav>
            <a href="/Default.aspx">Employees</a>
            <a href="/Products.aspx">Products</a>
            <a href="/Posts.aspx">Posts</a>
            <a href="/UsersServer.aspx">Users</a>
        </nav>
    </header>
    <main>
        <table id="tbl" class="datatable display">
            <thead><tr><th>First</th><th>Last</th><th>Email</th></tr></thead>
            <tbody>
                <tr><td>Terry</td><td>Medhurst</td><td>terry@x</td></tr>
                <tr><td>Sheldon</td><td>Quigley</td><td>sheldon@x</td></tr>
                <tr><td>Terrill</td><td>Hills</td><td>terrill@x</td></tr>
                <tr><td>Miles</td><td>Cummerata</td><td>miles@x</td></tr>
                <tr><td>Mavis</td><td>Schultz</td><td>mavis@x</td></tr>
            </tbody>
        </table>
        <div class="dataTables_paginate pagination">
            <a>Prev</a><a>1</a><a>2</a><a>Next</a>
        </div>
    </main>
</body>
</html>
"""


# ------------------------------------------------ pipeline E2E


def test_e2e_runtime_legacy_unavailable_falls_back_static(fake_aspx_project, signatures):
    """When the runner binary is missing, launch_legacy returns ok=False/fallback."""
    fake_run = MagicMock(return_value=MagicMock(returncode=127))  # binary missing
    result = legacy_runner.launch_legacy(
        fake_aspx_project,
        signatures,
        language="dotnet-webforms",
        _subprocess_run=fake_run,
        platform="win32",
    )
    assert result.ok is False
    assert result.mode == "fallback-static"
    assert result.errors[0].code == "REVERSE_UI_RUNNER_UNAVAILABLE"


def test_e2e_runtime_success_then_capture_persists_outputs(
    fake_aspx_project, signatures, captured_aspx_html_runtime, tmp_path
):
    """Full happy path : runner OK → capture OK → outputs persisted."""
    # Mock subprocess.run (binary detection)
    fake_run = MagicMock(return_value=MagicMock(returncode=0))
    # Mock subprocess.Popen (legacy spawn)
    fake_proc = MagicMock()
    fake_proc.pid = 12345

    launch_result = legacy_runner.launch_legacy(
        fake_aspx_project,
        signatures,
        language="php-procedural",
        _subprocess_run=fake_run,
        _subprocess_popen=lambda cmd, **kw: fake_proc,
        _is_free=MagicMock(return_value=True),
        _wait_ready_fn=MagicMock(return_value=True),
        platform="linux",
    )
    assert launch_result.ok is True
    assert launch_result.base_url.startswith("http://127.0.0.1:")

    # Now simulate Playwright capture with the realistic HTML
    async def fake_capture(**kwargs):
        return {
            "raw_html": captured_aspx_html_runtime,
            "palette": {
                "colors": ["rgb(51, 51, 51)", "rgb(255, 255, 255)"],
                "backgrounds": ["rgb(247, 247, 247)"],
                "fonts": ["Tahoma, Arial, sans-serif"],
                "spacings": ["8px", "12px"],
                "fontSizes": ["14px", "16px"],
                "elementCount": 30,
            },
            "screenshot_bytes": b"FAKE_PNG_BYTES",
            "status_code": 200,
        }

    capture_result = pc.capture_url(
        base_url=launch_result.base_url,
        route="/Default.aspx",
        unit_id="unit-001",
        _is_available_fn=MagicMock(return_value=True),
        _capture_fn=fake_capture,
        _asyncio_run=_drive_coroutine,
    )

    assert capture_result.ok is True
    assert capture_result.html_size > 500
    assert capture_result.status_code == 200

    # Persist outputs
    captures_dir = fake_aspx_project / ".sys" / "captures"
    written = pc.write_capture_outputs(capture_result, captures_dir)
    assert (captures_dir / "unit-001.html").is_file()
    assert (captures_dir / "unit-001-palette.json").is_file()
    assert (captures_dir / "unit-001.png").is_file()

    # No leftover .sddtmp files (atomic write hygiene)
    assert list(captures_dir.glob("*.sddtmp")) == []

    # Cleanup the pidfile written by launch_legacy
    legacy_runner.cleanup_pidfile_process(fake_aspx_project, _kill=MagicMock())


def test_e2e_palette_extraction_from_captures_produces_tokens_css(
    fake_aspx_project, captured_aspx_html_runtime, tmp_path
):
    """Multi-page captures → aggregate palette → tokens.css with deduplicated tokens."""
    captures_dir = fake_aspx_project / ".sys" / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)

    # Simulate 3 unit captures with overlapping palettes
    palettes = [
        {
            "colors": ["rgb(51, 51, 51)", "rgb(0, 0, 0)"],
            "backgrounds": ["rgb(247, 247, 247)"],
            "fonts": ["Tahoma, Arial, sans-serif"],
            "spacings": ["8px"],
            "fontSizes": ["14px"],
        },
        {
            "colors": ["rgb(51, 51, 51)", "rgb(44, 90, 160)"],
            "backgrounds": ["rgb(247, 247, 247)", "rgb(255, 255, 255)"],
            "fonts": ["Tahoma, Arial, sans-serif"],
            "spacings": ["8px", "16px"],
            "fontSizes": ["14px", "16px"],
        },
        {
            "colors": ["rgb(51, 51, 51)"],
            "backgrounds": ["rgb(247, 247, 247)"],
            "fonts": ["Tahoma, Arial, sans-serif"],
            "spacings": ["8px"],
            "fontSizes": ["14px"],
        },
    ]
    palette_paths = []
    for idx, p in enumerate(palettes, start=1):
        path = captures_dir / f"unit-{idx:03d}-palette.json"
        path.write_text(json.dumps(p), encoding="utf-8")
        palette_paths.append(path)

    aggregated = cpe.aggregate_from_files(palette_paths)
    assert len(aggregated.colors) >= 2  # at least dark + brand
    assert aggregated.fonts[0] == "Tahoma, Arial, sans-serif"  # most frequent
    assert "8px" in aggregated.spacings  # most frequent spacing

    target_css = tmp_path / "tokens.css"
    written = cpe.write_tokens_css(
        aggregated, target_css,
        project_name="FakeAspxApp",
        extraction_date="2026-06-10",
        routes=["/Default.aspx", "/Products.aspx", "/Posts.aspx"],
    )
    assert written is True
    css_content = target_css.read_text(encoding="utf-8")
    assert ":root {" in css_content
    assert "FakeAspxApp" in css_content
    assert "Tahoma" in css_content
    assert "rgb(51, 51, 51)" in css_content


def test_e2e_palette_idempotence_skips_on_same_sources(fake_aspx_project, tmp_path):
    """Re-aggregating identical inputs should produce identical sources_hash → write skipped."""
    captures_dir = fake_aspx_project / ".sys" / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    p_path = captures_dir / "unit-001-palette.json"
    p_path.write_text(
        json.dumps({"colors": ["rgb(0, 0, 0)"], "fonts": ["Arial"]}),
        encoding="utf-8",
    )

    agg1 = cpe.aggregate_from_files([p_path])
    target = tmp_path / "tokens.css"
    written1 = cpe.write_tokens_css(agg1, target)
    assert written1 is True

    # Second aggregation : identical inputs → same hash → skip
    agg2 = cpe.aggregate_from_files([p_path])
    assert agg2.sources_hash == agg1.sources_hash
    written2 = cpe.write_tokens_css(agg2, target)
    assert written2 is False


def test_e2e_components_inventory_from_captures(
    fake_aspx_project, captured_aspx_html_runtime, tmp_path
):
    """Captures → component heuristics → components-inventory.md."""
    captures_dir = fake_aspx_project / ".sys" / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    (captures_dir / "unit-001.html").write_text(captured_aspx_html_runtime, encoding="utf-8")

    # Simulate a second page with a form CRUD
    form_html = """
    <html><body>
        <main>
            <form action="/edit" method="post">
                <input type="text" name="name"/>
                <input type="text" name="email"/>
                <select name="role"><option>admin</option></select>
                <button type="submit">Save</button>
            </form>
        </main>
    </body></html>
    """
    (captures_dir / "unit-002.html").write_text(form_html, encoding="utf-8")

    # Build inventory
    captures = [
        ("unit-001", "/Default.aspx", captured_aspx_html_runtime),
        ("unit-002", "/Edit.aspx", form_html),
    ]
    inventory = lce.build_inventory_from_captures(captures)
    assert len(inventory.pages) == 2

    # Aggregate kinds : should include grid, nav, pagination, form
    agg = inventory.aggregate_by_kind()
    assert "grid" in agg
    assert "nav" in agg
    assert "pagination" in agg
    assert "form" in agg

    # Write inventory MD
    target_md = tmp_path / "components-inventory.md"
    lce.write_components_inventory(
        inventory, target_md,
        project_name="FakeAspxApp",
        extraction_date="2026-06-10",
    )
    md = target_md.read_text(encoding="utf-8")
    assert "| Grille" in md or "| GridDataTable" in md or "tbl" in md  # grid detected
    assert "| Menu de navigation |" in md or "Menu" in md
    assert "/Default.aspx" in md
    assert "/Edit.aspx" in md


def test_e2e_capture_empty_html_marked_not_ok():
    """Realistic failure mode : Playwright returns a 5-line error page (< 500 chars)."""
    async def fake_capture(**kwargs):
        return {
            "raw_html": "<html><body>500 Error</body></html>",  # ~36 chars
            "palette": {},
            "screenshot_bytes": b"",
            "status_code": 500,
        }

    result = pc.capture_url(
        "http://127.0.0.1:5099", "/Broken.aspx", "unit-099",
        _is_available_fn=MagicMock(return_value=True),
        _capture_fn=fake_capture,
        _asyncio_run=_drive_coroutine,
    )
    assert result.ok is False
    assert any(e.code == "REVERSE_UI_CAPTURE_EMPTY" for e in result.errors)


# ------------------------------------------------- isolation contract


def test_phase4_isolation_no_existing_sddpro_files_modified():
    """Ensure Phase 4 modules do NOT reference forbidden SDD_Pro paths."""
    forbidden_imports = {
        "sdd_lib.layered_config",
        "sdd_lib.cache_control",
        "sdd_scripts.preflight",
        "sdd_scripts.validate_readiness",
        "sdd_hooks",
    }
    phase4_modules = [
        Path(__file__).resolve().parent.parent / "sdd_reverse" / "legacy_runner.py",
        Path(__file__).resolve().parent.parent / "sdd_reverse" / "playwright_capture.py",
        Path(__file__).resolve().parent.parent / "sdd_reverse" / "css_palette_extractor.py",
        Path(__file__).resolve().parent.parent / "sdd_reverse" / "legacy_components_extractor.py",
        Path(__file__).resolve().parent.parent / "sdd_reverse_scripts" / "legacy_runner.py",
    ]
    for mod in phase4_modules:
        content = mod.read_text(encoding="utf-8")
        for forbidden in forbidden_imports:
            assert forbidden not in content, (
                f"Isolation violation : {mod.name} references {forbidden} "
                f"(Phase 4 must stay isolated from SDD_Pro existing modules)"
            )


def test_phase4_artifacts_exist():
    """All Sprint 4 artifacts are in place on disk."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    expected = [
        repo_root / ".claude" / "agents" / "reverse-ui-extractor.md",
        repo_root / ".claude" / "commands" / "sdd-reverse-ui.md",
        repo_root / ".claude" / "python" / "sdd_reverse" / "legacy_runner.py",
        repo_root / ".claude" / "python" / "sdd_reverse" / "playwright_capture.py",
        repo_root / ".claude" / "python" / "sdd_reverse" / "css_palette_extractor.py",
        repo_root / ".claude" / "python" / "sdd_reverse" / "legacy_components_extractor.py",
        repo_root / ".claude" / "python" / "sdd_reverse" / "runner_signatures.yml",
        repo_root / ".claude" / "python" / "sdd_reverse_scripts" / "legacy_runner.py",
        repo_root / ".claude" / "docs" / "reverse-engineering-phase4-runtime.md",
    ]
    missing = [p for p in expected if not p.is_file()]
    assert not missing, f"Missing Phase 4 artifacts: {missing}"


def test_phase4_loader_declares_new_artifacts():
    """loader.reverse.yml must mention legacy_runner_cli and playwright_capture scripts."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    loader_yml = repo_root / ".claude" / "loader.reverse.yml"
    content = loader_yml.read_text(encoding="utf-8")
    for required in ("legacy_runner_cli", "playwright_capture",
                     "css_palette_extractor", "legacy_components_extractor"):
        assert required in content, f"loader.reverse.yml missing {required}"


def test_phase4_rule_extension_present():
    """rules/reverse-engineering.md must contain §6 extension."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    rule = repo_root / ".claude" / "rules" / "reverse-engineering.md"
    content = rule.read_text(encoding="utf-8")
    assert "§6 — Phase 4 UI extraction" in content
    assert "[REVERSE_UI_RUNNER_UNAVAILABLE]" in content
    assert "[REVERSE_UI_PLAYWRIGHT_MISSING]" in content


# ---------------------------------------------------- ASPX strip realism


def test_e2e_viewstate_present_in_capture(captured_aspx_html_runtime):
    """The realistic ASPX capture should contain ViewState (which the agent will strip)."""
    assert "__VIEWSTATE" in captured_aspx_html_runtime
    assert "__EVENTVALIDATION" in captured_aspx_html_runtime
    # The agent reverse-ui-extractor will strip these — but the raw capture must contain them
    # to exercise that pathway in real usage.


# ------------------------------------------------ helper


def _drive_coroutine(coro):
    """Run a non-awaiting coroutine to completion without asyncio."""
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise RuntimeError("coroutine yielded ; cannot drive synchronously")
