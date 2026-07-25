"""Parse `.claude/loader.yml` to extract reads/writes per agent.

Hand-rolled YAML parser limited to the loader.yml structure (avoids PyYAML dep).

> v7.0.0-alpha (audit MIN-8, 2026-06-04) — a second hand-rolled YAML
> mini-parser exists at `sdd_lib/layered_config._parse_yaml_minimal`
> (for `## Project Config` blocks). The two could be merged into a
> shared `sdd_lib/yaml_minimal.py` but the structures are different
> enough (loader.yml = nested per-agent lists with inline-flow dicts ;
> project_config = flat scalar key:value) that the merge would add
> complexity without behavior gain. Decision : keep both ; if a third
> YAML site is ever added, extract then.

Format expected:

    agent_name:
      reads:
        - path/one                                            # scalar form
        - path/two   # comment
        - { path: path/three, cache_layer: stable }           # dict form (v7.0.0+)
      writes:
        - path/four
      forbidden_reads:
        - path/five

Both scalar and inline-dict-flow forms are supported on the same list.
For dict entries the value of `path:` is extracted; other keys
(`cache_layer`, etc.) are ignored by this parser (they are honored by
downstream cache-strategy tooling, cf. docs/cache-strategy.md).

Fixed 2026-05-20 (audit P0) : previous regex returned the full literal
`{ path: ..., cache_layer: ... }` as a single string, causing callers
that did `Path(item)` or glob expansion to silently lose those entries.
"""
from __future__ import annotations

import re
from pathlib import Path

from sdd_lib.paths import repo_root

_AGENT_RE = re.compile(r"^([a-z][a-z-]*):\s*$")
_SECTION_RE = re.compile(r"^\s{2}([a-zA-Z_]+):\s*$")
_ITEM_RE = re.compile(r"^\s{4}-\s*(.+?)\s*(?:#.*)?$")
# Inline-flow dict (YAML compact style) : { path: VALUE, cache_layer: X, ... }
# Extracts the `path:` value. The VALUE may contain SDD_Pro placeholders
# like `{n}`, `{m}`, `{Project}` (so `}` inside a path is NOT a terminator).
# Termination is on `, <key>:` (next dict key) or `}` at end-of-string.
_DICT_PATH_RE = re.compile(
    r"\bpath\s*:\s*['\"]?(.+?)['\"]?\s*(?:,\s*[a-z_]+\s*:|\}\s*$)"
)
# Extract `cache_layer: <value>` from inline-flow dict (audit C1, 2026-06-06).
_DICT_CACHE_LAYER_RE = re.compile(
    r"\bcache_layer\s*:\s*['\"]?([a-z_-]+)['\"]?"
)


def loader_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".claude" / "loader.yml"


def parse_agent_section(
    agent_name: str,
    section: str = "reads",
    root: Path | None = None,
) -> list[str]:
    """Extract list items from `agent: -> section: -> - item` in loader.yml.

    Args:
        agent_name: e.g. "po", "arch", "dev-backend"
        section: "reads", "writes", "forbidden_reads", etc.

    Returns:
        List of unquoted, comment-stripped strings (may be empty).
    """
    path = loader_path(root)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    items: list[str] = []
    in_agent = False
    in_section = False

    for line in text.splitlines():
        agent_match = _AGENT_RE.match(line)
        if agent_match:
            in_agent = agent_match.group(1) == agent_name
            in_section = False
            continue

        if not in_agent:
            continue

        section_match = _SECTION_RE.match(line)
        if section_match:
            in_section = section_match.group(1) == section
            continue

        if in_section:
            item_match = _ITEM_RE.match(line)
            if item_match:
                raw = item_match.group(1).strip()
                # Inline-flow dict form (v7.0.0+) : extract `path:` value.
                if raw.startswith("{"):
                    dict_match = _DICT_PATH_RE.search(raw)
                    if dict_match is None:
                        continue  # malformed dict entry — skip silently
                    raw = dict_match.group(1).strip()
                # Strip outer quotes (scalar form may be quoted)
                raw = raw.strip('"').strip("'").strip()
                if raw and not raw.startswith("#"):
                    items.append(raw)

    return items


# ---------------------------------------------------------------------------
# Cache annotations extractor (audit C1, 2026-06-06)
# ---------------------------------------------------------------------------
# Returns the (path, cache_layer) tuples for an agent's `reads:` section.
# v7.0.0 only stores annotations in loader.yml ; v7.1 will consume them to
# place `cache_control: ephemeral` markers on Anthropic API calls. This
# helper is the stable contract between the two versions.

#: Canonical cache layers (output-protocol cache_layer column).
CACHE_LAYERS = ("stable", "semi", "volatile")

#: Default layer when annotation is missing — treated as "volatile" so we
#: never accidentally cache a per-US file.
DEFAULT_CACHE_LAYER = "volatile"


def parse_agent_cache_annotations(
    agent_name: str,
    section: str = "reads",
    root: Path | None = None,
) -> list[dict[str, str]]:
    """Return [{path, cache_layer}, ...] for an agent's reads section.

    Scalar form entries (no annotation) default to `cache_layer=volatile`.
    Inline-flow dict entries honor whatever `cache_layer:` value is set.
    Unknown layer values are normalized to `volatile` (defensive).

    Used by `sdd_admin/cache_manifest.py --agent {id}` to emit a JSON
    manifest consumed by the harness in v7.1 to wire `cache_control`
    markers on Anthropic API requests.
    """
    path = loader_path(root)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    out: list[dict[str, str]] = []
    in_agent = False
    in_section = False

    for line in text.splitlines():
        agent_match = _AGENT_RE.match(line)
        if agent_match:
            in_agent = agent_match.group(1) == agent_name
            in_section = False
            continue
        if not in_agent:
            continue
        section_match = _SECTION_RE.match(line)
        if section_match:
            in_section = section_match.group(1) == section
            continue
        if not in_section:
            continue
        item_match = _ITEM_RE.match(line)
        if not item_match:
            continue
        raw = item_match.group(1).strip()
        layer = DEFAULT_CACHE_LAYER
        if raw.startswith("{"):
            dict_match = _DICT_PATH_RE.search(raw)
            if dict_match is None:
                continue
            path_str = dict_match.group(1).strip()
            layer_match = _DICT_CACHE_LAYER_RE.search(raw)
            if layer_match:
                cand = layer_match.group(1).lower()
                layer = cand if cand in CACHE_LAYERS else DEFAULT_CACHE_LAYER
        else:
            path_str = raw
        path_str = path_str.strip('"').strip("'").strip()
        if not path_str or path_str.startswith("#"):
            continue
        out.append({"path": path_str, "cache_layer": layer})

    return out
