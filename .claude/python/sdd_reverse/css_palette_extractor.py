"""css_palette_extractor.py — Extract colors, fonts, spacings from legacy CSS.

Phase 4 (UI) prerequisite. Feeds the reverse-ui-extractor agent with
a normalized palette so the generated HTML mockups can preserve
look-and-feel.

Public API:
    extract_palette(project_root, scan_result) -> dict

Output:
    {
        "schemaVersion": 1,
        "colors": [{"hex": "#2563eb", "occurrences": 12, "named_tokens": ["primary?"]}],
        "fonts": ["Roboto", "Arial", "sans-serif"],
        "spacings_px": [4, 8, 16, 24, 32],
        "border_radius_px": [4, 8],
        "css_sources": ["Site.css", "Content/bootstrap.css"]
    }
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import ScanResult, normalize_bytes

_RE_HEX = re.compile(r"#([0-9a-fA-F]{3,8})\b")
_RE_RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)")
_RE_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;{}]+);?", re.IGNORECASE)
_RE_PADDING_MARGIN = re.compile(r"\b(?:padding|margin|gap|top|left|right|bottom)\s*:\s*([^;{}]+);", re.IGNORECASE)
_RE_BORDER_RADIUS = re.compile(r"border-radius\s*:\s*([^;{}]+);", re.IGNORECASE)
_RE_PX_VALUE = re.compile(r"(\d+(?:\.\d+)?)\s*px\b")

# Heuristic: tokens names suggesting role (best-effort, not authoritative)
_SEMANTIC_HINTS = {
    "primary": [r"\bprimary\b", r"\bbrand\b", r"\baction\b"],
    "danger": [r"\bdanger\b", r"\berror\b", r"\bred\b", r"\bdelete\b"],
    "success": [r"\bsuccess\b", r"\bgreen\b", r"\bok\b", r"\bvalid"],
    "muted": [r"\bmuted\b", r"\bgrey\b", r"\bgray\b", r"\bdisabled\b"],
}


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return normalize_bytes(raw).decode("utf-8", errors="replace")


def _normalize_hex(hex_str: str) -> str:
    """Normalize ``#abc`` → ``#aabbcc``, ``#aabbcc`` → lowercase 6-digit.

    P1.8 closure (2026-06-10) : 8-digit hex (``#aabbccdd``) keeps its alpha
    channel in the canonical output. Previously the alpha was silently
    dropped — palettes grouped translucent colors with their opaque
    counterpart. Returned value is ``#RRGGBB`` (6 char) for fully-opaque or
    ``#RRGGBBAA`` (8 char) when an alpha is present.
    """
    h = hex_str.lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    elif len(h) == 4:
        # CSS3 short form #rgba → expand to #rrggbbaa
        h = "".join(c * 2 for c in h)
    # 6 and 8 are preserved as-is (alpha kept for 8-digit)
    return f"#{h}"


def _hex_strip_alpha(hex_str: str) -> str:
    """Return the RGB component only of a 6-or-8-digit normalized hex.

    Used for grouping translucent shades under one palette entry while
    still allowing the caller to recover the original alpha via
    ``_normalize_hex``.
    """
    h = hex_str.lstrip("#")
    return f"#{h[:6]}"


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _detect_semantic(name: str) -> list[str]:
    """Detect semantic role hints from a selector or context string."""
    detected: list[str] = []
    lower = name.lower()
    for role, patterns in _SEMANTIC_HINTS.items():
        for pat in patterns:
            if re.search(pat, lower):
                detected.append(role)
                break
    return detected


def extract_palette(project_root: str | Path, scan_result: ScanResult) -> dict[str, Any]:
    """Aggregate CSS-derived palette + fonts + spacings from the legacy."""
    root = Path(project_root).resolve()

    # Pass : find .css + inline <style> in .aspx/.cshtml/.html
    css_paths: list[Path] = []
    for lm in scan_result.languages:
        for f in lm.files:
            if f.suffix.lower() == ".css":
                css_paths.append(f)
    # Also rglob .css in case the scan missed them (e.g. resource-only files)
    for p in root.rglob("*.css"):
        if any(part in {"node_modules", "vendor", "bin", "obj", "packages"} for part in p.parts):
            continue
        if p not in css_paths and p.is_file():
            css_paths.append(p)

    # L4 — build the list of CSS sources: full .css files PLUS inline <style>
    # blocks and style="…" attributes embedded in templates (previously the
    # docstring claimed this but extract_palette only read .css files).
    _RE_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
    _RE_STYLE_ATTR = re.compile(r"\bstyle\s*=\s*\"([^\"]*)\"", re.IGNORECASE)
    _TEMPLATE_EXT = {".aspx", ".ascx", ".master", ".cshtml", ".vbhtml", ".html", ".htm"}

    style_sources: list[tuple[str, str]] = []
    for css_path in css_paths:
        content = _read_text(css_path)
        if not content:
            continue
        try:
            rel = str(css_path.relative_to(root).as_posix())
        except ValueError:
            rel = css_path.name
        style_sources.append((rel, content))

    seen_templates: set[Path] = set()
    for lm in scan_result.languages:
        for f in lm.files:
            if f.suffix.lower() not in _TEMPLATE_EXT or f in seen_templates:
                continue
            seen_templates.add(f)
            text = _read_text(f)
            if not text:
                continue
            inline_css_parts = _RE_STYLE_BLOCK.findall(text)
            inline_css_parts += [
                "x{" + v + "}" for v in _RE_STYLE_ATTR.findall(text)
            ]
            if not inline_css_parts:
                continue
            try:
                rel = str(f.relative_to(root).as_posix())
            except ValueError:
                rel = f.name
            style_sources.append((rel + " (inline)", "\n".join(inline_css_parts)))

    colors_counter: Counter[str] = Counter()
    color_contexts: dict[str, list[str]] = {}
    fonts_counter: Counter[str] = Counter()
    spacing_counter: Counter[int] = Counter()
    radius_counter: Counter[int] = Counter()
    css_sources: list[str] = []

    for rel, content in style_sources:
        css_sources.append(rel)

        # Strip comments to avoid false positives
        content_no_comments = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

        # Colors (hex)
        for m in _RE_HEX.finditer(content_no_comments):
            hex_val = _normalize_hex(m.group(1))
            colors_counter[hex_val] += 1
            # Context : the nearest selector (look back up to 200 chars for `{`)
            back = content_no_comments[max(0, m.start() - 200): m.start()]
            sel_match = re.search(r"([.\w-]+)\s*\{[^{}]*$", back)
            if sel_match:
                color_contexts.setdefault(hex_val, []).append(sel_match.group(1))

        # Colors (rgb/rgba)
        for m in _RE_RGB.finditer(content_no_comments):
            try:
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                    colors_counter[_rgb_to_hex(r, g, b)] += 1
            except ValueError:
                continue

        # Fonts
        for m in _RE_FONT_FAMILY.finditer(content_no_comments):
            stack = m.group(1)
            for part in stack.split(","):
                font = part.strip().strip('"\'')
                if font:
                    fonts_counter[font] += 1

        # Spacings
        for m in _RE_PADDING_MARGIN.finditer(content_no_comments):
            for px_match in _RE_PX_VALUE.finditer(m.group(1)):
                try:
                    spacing_counter[int(float(px_match.group(1)))] += 1
                except ValueError:
                    continue

        # Border radius
        for m in _RE_BORDER_RADIUS.finditer(content_no_comments):
            for px_match in _RE_PX_VALUE.finditer(m.group(1)):
                try:
                    radius_counter[int(float(px_match.group(1)))] += 1
                except ValueError:
                    continue

    # Build palette output
    colors_out: list[dict[str, Any]] = []
    for hex_val, count in colors_counter.most_common(20):
        contexts = color_contexts.get(hex_val, [])
        roles: set[str] = set()
        for ctx in contexts[:10]:
            roles.update(_detect_semantic(ctx))
        colors_out.append({
            "hex": hex_val,
            "occurrences": count,
            "sample_selectors": list(set(contexts))[:5],
            "named_tokens": sorted(roles),
        })

    # Standard spacing scale: keep most common 8 values
    spacings_sorted = [px for px, _ in spacing_counter.most_common(8)]
    spacings_sorted.sort()

    radius_sorted = [px for px, _ in radius_counter.most_common(5)]
    radius_sorted.sort()

    return {
        "schemaVersion": 1,
        "colors": colors_out,
        "fonts": [f for f, _ in fonts_counter.most_common(10)],
        "spacings_px": spacings_sorted,
        "border_radius_px": radius_sorted,
        "css_sources": sorted(set(css_sources)),
    }
