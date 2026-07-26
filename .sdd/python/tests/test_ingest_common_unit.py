"""Unit tests for sdd_lib.ingest_common (audit S3 2026-07-26).

Verrouille les 4 helpers extraits de `ingest_axe.py` + `ingest_lighthouse.py`
dans un module partagé, pour empêcher toute divergence future entre les
2 scripts qui les consomment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

from sdd_lib.ingest_common import (  # noqa: E402
    DEFAULT_THRESHOLD,
    SEVERITY_RANK,
    compute_verdict,
    emit_error_block,
)


pytestmark = pytest.mark.smoke


# --- SEVERITY_RANK ---------------------------------------------------------


def test_severity_rank_has_4_ordinals() -> None:
    assert set(SEVERITY_RANK) == {"critical", "serious", "moderate", "minor"}


def test_severity_rank_is_strict_desc() -> None:
    """critical > serious > moderate > minor (strict monotone)."""
    ordered = ["critical", "serious", "moderate", "minor"]
    ranks = [SEVERITY_RANK[k] for k in ordered]
    assert ranks == sorted(ranks, reverse=True)
    assert ranks == [4, 3, 2, 1]


def test_default_threshold_is_serious() -> None:
    """Aligned with legacy A11yFailOn / PerfFailOn defaults."""
    assert DEFAULT_THRESHOLD == "serious"
    assert DEFAULT_THRESHOLD in SEVERITY_RANK


# --- compute_verdict -------------------------------------------------------


def test_compute_verdict_empty_is_green() -> None:
    assert compute_verdict([], "serious") == "green"


def test_compute_verdict_all_below_threshold_is_warn() -> None:
    issues = [{"severity": "moderate"}, {"severity": "minor"}]
    assert compute_verdict(issues, "serious") == "warn"


def test_compute_verdict_one_at_threshold_is_red() -> None:
    issues = [{"severity": "moderate"}, {"severity": "serious"}]
    assert compute_verdict(issues, "serious") == "red"


def test_compute_verdict_above_threshold_is_red() -> None:
    issues = [{"severity": "critical"}]
    assert compute_verdict(issues, "moderate") == "red"


def test_compute_verdict_unknown_severity_defaults_moderate() -> None:
    """Unknown severity → treated as moderate (bias to warn, not red)."""
    # threshold=critical, moderate < critical → warn (issue present, below)
    issues = [{"severity": "unknown-value"}]
    assert compute_verdict(issues, "critical") == "warn"


def test_compute_verdict_missing_severity_defaults_moderate() -> None:
    issues = [{"other_key": "foo"}]  # no severity key
    assert compute_verdict(issues, "serious") == "warn"


def test_compute_verdict_unknown_threshold_falls_back_to_default() -> None:
    """Unknown threshold → falls back to DEFAULT_THRESHOLD (serious)."""
    issues = [{"severity": "serious"}]
    # Would be "red" against DEFAULT_THRESHOLD=serious
    assert compute_verdict(issues, "totally-invalid") == "red"


def test_compute_verdict_case_insensitive_severity() -> None:
    issues = [{"severity": "CRITICAL"}]
    assert compute_verdict(issues, "serious") == "red"


# --- emit_error_block ------------------------------------------------------


def test_emit_error_block_writes_3_lines_and_returns_code(capsys) -> None:
    code = emit_error_block(
        "test failure", "[TEST_CLASS] detail", "fix action", code=42,
    )
    captured = capsys.readouterr()
    assert code == 42
    assert captured.err.splitlines() == [
        "ERROR: test failure",
        "CAUSE: [TEST_CLASS] detail",
        "FIX: fix action",
    ]
    assert captured.out == ""  # never touch stdout


def test_emit_error_block_returns_verbatim_code(capsys) -> None:
    for expected in (0, 1, 2, 3, 4, 99):
        assert emit_error_block("e", "c", "f", code=expected) == expected


# --- SSoT parity : axe + lighthouse consume the shared instances -----------


def test_axe_module_imports_from_ingest_common() -> None:
    """Anti-regression: ingest_axe MUST reference sdd_lib.ingest_common."""
    from sdd_scripts import ingest_axe  # noqa: F401
    assert ingest_axe.SEVERITY_RANK is SEVERITY_RANK
    assert ingest_axe.DEFAULT_THRESHOLD == DEFAULT_THRESHOLD
    assert ingest_axe.compute_verdict is compute_verdict
    assert ingest_axe._err is emit_error_block


def test_lighthouse_module_imports_from_ingest_common() -> None:
    """Anti-regression: ingest_lighthouse MUST reference sdd_lib.ingest_common."""
    from sdd_scripts import ingest_lighthouse  # noqa: F401
    assert ingest_lighthouse.SEVERITY_RANK is SEVERITY_RANK
    assert ingest_lighthouse.DEFAULT_THRESHOLD == DEFAULT_THRESHOLD
    assert ingest_lighthouse.compute_verdict is compute_verdict
    assert ingest_lighthouse._err is emit_error_block
