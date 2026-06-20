"""Tests for sdd_reverse.css_palette_extractor — Phase 4 palette aggregation.

Covers :
- parse_css_color (rgb, rgba, alpha=0, malformed, hex unsupported, out-of-range)
- RGB.to_css / RGB.distance
- cluster_colors (single cluster, multi cluster, threshold respected)
- aggregate_palettes (merge multi-source, count occurrences, dedup)
- emit_tokens_css (header, root block, color/font/spacing tokens)
- read_existing_sources_hash (file absent, file with hash, file without hash)
- write_tokens_css (atomic write, idempotence with matching hash, force overwrite)
- aggregate_from_files (real JSON files)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdd_reverse import css_palette_extractor as cpe


# ----------------------------------------------------- parse_css_color


def test_parse_css_color_rgb_basic():
    c = cpe.parse_css_color("rgb(255, 128, 64)")
    assert c is not None
    assert (c.r, c.g, c.b, c.a) == (255, 128, 64, 1.0)


def test_parse_css_color_rgba_with_alpha():
    c = cpe.parse_css_color("rgba(0, 0, 0, 0.5)")
    assert c is not None
    assert c.a == 0.5


def test_parse_css_color_alpha_zero_returns_none():
    """Fully transparent colors are not useful as tokens."""
    assert cpe.parse_css_color("rgba(255, 255, 255, 0)") is None


def test_parse_css_color_malformed_returns_none():
    assert cpe.parse_css_color("not a color") is None


def test_parse_css_color_hex_returns_none():
    """Playwright always returns rgb()/rgba() ; hex not supported."""
    assert cpe.parse_css_color("#ff0000") is None


def test_parse_css_color_out_of_range_returns_none():
    """RGB values must be 0-255."""
    assert cpe.parse_css_color("rgb(999, 0, 0)") is None


def test_parse_css_color_empty_returns_none():
    assert cpe.parse_css_color("") is None


def test_parse_css_color_extra_whitespace_tolerated():
    c = cpe.parse_css_color("rgb(  10 ,  20 , 30 )")
    assert c is not None
    assert (c.r, c.g, c.b) == (10, 20, 30)


# ------------------------------------------------------------ RGB


def test_rgb_to_css_without_alpha():
    assert cpe.RGB(10, 20, 30).to_css() == "rgb(10, 20, 30)"


def test_rgb_to_css_with_alpha():
    assert cpe.RGB(10, 20, 30, 0.5).to_css() == "rgba(10, 20, 30, 0.5)"


def test_rgb_distance_zero_when_equal():
    assert cpe.RGB(10, 20, 30).distance(cpe.RGB(10, 20, 30)) == 0.0


def test_rgb_distance_euclidean():
    # (3, 4, 0) → sqrt(9+16) = 5
    assert cpe.RGB(0, 0, 0).distance(cpe.RGB(3, 4, 0)) == 5.0


def test_rgb_distance_ignores_alpha():
    """Clustering should not split colors only by alpha."""
    a = cpe.RGB(10, 20, 30, 1.0)
    b = cpe.RGB(10, 20, 30, 0.5)
    assert a.distance(b) == 0.0


# ---------------------------------------------------- cluster_colors


def test_cluster_colors_empty_returns_empty():
    assert cpe.cluster_colors([]) == []


def test_cluster_colors_single_color():
    result = cpe.cluster_colors([cpe.RGB(10, 20, 30)])
    assert len(result) == 1
    assert result[0][1] == 1


def test_cluster_colors_groups_close_colors():
    # Two near-identical colors (anti-aliasing scenario)
    colors = [cpe.RGB(255, 255, 255), cpe.RGB(254, 254, 254)]
    clustered = cpe.cluster_colors(colors, threshold=5.0)
    assert len(clustered) == 1
    assert clustered[0][1] == 2  # both folded into 1 cluster


def test_cluster_colors_separates_far_colors():
    colors = [cpe.RGB(255, 0, 0), cpe.RGB(0, 255, 0), cpe.RGB(0, 0, 255)]
    clustered = cpe.cluster_colors(colors, threshold=10.0)
    assert len(clustered) == 3


def test_cluster_colors_sorted_by_size():
    """Most frequent cluster appears first."""
    colors = [
        cpe.RGB(0, 0, 0),  # cluster A
        cpe.RGB(255, 255, 255),  # cluster B
        cpe.RGB(0, 0, 0),  # cluster A again
        cpe.RGB(0, 0, 0),  # cluster A again
    ]
    clustered = cpe.cluster_colors(colors)
    assert clustered[0][1] == 3  # cluster A (most frequent) first
    assert clustered[1][1] == 1


# ------------------------------------------------- aggregate_palettes


def test_aggregate_palettes_empty_returns_empty_aggregated():
    agg = cpe.aggregate_palettes([])
    assert agg.colors == []
    assert agg.backgrounds == []
    assert agg.fonts == []


def test_aggregate_palettes_single_palette():
    palette = {
        "colors": ["rgb(0, 0, 0)", "rgb(255, 255, 255)"],
        "backgrounds": ["rgb(247, 247, 247)"],
        "fonts": ["Arial, sans-serif"],
        "spacings": ["8px", "16px"],
        "fontSizes": ["14px"],
    }
    agg = cpe.aggregate_palettes([palette])
    assert len(agg.colors) == 2
    assert agg.backgrounds[0].to_css() == "rgb(247, 247, 247)"
    assert agg.fonts == ["Arial, sans-serif"]
    assert "8px" in agg.spacings
    assert agg.font_sizes == ["14px"]


def test_aggregate_palettes_counts_occurrences_across_pages():
    """Fonts/spacings most frequent across pages should be retained first."""
    p1 = {"fonts": ["Arial", "Verdana"], "spacings": ["8px"]}
    p2 = {"fonts": ["Arial", "Tahoma"], "spacings": ["8px", "16px"]}
    p3 = {"fonts": ["Arial"], "spacings": ["16px"]}
    agg = cpe.aggregate_palettes([p1, p2, p3])
    # Arial appears 3x, others 1x — Arial first
    assert agg.fonts[0] == "Arial"
    # 8px appears 2x, 16px 2x — both retained
    assert "8px" in agg.spacings
    assert "16px" in agg.spacings


def test_aggregate_palettes_caps_at_max_constants():
    """Verify MAX_COLORS / MAX_FONTS limits applied."""
    # Generate enough distinct colors to overflow MAX_COLORS
    raw_colors = [f"rgb({i*30}, 0, 0)" for i in range(20)]
    palette = {"colors": raw_colors}
    agg = cpe.aggregate_palettes([palette])
    assert len(agg.colors) <= cpe.MAX_COLORS


def test_aggregate_palettes_dedups_close_colors_across_pages():
    p1 = {"colors": ["rgb(255, 255, 255)"]}
    p2 = {"colors": ["rgb(254, 254, 254)"]}  # near-white, should fold
    agg = cpe.aggregate_palettes([p1, p2])
    assert len(agg.colors) == 1


def test_aggregate_palettes_skips_malformed_colors():
    palette = {"colors": ["not-a-color", "rgb(10, 20, 30)", "rgba(0,0,0,0)"]}
    agg = cpe.aggregate_palettes([palette])
    assert len(agg.colors) == 1
    assert agg.colors[0].r == 10


def test_aggregate_palettes_sources_hash_deterministic():
    p1 = {"colors": ["rgb(1, 2, 3)"]}
    a = cpe.aggregate_palettes([p1])
    b = cpe.aggregate_palettes([p1])
    assert a.sources_hash == b.sources_hash


def test_aggregate_palettes_sources_hash_changes_with_input():
    a = cpe.aggregate_palettes([{"colors": ["rgb(1, 2, 3)"]}])
    b = cpe.aggregate_palettes([{"colors": ["rgb(99, 0, 0)"]}])
    assert a.sources_hash != b.sources_hash


# --------------------------------------------------- emit_tokens_css


def test_emit_tokens_css_minimal_palette():
    agg = cpe.AggregatedPalette(sources_hash="abc123")
    css = cpe.emit_tokens_css(agg)
    assert ":root {" in css
    assert "}" in css
    assert "sha256:abc123" in css


def test_emit_tokens_css_full_palette():
    agg = cpe.AggregatedPalette(
        colors=[cpe.RGB(10, 20, 30), cpe.RGB(40, 50, 60)],
        backgrounds=[cpe.RGB(247, 247, 247)],
        fonts=["Arial, sans-serif"],
        spacings=["8px", "16px"],
        font_sizes=["14px"],
        sources_hash="x" * 64,
    )
    css = cpe.emit_tokens_css(agg, project_name="AcmeCRM", extraction_date="2026-06-10T14:00:00Z",
                              routes=["/Default.aspx", "/Login.aspx"])
    assert "AcmeCRM" in css
    assert "2 routes" in css
    assert "--legacy-text: rgb(10, 20, 30);" in css
    assert "--legacy-text-2: rgb(40, 50, 60);" in css
    assert "--legacy-bg: rgb(247, 247, 247);" in css
    assert "--legacy-font: Arial, sans-serif;" in css
    assert "--legacy-spacing-1: 8px;" in css
    assert "--legacy-spacing-2: 16px;" in css
    assert "--legacy-fontsize-1: 14px;" in css


def test_emit_tokens_css_skips_empty_groups():
    """Empty colors/fonts/spacings sections should not produce orphan lines."""
    agg = cpe.AggregatedPalette(
        fonts=["Tahoma"],
        sources_hash="z",
    )
    css = cpe.emit_tokens_css(agg)
    assert "--legacy-text" not in css  # no colors → no text token
    assert "--legacy-bg" not in css
    assert "--legacy-font: Tahoma;" in css


# ----------------------------------------- read_existing_sources_hash


def test_read_existing_sources_hash_file_absent(tmp_path):
    assert cpe.read_existing_sources_hash(tmp_path / "absent.css") is None


def test_read_existing_sources_hash_no_header(tmp_path):
    f = tmp_path / "tokens.css"
    f.write_text(":root { --foo: bar; }\n", encoding="utf-8")
    assert cpe.read_existing_sources_hash(f) is None


def test_read_existing_sources_hash_present(tmp_path):
    f = tmp_path / "tokens.css"
    f.write_text("/* sources-hash: sha256:" + ("a" * 64) + " */\n:root {}\n", encoding="utf-8")
    assert cpe.read_existing_sources_hash(f) == "a" * 64


# --------------------------------------------------- write_tokens_css


def test_write_tokens_css_first_write(tmp_path):
    agg = cpe.AggregatedPalette(
        colors=[cpe.RGB(10, 20, 30)],
        sources_hash="hash_first",
    )
    target = tmp_path / "tokens.css"
    written = cpe.write_tokens_css(agg, target)
    assert written is True
    assert target.is_file()
    assert "sha256:hash_first" in target.read_text(encoding="utf-8")


def test_write_tokens_css_idempotent_skips_when_hash_match(tmp_path):
    # Use a real-looking 64-hex hash (regex in module requires this format)
    same_hash = "a" * 64
    agg = cpe.AggregatedPalette(
        colors=[cpe.RGB(10, 20, 30)],
        sources_hash=same_hash,
    )
    target = tmp_path / "tokens.css"
    cpe.write_tokens_css(agg, target)
    original_mtime = target.stat().st_mtime_ns

    # Second call : same hash → skip
    written = cpe.write_tokens_css(agg, target)
    assert written is False
    assert target.stat().st_mtime_ns == original_mtime


def test_write_tokens_css_overwrites_when_hash_differs(tmp_path):
    target = tmp_path / "tokens.css"
    old_hash = "a" * 64
    new_hash = "b" * 64
    cpe.write_tokens_css(
        cpe.AggregatedPalette(sources_hash=old_hash),
        target,
    )
    cpe.write_tokens_css(
        cpe.AggregatedPalette(sources_hash=new_hash),
        target,
    )
    assert f"sha256:{new_hash}" in target.read_text(encoding="utf-8")


def test_write_tokens_css_force_overwrites_anyway(tmp_path):
    target = tmp_path / "tokens.css"
    agg = cpe.AggregatedPalette(sources_hash="c" * 64)
    cpe.write_tokens_css(agg, target)
    written = cpe.write_tokens_css(agg, target, force=True)
    assert written is True


# ----------------------------------------------- aggregate_from_files


def test_aggregate_from_files_loads_multiple_json(tmp_path):
    (tmp_path / "p1.json").write_text(
        json.dumps({"colors": ["rgb(10, 20, 30)"], "fonts": ["Arial"]}),
        encoding="utf-8",
    )
    (tmp_path / "p2.json").write_text(
        json.dumps({"colors": ["rgb(40, 50, 60)"], "fonts": ["Arial"]}),
        encoding="utf-8",
    )
    agg = cpe.aggregate_from_files([tmp_path / "p1.json", tmp_path / "p2.json"])
    assert len(agg.colors) == 2
    assert agg.fonts == ["Arial"]


def test_aggregate_from_files_skips_missing(tmp_path):
    (tmp_path / "p1.json").write_text(
        json.dumps({"colors": ["rgb(1, 2, 3)"]}), encoding="utf-8"
    )
    # p2 absent : should be skipped silently
    agg = cpe.aggregate_from_files([tmp_path / "p1.json", tmp_path / "p2.json"])
    assert len(agg.colors) == 1


def test_aggregate_from_files_skips_malformed_json(tmp_path):
    (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
    (tmp_path / "good.json").write_text(
        json.dumps({"colors": ["rgb(0, 0, 0)"]}), encoding="utf-8"
    )
    agg = cpe.aggregate_from_files([tmp_path / "bad.json", tmp_path / "good.json"])
    assert len(agg.colors) == 1
