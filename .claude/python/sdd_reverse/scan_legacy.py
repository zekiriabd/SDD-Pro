"""SDD_Pro Reverse Engineering — Deterministic legacy code scanner.

Scans workspace/old/{LegacyProject}/ and produces a structured inventory dict
matching the schema documented in docs/reverse-engineering-workflow.md SS2.3.

Pure deterministic Python (0 LLM tokens). Detection driven by
language_signatures.yml (declarative, extensible without code changes).

Anti-derive:
- No imports from sdd_lib/, sdd_scripts/, sdd_admin/, sdd_hooks/
- Read-only on legacy code (never writes back into workspace/old/)
- No network calls
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1


def load_signatures(signatures_path: Path) -> dict[str, Any]:
    """Load and parse language_signatures.yml."""
    if not signatures_path.is_file():
        raise FileNotFoundError(
            f"[REVERSE_SCAN_FAILED] language_signatures.yml not found at {signatures_path}"
        )
    try:
        data = yaml.safe_load(signatures_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(
            f"[REVERSE_SCAN_FAILED] language_signatures.yml YAML parse error: {exc}"
        ) from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"[REVERSE_SCAN_FAILED] signatures schema_version mismatch (expected {SCHEMA_VERSION})"
        )
    return data


def _build_indexes(signatures: dict[str, Any]) -> tuple[dict, dict, dict, dict]:
    """Build lookup indexes from signatures (called once per scan).

    Returns: (ext_index, companion_index, manifest_index, languages_by_id)
    """
    ext_index: dict[str, list[str]] = {}
    companion_index: dict[str, list[str]] = {}
    manifest_index: dict[str, list[str]] = {}
    languages_by_id: dict[str, dict] = {}

    for lang in signatures.get("languages", []):
        lang_id = lang["id"]
        languages_by_id[lang_id] = lang
        for ext in lang.get("extensions", []):
            ext_index.setdefault(ext.lower(), []).append(lang_id)
        for comp in lang.get("companion_extensions", []) or []:
            companion_index.setdefault(comp.lower(), []).append(lang_id)
        for manifest in lang.get("manifests", []) or []:
            manifest_index.setdefault(manifest, []).append(lang_id)

    return ext_index, companion_index, manifest_index, languages_by_id


def _is_excluded(rel_path: str, exclusions: dict[str, list[str]]) -> tuple[bool, str | None]:
    """Check if a relative path matches an exclusion pattern.

    Returns (is_excluded, category). Categories: vendored, generated, test, ide.

    Match strategy (any one is enough):
    1. Full rel_path matches pattern (e.g. 'Scripts/jquery-*.js' vs 'Scripts/jquery-1.11.3.min.js')
    2. Basename matches pattern (e.g. 'test_*.py' vs 'src/test_main.py' → basename 'test_main.py')
    3. Pattern with '/' tries each path-trailing variant (handles 'obj/**' on nested files)
    """
    rel_norm = rel_path.replace("\\", "/")
    basename = rel_norm.rsplit("/", 1)[-1]
    categories = [
        ("vendored", exclusions.get("vendored_patterns", [])),
        ("generated", exclusions.get("generated_patterns", [])),
        ("test", exclusions.get("test_patterns", [])),
        ("ide", exclusions.get("ide_patterns", [])),
    ]
    for category, patterns in categories:
        for pattern in patterns:
            # 1. Full path match
            if fnmatch.fnmatch(rel_norm, pattern):
                return True, category
            # 2. Basename match (catches test_*.py at any depth)
            if "/" not in pattern and fnmatch.fnmatch(basename, pattern):
                return True, category
            # 3. Path-with-trailing-slash variant (for patterns like 'obj/**')
            if "/" in pattern and fnmatch.fnmatch(rel_norm + "/", pattern + "/"):
                return True, category
            # 4. Folder-pattern match: 'node_modules/**' should match any file inside node_modules/
            if pattern.endswith("/**"):
                prefix = pattern[:-3]
                if rel_norm.startswith(prefix + "/") or ("/" + prefix + "/") in ("/" + rel_norm):
                    return True, category
    return False, None


def _detect_language_by_extension(
    file_path: Path,
    ext_index: dict[str, list[str]],
    companion_index: dict[str, list[str]],
) -> list[str]:
    """Return candidate language IDs from extension matching.

    Companion (longer/double) extensions checked first to handle .aspx.cs etc.
    """
    name_lower = file_path.name.lower()
    # Companion check (longest first to handle .aspx.cs before .cs)
    for comp_ext in sorted(companion_index.keys(), key=len, reverse=True):
        if name_lower.endswith(comp_ext):
            return list(companion_index[comp_ext])
    # Fallback: primary extension
    ext = file_path.suffix.lower()
    return list(ext_index.get(ext, []))


def _read_file_head(file_path: Path, max_bytes: int) -> str | None:
    """Read first `max_bytes` of file, decode best-effort.

    Returns None if file is binary or unreadable.
    """
    try:
        size = file_path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return ""
    read_bytes = min(size, max_bytes)
    try:
        with file_path.open("rb") as f:
            raw = f.read(read_bytes)
    except OSError:
        return None
    # Binary heuristic: high ratio of null bytes
    if raw.count(b"\x00") > len(raw) * 0.01:
        return None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1, "n/a": 0}


def _disambiguate_by_signals(
    file_path: Path,
    rel_path: str,
    content_head: str,
    candidates: list[str],
    languages_by_id: dict[str, dict],
) -> str:
    """Disambiguate between candidate languages using grep + folder signals.

    Rules (load-bearing for false-positive prevention):
    1. Languages that declare grep_signals MUST match at least one to win against
       a "generic" language (one that declares no grep_signals).
    2. If no specific language matches and a generic candidate exists, generic wins.
    3. Otherwise highest signal_score wins, tiebreak by confidence_hint.
    """
    if len(candidates) == 1:
        return candidates[0]

    rel_norm = rel_path.replace("\\", "/").lower()

    # Compute signal_score per candidate (folder=+2, grep=+3)
    signal_scores: dict[str, int] = {}
    has_grep_match: dict[str, bool] = {}

    for lang_id in candidates:
        lang = languages_by_id[lang_id]
        score = 0
        grep_matched = False

        for folder_signal in lang.get("folder_signals", []) or []:
            signal_norm = folder_signal.rstrip("/").lower()
            if signal_norm and signal_norm in rel_norm:
                score += 2

        grep_patterns = lang.get("grep_signals", []) or []
        for pattern in grep_patterns:
            if not pattern:
                continue
            try:
                if re.search(pattern, content_head, re.IGNORECASE | re.MULTILINE):
                    score += 3
                    grep_matched = True
            except re.error:
                continue

        signal_scores[lang_id] = score
        # "has_grep_match" is True if the lang declares no grep (generic), OR
        # at least one of its grep_signals matched.
        has_grep_match[lang_id] = (not grep_patterns) or grep_matched

    # Phase 1: filter to candidates that have grep_match (specific with match OR generic)
    valid = [c for c in candidates if has_grep_match[c]]

    if not valid:
        # No specific language matched and no generic candidate — pick highest scorer
        # (this is a rare path; falls back to candidate order otherwise)
        return max(candidates, key=lambda c: (signal_scores[c], -candidates.index(c)))

    # Phase 2: among valid, prefer non-generic (with grep_signals) if any matched
    specific_matched = [
        c for c in valid
        if (languages_by_id[c].get("grep_signals") or [])
    ]
    pool = specific_matched if specific_matched else valid

    # Phase 3: highest signal_score wins; tiebreak by confidence_hint then declaration order
    def sort_key(lang_id: str) -> tuple:
        hint = languages_by_id[lang_id].get("confidence_hint", "medium")
        return (-signal_scores[lang_id], -_CONFIDENCE_RANK.get(hint, 0), candidates.index(lang_id))

    pool_sorted = sorted(pool, key=sort_key)
    return pool_sorted[0]


def _count_loc(content: str) -> int:
    """Count non-empty, non-pure-whitespace lines."""
    if not content:
        return 0
    return sum(1 for line in content.splitlines() if line.strip())


def _detect_frameworks(
    project_path: Path,
    found_manifests: list[dict],
    files_sampled: list[dict],
) -> list[dict]:
    """Detect frameworks based on manifest presence + grep signals on samples.

    Returns list of {id, evidence, version_detected?}.
    """
    frameworks: list[dict] = []
    manifest_paths = {m["path"] for m in found_manifests}

    # ASP.NET WebForms: Web.config presence
    if any("Web.config" in p for p in manifest_paths):
        frameworks.append(
            {"id": "asp.net", "evidence": "Web.config detected"}
        )

    # Spring Boot: application.yml/properties + pom/gradle with spring-boot
    if any(p.endswith(("application.yml", "application.properties")) for p in manifest_paths):
        frameworks.append({"id": "spring", "evidence": "application.{yml,properties} detected"})

    # Maven / Gradle / npm signals
    if any(p.endswith("pom.xml") for p in manifest_paths):
        frameworks.append({"id": "maven", "evidence": "pom.xml detected"})
    if any(p.endswith(("build.gradle", "build.gradle.kts")) for p in manifest_paths):
        frameworks.append({"id": "gradle", "evidence": "build.gradle detected"})
    if any(p.endswith("package.json") for p in manifest_paths):
        # Detect jQuery / React / Vue / Angular by inspecting package.json content
        for m in found_manifests:
            if m["path"].endswith("package.json"):
                try:
                    pkg_path = project_path / m["path"]
                    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    for known in ("jquery", "react", "vue", "@angular/core", "next", "nuxt"):
                        if known in deps:
                            frameworks.append({
                                "id": known.lstrip("@").split("/")[0],
                                "version_detected": deps[known],
                                "evidence": f"{m['path']} dependency",
                            })
                except (OSError, json.JSONDecodeError):
                    pass

    # composer.json (PHP)
    if any(p.endswith("composer.json") for p in manifest_paths):
        frameworks.append({"id": "composer", "evidence": "composer.json detected"})

    return frameworks


def scan_project(
    project_path: Path,
    signatures: dict[str, Any],
) -> dict[str, Any]:
    """Scan a legacy project root, return inventory-raw structure.

    Args:
        project_path: Absolute path to workspace/old/{LegacyProject}/
        signatures: Parsed language_signatures.yml dict

    Returns:
        Dict matching schema docs/reverse-engineering-workflow.md SS2.3.

    Raises:
        FileNotFoundError: project_path doesn't exist
        ValueError: schema mismatch
    """
    if not project_path.is_dir():
        raise FileNotFoundError(
            f"[REVERSE_PRECONDITION] project_path not found or not a directory: {project_path}"
        )

    ext_index, companion_index, manifest_index, languages_by_id = _build_indexes(signatures)
    exclusions = signatures.get("exclusions", {})
    limits = signatures.get("limits", {})
    max_file_size = limits.get("max_file_size_kb", 512) * 1024
    grep_max_bytes = limits.get("grep_max_bytes", 16384)
    max_files = limits.get("max_files_scanned", 10000)

    # Aggregations
    lang_stats: dict[str, dict] = {}
    found_manifests: list[dict] = []
    excluded_lists: dict[str, list[str]] = {
        "vendored": [],
        "generated": [],
        "tests": [],
        "ide": [],
    }
    files_total = 0
    files_analyzed = 0
    files_excluded = 0
    loc_total = 0
    loc_analyzed = 0
    cap_reached = False
    files_sampled: list[dict] = []

    project_path = project_path.resolve()
    # Ignore the .sys/ subdirectory itself (our own output) AND workspace/old root .sys
    sys_subdir = project_path / ".sys"

    for root, dirs, files in os.walk(project_path):
        # Skip .sys/ produced by /sdd-reverse itself
        if Path(root).resolve() == sys_subdir or sys_subdir in Path(root).resolve().parents:
            dirs[:] = []
            continue
        # In-place prune dirs starting with . (except top-level) for hidden git/etc
        dirs[:] = [d for d in dirs if d != ".sys"]

        for fname in files:
            files_total += 1
            if files_total > max_files:
                cap_reached = True
                continue

            full_path = Path(root) / fname
            rel_path = str(full_path.relative_to(project_path))

            # Exclusion check
            is_excluded, exc_category = _is_excluded(rel_path, exclusions)
            if is_excluded:
                files_excluded += 1
                key = "tests" if exc_category == "test" else (exc_category or "ide")
                excluded_lists.setdefault(key, []).append(rel_path)
                continue

            # Size guard
            try:
                fsize = full_path.stat().st_size
            except OSError:
                files_excluded += 1
                continue
            if fsize > max_file_size:
                files_excluded += 1
                continue

            # Manifest detection
            for manifest_pattern, manifest_lang_ids in manifest_index.items():
                if fnmatch.fnmatch(fname, manifest_pattern):
                    found_manifests.append({
                        "path": rel_path,
                        "type": manifest_pattern,
                    })
                    break

            # Language detection
            ext_candidates = _detect_language_by_extension(full_path, ext_index, companion_index)
            content_head = _read_file_head(full_path, grep_max_bytes)
            if content_head is None:
                # Binary or unreadable — count as excluded
                files_excluded += 1
                continue

            if not ext_candidates:
                lang_id = "unknown"
            elif len(ext_candidates) == 1:
                lang_id = ext_candidates[0]
            else:
                lang_id = _disambiguate_by_signals(
                    full_path, rel_path, content_head, ext_candidates, languages_by_id
                )

            # Compute LOC (use full file for accuracy, not just head)
            if fsize <= grep_max_bytes:
                file_content = content_head
            else:
                try:
                    file_content = full_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    file_content = content_head
            loc = _count_loc(file_content)

            # Aggregate per-language stats
            stat = lang_stats.setdefault(
                lang_id,
                {
                    "id": lang_id,
                    "confidence_hint": languages_by_id.get(lang_id, {}).get(
                        "confidence_hint", "low"
                    ),
                    "files_count": 0,
                    "loc": 0,
                },
            )
            stat["files_count"] += 1
            stat["loc"] += loc

            loc_total += loc
            loc_analyzed += loc
            files_analyzed += 1

            # Sample first 50 files for framework detection input
            if len(files_sampled) < 50:
                files_sampled.append({"path": rel_path, "lang_id": lang_id})

    # Framework detection (post-walk)
    frameworks = _detect_frameworks(project_path, found_manifests, files_sampled)

    # Sort lang_stats by LOC desc for readability
    languages = sorted(lang_stats.values(), key=lambda x: x["loc"], reverse=True)

    return {
        "schema_version": SCHEMA_VERSION,
        "project": project_path.name,
        "project_path": str(project_path).replace("\\", "/"),
        "scanned_at": _now_iso(),
        "languages": languages,
        "frameworks": frameworks,
        "manifests": found_manifests,
        "exclusions": {
            "vendored": sorted(excluded_lists["vendored"])[:50],
            "generated": sorted(excluded_lists["generated"])[:50],
            "tests": sorted(excluded_lists.get("tests", []))[:50],
            "ide": sorted(excluded_lists.get("ide", []))[:50],
            "cap_reached": cap_reached,
        },
        "stats": {
            "files_total": files_total,
            "files_analyzed": files_analyzed,
            "files_excluded": files_excluded,
            "loc_total": loc_total,
            "loc_analyzed": loc_analyzed,
        },
    }


def _now_iso() -> str:
    """Return current UTC time in ISO-8601 with Z suffix."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
