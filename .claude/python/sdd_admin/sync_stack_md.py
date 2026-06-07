#!/usr/bin/env python3
"""SDD_Pro: regenerate §2.4 + install command blocks of a stack .md from its .libs.json.

Three injection zones:
    1) §2.4 Librairies table — marked by `<!-- LIBS_CATALOG_START/END -->`
    2) Core install commands  — marked by `<!-- CORE_PACKAGES_START/END -->`
    3) OnDemand install cmds  — marked by `<!-- ONDEMAND_PACKAGES_START/END -->`

Zones 2 and 3 are optional; if markers are absent they are silently skipped.

Usage:
    python sync_stack_md.py --stack-id kotlin-spring-boot [--repo-root .] [--dry-run]

Migrated from .claude/scripts/sync-stack-md.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.atomic_write import atomic_write_text  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--stack-id", required=True)
    p.add_argument("--repo-root", default=None)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def resolve_version(lib: dict[str, Any], catalog: dict[str, Any]) -> str:
    if lib.get("version"):
        return str(lib["version"])
    ref = lib.get("ref") or lib.get("versionRef")
    versions = catalog.get("versions") or {}
    if ref and isinstance(versions, dict) and ref in versions:
        return str(versions[ref])
    return ""


def resolve_lib_id(lib: dict[str, Any]) -> str:
    if lib.get("id"):
        return str(lib["id"])
    module = lib.get("module")
    if not module:
        return "?"
    if ":" in module:
        return module.split(":")[-1]
    return module


def primary_project_file(catalog: dict[str, Any]) -> str | None:
    manifest = catalog.get("manifest") or {}
    files = manifest.get("files") or []
    return files[0] if files else None


def primary_project_dir(catalog: dict[str, Any]) -> str | None:
    f = primary_project_file(catalog)
    if not f:
        return None
    m = re.match(r"^(.+)/[^/]+$", f)
    return m.group(1) if m else f


def format_core_package_lines(libs: list[dict[str, Any]], catalog: dict[str, Any]) -> list[str]:
    bs = catalog.get("buildSystem", "")
    project_file = primary_project_file(catalog)
    project_dir = primary_project_dir(catalog)
    lines: list[str] = []

    if not libs:
        return ["# (aucune lib core declaree)"]

    if bs == "dotnet":
        for lib in libs:
            v = resolve_version(lib, catalog)
            cmd = f"dotnet add {project_file} package {lib.get('module')}"
            if v:
                cmd += f" --version {v}"
            lines.append(cmd)
    elif bs in ("npm", "pnpm", "yarn"):
        cmd_word = "npm install" if bs == "npm" else f"{bs} add"
        items = [
            f"{lib.get('module')}@{resolve_version(lib, catalog)}" if resolve_version(lib, catalog)
            else lib.get("module", "")
            for lib in libs
        ]
        lines.append(f"(cd {project_dir} && {cmd_word} \\")
        for i, item in enumerate(items):
            sep = " \\" if i < len(items) - 1 else ")"
            lines.append(f"  {item}{sep}")
    elif bs == "uv":
        items = [
            f"{lib.get('module')}=={resolve_version(lib, catalog)}" if resolve_version(lib, catalog)
            else lib.get("module", "")
            for lib in libs
        ]
        lines.append(f"uv add --project {project_dir} \\")
        for i, item in enumerate(items):
            sep = " \\" if i < len(items) - 1 else ""
            lines.append(f"  {item}{sep}")
    elif bs == "pip":
        items = [
            f'"{lib.get("module")}=={resolve_version(lib, catalog)}"' if resolve_version(lib, catalog)
            else f'"{lib.get("module", "")}"'
            for lib in libs
        ]
        lines.append(f"(cd {project_dir} && pip install \\")
        for i, item in enumerate(items):
            sep = " \\" if i < len(items) - 1 else ")"
            lines.append(f"  {item}{sep}")
    elif bs == "poetry":
        items = [
            f"{lib.get('module')}@{resolve_version(lib, catalog)}" if resolve_version(lib, catalog)
            else lib.get("module", "")
            for lib in libs
        ]
        lines.append(f"(cd {project_dir} && poetry add \\")
        for i, item in enumerate(items):
            sep = " \\" if i < len(items) - 1 else ")"
            lines.append(f"  {item}{sep}")
    elif bs == "gradle":
        manifest = catalog.get("manifest") or {}
        catalog_path = manifest.get("versionCatalogPath") or "gradle/libs.versions.toml"
        lines.append(f"# Gradle managed via build.gradle.kts + {catalog_path}.")
        lines.append(f"# Versions auto-derivees de {catalog.get('stackId')}.libs.json -- regenerer le catalog Gradle")
        lines.append("# en cas de bump (cf. gradle/libs.versions.toml).")
    elif bs == "maven":
        lines.append("# Maven managed via pom.xml -- les versions vivent dans <properties> du pom.")
        lines.append(f"# Sync depuis {catalog.get('stackId')}.libs.json a faire manuellement (pas de CLI atomique).")
    elif bs == "cargo":
        for lib in libs:
            v = resolve_version(lib, catalog)
            cmd = f"cargo add {lib.get('module')}"
            if v:
                cmd += f" --vers {v}"
            lines.append(cmd)
    elif bs == "go-mod":
        for lib in libs:
            v = resolve_version(lib, catalog)
            cmd = f"go get {lib.get('module')}"
            if v:
                cmd += f"@v{v}"
            lines.append(cmd)
    else:
        lines.append(f"# buildSystem '{bs}' non supporte par sync_stack_md.py -- regenerer manuellement.")

    return lines


def format_ondemand_package_lines(libs: list[dict[str, Any]], catalog: dict[str, Any]) -> list[str]:
    if not libs:
        return ["# (aucune lib on-demand declaree)"]

    bs = catalog.get("buildSystem", "")
    project_file = primary_project_file(catalog)
    project_dir = primary_project_dir(catalog)
    lines: list[str] = []

    # Group by capability
    groups: dict[str, list[dict[str, Any]]] = {}
    for lib in libs:
        cap = lib.get("capability", "")
        groups.setdefault(cap, []).append(lib)

    for cap, group_libs in groups.items():
        if lines:
            lines.append("")
        lines.append(f"# capability: {cap}")
        primary_libs = [l for l in group_libs if not l.get("alternative")]
        alt_libs = [l for l in group_libs if l.get("alternative")]

        if bs == "dotnet":
            for lib in primary_libs:
                v = resolve_version(lib, catalog)
                cmd = f"dotnet add {project_file} package {lib.get('module')}"
                if v:
                    cmd += f" --version {v}"
                lines.append(cmd)
            for a in alt_libs:
                av = resolve_version(a, catalog)
                cmt = f"# OU (alt mutuellement exclusif) : dotnet add {project_file} package {a.get('module')}"
                if av:
                    cmt += f" --version {av}"
                lines.append(cmt)
        elif bs in ("npm", "pnpm", "yarn"):
            cmd_word = "npm install" if bs == "npm" else f"{bs} add"
            if primary_libs:
                items = [
                    f"{lib.get('module')}@{resolve_version(lib, catalog)}" if resolve_version(lib, catalog)
                    else lib.get("module", "")
                    for lib in primary_libs
                ]
                lines.append(f"(cd {project_dir} && {cmd_word} {' '.join(items)})")
            for a in alt_libs:
                av = resolve_version(a, catalog)
                token = f"{a.get('module')}@{av}" if av else a.get("module", "")
                lines.append(f"# OU (alt) : (cd {project_dir} && {cmd_word} {token})")
        elif bs == "uv":
            if primary_libs:
                items = [
                    f"{lib.get('module')}=={resolve_version(lib, catalog)}" if resolve_version(lib, catalog)
                    else lib.get("module", "")
                    for lib in primary_libs
                ]
                lines.append(f"uv add --project {project_dir} {' '.join(items)}")
            for a in alt_libs:
                av = resolve_version(a, catalog)
                token = f"{a.get('module')}=={av}" if av else a.get("module", "")
                lines.append(f"# OU (alt) : uv add --project {project_dir} {token}")
        elif bs == "pip":
            if primary_libs:
                items = [
                    f'"{lib.get("module")}=={resolve_version(lib, catalog)}"' if resolve_version(lib, catalog)
                    else f'"{lib.get("module", "")}"'
                    for lib in primary_libs
                ]
                lines.append(f"(cd {project_dir} && pip install {' '.join(items)})")
            for a in alt_libs:
                av = resolve_version(a, catalog)
                token = f'"{a.get("module")}=={av}"' if av else f'"{a.get("module", "")}"'
                lines.append(f"# OU (alt) : (cd {project_dir} && pip install {token})")
        elif bs == "poetry":
            if primary_libs:
                items = [
                    f"{lib.get('module')}@{resolve_version(lib, catalog)}" if resolve_version(lib, catalog)
                    else lib.get("module", "")
                    for lib in primary_libs
                ]
                lines.append(f"(cd {project_dir} && poetry add {' '.join(items)})")
            for a in alt_libs:
                av = resolve_version(a, catalog)
                token = f"{a.get('module')}@{av}" if av else a.get("module", "")
                lines.append(f"# OU (alt) : (cd {project_dir} && poetry add {token})")
        elif bs == "gradle":
            lines.append("# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts")
            for lib in primary_libs:
                lines.append(f'#   implementation("{lib.get("module")}:{resolve_version(lib, catalog)}")')
            for a in alt_libs:
                lines.append(f'#   OU (alt) implementation("{a.get("module")}:{resolve_version(a, catalog)}")')
        else:
            for lib in primary_libs:
                lines.append(f"# {bs} : install {lib.get('module')} (version {resolve_version(lib, catalog)})")
            for a in alt_libs:
                lines.append(f"# {bs} : OU (alt) install {a.get('module')} (version {resolve_version(a, catalog)})")

    return lines


def build_fenced_block(comment: str, lines: list[str]) -> str:
    body = "\n".join(lines)
    return f"```bash\n# {comment}\n{body}\n```"


def replace_marked_section(md: str, start: str, end: str, new_content: str) -> str:
    if start not in md or end not in md:
        return md
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    # Audit CTO 2026-06-07 fix: use lambda replacement (not raw string) so that
    # backslash sequences in `new_content` (e.g. regex triggers `\s` rendered
    # in §2.4 table for stacks like mutation-testing) are NOT interpreted as
    # re.sub backreferences. Plain string would raise `re.PatternError: bad
    # escape \s` on Python 3.12+ stricter validation.
    replacement = f"{start}\r\n{new_content}\r\n{end}"
    return pattern.sub(lambda _m: replacement, md)


def build_libs_table(cat: dict[str, Any], stack_id: str) -> str:
    sb: list[str] = []
    sb.append("### 2.4 Librairies")
    sb.append("")
    sb.append(
        f"> Source de verite : `.claude/stacks/{cat.get('category')}/{stack_id}.libs.json`. "
        f"Ne pas editer cette section manuellement -- utiliser "
        f"`.claude/python/sdd_admin/sync_stack_md.py --stack-id {stack_id}`."
    )
    sb.append("")
    sb.append("#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)")
    sb.append("")
    sb.append("| Lib | Version | Role |")
    sb.append("|-----|---------|------|")
    for lib in (cat.get("core") or []):
        v = resolve_version(lib, cat)
        lib_id = resolve_lib_id(lib)
        rationale = lib.get("rationale", "")
        sb.append(f"| {lib_id} | {v} | {rationale} |")
    sb.append("")

    on_demand = cat.get("onDemand") or []
    if on_demand:
        sb.append("### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)")
        sb.append("")
        sb.append("Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.")
        sb.append("")
        sb.append("| Capability | Lib | Version | Triggers |")
        sb.append("|---|---|---|---|")
        for lib in on_demand:
            v = resolve_version(lib, cat)
            lib_id = resolve_lib_id(lib)
            alt = " (alt)" if lib.get("alternative") else ""
            triggers = ", ".join(lib.get("triggers") or [])
            sb.append(f"| {lib.get('capability', '')} | {lib_id}{alt} | {v} | {triggers} |")
        sb.append("")

    plugins = cat.get("plugins") or []
    if plugins:
        sb.append("#### 2.4.c Plugins build-system")
        sb.append("")
        sb.append("| Plugin | Version | Role |")
        sb.append("|---|---|---|")
        for p in plugins:
            v = resolve_version(p, cat)
            rationale = p.get("rationale", "")
            sb.append(f"| {p.get('id')} | {v} | {rationale} |")
        sb.append("")

    db_drivers = cat.get("dbDrivers") or {}
    if isinstance(db_drivers, dict) and db_drivers:
        sb.append("#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)")
        sb.append("")
        sb.append("| DatabaseType | Module | Version | Scope |")
        sb.append("|---|---|---|---|")
        for db_type, d in db_drivers.items():
            v = resolve_version(d, cat)
            scope = d.get("scope") or "runtime"
            sb.append(f"| {db_type} | `{d.get('module')}` | {v} | {scope} |")
        sb.append("")

    return "\n".join(sb).rstrip()


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).resolve() if args.repo_root else repo_root()

    catalog_path: Path | None = None
    for f in (root / ".claude" / "stacks").rglob(f"{args.stack_id}.libs.json"):
        catalog_path = f
        break
    if catalog_path is None:
        warn(f"Catalog not found for stackId={args.stack_id}")
        return FAIL_FAST
    md_path = catalog_path.parent / f"{args.stack_id}.md"
    if not md_path.is_file():
        warn(f"Companion .md not found: {md_path}")
        return FAIL_FAST
    try:
        cat = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        warn(f"Failed to read catalog: {e}")
        return FAIL_FAST
    generated_table = build_libs_table(cat, args.stack_id)

    core_lines = format_core_package_lines(cat.get("core") or [], cat)
    ondemand_lines = format_ondemand_package_lines(cat.get("onDemand") or [], cat)

    core_block = build_fenced_block(
        f"Auto-genere depuis {args.stack_id}.libs.json -- ne pas editer "
        "(utiliser sync_stack_md.py).",
        core_lines,
    )
    ondemand_block = build_fenced_block(
        f"Auto-genere depuis {args.stack_id}.libs.json (on-demand) -- "
        "installe par dev-* si l'US declenche un trigger.",
        ondemand_lines,
    )

    md = md_path.read_text(encoding="utf-8")

    # Zone 1 — §2.4 Librairies (fallback regex if marker missing)
    start_libs = "<!-- LIBS_CATALOG_START -->"
    end_libs = "<!-- LIBS_CATALOG_END -->"
    if start_libs in md and end_libs in md:
        md = replace_marked_section(md, start_libs, end_libs, generated_table)
    else:
        pattern = re.compile(r"(?ms)^#{2,3} 2\.4 Librairies.*?(?=^#{1,3} )")
        if pattern.search(md):
            md = pattern.sub(
                f"{start_libs}\r\n{generated_table}\r\n{end_libs}\r\n\r\n",
                md,
            )
        else:
            print(
                f"Cannot find '## 2.4 Librairies' or '### 2.4 Librairies' in {md_path}. "
                "Insert <!-- LIBS_CATALOG_START --> / <!-- LIBS_CATALOG_END --> markers manually.",
                file=sys.stderr,
            )
            return FAIL_FAST
    core_injected = False
    if "<!-- CORE_PACKAGES_START -->" in md:
        md = replace_marked_section(
            md, "<!-- CORE_PACKAGES_START -->", "<!-- CORE_PACKAGES_END -->", core_block,
        )
        core_injected = True

    ondemand_injected = False
    if "<!-- ONDEMAND_PACKAGES_START -->" in md:
        md = replace_marked_section(
            md, "<!-- ONDEMAND_PACKAGES_START -->", "<!-- ONDEMAND_PACKAGES_END -->", ondemand_block,
        )
        ondemand_injected = True

    if args.dry_run:
        print(f"=== DRY RUN -- generated for {args.stack_id} ===")
        print("[Zone 1: 2.4 table]")
        print(generated_table)
        print()
        print(f"[Zone 2: CORE_PACKAGES] (markers present: {core_injected})")
        print(core_block)
        print()
        print(f"[Zone 3: ONDEMAND_PACKAGES] (markers present: {ondemand_injected})")
        print(ondemand_block)
    else:
        atomic_write_text(md_path, md, newline="")
        core_n = len(cat.get("core") or [])
        ondemand_n = len(cat.get("onDemand") or [])
        plugins_n = len(cat.get("plugins") or [])
        drivers_n = len(cat.get("dbDrivers") or {})
        zones = ["2.4-table"]
        if core_injected:
            zones.append("core-pkg")
        if ondemand_injected:
            zones.append("ondemand-pkg")
        print(
            f"OK {args.stack_id}.md synced from {args.stack_id}.libs.json "
            f"[core={core_n}, onDemand={ondemand_n}, plugins={plugins_n}, dbDrivers={drivers_n}], "
            f"zones=[{', '.join(zones)}]"
        )

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
