"""Tests for sdd_reverse.scan_legacy — language detection, exclusions, disambiguation."""
from __future__ import annotations

from pathlib import Path

import pytest

from sdd_reverse import scan_legacy


SIGNATURES_PATH = (
    Path(__file__).resolve().parent.parent / "sdd_reverse" / "language_signatures.yml"
)


@pytest.fixture
def signatures():
    return scan_legacy.load_signatures(SIGNATURES_PATH)


def _write(path: Path, content: str = "") -> None:
    """Helper: create file with parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_signatures_returns_dict_with_languages(signatures):
    assert isinstance(signatures, dict)
    assert "languages" in signatures
    assert len(signatures["languages"]) >= 15
    lang_ids = {l["id"] for l in signatures["languages"]}
    # Core langs we promised
    for required in ("dotnet-webforms", "dotnet-mvc", "java-jee", "php-procedural",
                     "delphi", "javascript-jquery", "python", "yaml", "unknown"):
        assert required in lang_ids, f"missing language: {required}"


def test_load_signatures_missing_file_raises():
    with pytest.raises(FileNotFoundError, match=r"\[REVERSE_SCAN_FAILED\]"):
        scan_legacy.load_signatures(Path("/does/not/exist.yml"))


def test_scan_empty_project_returns_no_languages(tmp_path, signatures):
    result = scan_legacy.scan_project(tmp_path, signatures)
    assert result["languages"] == []
    assert result["stats"]["files_total"] == 0


def test_scan_aspx_webforms_minimal(tmp_path, signatures):
    _write(tmp_path / "Default.aspx", '<%@ Page Language="C#" %><html runat="server"></html>')
    _write(tmp_path / "Default.aspx.cs", "public partial class Default : Page { }")
    _write(tmp_path / "Web.config", '<?xml version="1.0"?><configuration></configuration>')
    result = scan_legacy.scan_project(tmp_path, signatures)
    lang_ids = {l["id"] for l in result["languages"]}
    assert "dotnet-webforms" in lang_ids
    # Web.config should be detected as manifest
    manifest_paths = {m["path"] for m in result["manifests"]}
    assert any(p.endswith("Web.config") for p in manifest_paths)


def test_scan_excludes_vendored_jquery(tmp_path, signatures):
    _write(tmp_path / "Default.aspx", '<%@ Page Language="C#" %>')
    _write(tmp_path / "Scripts" / "jquery-1.11.3.min.js", "/* jquery */")
    result = scan_legacy.scan_project(tmp_path, signatures)
    vendored = result["exclusions"]["vendored"]
    assert any("jquery-1.11.3" in v for v in vendored)
    # File should NOT count toward analyzed files
    js_langs = [l for l in result["languages"] if "javascript" in l["id"]]
    assert all(l["files_count"] == 0 for l in js_langs) or not js_langs


def test_scan_excludes_obj_bin_generated(tmp_path, signatures):
    _write(tmp_path / "Default.aspx", '<%@ Page %>')
    _write(tmp_path / "obj" / "Release" / "tmp.cs", "// generated")
    _write(tmp_path / "bin" / "App.dll.config", "<x/>")
    result = scan_legacy.scan_project(tmp_path, signatures)
    generated = result["exclusions"]["generated"]
    assert any("obj/" in g or "obj\\" in g for g in generated)
    assert any("bin/" in g or "bin\\" in g for g in generated)


def test_scan_detects_python_generic_not_django(tmp_path, signatures):
    """Generic Python file should be classified as 'python', not 'python-django'."""
    _write(tmp_path / "module.py", "def hello():\n    return 'world'\n")
    result = scan_legacy.scan_project(tmp_path, signatures)
    lang_ids = {l["id"] for l in result["languages"]}
    assert "python" in lang_ids
    assert "python-django" not in lang_ids


def test_scan_detects_python_django_when_pattern_matches(tmp_path, signatures):
    """Python file with Django patterns should be classified as 'python-django'."""
    _write(
        tmp_path / "views.py",
        "from django.shortcuts import render\nfrom django.http import HttpResponse\n"
        "from .models import Customer\n\ndef index(request):\n    return render(request, 'index.html')\n",
    )
    _write(tmp_path / "manage.py", "import django\n")
    result = scan_legacy.scan_project(tmp_path, signatures)
    lang_ids = {l["id"] for l in result["languages"]}
    assert "python-django" in lang_ids


def test_scan_disambiguates_cshtml_to_dotnet_mvc(tmp_path, signatures):
    """A .cshtml file should resolve to dotnet-mvc."""
    _write(tmp_path / "Views" / "Home" / "Index.cshtml",
           '@model MyApp.HomeViewModel\n<h1>@Model.Title</h1>')
    result = scan_legacy.scan_project(tmp_path, signatures)
    lang_ids = {l["id"] for l in result["languages"]}
    assert "dotnet-mvc" in lang_ids


def test_scan_handles_binary_file_gracefully(tmp_path, signatures):
    """Binary file should be skipped, not crash the scanner."""
    binary_path = tmp_path / "image.bin"
    binary_path.write_bytes(b"\x00\x01\x02\x03" * 1000)
    _write(tmp_path / "Default.aspx", '<%@ Page %>')
    result = scan_legacy.scan_project(tmp_path, signatures)
    # Binary file should be in excluded count
    assert result["stats"]["files_excluded"] >= 1


def test_scan_codebehind_companion_extension(tmp_path, signatures):
    """A .aspx.cs file (companion of .aspx) should be classified as dotnet-webforms."""
    _write(tmp_path / "Login.aspx", '<%@ Page Language="C#" %><html runat="server"></html>')
    _write(tmp_path / "Login.aspx.cs", "public partial class Login : Page { }")
    result = scan_legacy.scan_project(tmp_path, signatures)
    # Both files should be in dotnet-webforms
    webforms = next((l for l in result["languages"] if l["id"] == "dotnet-webforms"), None)
    assert webforms is not None
    assert webforms["files_count"] >= 2


def test_scan_project_path_not_dir_raises(signatures, tmp_path):
    """Scanning a non-existent path raises with [REVERSE_PRECONDITION]."""
    with pytest.raises(FileNotFoundError, match=r"\[REVERSE_PRECONDITION\]"):
        scan_legacy.scan_project(tmp_path / "does-not-exist", signatures)


def test_scan_php_procedural_detected(tmp_path, signatures):
    _write(tmp_path / "index.php", '<?php $_POST["x"]; mysqli_query($conn, "SELECT 1"); ?>')
    result = scan_legacy.scan_project(tmp_path, signatures)
    lang_ids = {l["id"] for l in result["languages"]}
    assert "php-procedural" in lang_ids


def test_scan_excludes_test_patterns(tmp_path, signatures):
    """Test files should be excluded from analyzed counts."""
    _write(tmp_path / "src" / "main.py", "def main(): pass")
    _write(tmp_path / "src" / "test_main.py", "def test_main(): pass")
    result = scan_legacy.scan_project(tmp_path, signatures)
    test_excluded = result["exclusions"].get("tests", [])
    assert any("test_main.py" in t for t in test_excluded)


def test_scan_languages_sorted_by_loc_desc(tmp_path, signatures):
    """Languages list should be sorted by LOC desc."""
    # Create more PHP than ASPX
    for i in range(3):
        _write(tmp_path / f"page_{i}.php", "<?php " + "x = 1;\n" * 50 + "?>")
    _write(tmp_path / "Default.aspx", '<%@ Page %>\n<html></html>')
    result = scan_legacy.scan_project(tmp_path, signatures)
    if len(result["languages"]) >= 2:
        for i in range(len(result["languages"]) - 1):
            assert result["languages"][i]["loc"] >= result["languages"][i + 1]["loc"]


def test_scan_schema_version_present(tmp_path, signatures):
    _write(tmp_path / "Default.aspx", '<%@ Page %>')
    result = scan_legacy.scan_project(tmp_path, signatures)
    assert result["schema_version"] == 1
    assert "scanned_at" in result
    assert "project" in result


def test_disambiguation_aspx_cs_vs_csharp_classic(tmp_path, signatures):
    """A .aspx.cs file with sibling .aspx should be dotnet-webforms, not csharp-classic."""
    _write(tmp_path / "Login.aspx", '<%@ Page %><html runat="server"></html>')
    _write(tmp_path / "Login.aspx.cs", "namespace App { public partial class Login {} }")
    # Also add a pure C# file
    _write(tmp_path / "Helper.cs", "namespace App { public static class Helper {} }")
    result = scan_legacy.scan_project(tmp_path, signatures)
    lang_ids = {l["id"] for l in result["languages"]}
    # Login.aspx.cs → dotnet-webforms (companion)
    # Login.aspx → dotnet-webforms
    # Helper.cs → csharp-classic (no companion .aspx)
    assert "dotnet-webforms" in lang_ids
    assert "csharp-classic" in lang_ids
