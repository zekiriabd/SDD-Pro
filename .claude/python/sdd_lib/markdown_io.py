"""Canonical markdown I/O helpers — SSoT for frontmatter + section parsing.

v7.0.0-alpha (audit CRIT-3) : consolidates 3 `parse_frontmatter` and
5 `extract_section`/`section_body` implementations previously scattered
across `validate_plan.py`, `ingest_plans.py`, `preflight.py`,
`validate_semantic.py`, `project_config.py`, `ingest_feats_us.py`
(and the now-retired `compact_front_plans.py`). Before this module,
each site rolled its own regex with subtle divergences
(e.g. `(?=^##\\s|\\Z)` vs `(?=^##\\s+|\\Z)`) — indistinguishable on
canonical inputs but a latent drift risk.

Out of scope (kept local, too specialized) :
  - `index_adrs.parse_adr`        — ADR-specific (H1, Status, Phase, date)
  - `migrate_us_v1_to_v2`         — write/transform, not parse
  - `ingest_feats_us.parse_us`    — Status/AC count regex (bespoke)
"""
from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Frontmatter (YAML-ish key:value between `---` fences at the top of the file)
# ---------------------------------------------------------------------------
# Match `---\\n…\\n---\\n` at the very start. The body returned is the text
# AFTER the closing fence (leading newline preserved). Lines starting with
# `#` inside the frontmatter are treated as YAML comments and skipped.
_FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)^---\s*\r?\n", re.DOTALL | re.MULTILINE)
_FRONTMATTER_KV_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_\-]*)\s*:\s*(.*?)\s*$")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    """Parse YAML-ish frontmatter from `text` and return (kv_dict, body) or None.

    Returns :
        ``(frontmatter_dict, body_after_closing_fence)`` when the document
        opens with a ``---`` fenced block, otherwise ``None``.

    Behaviour :
      - Keys must match `^[A-Za-z][A-Za-z0-9_-]*$` (typed YAML scalar keys).
      - Values are stripped of surrounding whitespace and matching outer
        quotes (`"` or `'`).
      - Lines that are blank or start with `#` are skipped (YAML comments).
      - Nested / multiline YAML structures are not supported (flat keys
        only). Multiline values get truncated at the newline — matches
        the v6.x behaviour of all previous ad-hoc implementations.

    Idempotence : calling twice on the same input returns equal dicts.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    block = m.group(1)
    body = text[m.end():]
    out: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m2 = _FRONTMATTER_KV_RE.match(line)
        if not m2:
            continue
        key, raw = m2.group(1), m2.group(2)
        out[key] = raw.strip().strip('"').strip("'")
    return out, body


def extract_frontmatter_raw(text: str) -> str:
    """Return the raw frontmatter block including both `---` fences, or ``""``.

    Preserves the source bytes verbatim (newlines, ordering, comments) —
    used by tools that need to re-emit the frontmatter unchanged.
    """
    m = _FRONTMATTER_RE.match(text)
    return m.group(0) if m else ""


# ---------------------------------------------------------------------------
# Section extraction (`## Heading` … until next `## ` or EOF)
# ---------------------------------------------------------------------------
# The canonical regex uses `\\s+` after `##` for the heading match (matches
# at least one whitespace char) and `\\s` in the trailing lookahead (single
# whitespace char suffices for boundary detection). This is functionally
# equivalent to the divergent variants found in the previous sites — the
# `+` quantifier only matters when capturing the whitespace, not when
# detecting a section boundary.
_SECTION_RE_TMPL = r"^##\s+{heading}\s*\r?\n(.*?)(?=^##\s|\Z)"


def section_body(text: str, heading: str) -> str | None:
    """Return the body between ``## {heading}`` and the next ``##`` (or EOF).

    The heading match is regex-escaped, then internal whitespace is
    relaxed so callers can pass either ``"Project Config"`` or
    ``"Project   Config"`` and still match a slightly reformatted source.
    Returns ``None`` when no such section is present.

    The body is returned verbatim (no `.strip()`) — callers that want a
    stripped result should call `.strip()` themselves. This preserves
    backward compat with the previous `project_config.section_body`
    behaviour, while `validate_plan.extract_section_body` (which used
    `.strip()`) is wrapped at the call site.
    """
    pattern = _SECTION_RE_TMPL.format(
        heading=re.escape(heading).replace(r"\ ", r"\s+")
    )
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else None


def section_body_stripped(text: str, heading: str) -> str | None:
    """Like `section_body` but `.strip()`-ed (None preserved when absent).

    Convenience for callers that previously used `extract_section_body`
    in `validate_plan.py`.
    """
    body = section_body(text, heading)
    return body.strip() if body is not None else None


# ---------------------------------------------------------------------------
# US file helpers (frontmatter + body + ACs)
# ---------------------------------------------------------------------------
# Most callers parse a US file to extract `Status:`, ACs, and `Covers:`.
# This wrapper centralizes file I/O + frontmatter parsing + body retrieval.
_AC_LINE_RE = re.compile(r"^\s*[-*]?\s*AC-(\d+)\b", re.MULTILINE)
_COVERS_RE = re.compile(r"^Covers:\s*\n(.*?)(?=^[A-Z][a-z]|\Z)", re.DOTALL | re.MULTILINE)
_COVERS_ID_RE = re.compile(r"\b(?:SFD|BR|AC|FD)-\d+")


def parse_us_file(path: Path) -> dict:
    """Parse a User Story markdown file into a normalized dict.

    Output schema :
        {
          "us_id":       "{n}-{m}",
          "n":           int,
          "m":           int,
          "name":        str,                # remainder of basename
          "status":      str,                # "Draft" if not declared
          "ac_ids":      list[str],          # sorted, deduped (e.g. ["AC-1", "AC-3"])
          "covers":      list[str],          # sorted, deduped union of SFD/BR/AC/FD refs
          "frontmatter": dict[str, str],     # empty when no `---` block
          "body":        str,                # everything after the frontmatter
          "raw":         str,                # whole file content
        }

    Returns an empty dict ``{}`` when the filename does not match the
    canonical `{n}-{m}-{Name}.md` pattern or when the file is unreadable.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}

    stem = path.stem
    m = re.match(r"^(\d+)-(\d+)-(.+)$", stem)
    if not m:
        return {}
    n, mm = int(m.group(1)), int(m.group(2))
    name = m.group(3)

    fm_result = parse_frontmatter(raw)
    if fm_result is None:
        frontmatter, body = {}, raw
    else:
        frontmatter, body = fm_result

    # Status: line — frontmatter wins, else `Status: X` line in body, else "Draft".
    status = frontmatter.get("Status")
    if status is None:
        status_match = re.search(r"^Status:\s*(\w+)", body, re.MULTILINE)
        status = status_match.group(1) if status_match else "Draft"

    ac_ids = sorted({f"AC-{i}" for i in _AC_LINE_RE.findall(raw)}, key=_ac_sort_key)

    covers_block = _COVERS_RE.search(raw)
    covers: list[str] = []
    if covers_block:
        covers = sorted(set(_COVERS_ID_RE.findall(covers_block.group(1))))

    return {
        "us_id":       f"{n}-{mm}",
        "n":           n,
        "m":           mm,
        "name":        name,
        "status":      status,
        "ac_ids":      ac_ids,
        "covers":      covers,
        "frontmatter": frontmatter,
        "body":        body,
        "raw":         raw,
    }


def _ac_sort_key(ac_id: str) -> int:
    """Numeric sort of ``AC-N`` strings."""
    try:
        return int(ac_id.split("-", 1)[1])
    except (IndexError, ValueError):
        return 0
