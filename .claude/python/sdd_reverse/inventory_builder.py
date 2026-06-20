"""SDD_Pro Reverse Engineering — Inventory builder.

Enriches scan_legacy output with:
- Pages identification (web entry points, screens)
- Entry points detection (root, auth, main)
- Module suggestions (group pages by folder structure)

Produces the final inventory-raw.json structure documented in
docs/reverse-engineering-workflow.md SS2.3.

Pure deterministic Python (0 LLM tokens). No imports from sdd_lib/.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# Page extensions per technology
# Note: .master (ASP.NET master pages) and .ascx (user controls) included because
# they often contain shared UI units (menus, layout, header) that produce FEATs.
PAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "dotnet-webforms": (".aspx", ".master", ".ascx"),
    "dotnet-mvc": (".cshtml",),
    "dotnet-blazor": (".razor",),
    "java-jee": (".jsp", ".jspx"),
    "php-procedural": (".php", ".phtml"),
    "php-framework": (".php",),
    "html-static": (".html", ".htm"),
}

# Entry-point filename patterns (case-insensitive)
ENTRY_POINT_PATTERNS: list[tuple[str, str]] = [
    (r"^default\.(aspx|html|htm|jsp|php)$", "root"),
    (r"^index\.(html|htm|jsp|php|aspx)$", "root"),
    (r"^home\.(aspx|cshtml|razor|jsp|php)$", "root"),
    (r"^login\.(aspx|cshtml|razor|jsp|php)$", "auth"),
    (r"^signin\.(aspx|cshtml|razor|jsp|php)$", "auth"),
    (r"^logout\.(aspx|cshtml|razor|jsp|php)$", "auth"),
    (r"^main\.(java|cs|vb)$", "code-entry"),
    (r"^program\.cs$", "code-entry"),
    (r"^app\.config$", "config"),
    (r"^startup\.cs$", "code-entry"),
]

# Routes derived from path conventions
ROUTE_DERIVATION_RULES = [
    (r"^Default\.aspx$", "/"),
    (r"^index\.(html|php)$", "/"),
    (r"^Login\.aspx$", "/Login"),
]


def _read_text_safe(path: Path, max_bytes: int = 32768) -> str:
    """Read file content (UTF-8 best-effort, capped)."""
    try:
        size = min(path.stat().st_size, max_bytes)
        with path.open("rb") as f:
            raw = f.read(size)
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
    except OSError:
        pass
    return ""


def _extract_title(content: str) -> str | None:
    """Extract page title from <title> tag, <h1>, or @page title attribute."""
    # <title>...</title>
    m = re.search(r"<title>\s*([^<\n]+?)\s*</title>", content, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
        if title and len(title) < 200:
            return title
    # <h1>...</h1>
    m = re.search(r"<h1[^>]*>\s*([^<\n]+?)\s*</h1>", content, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
        if title and len(title) < 200:
            return title
    # <%@ Page Title="..."
    m = re.search(r'@\s*Page[^%]*?Title\s*=\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _compute_complexity_score(content: str, loc: int) -> int:
    """Heuristic complexity score (1-5) based on LOC + control density."""
    if loc < 50:
        base = 1
    elif loc < 150:
        base = 2
    elif loc < 300:
        base = 3
    elif loc < 500:
        base = 4
    else:
        base = 5

    # Boost on detection of complex controls
    boost = 0
    if re.search(r"<asp:GridView|<asp:DataGrid", content, re.IGNORECASE):
        boost += 1
    if re.search(r"<asp:Wizard", content, re.IGNORECASE):
        boost += 1
    if re.search(r"<asp:UpdatePanel", content, re.IGNORECASE):
        boost += 1
    if content.count("<form") >= 2:
        boost += 1

    return min(5, base + min(boost, 2))


def _find_code_behind(page_path: Path, project_path: Path) -> str | None:
    """Find code-behind file (.aspx.cs, .ascx.vb, etc.)."""
    name = page_path.name
    parent = page_path.parent
    candidates = [
        parent / f"{name}.cs",
        parent / f"{name}.vb",
        parent / f"{page_path.stem}.razor.cs",
        parent / f"{page_path.stem}.xaml.cs",
    ]
    for c in candidates:
        if c.is_file():
            try:
                return str(c.relative_to(project_path)).replace("\\", "/")
            except ValueError:
                continue
    return None


def detect_pages(
    scan_result: dict[str, Any],
    project_path: Path,
) -> list[dict[str, Any]]:
    """Identify pages/screens in the legacy project.

    Walks the file tree (excluding scan_result.exclusions paths) and picks
    files matching page extensions per detected language family.
    """
    project_path = project_path.resolve()
    detected_langs = {lang["id"] for lang in scan_result.get("languages", [])}

    # Build a set of all "page" extensions relevant to this project
    page_exts: set[str] = set()
    for lang_id, exts in PAGE_EXTENSIONS.items():
        if lang_id in detected_langs:
            page_exts.update(exts)

    if not page_exts:
        # Fallback: still scan html files
        page_exts = {".html", ".htm"}

    excluded_set = set()
    for cat in ("vendored", "generated", "tests", "ide"):
        for p in scan_result.get("exclusions", {}).get(cat, []) or []:
            excluded_set.add(p.replace("\\", "/"))

    pages: list[dict[str, Any]] = []
    page_counter = 0

    for root, dirs, files in os.walk(project_path):
        # Skip .sys/
        if ".sys" in dirs:
            dirs.remove(".sys")
        for fname in files:
            ext = "." + fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
            if ext not in page_exts:
                continue
            full_path = Path(root) / fname
            try:
                rel_path = str(full_path.relative_to(project_path)).replace("\\", "/")
            except ValueError:
                continue
            if rel_path in excluded_set:
                continue

            content = _read_text_safe(full_path)
            loc = sum(1 for line in content.splitlines() if line.strip())
            title = _extract_title(content)
            complexity = _compute_complexity_score(content, loc)
            code_behind = _find_code_behind(full_path, project_path)

            page_counter += 1
            pages.append({
                "id": f"page-{page_counter:03d}",
                "path": rel_path,
                "code_behind": code_behind,
                "title_detected": title,
                "loc": loc,
                "complexity_score": complexity,
            })

    # Sort by path for determinism
    pages.sort(key=lambda p: p["path"])
    # Re-assign IDs in sorted order
    for i, p in enumerate(pages, 1):
        p["id"] = f"page-{i:03d}"
    return pages


def detect_entry_points(
    pages: list[dict[str, Any]],
    scan_result: dict[str, Any],
    project_path: Path,
) -> list[dict[str, Any]]:
    """Identify entry points from filenames + paths."""
    entries: list[dict[str, Any]] = []
    for page in pages:
        fname = Path(page["path"]).name.lower()
        for pattern, role in ENTRY_POINT_PATTERNS:
            if re.match(pattern, fname, re.IGNORECASE):
                route = _derive_route(page["path"])
                entries.append({
                    "path": page["path"],
                    "type": "page",
                    "role": role,
                    "route": route,
                })
                break
    return entries


def _derive_route(rel_path: str) -> str:
    """Convert a relative file path to a likely URL route."""
    p = rel_path.replace("\\", "/")
    # Strip leading folders like 'wwwroot/' if any
    # Strip the file extension (last . onwards)
    p_no_ext = p.rsplit(".", 1)[0]
    # Replace index/default with /
    parts = p_no_ext.split("/")
    if parts[-1].lower() in ("default", "index", "home"):
        parts = parts[:-1]
    route = "/" + "/".join(parts)
    return route if route != "/" or parts else "/"


def suggest_modules(
    pages: list[dict[str, Any]],
    scan_result: dict[str, Any],
    project_path: Path,
) -> list[dict[str, Any]]:
    """Group pages into modules based on folder structure.

    Heuristic:
    - Pages in a subfolder of depth >= 1 → module = first folder name
    - Pages at root with auth-related names → module 'Authentication'
    - Other root pages → module 'Common'
    """
    modules: dict[str, dict[str, Any]] = {}

    for page in pages:
        rel = page["path"].replace("\\", "/")
        parts = rel.split("/")
        fname_lower = parts[-1].lower()

        if len(parts) > 1:
            module_label = parts[0]
        elif re.match(r"^(login|signin|signup|register|logout|auth).*", fname_lower):
            module_label = "Authentication"
        elif re.match(r"^(default|index|home).*", fname_lower):
            module_label = "Layout"
        else:
            module_label = "Common"

        module_id = f"module-{module_label.lower()}"
        mod = modules.setdefault(module_id, {
            "id": module_id,
            "label": module_label,
            "pages": [],
            "loc_total": 0,
        })
        mod["pages"].append(page["id"])
        mod["loc_total"] += page["loc"]

    # Sort modules by loc_total desc
    return sorted(modules.values(), key=lambda m: m["loc_total"], reverse=True)


def build_inventory(
    scan_result: dict[str, Any],
    project_path: Path,
) -> dict[str, Any]:
    """Combine scan_result + pages + entry_points + modules into inventory-raw.

    Returns a dict matching docs/reverse-engineering-workflow.md SS2.3 schema.
    """
    project_path = project_path.resolve()
    pages = detect_pages(scan_result, project_path)
    entry_points = detect_entry_points(pages, scan_result, project_path)
    modules = suggest_modules(pages, scan_result, project_path)

    inventory = dict(scan_result)
    inventory["pages"] = pages
    inventory["entry_points"] = entry_points
    inventory["modules_suggested"] = modules
    # Detect dead-code candidates: pages with no inbound code_behind reference
    inventory["exclusions"]["dead_code_candidates"] = _detect_dead_code(pages, project_path)
    return inventory


def _detect_dead_code(
    pages: list[dict[str, Any]],
    project_path: Path,
) -> list[str]:
    """Naive dead-code: pages whose stem name is never referenced in code-behind text.

    NOTE: heuristic only — may produce false positives. Tech Lead validates.
    """
    candidates: list[str] = []
    # Build a corpus of all code-behind / source content
    corpus_parts: list[str] = []
    for page in pages:
        if page.get("code_behind"):
            cb_path = project_path / page["code_behind"]
            if cb_path.is_file():
                corpus_parts.append(_read_text_safe(cb_path, max_bytes=16384))
    corpus = "\n".join(corpus_parts).lower()
    for page in pages:
        stem = Path(page["path"]).stem.lower()
        # Skip very short or generic names
        if len(stem) < 4 or stem in {"default", "index", "home", "login"}:
            continue
        if stem not in corpus:
            candidates.append(f"{page['path']} (no inbound reference)")
    return candidates[:10]  # cap to avoid noise
