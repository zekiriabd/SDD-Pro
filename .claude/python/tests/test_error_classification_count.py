"""Enforcement test for `error-classification.md §0` quick-ref count.

Audit CTO 2026-06-07 — the §0 intro stated "151 classes" while the sum of
the quick-ref table actually totaled 163. Drift went undetected for ~6
months because no test pinned the relation `intro count == sum(table)`.

This test:
  1. Parses the intro `> **Note granularité ... : NNN classes` line.
  2. Parses the quick-ref §0 table column "Classes".
  3. Asserts intro_count == sum(table_classes).
  4. Asserts the table has exactly 16 rows (the documented family count).

Smoke-tagged: framework_smoke `-m smoke` runs this, gating any future
drift via the Stop hook / CI.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Smoke marker — count drift is a load-bearing communication metric.
pytestmark = pytest.mark.smoke


REPO_ROOT = Path(__file__).resolve().parents[3]
EC_PATH = REPO_ROOT / ".claude" / "rules" / "error-classification.md"


def _read_doc() -> str:
    return EC_PATH.read_text(encoding="utf-8", errors="replace")


def _parse_intro_count(text: str) -> int:
    """Extract the integer from the `> **Note granularité ...** : NNN classes` intro line."""
    m = re.search(r"\*\*Note granularit[^*]*\*\*[^:]*:\s*\*\*?(\d+)\s+classes\*\*?", text)
    assert m, "Could not locate '**NNN classes**' marker in error-classification.md intro"
    return int(m.group(1))


def _parse_header_count(text: str) -> int:
    """Extract the integer from the `## 0. Quick reference — 16 familles (NNN classes)` header."""
    m = re.search(r"##\s*0\.\s*Quick reference[^(]*\((\d+)\s+classes\)", text)
    assert m, "Could not locate '## 0. Quick reference (NNN classes)' header"
    return int(m.group(1))


def _parse_table_sum(text: str) -> tuple[int, int]:
    """Sum the 'Classes' column of the §0 quick-ref table.

    Returns (sum, n_rows).

    Table lines look like:
        | §1.1 | **Runtime** (...) | 8 | tous | STOP |

    We grep rows starting with `| §` then extract the 3rd cell.
    """
    rows = [line for line in text.splitlines() if line.lstrip().startswith("| §")]
    total = 0
    for row in rows:
        cells = [c.strip() for c in row.split("|")]
        # cells = ['', '§1.1', '**Runtime** ...', '8', 'tous', 'STOP', '']
        if len(cells) < 4:
            continue
        try:
            total += int(cells[3])
        except ValueError:
            continue
    return total, len(rows)


def test_quickref_intro_matches_table_sum():
    text = _read_doc()
    intro_count = _parse_intro_count(text)
    table_sum, _n_rows = _parse_table_sum(text)
    assert intro_count == table_sum, (
        f"Drift: intro says {intro_count} classes but §0 table sum = {table_sum}. "
        f"Update the intro count OR the table cells to reconcile."
    )


def test_quickref_header_matches_table_sum():
    text = _read_doc()
    header_count = _parse_header_count(text)
    table_sum, _n_rows = _parse_table_sum(text)
    assert header_count == table_sum, (
        f"Drift: header says {header_count} classes but §0 table sum = {table_sum}."
    )


def test_quickref_table_has_16_families():
    text = _read_doc()
    _total, n_rows = _parse_table_sum(text)
    assert n_rows == 16, (
        f"Drift: §0 quick-ref table has {n_rows} rows, expected 16 (the documented family count). "
        f"If a family was added/removed, update both the row count AND the intro/header."
    )


def test_intro_and_header_agree():
    text = _read_doc()
    intro_count = _parse_intro_count(text)
    header_count = _parse_header_count(text)
    assert intro_count == header_count, (
        f"Drift: intro says {intro_count} classes but §0 header says {header_count}."
    )
