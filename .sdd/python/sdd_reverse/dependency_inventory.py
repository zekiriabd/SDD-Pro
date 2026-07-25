r"""dependency_inventory.py — Full library / DLL inventory for legacy (L1).

Before L1 only `packages.config` (legacy NuGet) + 4 non-.NET manifests were
parsed, and `bin/*.dll` / `<Reference HintPath>` were ignored — so modern
SDK-style .NET projects produced an empty or wrong library list. This module
inventories every dependency signal needed to drive the "Libraries to install"
cross-cutting FEAT (L3) and the target-stack mapping:

    - NuGet `packages.config`              (<package id= version=>)
    - NuGet SDK-style `.csproj`            (<PackageReference Include= Version=>)
    - central versions `Directory.Packages.props` / `*.props` (<PackageVersion>)
    - assembly references in `.csproj`     (<Reference Include= [HintPath]>)
    - compiled assemblies under `bin/`     (filenames only — binary, no parse)
    - npm `package.json`, Maven `pom.xml`, pip `requirements.txt`, composer.json

Public API:
    extract_dependencies(project_root, scan_result=None) -> dict   # dependencies.json
    parse_csproj(text, source) -> tuple[list[pkg], list[ref]]      # reusable

Anti-hallucination: every package carries `evidence` (file[:line]); nothing is
inferred from "a project of this type would use".
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import normalize_bytes, read_text_normalized as _read_text

DEPENDENCY_SCHEMA_VERSION = 1

# packages.config — <package id="X" version="Y" targetFramework="..."/>
_RE_PKG_CONFIG = re.compile(
    r"<package\s+[^>]*?id\s*=\s*\"([^\"]+)\"[^>]*?version\s*=\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
# <PackageReference Include="X" Version="Y" />
_RE_PKG_REF_INLINE = re.compile(
    r"<PackageReference\s+[^>]*?Include\s*=\s*\"([^\"]+)\"[^>]*?Version\s*=\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
# <PackageReference Include="X"> ... <Version>Y</Version> ... </PackageReference>
# `(?<!/)>` ensures the open tag is NOT self-closing (`/>`), otherwise a
# preceding self-closed <PackageReference .../> would greedily borrow this
# block's <Version>. The body must not cross into another PackageReference tag.
_RE_PKG_REF_NESTED = re.compile(
    r"<PackageReference\s+[^>]*?Include\s*=\s*\"([^\"]+)\"[^>]*?(?<!/)>"
    r"(?:(?!</?PackageReference\b).)*?<Version>\s*([^<]+?)\s*</Version>",
    re.IGNORECASE | re.DOTALL,
)
# <PackageReference Include="X" /> with no version (central package management)
_RE_PKG_REF_NOVER = re.compile(
    r"<PackageReference\s+[^>]*?Include\s*=\s*\"([^\"]+)\"[^>]*?/?>",
    re.IGNORECASE,
)
# Directory.Packages.props — <PackageVersion Include="X" Version="Y"/>
_RE_PKG_VERSION = re.compile(
    r"<PackageVersion\s+[^>]*?Include\s*=\s*\"([^\"]+)\"[^>]*?Version\s*=\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
# <Reference Include="System.Xml" /> or <Reference Include="X"><HintPath>…</HintPath></Reference>.
# Capture the whole element body, then pull HintPath out separately (a lazy
# optional inline group reliably mis-captures it as empty).
_RE_ASM_REF = re.compile(
    r"<Reference\s+[^>]*?Include\s*=\s*\"([^\"]+)\""
    r"(?P<body>\s*/>|[^>]*?>.*?</Reference>)",
    re.IGNORECASE | re.DOTALL,
)
_RE_HINTPATH = re.compile(r"<HintPath>\s*([^<]+?)\s*</HintPath>", re.IGNORECASE)


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# _read_text centralise dans scan_legacy (audit 2026-06-11 B5 — cap 5 Mo).


def parse_csproj(text: str, source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (packages, assemblyReferences) from a .csproj/.props file."""
    packages: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    seen_pkg: set[str] = set()

    for m in _RE_PKG_REF_INLINE.finditer(text):
        name, version = m.group(1), m.group(2)
        if name.lower() in seen_pkg:
            continue
        seen_pkg.add(name.lower())
        packages.append({"name": name, "version": version, "ecosystem": "nuget",
                         "source": "PackageReference", "evidence": f"{source}:{_line_at(text, m.start())}"})
    for m in _RE_PKG_REF_NESTED.finditer(text):
        name, version = m.group(1), m.group(2)
        if name.lower() in seen_pkg:
            continue
        seen_pkg.add(name.lower())
        packages.append({"name": name, "version": version, "ecosystem": "nuget",
                         "source": "PackageReference", "evidence": f"{source}:{_line_at(text, m.start())}"})
    for m in _RE_PKG_REF_NOVER.finditer(text):
        name = m.group(1)
        if name.lower() in seen_pkg:
            continue
        seen_pkg.add(name.lower())
        packages.append({"name": name, "version": None, "ecosystem": "nuget",
                         "source": "PackageReference (central version)",
                         "evidence": f"{source}:{_line_at(text, m.start())}"})
    for m in _RE_PKG_VERSION.finditer(text):
        name, version = m.group(1), m.group(2)
        packages.append({"name": name, "version": version, "ecosystem": "nuget",
                         "source": "PackageVersion (central)", "evidence": f"{source}:{_line_at(text, m.start())}"})

    for m in _RE_ASM_REF.finditer(text):
        name = m.group(1).split(",")[0].strip()  # strip strong-name suffix
        hm = _RE_HINTPATH.search(m.group("body") or "")
        hint = hm.group(1).strip() if hm else None
        refs.append({"name": name, "hintPath": hint,
                     "evidence": f"{source}:{_line_at(text, m.start())}"})
    return packages, refs


def _parse_packages_config(text: str, source: str) -> list[dict[str, Any]]:
    return [
        {"name": m.group(1), "version": m.group(2), "ecosystem": "nuget",
         "source": "packages.config", "evidence": f"{source}:{_line_at(text, m.start())}"}
        for m in _RE_PKG_CONFIG.finditer(text)
    ]


def _parse_package_json(text: str, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        block = re.search(r"\"" + section + r"\"\s*:\s*\{(.*?)\}", text, re.DOTALL)
        if not block:
            continue
        for m in re.finditer(r"\"([^\"]+)\"\s*:\s*\"([^\"]+)\"", block.group(1)):
            out.append({"name": m.group(1), "version": m.group(2), "ecosystem": "npm",
                        "source": section, "evidence": source})
    return out


def _parse_requirements(text: str, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"([A-Za-z0-9_.\-]+)\s*(?:[=<>!~]=?\s*([\w.\-]+))?", s)
        if m:
            out.append({"name": m.group(1), "version": m.group(2), "ecosystem": "pypi",
                        "source": "requirements.txt", "evidence": source})
    return out


def _parse_pom(text: str, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(
        r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>"
        r"(?:\s*<version>([^<]+)</version>)?",
        text, re.IGNORECASE | re.DOTALL,
    ):
        out.append({"name": f"{m.group(1).strip()}:{m.group(2).strip()}",
                    "version": (m.group(3) or "").strip() or None, "ecosystem": "maven",
                    "source": "pom.xml", "evidence": source})
    return out


def _parse_composer(text: str, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    block = re.search(r"\"require\"\s*:\s*\{(.*?)\}", text, re.DOTALL)
    if block:
        for m in re.finditer(r"\"([^\"]+)\"\s*:\s*\"([^\"]+)\"", block.group(1)):
            out.append({"name": m.group(1), "version": m.group(2), "ecosystem": "composer",
                        "source": "composer.json", "evidence": source})
    return out


def extract_dependencies(
    project_root: str | Path, scan_result: Any = None
) -> dict[str, Any]:
    """Inventory every dependency signal across the legacy project."""
    root = Path(project_root).resolve()
    packages: list[dict[str, Any]] = []
    asm_refs: list[dict[str, Any]] = []
    binaries: list[dict[str, Any]] = []

    excl = {".git", "obj", "node_modules", "vendor", "packages"}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = p.relative_to(root).parts
        # bin/ is excluded from the language scan but we DO want its DLL names.
        if "bin" in parts:
            if p.suffix.lower() == ".dll":
                binaries.append({"file": p.relative_to(root).as_posix(), "name": p.stem})
            continue
        if any(part in excl for part in parts):
            continue
        rel = p.relative_to(root).as_posix()
        name_low = p.name.lower()
        suffix = p.suffix.lower()
        if name_low == "packages.config":
            packages.extend(_parse_packages_config(_read_text(p), rel))
        elif suffix in (".csproj", ".props", ".targets", ".vbproj", ".fsproj"):
            pk, rf = parse_csproj(_read_text(p), rel)
            packages.extend(pk)
            asm_refs.extend(rf)
        elif name_low == "package.json":
            packages.extend(_parse_package_json(_read_text(p), rel))
        elif name_low == "pom.xml":
            packages.extend(_parse_pom(_read_text(p), rel))
        elif name_low == "requirements.txt":
            packages.extend(_parse_requirements(_read_text(p), rel))
        elif name_low == "composer.json":
            packages.extend(_parse_composer(_read_text(p), rel))

    # Dedup packages by (name, ecosystem) keeping first evidence.
    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for pkg in packages:
        key = (pkg["name"].lower(), pkg["ecosystem"])
        if key not in dedup:
            dedup[key] = pkg
    packages_final = sorted(dedup.values(), key=lambda d: (d["ecosystem"], d["name"].lower()))

    ecosystems: dict[str, int] = {}
    for pkg in packages_final:
        ecosystems[pkg["ecosystem"]] = ecosystems.get(pkg["ecosystem"], 0) + 1

    return {
        "schemaVersion": DEPENDENCY_SCHEMA_VERSION,
        "project": root.name,
        "extractDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "packages": packages_final,
        "assemblyReferences": sorted(
            {(r["name"], r.get("hintPath")): r for r in asm_refs}.values(),
            key=lambda d: d["name"].lower(),
        ),
        "binaries": sorted(binaries, key=lambda d: d["name"].lower()),
        "summary": {
            "packagesCount": len(packages_final),
            "assemblyReferencesCount": len(asm_refs),
            "binariesCount": len(binaries),
            "ecosystems": ecosystems,
        },
    }
