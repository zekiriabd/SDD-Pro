"""Drift gate: per-agent error-class digests must match the generator output.

Audit 2026-06-12 (block 5) — `sync_error_class_digests.py` slices
`error-classification.md` into small per-agent digests that ~12 agents load
instead of the full ~40 KB file. If the source taxonomy changes and the
digests aren't regenerated, agents would read stale error tables. This test
runs the generator in `--check` mode (exit 1 on any drift), mirroring the
`sync_stack_md` anti-drift discipline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_admin import sync_error_class_digests as gen  # noqa: E402


def test_digests_in_sync_with_source():
    rc = gen.main(["--check"])
    assert rc == 0, (
        "error-class digests are stale vs error-classification.md — "
        "run: python .sdd/python/sdd_admin/sync_error_class_digests.py"
    )


def test_every_mapped_agent_has_a_digest_file():
    for agent in gen.AGENT_FAMILIES:
        p = gen._OUT_DIR / f"error-classification.{agent}.md"
        assert p.is_file(), f"missing digest for {agent}: {p}"


def test_quickref_present_in_every_digest():
    """§0 quick-ref (full 16-family map) MUST be in every slice — no blind spots."""
    for agent in gen.AGENT_FAMILIES:
        text = (gen._OUT_DIR / f"error-classification.{agent}.md").read_text(encoding="utf-8")
        assert "## 0. Quick reference" in text, f"{agent} digest lost the §0 quick-ref"
        assert "## 2. Format obligatoire" in text, f"{agent} digest lost the ERROR format"
