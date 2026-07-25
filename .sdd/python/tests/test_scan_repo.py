"""Tests for sdd_scripts.scan_repo — deterministic manifest detection."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.scan_repo import (
    _derive_auth_indicators,
    _derive_database_indicators,
    _derive_frameworks,
    _derive_languages,
    _derive_ui_indicators,
    _match_glob,
    _parse_csproj,
    _parse_package_json,
    _parse_pyproject,
    scan,
)


class TestMatchGlob(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(_match_glob("foo.json", "foo.json"))

    def test_prefix_wildcard(self):
        self.assertTrue(_match_glob("tailwind.config.ts", "tailwind.config.*"))
        self.assertTrue(_match_glob("tailwind.config.js", "tailwind.config.*"))
        self.assertFalse(_match_glob("postcss.config.ts", "tailwind.config.*"))


class TestParseCsproj(unittest.TestCase):
    def test_extracts_target_framework_and_deps(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csproj", delete=False, encoding="utf-8") as f:
            f.write("""<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.OpenApi" Version="10.0.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="10.0.6" />
  </ItemGroup>
</Project>""")
            path = Path(f.name)
        try:
            data = _parse_csproj(path)
            self.assertEqual(data["framework"], "net10.0")
            self.assertEqual(data["sdk"], "Microsoft.NET.Sdk.Web")
            self.assertEqual(data["deps"]["Microsoft.AspNetCore.OpenApi"], "10.0.0")
            self.assertEqual(data["deps"]["Microsoft.EntityFrameworkCore.SqlServer"], "10.0.6")
        finally:
            path.unlink()

    def test_blazor_webassembly_sdk(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csproj", delete=False, encoding="utf-8") as f:
            f.write("""<Project Sdk="Microsoft.NET.Sdk.BlazorWebAssembly">
  <PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup>
</Project>""")
            path = Path(f.name)
        try:
            data = _parse_csproj(path)
            self.assertEqual(data["sdk"], "Microsoft.NET.Sdk.BlazorWebAssembly")
        finally:
            path.unlink()


class TestParsePackageJson(unittest.TestCase):
    def test_extracts_deps_and_name(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(json.dumps({
                "name": "my-app",
                "dependencies": {"react": "^19.0.0", "vue": "^3.5"},
                "devDependencies": {"typescript": "^5.7", "vite": "^6.0"},
            }))
            path = Path(f.name)
        try:
            data = _parse_package_json(path)
            self.assertEqual(data["name"], "my-app")
            self.assertEqual(data["deps"]["react"], "^19.0.0")
            self.assertEqual(data["deps"]["vue"], "^3.5")
            self.assertEqual(data["deps"]["typescript"], "^5.7")
            self.assertEqual(data["deps"]["vite"], "^6.0")
        finally:
            path.unlink()

    def test_handles_invalid_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not json {{{")
            path = Path(f.name)
        try:
            data = _parse_package_json(path)
            self.assertEqual(data, {})
        finally:
            path.unlink()


class TestParsePyproject(unittest.TestCase):
    def test_pep621_dependencies(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8") as f:
            f.write("""[project]
name = "myapp"
dependencies = [
    "fastapi>=0.100",
    "pydantic>=2.0",
    "uvicorn",
]
""")
            path = Path(f.name)
        try:
            data = _parse_pyproject(path)
            self.assertIn("fastapi", data["deps"])
            self.assertIn("pydantic", data["deps"])
            self.assertIn("uvicorn", data["deps"])
        finally:
            path.unlink()


class TestDeriveLanguages(unittest.TestCase):
    def test_dotnet(self):
        manifests = [{"type": "csproj", "data": {}}]
        self.assertEqual(_derive_languages(manifests), ["dotnet"])

    def test_typescript_via_types(self):
        manifests = [{
            "type": "package.json",
            "data": {"deps": {"react": "^19.0.0", "@types/react": "^19.0.2"}},
        }]
        langs = _derive_languages(manifests)
        self.assertIn("javascript", langs)
        self.assertIn("typescript", langs)

    def test_kotlin_via_plugin(self):
        manifests = [{
            "type": "build.gradle.kts",
            "data": {"plugins": ["kotlin(\"jvm\")", "org.springframework.boot"]},
        }]
        self.assertIn("kotlin", _derive_languages(manifests))

    def test_python_via_pyproject(self):
        manifests = [{"type": "pyproject.toml", "data": {}}]
        self.assertEqual(_derive_languages(manifests), ["python"])


class TestDeriveFrameworks(unittest.TestCase):
    def test_aspnetcore_minimal(self):
        manifests = [{
            "type": "csproj",
            "data": {
                "sdk": "Microsoft.NET.Sdk.Web",
                "deps": {"Microsoft.AspNetCore.OpenApi": "10.0.0"},
            },
        }]
        self.assertIn("aspnetcore-minimal", _derive_frameworks(manifests))

    def test_blazor(self):
        manifests = [{
            "type": "csproj",
            "data": {"sdk": "Microsoft.NET.Sdk.BlazorWebAssembly", "deps": {}},
        }]
        self.assertIn("blazor-webassembly", _derive_frameworks(manifests))

    def test_react_with_vite(self):
        manifests = [{
            "type": "package.json",
            "data": {"deps": {"react": "^19", "vite": "^6"}},
        }]
        fw = _derive_frameworks(manifests)
        self.assertIn("react", fw)
        self.assertIn("vite", fw)

    def test_spring_boot(self):
        manifests = [{
            "type": "build.gradle.kts",
            "data": {"plugins": ["org.springframework.boot", "kotlin(\"jvm\")"]},
        }]
        self.assertIn("spring-boot", _derive_frameworks(manifests))

    def test_fastapi(self):
        manifests = [{
            "type": "pyproject.toml",
            "data": {"deps": {"fastapi": "^0.100"}},
        }]
        self.assertIn("fastapi", _derive_frameworks(manifests))


class TestDeriveUi(unittest.TestCase):
    def test_shadcn_via_components_json(self):
        manifests = [{"type": "components.json", "data": {}}]
        self.assertIn("shadcn", _derive_ui_indicators(manifests))

    def test_tailwind_via_dep(self):
        manifests = [{"type": "package.json", "data": {"deps": {"tailwindcss": "^4"}}}]
        self.assertIn("tailwind", _derive_ui_indicators(manifests))

    def test_radix_ui(self):
        manifests = [{
            "type": "package.json",
            "data": {"deps": {"@radix-ui/react-dialog": "^1.0"}},
        }]
        self.assertIn("radix-ui", _derive_ui_indicators(manifests))

    def test_vuetify(self):
        manifests = [{"type": "package.json", "data": {"deps": {"vuetify": "^3"}}}]
        self.assertIn("vuetify", _derive_ui_indicators(manifests))


class TestDeriveDatabase(unittest.TestCase):
    def test_sqlserver_via_ef(self):
        manifests = [{
            "type": "csproj",
            "data": {"deps": {"Microsoft.EntityFrameworkCore.SqlServer": "10.0.6"}},
        }]
        self.assertIn("sqlserver", _derive_database_indicators(manifests))

    def test_postgresql_via_npgsql(self):
        manifests = [{"type": "csproj", "data": {"deps": {"Npgsql.EntityFrameworkCore": "9.0"}}}]
        self.assertIn("postgresql", _derive_database_indicators(manifests))

    def test_mysql_node(self):
        manifests = [{"type": "package.json", "data": {"deps": {"mysql2": "^3"}}}]
        self.assertIn("mysql", _derive_database_indicators(manifests))


class TestDeriveAuth(unittest.TestCase):
    def test_azure_ad_via_identity_web(self):
        manifests = [{"type": "csproj", "data": {"deps": {"Microsoft.Identity.Web": "4.9.0"}}}]
        self.assertIn("azure-ad", _derive_auth_indicators(manifests))

    def test_azure_ad_via_msal(self):
        manifests = [{"type": "package.json", "data": {"deps": {"@azure/msal-browser": "^3"}}}]
        self.assertIn("azure-ad", _derive_auth_indicators(manifests))


class TestScanIntegration(unittest.TestCase):
    """Black-box scan() over a temp directory with real-ish manifests."""

    def test_full_stack_dotnet_react(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            # Backend
            be = root / "backend"
            be.mkdir()
            (be / "Backend.csproj").write_text(
                """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.OpenApi" Version="10.0.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="10.0.6" />
    <PackageReference Include="Microsoft.Identity.Web" Version="4.9.0" />
  </ItemGroup>
</Project>""",
                encoding="utf-8",
            )
            # Frontend
            fe = root / "frontend"
            fe.mkdir()
            (fe / "package.json").write_text(json.dumps({
                "name": "frontend",
                "dependencies": {
                    "react": "^19.0.0",
                    "react-dom": "^19.0.0",
                    "@azure/msal-browser": "^3.0",
                },
                "devDependencies": {
                    "typescript": "^5.7",
                    "vite": "^6.0",
                    "@vitejs/plugin-react": "^4.3",
                    "tailwindcss": "^4.0",
                },
            }), encoding="utf-8")
            (fe / "components.json").write_text(
                json.dumps({"style": "default", "rsc": False, "tsx": True}),
                encoding="utf-8",
            )

            report = scan(root)

            self.assertIn("dotnet", report["languages"])
            self.assertIn("typescript", report["languages"])
            self.assertIn("javascript", report["languages"])
            self.assertIn("aspnetcore-minimal", report["frameworks"])
            self.assertIn("react", report["frameworks"])
            self.assertIn("vite", report["frameworks"])
            self.assertIn("shadcn", report["ui_indicators"])
            self.assertIn("tailwind", report["ui_indicators"])
            self.assertIn("sqlserver", report["database_indicators"])
            self.assertIn("azure-ad", report["auth_indicators"])

    def test_empty_dir_warning(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            report = scan(Path(tmp))
            self.assertEqual(report["manifests"], [])
            self.assertTrue(any("SCAN_NO_MANIFESTS" in w for w in report["warnings"]))

    def test_skips_node_modules(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps({"name": "main", "dependencies": {"react": "^19"}}),
                encoding="utf-8",
            )
            # Plant a decoy package.json inside node_modules
            nm = root / "node_modules" / "fake-lib"
            nm.mkdir(parents=True)
            (nm / "package.json").write_text(
                json.dumps({"name": "decoy", "dependencies": {"vue": "^3"}}),
                encoding="utf-8",
            )
            report = scan(root)
            names = [m.get("data", {}).get("name") for m in report["manifests"]]
            self.assertIn("main", names)
            self.assertNotIn("decoy", names)


if __name__ == "__main__":
    unittest.main()
