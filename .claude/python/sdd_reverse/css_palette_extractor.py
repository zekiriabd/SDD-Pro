"""SDD_Pro Reverse Engineering Phase 4 — CSS palette extractor (library).

Aggregates 1+ palette JSONs (output of playwright_capture) into a deduplicated
tokens.css per the design doc §4.2 spec.

Algorithm :
- Colors : parse rgb()/rgba() into (r,g,b,a) tuples ; deduplicate ; cluster
  similar colors (Euclidean distance < CLUSTER_THRESHOLD in RGB space) ;
  output up to MAX_COLORS / MAX_BACKGROUNDS / MAX_BORDERS distinct tokens.
- Fonts : count occurrences, output top MAX_FONTS, kept as raw CSS font-family
  stack (Playwright returns "Tahoma, Arial, sans-serif" already concatenated).
- Spacings : count occurrences, output top MAX_SPACINGS distinct values.
- FontSizes : count occurrences, output top MAX_FONT_SIZES distinct values.

Pure Python, no external dependencies (stdlib only). Fully testable.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ----------------------------------------------------------- thresholds


MAX_COLORS = 8       # max --legacy-text-*
MAX_BACKGROUNDS = 5  # max --legacy-bg-*
MAX_FONTS = 3        # max --legacy-font-*
MAX_SPACINGS = 5     # max --legacy-spacing-*
MAX_FONT_SIZES = 4   # max --legacy-fontsize-*

# Two RGB colors with Euclidean distance below this are considered equivalent.
# Range 0-441 (sqrt(3*255²)). 20 = "very close" (anti-aliasing noise).
CLUSTER_THRESHOLD = 20.0


# ------------------------------------------------------------- data types


@dataclass
class RGB:
    """RGB color with optional alpha. Stored as 0-255 ints, alpha 0.0-1.0."""

    r: int
    g: int
    b: int
    a: float = 1.0

    def to_css(self) -> str:
        if self.a < 1.0:
            return f"rgba({self.r}, {self.g}, {self.b}, {self.a:g})"
        return f"rgb({self.r}, {self.g}, {self.b})"

    def distance(self, other: "RGB") -> float:
        # Ignore alpha for clustering — it's a separate visual concern
        dr = self.r - other.r
        dg = self.g - other.g
        db = self.b - other.b
        return (dr * dr + dg * dg + db * db) ** 0.5


@dataclass
class AggregatedPalette:
    """Final deduplicated palette ready for tokens.css emission."""

    colors: list[RGB] = field(default_factory=list)
    backgrounds: list[RGB] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    spacings: list[str] = field(default_factory=list)
    font_sizes: list[str] = field(default_factory=list)
    sources_hash: str = ""


# --------------------------------------------------------- color parsing


_RGB_RE = re.compile(
    r"rgba?\(\s*"
    r"(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})"
    r"(?:\s*,\s*([\d.]+))?\s*\)"
)


def parse_css_color(value: str) -> RGB | None:
    """Parse 'rgb(r, g, b)' or 'rgba(r, g, b, a)' into an RGB instance.

    Returns None on parse failure or transparent colors (a == 0).
    Does NOT handle hex (#rrggbb) — Playwright always returns rgb()/rgba().
    """
    if not value:
        return None
    m = _RGB_RE.match(value.strip())
    if m is None:
        return None
    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
        return None
    a_str = m.group(4)
    a = float(a_str) if a_str is not None else 1.0
    if a == 0.0:
        return None  # fully transparent — not useful as token
    return RGB(r, g, b, a)


# -------------------------------------------------------------- clustering


def cluster_colors(
    colors: list[RGB],
    threshold: float = CLUSTER_THRESHOLD,
) -> list[tuple[RGB, int]]:
    """Group colors within `threshold` Euclidean distance. Return (representative, count).

    Greedy clustering : iterate input, assign to first cluster whose centroid
    is within threshold, else create a new cluster. Representative is the
    first color of each cluster (deterministic for a given input order).
    """
    clusters: list[list[RGB]] = []
    for c in colors:
        placed = False
        for cluster in clusters:
            if cluster[0].distance(c) <= threshold:
                cluster.append(c)
                placed = True
                break
        if not placed:
            clusters.append([c])

    # Sort by cluster size DESC (most frequent colors first)
    clusters.sort(key=lambda cluster: -len(cluster))
    return [(cluster[0], len(cluster)) for cluster in clusters]


# ---------------------------------------------------------- aggregation


def aggregate_palettes(palettes: Iterable[dict]) -> AggregatedPalette:
    """Merge N palette dicts (output of playwright_capture) into one deduplicated palette.

    Each input palette has shape:
        {"colors": [...], "backgrounds": [...], "fonts": [...],
         "spacings": [...], "fontSizes": [...], "elementCount": int}
    """
    all_colors_raw: list[str] = []
    all_bgs_raw: list[str] = []
    fonts_counter: Counter[str] = Counter()
    spacings_counter: Counter[str] = Counter()
    font_sizes_counter: Counter[str] = Counter()

    raw_for_hash: list[str] = []
    for palette in palettes:
        all_colors_raw.extend(palette.get("colors", []))
        all_bgs_raw.extend(palette.get("backgrounds", []))
        for f in palette.get("fonts", []):
            fonts_counter[_normalize_font(f)] += 1
        for s in palette.get("spacings", []):
            spacings_counter[s] += 1
        for fs in palette.get("fontSizes", []):
            font_sizes_counter[fs] += 1
        raw_for_hash.append(json.dumps(palette, sort_keys=True))

    # Parse and dedup colors
    parsed_colors = [c for c in (parse_css_color(s) for s in all_colors_raw) if c is not None]
    parsed_bgs = [c for c in (parse_css_color(s) for s in all_bgs_raw) if c is not None]

    clustered_colors = cluster_colors(parsed_colors)
    clustered_bgs = cluster_colors(parsed_bgs)

    sources_hash = hashlib.sha256("|".join(raw_for_hash).encode("utf-8")).hexdigest()

    return AggregatedPalette(
        colors=[c for c, _ in clustered_colors[:MAX_COLORS]],
        backgrounds=[c for c, _ in clustered_bgs[:MAX_BACKGROUNDS]],
        fonts=[f for f, _ in fonts_counter.most_common(MAX_FONTS)],
        spacings=[s for s, _ in spacings_counter.most_common(MAX_SPACINGS)],
        font_sizes=[fs for fs, _ in font_sizes_counter.most_common(MAX_FONT_SIZES)],
        sources_hash=sources_hash,
    )


def _normalize_font(font_family: str) -> str:
    """Trim whitespace + collapse internal whitespace. Preserve quotes."""
    return " ".join(font_family.split())


# ------------------------------------------------------------- emit CSS


def emit_tokens_css(
    palette: AggregatedPalette,
    project_name: str = "",
    extraction_date: str = "",
    routes: list[str] | None = None,
) -> str:
    """Render the aggregated palette as a CSS file matching design doc §4.2.

    Header comment includes source provenance + sources_hash for idempotence.
    """
    lines: list[str] = []
    header_extra = f" from {project_name}" if project_name else ""
    date_extra = f", {extraction_date}" if extraction_date else ""
    lines.append(f"/* Extracted{header_extra} runtime capture{date_extra} */")
    if routes:
        joined = ", ".join(routes)
        lines.append(f"/* Aggregated from {len(routes)} routes: {joined} */")
    lines.append(f"/* sources-hash: sha256:{palette.sources_hash} */")
    lines.append(":root {")

    # Colors : --legacy-text (primary) + --legacy-text-2, -3, ...
    if palette.colors:
        lines.append(f"  --legacy-text: {palette.colors[0].to_css()};")
        for idx, c in enumerate(palette.colors[1:], start=2):
            lines.append(f"  --legacy-text-{idx}: {c.to_css()};")

    # Backgrounds : --legacy-bg + --legacy-bg-2, -3...
    if palette.backgrounds:
        lines.append(f"  --legacy-bg: {palette.backgrounds[0].to_css()};")
        for idx, c in enumerate(palette.backgrounds[1:], start=2):
            lines.append(f"  --legacy-bg-{idx}: {c.to_css()};")

    # Fonts : --legacy-font + --legacy-font-2 ...
    if palette.fonts:
        lines.append(f"  --legacy-font: {palette.fonts[0]};")
        for idx, f in enumerate(palette.fonts[1:], start=2):
            lines.append(f"  --legacy-font-{idx}: {f};")

    # Spacings : --legacy-spacing-1, -2, ...
    for idx, s in enumerate(palette.spacings, start=1):
        lines.append(f"  --legacy-spacing-{idx}: {s};")

    # Font sizes : --legacy-fontsize-1, -2, ...
    for idx, fs in enumerate(palette.font_sizes, start=1):
        lines.append(f"  --legacy-fontsize-{idx}: {fs};")

    lines.append("}")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------- idempotence


_HASH_LINE_RE = re.compile(r"sources-hash:\s*sha256:([a-f0-9]{64})")


def read_existing_sources_hash(tokens_css_path: Path) -> str | None:
    """Read the sources-hash from an existing tokens.css. None if file absent or no header."""
    if not tokens_css_path.is_file():
        return None
    try:
        content = tokens_css_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _HASH_LINE_RE.search(content)
    return m.group(1) if m else None


def write_tokens_css(
    palette: AggregatedPalette,
    tokens_css_path: Path,
    *,
    project_name: str = "",
    extraction_date: str = "",
    routes: list[str] | None = None,
    force: bool = False,
) -> bool:
    """Write tokens.css atomically. Returns True if written, False if skipped (hash match).

    If `tokens.css` already exists with a matching sources-hash, skip (idempotent).
    Pass force=True to overwrite regardless.
    """
    if not force:
        existing = read_existing_sources_hash(tokens_css_path)
        if existing == palette.sources_hash:
            return False

    css = emit_tokens_css(
        palette,
        project_name=project_name,
        extraction_date=extraction_date,
        routes=routes,
    )

    tokens_css_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tokens_css_path.with_suffix(tokens_css_path.suffix + ".sddtmp")
    tmp.write_text(css, encoding="utf-8")
    tmp.replace(tokens_css_path)
    return True


# --------------------------------------------------------- entry helper


def aggregate_from_files(palette_json_paths: list[Path]) -> AggregatedPalette:
    """Load N palette JSON files and aggregate them.

    Skips files that don't exist or fail to parse (logs to stderr would be in CLI).
    """
    palettes: list[dict] = []
    for p in palette_json_paths:
        if not p.is_file():
            continue
        try:
            palettes.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return aggregate_palettes(palettes)
