"""feat_structure_spec.py — Shared FEAT structure contracts (ADV-14).

This module is the LOCAL source of truth for the structural checks shared
between SDD_Pro's `validate_readiness.py` (standard) and the reverse
workflow's `validate_reverse_feat.py`.

Strategy: keep the structural invariants here (regex, section order, IDs)
so that both validators converge on them. Parity tests in
test_validators_parity.py grep validate_readiness.py for drift.

Public:
    REQUIRED_FRONTMATTER_KEYS_REVERSE: set[str]
    CONFIDENCE_ENUM: frozenset[str]
    REQUIRED_SECTIONS: list[str]                  # ordered
    ID_PATTERNS: dict[section_name, re.Pattern]   # SFD-N, FD-N, ...
    AC_GIVEN_WHEN_THEN_RE: re.Pattern
    EVIDENCE_COMMENT_RE: re.Pattern
    CONFIDENCE_COMMENT_RE: re.Pattern
    REVERSE_GATE_RE: re.Pattern
"""

from __future__ import annotations

import re

# Frontmatter contract for reverse-generated FEATs
REQUIRED_FRONTMATTER_KEYS_REVERSE = frozenset({
    "generated-by",
    "legacy-sources",
    "confidence",
    "extraction-date",
    "language-detected",
    "source-unit",
})

CONFIDENCE_ENUM = frozenset({"high", "medium", "low"})

# Required sections in fixed order
REQUIRED_SECTIONS = [
    "## Actors",
    "## Functional Needs",
    "## Functional Deliverables",
    "## Business Rules",
    "## Acceptance Criteria",
    "## Project Config",
]

# Stable ID patterns
ID_PATTERNS = {
    "## Functional Needs": re.compile(r"^\*\*?SFD-(\d+)\*?\*?", re.MULTILINE),
    "## Functional Deliverables": re.compile(r"^\*\*?FD-(\d+)\*?\*?", re.MULTILINE),
    "## Business Rules": re.compile(r"^\*\*?BR-(\d+)\*?\*?", re.MULTILINE),
    "## Acceptance Criteria": re.compile(r"^\*\*?AC-(\d+)\*?\*?", re.MULTILINE),
}

# AC: Given X, when Y, then Z (single-line or multi-line tolerated)
AC_GIVEN_WHEN_THEN_RE = re.compile(
    r"\bGiven\s+.+?,?\s+when\s+.+?,?\s+then\s+.+?[.\n]",
    re.IGNORECASE | re.DOTALL,
)

# Evidence comment: <!-- evidence: path/file.ext:Lstart-Lend -->
EVIDENCE_COMMENT_RE = re.compile(
    r"<!--\s*evidence:\s*[^\s>]+?:\d+(?:-\d+)?\s*-->",
)

# Confidence comment: <!-- confidence: high|medium|low -->
CONFIDENCE_COMMENT_RE = re.compile(
    r"<!--\s*confidence:\s*(high|medium|low)\s*-->",
)

# REVERSE-GATE comment (ADV-15 + ADV-22)
REVERSE_GATE_RE = re.compile(
    r"<!--\s*REVERSE-GATE:\s*"
    r"confidence=(high|medium|low)\s*;\s*"
    r"allow-sdd-full=(true|false)\s*"
    r"(?:;\s*reason=([^>]*?))?\s*-->",
)


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML-like frontmatter from a markdown file.

    Returns (frontmatter_dict, body_after_frontmatter).
    If no frontmatter, returns ({}, content).
    Simple parser — does not handle nested YAML, only flat key: value lines.
    """
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body


def section_order_violations(content: str) -> list[str]:
    """Return list of error messages if sections are missing or out of order."""
    errors: list[str] = []
    positions: list[tuple[int, str]] = []
    for section in REQUIRED_SECTIONS:
        idx = content.find(f"\n{section}")
        # Also accept at start of body (no leading \n)
        if idx == -1 and content.startswith(section):
            idx = 0
        if idx == -1:
            errors.append(f"Missing section: {section}")
        else:
            positions.append((idx, section))
    # Check order
    sorted_by_pos = sorted(positions, key=lambda t: t[0])
    expected_order = [s for s in REQUIRED_SECTIONS if any(p[1] == s for p in positions)]
    actual_order = [s for _, s in sorted_by_pos]
    if expected_order != actual_order:
        errors.append(
            f"Section order incorrect: expected {expected_order}, got {actual_order}"
        )
    return errors


def ids_are_stable(content: str, section: str) -> tuple[bool, str]:
    """Check that IDs in a section are non-decreasing (no reordering).

    Trous tolérés (e.g. SFD-1, SFD-3, SFD-4 — SFD-2 may have been removed).
    """
    pat = ID_PATTERNS.get(section)
    if not pat:
        return True, ""
    section_start = content.find(section)
    if section_start == -1:
        return True, ""
    next_section_start = -1
    for other in REQUIRED_SECTIONS:
        if other == section:
            continue
        idx = content.find(f"\n{other}", section_start + 1)
        if idx != -1 and (next_section_start == -1 or idx < next_section_start):
            next_section_start = idx
    section_body = content[section_start:next_section_start] if next_section_start != -1 else content[section_start:]
    nums = [int(m.group(1)) for m in pat.finditer(section_body)]
    if not nums:
        return True, ""
    if nums != sorted(nums):
        return False, f"IDs reordered in {section}: {nums}"
    return True, ""
