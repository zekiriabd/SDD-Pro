#!/usr/bin/env python3
"""SDD_Pro repo scanner — detects build system manifests in a target directory.

Reads project manifests (csproj, package.json, build.gradle.kts,
pyproject.toml, angular.json, components.json, etc.) and extracts
facts: language, framework, key dependencies, versions.

This script is **deterministic and SDD-agnostic**: it just reports
what it finds. The mapping to SDD_Pro stack ids is done by the
companion `match_stack_catalog.py`.

Output: JSON to stdout.

Schema:
    {
      "scanned_at": "2026-05-15T...",
      "scope_dir": "/path/scanned",
      "manifests": [
        {"type": "csproj", "path": "...", "framework": "net10.0",
         "deps": {"Microsoft.AspNetCore.OpenApi": "10.0.0", ...}}
      ],
      "languages": ["dotnet", "typescript"],
      "frameworks": ["aspnetcore-minimal", "react", "vite"],
      "ui_indicators": ["shadcn", "tailwind"],
      "database_indicators": ["sqlserver"],
      "auth_indicators": ["azure-ad"],
      "warnings": []
    }

Usage:
    python scan_repo.py --scope path/to/repo [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import iso_now  # noqa: E402
from sdd_lib.exit_codes import SUCCESS  # noqa: E402


# Manifest file patterns (relative to scope root)
MANIFEST_GLOBS: tuple[tuple[str, str], ...] = (
    ("csproj", "**/*.csproj"),
    ("sln", "**/*.sln"),
    ("package.json", "**/package.json"),
    ("pyproject.toml", "**/pyproject.toml"),
    ("requirements.txt", "**/requirements.txt"),
    ("build.gradle.kts", "**/build.gradle.kts"),
    ("build.gradle", "**/build.gradle"),
    ("pom.xml", "**/pom.xml"),
    ("angular.json", "**/angular.json"),
    ("components.json", "**/components.json"),
    ("tailwind.config", "**/tailwind.config.*"),
    ("vite.config", "**/vite.config.*"),
    ("nuxt.config", "**/nuxt.config.*"),
    ("appsettings", "**/appsettings*.json"),
    ("application.yml", "**/application*.yml"),
    ("Dockerfile", "**/Dockerfile"),
)

# Directories to skip during scan (large, generated, vendored)
SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", "bin", "obj", "dist", "build", "target", ".gradle",
    "__pycache__", ".venv", "venv", ".env", "vendor", ".next", ".nuxt",
    ".idea", ".vs", ".vscode", "coverage", ".pytest_cache", ".mypy_cache",
    "workspace",  # SDD_Pro workspace -- don't scan generated output
})

# Max depth for the recursive glob (protect against giant repos)
MAX_DEPTH = 6


def _is_skipped(rel: Path) -> bool:
    return any(part in SKIP_DIRS for part in rel.parts)


def _glob_manifests(scope: Path) -> list[tuple[str, Path]]:
    """Walk scope, yield (manifest_type, path) for known manifest filenames.

    Manual walk (not rglob) so we can prune SKIP_DIRS efficiently and cap depth.
    """
    found: list[tuple[str, Path]] = []
    if not scope.is_dir():
        return found

    # Precompile filename matchers
    name_matchers: list[tuple[str, str]] = []
    glob_matchers: list[tuple[str, str]] = []
    for mtype, pattern in MANIFEST_GLOBS:
        # If pattern is "**/X" with no wildcard in X, it's a simple filename match
        leaf = pattern.replace("**/", "")
        if "*" not in leaf:
            name_matchers.append((mtype, leaf))
        else:
            glob_matchers.append((mtype, leaf))

    def walk(d: Path, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        try:
            entries = list(d.iterdir())
        except (OSError, PermissionError):
            return
        for entry in entries:
            try:
                if entry.is_dir():
                    if entry.name in SKIP_DIRS:
                        continue
                    walk(entry, depth + 1)
                elif entry.is_file():
                    fn = entry.name
                    for mtype, leaf in name_matchers:
                        if fn == leaf:
                            found.append((mtype, entry))
                            break
                    else:
                        for mtype, pattern in glob_matchers:
                            # Simple glob: prefix*suffix
                            if _match_glob(fn, pattern):
                                found.append((mtype, entry))
                                break
            except OSError:
                continue

    walk(scope, depth=0)
    return found


def _match_glob(filename: str, pattern: str) -> bool:
    """Minimal glob matching (only `*` supported)."""
    parts = pattern.split("*")
    if len(parts) == 1:
        return filename == pattern
    if not filename.startswith(parts[0]):
        return False
    if not filename.endswith(parts[-1]):
        return False
    return True


def _parse_csproj(path: Path) -> dict[str, Any]:
    """Extract TargetFramework + PackageReferences from a .csproj file."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}

    out: dict[str, Any] = {}
    tf = re.search(r"<TargetFramework>([^<]+)</TargetFramework>", text)
    if tf:
        out["framework"] = tf.group(1).strip()
    tfs = re.search(r"<TargetFrameworks>([^<]+)</TargetFrameworks>", text)
    if tfs:
        out["frameworks"] = [f.strip() for f in tfs.group(1).split(";") if f.strip()]

    sdk = re.search(r'<Project\s+Sdk="([^"]+)"', text)
    if sdk:
        out["sdk"] = sdk.group(1).strip()

    deps: dict[str, str] = {}
    for m in re.finditer(
        r'<PackageReference\s+Include="([^"]+)"\s+Version="([^"]+)"', text
    ):
        deps[m.group(1)] = m.group(2)
    if deps:
        out["deps"] = deps
    return out


def _parse_package_json(path: Path) -> dict[str, Any]:
    """Extract dependencies + devDependencies from package.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, Any] = {}
    name = data.get("name")
    if isinstance(name, str):
        out["name"] = name
    deps: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            for k, v in block.items():
                if isinstance(k, str) and isinstance(v, str):
                    deps[k] = v
    if deps:
        out["deps"] = deps
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        out["scripts"] = {k: v for k, v in scripts.items() if isinstance(v, str)}
    return out


def _parse_pyproject(path: Path) -> dict[str, Any]:
    """Extract dependencies from pyproject.toml (PEP 621 + poetry style)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    out: dict[str, Any] = {}
    deps: dict[str, str] = {}

    # PEP 621 dependencies = ["fastapi>=0.100", ...]
    pep621 = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)\]", text)
    if pep621:
        for line in pep621.group(1).splitlines():
            line = line.strip().strip(",").strip('"').strip("'")
            if not line:
                continue
            m = re.match(r"^([A-Za-z][\w\-\.]*)\s*([=<>!~].*)?$", line)
            if m:
                deps[m.group(1).lower()] = (m.group(2) or "*").strip()

    # Poetry style [tool.poetry.dependencies]
    poetry_block = re.search(
        r"(?ms)^\[tool\.poetry\.dependencies\](.*?)^\[", text + "\n["
    )
    if poetry_block:
        for line in poetry_block.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z][\w\-\.]*)\s*=\s*[\"\']?([^\"\']+)[\"\']?', line)
            if m:
                deps[m.group(1).lower()] = m.group(2).strip()

    if deps:
        out["deps"] = deps

    python_req = re.search(r'python\s*=\s*"([^"]+)"', text)
    if python_req:
        out["python_version"] = python_req.group(1)
    return out


def _parse_requirements_txt(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    deps: dict[str, str] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z][\w\-\.]*)\s*([=<>!~].*)?$", line)
        if m:
            deps[m.group(1).lower()] = (m.group(2) or "*").strip()
    return {"deps": deps} if deps else {}


def _parse_gradle(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, Any] = {}
    plugins: list[str] = []
    for m in re.finditer(r'id\s*\(?\s*"([^"]+)"\s*\)?', text):
        plugins.append(m.group(1))
    if plugins:
        out["plugins"] = plugins
    deps: list[str] = []
    for m in re.finditer(
        r'(?:implementation|api|testImplementation)\s*\(?\s*"([^"]+)"', text
    ):
        deps.append(m.group(1))
    if deps:
        out["deps"] = deps
    kotlin_version = re.search(r'kotlin\s*\(\s*"jvm"\s*\)\s*version\s*"([^"]+)"', text)
    if kotlin_version:
        out["kotlin_version"] = kotlin_version.group(1)
    return out


def _parse_pom_xml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, Any] = {}
    deps: list[str] = []
    # Crude regex parse — sufficient to detect spring-boot
    for m in re.finditer(
        r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>",
        text,
    ):
        deps.append(f"{m.group(1)}:{m.group(2)}")
    if deps:
        out["deps"] = deps
    return out


def _parse_angular_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {"projects": list(data.get("projects", {}).keys())}


def _parse_components_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {"style": data.get("style"), "rsc": data.get("rsc"), "tsx": data.get("tsx")}


def _parse_manifest(mtype: str, path: Path) -> dict[str, Any]:
    parsers = {
        "csproj": _parse_csproj,
        "package.json": _parse_package_json,
        "pyproject.toml": _parse_pyproject,
        "requirements.txt": _parse_requirements_txt,
        "build.gradle.kts": _parse_gradle,
        "build.gradle": _parse_gradle,
        "pom.xml": _parse_pom_xml,
        "angular.json": _parse_angular_json,
        "components.json": _parse_components_json,
    }
    fn = parsers.get(mtype)
    return fn(path) if fn else {}


# -----------------------------------------------------------------------------
# Indicator derivation (high-level facts from low-level manifests)
# -----------------------------------------------------------------------------

def _derive_languages(manifests: list[dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for m in manifests:
        t = m["type"]
        if t in ("csproj", "sln"):
            out.add("dotnet")
        elif t == "package.json":
            out.add("javascript")
            deps = m.get("data", {}).get("deps", {})
            if "typescript" in deps or any(k.startswith("@types/") for k in deps):
                out.add("typescript")
        elif t in ("pyproject.toml", "requirements.txt"):
            out.add("python")
        elif t in ("build.gradle.kts", "build.gradle"):
            data = m.get("data", {})
            plugins = data.get("plugins", [])
            if any("kotlin" in p for p in plugins):
                out.add("kotlin")
            else:
                out.add("java")
        elif t == "pom.xml":
            out.add("java")
    return sorted(out)


def _derive_frameworks(manifests: list[dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for m in manifests:
        data = m.get("data", {})
        deps = data.get("deps", {})

        if m["type"] == "csproj":
            sdk = data.get("sdk", "")
            if "BlazorWebAssembly" in sdk:
                out.add("blazor-webassembly")
            elif "Web" in sdk:
                if isinstance(deps, dict) and any(
                    k.startswith("Microsoft.AspNetCore.OpenApi")
                    or k.startswith("Swashbuckle.AspNetCore")
                    for k in deps
                ):
                    out.add("aspnetcore-minimal")
                elif isinstance(deps, dict):
                    out.add("aspnetcore")
            if isinstance(deps, dict) and "Radzen.Blazor" in deps:
                out.add("radzen-blazor")

        elif m["type"] == "package.json":
            if isinstance(deps, dict):
                if "react" in deps:
                    out.add("react")
                if "vue" in deps:
                    out.add("vue")
                if "@angular/core" in deps:
                    out.add("angular")
                if "next" in deps:
                    out.add("nextjs")
                if "vite" in deps or "@vitejs/plugin-react" in deps:
                    out.add("vite")
                if "express" in deps:
                    out.add("express")
                if "vuetify" in deps:
                    out.add("vuetify")
                if "tailwindcss" in deps:
                    out.add("tailwind")

        elif m["type"] in ("pyproject.toml", "requirements.txt"):
            if isinstance(deps, dict):
                if "fastapi" in deps:
                    out.add("fastapi")
                if "django" in deps:
                    out.add("django")
                if "flask" in deps:
                    out.add("flask")

        elif m["type"] in ("build.gradle.kts", "build.gradle"):
            plugins = data.get("plugins", [])
            if any("org.springframework.boot" in p for p in plugins):
                out.add("spring-boot")
            if any("org.jetbrains.kotlin.jvm" in p or "kotlin(\"jvm\")" in p
                   for p in plugins):
                out.add("kotlin-jvm")

        elif m["type"] == "pom.xml":
            pom_deps = data.get("deps", [])
            if any("spring-boot-starter-web" in d for d in pom_deps):
                out.add("spring-boot")

        elif m["type"] == "angular.json":
            out.add("angular")

    return sorted(out)


def _derive_ui_indicators(manifests: list[dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for m in manifests:
        if m["type"] == "components.json":
            out.add("shadcn")  # components.json is shadcn-specific
        elif m["type"] == "tailwind.config":
            out.add("tailwind")
        elif m["type"] == "package.json":
            deps = m.get("data", {}).get("deps", {})
            if isinstance(deps, dict):
                if "vuetify" in deps:
                    out.add("vuetify")
                if any(k.startswith("@radix-ui/") for k in deps):
                    out.add("radix-ui")
                if "tailwindcss" in deps:
                    out.add("tailwind")
                if "@mui/material" in deps or "@material-ui/core" in deps:
                    out.add("material-ui")
        elif m["type"] == "csproj":
            deps = m.get("data", {}).get("deps", {})
            if isinstance(deps, dict) and "Radzen.Blazor" in deps:
                out.add("radzen-blazor")
    return sorted(out)


def _derive_database_indicators(manifests: list[dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for m in manifests:
        data = m.get("data", {})
        deps = data.get("deps", {})

        if isinstance(deps, dict):
            for k in deps:
                k_low = k.lower()
                if "sqlserver" in k_low or "microsoft.entityframeworkcore.sqlserver" in k_low:
                    out.add("sqlserver")
                if "npgsql" in k_low or "postgresql" in k_low or "psycopg" in k_low:
                    out.add("postgresql")
                if "mysql" in k_low or "mariadb" in k_low:
                    out.add("mysql")
                if "sqlite" in k_low or "better-sqlite3" in k_low:
                    out.add("sqlite")
                if "mongodb" in k_low or "mongoose" in k_low:
                    out.add("mongodb")

        if isinstance(deps, list):
            for d in deps:
                d_low = d.lower()
                if "spring-boot-starter-data-jpa" in d_low:
                    out.add("jpa")
                if "postgresql" in d_low:
                    out.add("postgresql")
                if "mssql" in d_low or "sqlserver" in d_low:
                    out.add("sqlserver")
                if "mysql" in d_low:
                    out.add("mysql")
    return sorted(out)


def _derive_auth_indicators(manifests: list[dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for m in manifests:
        data = m.get("data", {})
        deps = data.get("deps", {})

        if isinstance(deps, dict):
            for k in deps:
                k_low = k.lower()
                if "microsoft.identity.web" in k_low or "@azure/msal" in k_low:
                    out.add("azure-ad")
                if "spring-security-oauth2-resource-server" in k_low:
                    out.add("oauth2-resource-server")
                if "passport" in k_low or "next-auth" in k_low:
                    out.add("auth-library")
                if "jsonwebtoken" in k_low or "system.identitymodel.tokens.jwt" in k_low:
                    out.add("jwt-local")

        if isinstance(deps, list):
            for d in deps:
                d_low = d.lower()
                if "spring-security-oauth2-resource-server" in d_low:
                    out.add("oauth2-resource-server")
                if "spring-boot-starter-security" in d_low:
                    out.add("spring-security")
    return sorted(out)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def scan(scope: Path) -> dict[str, Any]:
    scope = scope.resolve()
    raw_manifests = _glob_manifests(scope)

    manifests: list[dict[str, Any]] = []
    warnings: list[str] = []

    for mtype, path in raw_manifests:
        try:
            rel = path.relative_to(scope)
        except ValueError:
            rel = path
        entry: dict[str, Any] = {
            "type": mtype,
            "path": str(rel).replace("\\", "/"),
        }
        try:
            data = _parse_manifest(mtype, path)
            if data:
                entry["data"] = data
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            warnings.append(f"[SCAN_PARSE_ERROR] {entry['path']}: {type(e).__name__}")
        manifests.append(entry)

    if not manifests:
        warnings.append("[SCAN_NO_MANIFESTS] aucun manifest détecté dans le périmètre")

    return {
        "scanned_at": iso_now(),
        "scope_dir": str(scope),
        "manifests": manifests,
        "languages": _derive_languages(manifests),
        "frameworks": _derive_frameworks(manifests),
        "ui_indicators": _derive_ui_indicators(manifests),
        "database_indicators": _derive_database_indicators(manifests),
        "auth_indicators": _derive_auth_indicators(manifests),
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan_repo",
        description="SDD_Pro repo scanner — detect build system manifests.",
    )
    parser.add_argument("--scope", type=Path, default=Path("."), help="Directory to scan")
    parser.add_argument("--output", type=Path, default=None, help="Write JSON to file")
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout (only file write)")
    args = parser.parse_args(argv)

    result = scan(args.scope)
    text = json.dumps(result, ensure_ascii=False, indent=2)

    if not args.quiet:
        sys.stdout.write(text + "\n")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
