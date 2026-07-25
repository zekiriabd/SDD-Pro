#!/usr/bin/env python3
"""SDD_Pro: validate all `.claude/stacks/**/*.libs.json` catalogs.

Checks each catalog against the schema rules (versionRef resolves to a key,
onDemand entries have capability + triggers, etc.).

Usage:
    python validate_libs_catalog.py [--repo-root .] [--json]

Exit codes:
    0 = all valid (warnings allowed)
    1 = at least one error

Migrated from .claude/scripts/validate-libs-catalog.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST  # noqa: E402


BUILD_SYSTEMS = (
    "dotnet", "npm", "pnpm", "yarn", "gradle", "maven",
    "pip", "poetry", "uv", "cargo", "go-mod", "msbuild",
)
REQUIRED_TOP_KEYS = ("stackId", "category", "schemaVersion", "buildSystem", "versions", "core")
VERSION_KEY_RE = re.compile(r"^[a-z][a-z0-9-]*$")
PRERELEASE_RE = re.compile(r"-(alpha|beta|rc|preview|snapshot)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=None)
    p.add_argument("--json", action="store_true")
    return p.parse_args()


def derive_lib_id(lib: dict[str, Any]) -> str:
    if "id" in lib and lib["id"]:
        return str(lib["id"])
    module = lib.get("module")
    if not module:
        return "?"
    if ":" in module:
        return module.split(":")[-1]
    m = re.match(r"^@.+/(.+)$", module)
    return m.group(1) if m else module


def validate_catalog(file: Path, root: Path) -> tuple[dict[str, Any], list[dict], list[dict]]:
    rel = normalize(file.relative_to(root))
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    try:
        raw = file.read_text(encoding="utf-8")
        cat = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        errors.append({"File": rel, "Code": "JSON_PARSE", "Message": str(e)})
        return {"File": rel}, errors, warnings

    if not isinstance(cat, dict):
        errors.append({"File": rel, "Code": "JSON_PARSE", "Message": "root is not an object"})
        return {"File": rel}, errors, warnings

    for key in REQUIRED_TOP_KEYS:
        if key not in cat:
            errors.append({"File": rel, "Code": "MISSING_KEY", "Message": f"missing top-level '{key}'"})

    if not cat.get("stackId"):
        return {"File": rel}, errors, warnings

    expected_id = file.stem.replace(".libs", "")
    if cat.get("stackId") != expected_id:
        errors.append({
            "File": rel,
            "Code": "STACK_ID_MISMATCH",
            "Message": f"stackId='{cat.get('stackId')}' != filename '{expected_id}'",
        })

    expected_cat = file.parent.name
    if cat.get("category") != expected_cat:
        errors.append({
            "File": rel,
            "Code": "CATEGORY_MISMATCH",
            "Message": f"category='{cat.get('category')}' != parent dir '{expected_cat}'",
        })

    if cat.get("schemaVersion") != 1:
        errors.append({
            "File": rel,
            "Code": "SCHEMA_VERSION",
            "Message": f"schemaVersion={cat.get('schemaVersion')}, expected 1",
        })

    if cat.get("buildSystem") not in BUILD_SYSTEMS:
        errors.append({
            "File": rel,
            "Code": "BAD_BUILDSYSTEM",
            "Message": f"buildSystem='{cat.get('buildSystem')}' not in [{', '.join(BUILD_SYSTEMS)}]",
        })

    versions_keys: list[str] = []
    versions = cat.get("versions") or {}
    if isinstance(versions, dict):
        for k, v in versions.items():
            versions_keys.append(k)
            if not VERSION_KEY_RE.match(k):
                errors.append({"File": rel, "Code": "BAD_VERSION_KEY", "Message": f"versions.{k} not kebab-case"})
            if not (isinstance(v, str) and v.strip()):
                errors.append({"File": rel, "Code": "EMPTY_VERSION", "Message": f"versions.{k} is empty"})
            elif PRERELEASE_RE.search(v):
                warnings.append({
                    "File": rel,
                    "Code": "PRERELEASE",
                    "Message": f"versions.{k}='{v}' is pre-release",
                })

    all_libs: list[tuple[dict[str, Any], str]] = []
    for sec_name in ("core", "onDemand"):
        section = cat.get(sec_name) or []
        if isinstance(section, list):
            for lib in section:
                if isinstance(lib, dict):
                    all_libs.append((lib, sec_name))

    for lib, sec in all_libs:
        lib_id = derive_lib_id(lib)
        lib_ref = f"{sec}.{lib_id}"

        if not lib.get("module"):
            errors.append({"File": rel, "Code": "MISSING_MODULE", "Message": f"{lib_ref} missing module"})

        has_ver = bool(lib.get("version"))
        has_ref = bool(lib.get("ref"))
        has_verref = bool(lib.get("versionRef"))
        ref_count = sum((has_ver, has_ref, has_verref))
        if ref_count > 1:
            errors.append({
                "File": rel,
                "Code": "VERSION_BOTH",
                "Message": f"{lib_ref} has more than one of {{version, ref, versionRef}}",
            })

        ref_key = lib.get("ref") or lib.get("versionRef")
        if ref_key and ref_key not in versions_keys:
            errors.append({
                "File": rel,
                "Code": "BAD_VERSIONREF",
                "Message": f"{lib_ref} ref='{ref_key}' not declared in versions{{}}",
            })

        if sec == "onDemand":
            if not lib.get("capability"):
                errors.append({"File": rel, "Code": "ONDEMAND_NO_CAP", "Message": f"{lib_ref} missing capability"})
            triggers = lib.get("triggers") or []
            if not (isinstance(triggers, list) and triggers):
                errors.append({"File": rel, "Code": "ONDEMAND_NO_TRIGGERS", "Message": f"{lib_ref} missing triggers[]"})

    plugins = cat.get("plugins") or []
    if isinstance(plugins, list):
        for p_obj in plugins:
            if not isinstance(p_obj, dict):
                continue
            p_id = p_obj.get("id", "?")
            p_ref = p_obj.get("ref") or p_obj.get("versionRef")
            if p_ref and p_ref not in versions_keys:
                errors.append({
                    "File": rel,
                    "Code": "BAD_VERSIONREF",
                    "Message": f"plugins.{p_id} ref='{p_ref}' not declared",
                })

    db_drivers = cat.get("dbDrivers") or {}
    if isinstance(db_drivers, dict):
        for name, d in db_drivers.items():
            if not isinstance(d, dict):
                continue
            if not d.get("module"):
                errors.append({"File": rel, "Code": "DRIVER_NO_MODULE", "Message": f"dbDrivers.{name} missing module"})
            d_ref = d.get("ref") or d.get("versionRef")
            if d_ref and d_ref not in versions_keys:
                errors.append({
                    "File": rel,
                    "Code": "BAD_VERSIONREF",
                    "Message": f"dbDrivers.{name} ref='{d_ref}' not declared",
                })

    # v7.0.0 audit P0 §6.2 — Empty `core` is a configuration smell unless
    # the stack explicitly opts out of arch auto-install via
    # `metadata.manualInstall: true`. Catches accidentally-empty catalogs
    # (would produce a project with zero installed libs at arch Phase A)
    # while accepting intentional manual-install stacks like
    # `qa/mutation-testing` (multi-runtime, target picked at qa STEP 8.5).
    core_libs = cat.get("core") or []
    metadata = cat.get("metadata") or {}
    manual_install = isinstance(metadata, dict) and metadata.get("manualInstall") is True
    if not core_libs and not manual_install:
        warnings.append({
            "File": rel,
            "Code": "EMPTY_CORE",
            "Message": (
                "core=[] without metadata.manualInstall=true — arch Phase A "
                "will install NO library for this stack. If intentional, add "
                "metadata.manualInstall=true + manualInstallRationale to the catalog."
            ),
        })

    summary = {
        "File":        rel,
        "StackId":     cat.get("stackId"),
        "Category":    cat.get("category"),
        "BuildSystem": cat.get("buildSystem"),
        "Versions":    len(versions_keys),
        "Core":        len(core_libs),
        "OnDemand":    len(cat.get("onDemand") or []),
        "Plugins":     len(cat.get("plugins") or []),
        "ManualInstall": manual_install,
    }
    return summary, errors, warnings


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).resolve() if args.repo_root else repo_root()
    stacks_dir = root / ".claude" / "stacks"

    # All stacks under .claude/stacks/ are validated (v7.0.0+ rollback of
    # _drafts/ quarantine — every category subdirectory is now active).
    #
    # v7.0.0-alpha (audit MAJ-12, 2026-06-04) — `auth/*.md` intentionally
    # has NO `.libs.json` companion. Auth is a cross-language *protocol*
    # (Azure AD OIDC, local JWT, etc.) ; the concrete consumer libraries
    # (`Microsoft.Identity.Web`, `spring-security-oauth2-resource-server`,
    # `@azure/msal-browser`) live in the BACKEND/FRONTEND `.libs.json` of
    # the project consuming the auth protocol. Validation of backend↔auth
    # compatibility happens at `arch` STEP 4.5.6 via `## Active Auth Specs`
    # cross-check, not via schema validation. Cf. `library-and-stack.md §1.0`.
    catalogs = (
        sorted(stacks_dir.rglob("*.libs.json"))
        if stacks_dir.is_dir() else []
    )
    all_errors: list[dict[str, Any]] = []
    all_warnings: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for f in catalogs:
        summary, errs, warns = validate_catalog(f, root)
        summaries.append(summary)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    if args.json:
        print(json.dumps({
            "catalogs": summaries,
            "errors":   all_errors,
            "warnings": all_warnings,
            "passed":   len(all_errors) == 0,
        }, indent=2, ensure_ascii=False))
    else:
        print(f"\nCatalogs scanned : {len(catalogs)}")
        for s in summaries:
            print(
                f"  [{s.get('BuildSystem', '?'):<8}] "
                f"{s.get('StackId') or '?':<30} "
                f"core={s.get('Core', 0):>3} "
                f"onDemand={s.get('OnDemand', 0):>2} "
                f"plugins={s.get('Plugins', 0):>2} "
                f"versions={s.get('Versions', 0):>2}"
            )
        print()
        if all_warnings:
            print(f"Warnings ({len(all_warnings)}) :")
            for w in all_warnings:
                print(f"  WARN  {w['File']:<30} {w['Code']:<20} {w['Message']}")
            print()
        if all_errors:
            warn(f"Errors ({len(all_errors)}) :")
            for e in all_errors:
                warn(f"  ERROR {e['File']:<30} {e['Code']:<20} {e['Message']}")
            warn("\nFAIL")
            return FAIL_FAST
        print("OK")

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
