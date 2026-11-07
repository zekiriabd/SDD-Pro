"""env_placeholders n'expanse plus que `${VAR}` (audit sécurité 2026-11).

La forme nue `$VAR` mangeait les `$` littéraux des valeurs (mots de passe,
regex) et produisait des WARN [ENV_MISSING] citant un fragment du secret.
"""
from __future__ import annotations

from sdd_lib.env_placeholders import resolve_value


def test_braced_placeholder_resolved():
    assert resolve_value("${A}-x", {"A": "1"}, set()) == "1-x"


def test_bare_dollar_left_literal_and_not_reported():
    missing: set[str] = set()
    assert resolve_value("pa$word1", {"word1": "LEAK"}, missing) == "pa$word1"
    assert missing == set()


def test_unresolved_braced_is_reported():
    missing: set[str] = set()
    assert resolve_value("${NOPE}", {}, missing) == "${NOPE}"
    assert missing == {"NOPE"}
