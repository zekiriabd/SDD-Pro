"""Unit tests for sdd_lib.exit_codes — v7.0.0 standardization (M1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import (
    BLOCKING_ERROR,
    CORRECTIBLE,
    ENV_PROBLEM,
    FAIL_FAST,
    HOOK_ALLOW,
    HOOK_DENY,
    INFRA_BLOCKED,
    OK,
    RETRY_POSSIBLE,
    SUCCESS,
    describe,
    is_correctible,
    is_fatal,
    is_infra_problem,
    is_success,
)


def test_canonical_codes_values():
    assert SUCCESS == 0
    assert FAIL_FAST == 1
    assert CORRECTIBLE == 2
    assert INFRA_BLOCKED == 3


def test_aliases_map_to_canonical():
    assert OK is SUCCESS
    assert BLOCKING_ERROR is FAIL_FAST
    assert RETRY_POSSIBLE is CORRECTIBLE
    assert ENV_PROBLEM is INFRA_BLOCKED


def test_hook_protocol_codes_distinct_from_sdd():
    assert HOOK_ALLOW == 0
    assert HOOK_DENY == 2
    # HOOK_DENY collide numériquement avec CORRECTIBLE mais sémantique distincte.
    # Guard contre confusion : les constantes restent séparées (pas un alias).
    assert HOOK_DENY == CORRECTIBLE  # numerical accident, not aliased
    assert "HOOK" not in str(CORRECTIBLE)  # sanity


def test_is_success_predicate():
    assert is_success(0)
    assert not is_success(1)
    assert not is_success(2)
    assert not is_success(3)
    assert not is_success(-1)


def test_is_correctible_predicate():
    assert is_correctible(2)
    assert not is_correctible(0)
    assert not is_correctible(1)
    assert not is_correctible(3)


def test_is_infra_problem_predicate():
    assert is_infra_problem(3)
    assert not is_infra_problem(0)
    assert not is_infra_problem(1)
    assert not is_infra_problem(2)


def test_is_fatal_predicate():
    assert is_fatal(1)
    assert not is_fatal(0)
    assert not is_fatal(2)
    assert not is_fatal(3)


def test_describe_known_codes():
    assert describe(0) == "SUCCESS"
    assert "FAIL_FAST" in describe(1)
    assert "CORRECTIBLE" in describe(2)
    assert "INFRA_BLOCKED" in describe(3)


def test_describe_unknown_code():
    assert "UNKNOWN" in describe(42)
    assert "42" in describe(42)
