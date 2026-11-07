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


def test_mixed_case_shell_var_resolved(monkeypatch, tmp_path):
    """Windows : `os.environ` upper-cases names ; a mixed-case placeholder
    (`${FrontendLocalPort}`, the stack.md convention) must still resolve from
    the shell (regression 2026-11-07 : it only ever resolved from a dotenv)."""
    from sdd_lib.env_placeholders import resolve_config

    monkeypatch.setenv("SddMixedCasePort", "5173")
    (tmp_path / "workspace").mkdir()  # isolate the dotenv lookup from the repo
    out = resolve_config({"Port": "${SddMixedCasePort}"}, tmp_path, warn_unresolved=False)
    assert out == {"Port": "5173"}
