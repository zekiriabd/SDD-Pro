#!/usr/bin/env python3
"""SDD_Pro — Cross-check .md library tables vs .libs.json versions.

Audit consolidé 2026-06-07 Sprint 2 — Sprint 2 outil P1 pour éliminer les
drifts version `.md` ↔ `.libs.json` (cf. CRIT-2 Spring Boot 4 doc vs 3.3.5
libs, CRIT-3 Radzen 10.2.3 vs 5.5.7) qui ont passé sous les radars 6 mois.

Pattern attendu pour chaque stack :
  - `{stack-id}.md` contient un tableau §2.4 régénéré par `sync_stack_md.py`
    avec format `| {lib-name} | {version} | {rationale} |`
  - `{stack-id}.libs.json` contient `versions: { "lib-name": "X.Y.Z" }`
  - Pour chaque ligne du `.md` : si la version est explicite (≠ vide ≠ "—"),
    elle DOIT matcher la version du `.libs.json` pour la même clé.
  - Si le `.md` mentionne une version dans la prose (`Spring Boot 4.0.x`,
    `Kotlin 2.3.21`) qui contredit le `.libs.json`, c'est un drift.

Usage :
    python validate_libs_versions_in_md.py [--stack-id ID] [--json] [--quiet]

Exit codes :
    0  SUCCESS    — aucun drift
    1  FAIL_FAST  — au moins 1 drift trouvé (table.md vs libs.json)
    3  INFRA_BLOCKED — fichier manquant / illisible / JSON invalide

JSON output (--json) :
    {
      "stacks_scanned": int,
      "stacks_with_drift": int,
      "drifts": [
        {"stack_id": str, "lib": str, "md_version": str, "json_version": str,
         "source": "table" | "prose", "file": str, "line": int}
      ],
      "exit_code": int
    }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402

# Tableau MD : `| lib-name | version | rationale |`
# Capture lib-name (colonne 1) + version (colonne 2). Rationale optionnel.
# Ignore les lignes header `|---|---|---|` et `| Module | Version | ...`.
_TABLE_ROW_RE = re.compile(
    r"^\|\s*([A-Za-z0-9._@/-]+)\s*\|\s*([0-9][0-9A-Za-z.+_-]*)\s*\|",
    re.MULTILINE,
)

# Mentions explicites de version dans la prose : "Spring Boot 4.0.x",
# "Kotlin 2.3.21", "Vuetify 3.7", "Angular 19", "Express 5". On capture
# (libname, version) pour cross-check contre libs.json. Ignore les
# versions non-pinables ("Spring Boot 4" générique sans .x ni patch).
_PROSE_VERSION_RE = re.compile(
    r"\b(Spring Boot|Spring Security|Kotlin|Vuetify|Angular|React|Vue|Express|FastAPI|"
    r"Next\.?js|Nuxt|Tailwind|TypeScript|Node|Python|JDK|Java|\.NET|EF Core)\s+"
    r"(\d+(?:\.\d+){1,3}(?:[.x][0-9a-zA-Z._-]*)?\+?)",
    re.IGNORECASE,
)

# Mapping prose libname → libs.json versions key (case-insensitive).
_PROSE_TO_JSON_KEY = {
    "spring boot": "spring-boot",
    "spring security": "spring-security",
    "kotlin": "kotlin",
    "vuetify": "vuetify",
    "angular": "angular",
    "react": "react",
    "vue": "vue",
    "express": "express",
    "fastapi": "fastapi",
    "next.js": "next",
    "nextjs": "next",
    "nuxt": "nuxt",
    "tailwind": "tailwindcss",
    "typescript": "typescript",
    "node": "node-types",  # often refers to Node runtime, mapped to @types/node
    "python": "python",
    "jdk": "jdk",
    "java": "java",
    ".net": "dotnet",
    "ef core": "ef-core",
}


def _normalize_version(v: str) -> str:
    """Strip suffixes like `.x` and `-LTS` for comparison purposes.

    `4.0.x` matches `4.0.0`, `4.0.1`, etc. (treats `.x` as wildcard for the
    last segment). `3.3.x` matches `3.3.5`. `2.0.21` exact match.
    """
    return v.strip().lower().rstrip(".x").rstrip(".X")


def _parse_semver(v: str) -> tuple[int, ...]:
    """Parse `X.Y.Z` into tuple of ints. Non-numeric segments → 0 (best-effort).

    Returns at least 3 components (pads with zeros). Used for semver-aware
    comparison in lower-bound `+` cases.
    """
    cleaned = v.strip().lstrip("vV").rstrip("+xX.").rstrip(".")
    parts: list[int] = []
    for seg in cleaned.split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            # First non-numeric segment ends parsing (treat suffix as ignored)
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _versions_compatible(md_v: str, json_v: str) -> bool:
    """Return True if .md version is compatible with .libs.json version.

    Cases handled :
    - Exact match : `2.0.21` == `2.0.21` → True
    - Wildcard `.x` : `.md` `4.0.x` matches `.libs.json` `4.0.5`
    - Lower-bound `+` : `.md` `3.10+` accepts `.libs.json` `>= 3.10` (semver)
      (used in stacks like shadcn where the catalog pins exact but the
      .md states the minimum required version ; also Python `3.10+` prose
      annotating that a syntax requires that runtime minimum)
    - Prefix : `.md` `3.3` matches `3.3.5`
    """
    md_clean = md_v.strip().lower()
    json_clean = json_v.strip().lower()
    # Lower-bound `+` suffix : `3.10+` means `>= 3.10` (semver-aware).
    if md_clean.endswith("+"):
        md_lb = _parse_semver(md_clean)
        json_v_tuple = _parse_semver(json_clean)
        return json_v_tuple >= md_lb
    # Wildcard `.x` suffix : `4.0.x` means any patch on `4.0`.
    md_norm = _normalize_version(md_v)
    json_norm = _normalize_version(json_v)
    if md_norm == json_norm:
        return True
    # Prefix match : md `3.3` matches json `3.3.5`.
    if json_norm.startswith(md_norm + "."):
        return True
    return False


def _scan_md_table(md_path: Path, md_text: str, libs_versions: dict) -> list[dict]:
    """Find drifts in §2.4 table rows where lib name matches a json key."""
    drifts: list[dict] = []
    lines = md_text.splitlines()
    for i, line in enumerate(lines, start=1):
        m = _TABLE_ROW_RE.match(line)
        if m is None:
            continue
        lib_raw = m.group(1).strip()
        md_version = m.group(2).strip()
        # Build candidate keys to look up in libs.json `versions:`.
        # Priority order (most specific first) :
        #   1. exact MD key (e.g. `vite`)
        #   2. `@types/X` → `X-types` (SDD_Pro convention key name)
        #   3. lowercased + scope-stripped
        #   4. scope normalized with `-` separator
        candidates: list[str] = [lib_raw]
        if lib_raw.startswith("@types/"):
            type_name = lib_raw[len("@types/"):]
            # `@types/react` → try `react-types` (SDD_Pro convention) FIRST
            candidates.append(f"{type_name}-types")
            candidates.append(f"{type_name.replace('/', '-')}-types")
            # `@types/swagger-ui-express` → libs key `swagger-ui-types` (stem
            # `swagger-ui` is a prefix of `swagger-ui-express`). Match by
            # picking the longest existing `*-types` key whose stem prefixes
            # the @types target. Avoids false positive against base lib key.
            existing_type_keys = [
                k for k in libs_versions
                if k.endswith("-types") and type_name.startswith(k[: -len("-types")])
            ]
            if existing_type_keys:
                best_match = max(existing_type_keys, key=len)
                candidates.insert(1, best_match)  # priority right after lib_raw
        lib_key = lib_raw.lower().replace("@types/", "").lstrip("@")
        candidates.extend([lib_key, lib_key.replace("/", "-")])
        json_version = None
        for cand in candidates:
            if cand in libs_versions:
                json_version = libs_versions[cand]
                break
        if json_version is None:
            continue  # lib not in libs.json — ignore (could be transitive)
        if not _versions_compatible(md_version, json_version):
            drifts.append({
                "lib": lib_raw,
                "md_version": md_version,
                "json_version": json_version,
                "source": "table",
                "file": str(md_path),
                "line": i,
            })
    return drifts


def _scan_md_prose(md_path: Path, md_text: str, libs_versions: dict) -> list[dict]:
    """Find drifts in prose mentions like 'Spring Boot 4.0.x'."""
    drifts: list[dict] = []
    for m in _PROSE_VERSION_RE.finditer(md_text):
        prose_name = m.group(1).lower()
        md_version = m.group(2)
        json_key = _PROSE_TO_JSON_KEY.get(prose_name)
        if json_key is None or json_key not in libs_versions:
            continue
        json_version = libs_versions[json_key]
        if not _versions_compatible(md_version, json_version):
            # Compute line number from byte offset.
            line = md_text[: m.start()].count("\n") + 1
            drifts.append({
                "lib": prose_name,
                "md_version": md_version,
                "json_version": json_version,
                "source": "prose",
                "file": str(md_path),
                "line": line,
            })
    return drifts


def scan_stack(md_path: Path, json_path: Path) -> tuple[list[dict], str | None]:
    """Scan one stack pair. Returns (drifts, error_message_or_None)."""
    try:
        md_text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], f"cannot read {md_path}: {exc}"
    try:
        json_obj = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"cannot parse {json_path}: {exc}"
    versions = json_obj.get("versions", {})
    if not isinstance(versions, dict):
        return [], f"{json_path}: 'versions' is not an object"
    drifts = _scan_md_table(md_path, md_text, versions)
    drifts.extend(_scan_md_prose(md_path, md_text, versions))
    return drifts, None


def find_stack_pairs(root: Path, only_stack_id: str | None = None) -> list[tuple[str, Path, Path]]:
    """Return list of (stack_id, md_path, libs_json_path) for stacks with both files."""
    stacks_root = root / ".claude" / "stacks"
    pairs: list[tuple[str, Path, Path]] = []
    if not stacks_root.is_dir():
        return pairs
    for cat_dir in stacks_root.iterdir():
        if not cat_dir.is_dir():
            continue
        for md_file in cat_dir.glob("*.md"):
            if md_file.name == "README.md":
                continue
            stack_id = md_file.stem
            if only_stack_id and stack_id != only_stack_id:
                continue
            json_file = cat_dir / f"{stack_id}.libs.json"
            if json_file.is_file():
                pairs.append((stack_id, md_file, json_file))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-check .md library tables vs .libs.json versions"
    )
    parser.add_argument("--stack-id", default=None,
                        help="Restrict to one stack (e.g. kotlin-spring-boot)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON report on stdout")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-drift stderr output")
    args = parser.parse_args(argv)

    try:
        root = repo_root()
    except Exception as exc:
        print(f"[FAIL] cannot resolve repo root: {exc}", file=sys.stderr)
        return INFRA_BLOCKED

    pairs = find_stack_pairs(root, args.stack_id)
    if not pairs:
        msg = f"No stack pairs found (filter: {args.stack_id or 'none'})"
        if args.json:
            print(json.dumps({
                "stacks_scanned": 0, "stacks_with_drift": 0,
                "drifts": [], "exit_code": SUCCESS, "warning": msg,
            }, indent=2))
        else:
            print(f"[WARN] {msg}", file=sys.stderr)
        return SUCCESS

    all_drifts: list[dict] = []
    infra_errors: list[str] = []
    stacks_with_drift = 0

    for stack_id, md_path, json_path in pairs:
        drifts, err = scan_stack(md_path, json_path)
        if err is not None:
            infra_errors.append(err)
            continue
        if drifts:
            stacks_with_drift += 1
            for d in drifts:
                d["stack_id"] = stack_id
            all_drifts.extend(drifts)

    if infra_errors:
        for e in infra_errors:
            print(f"[FAIL] {e}", file=sys.stderr)
        return INFRA_BLOCKED

    exit_code = FAIL_FAST if all_drifts else SUCCESS

    if args.json:
        print(json.dumps({
            "stacks_scanned": len(pairs),
            "stacks_with_drift": stacks_with_drift,
            "drifts": all_drifts,
            "exit_code": exit_code,
        }, indent=2))
    else:
        if all_drifts:
            print(f"[FAIL] {len(all_drifts)} drift(s) across {stacks_with_drift} stack(s):",
                  file=sys.stderr)
            if not args.quiet:
                for d in all_drifts:
                    print(
                        f"  - {d['stack_id']} [{d['source']}] {d['lib']}: "
                        f".md says {d['md_version']!r}, .libs.json says {d['json_version']!r} "
                        f"({d['file']}:{d['line']})",
                        file=sys.stderr,
                    )
            print(
                "\nFIX: éditer le .md ou le .libs.json pour aligner. "
                "Si le .md auto-régénéré (sync_stack_md.py), corriger le .libs.json amont.",
                file=sys.stderr,
            )
        else:
            print(f"[OK] {len(pairs)} stack(s) scanned, no drift detected.",
                  file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
