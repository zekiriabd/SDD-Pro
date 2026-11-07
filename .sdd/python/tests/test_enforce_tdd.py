"""test_enforce_tdd.py — couverture du hook PreToolUse enforce_tdd (audit 2026-06-11).

L'enforcer de l'invariant `tdd-test-first-no-prod-code-without-failing-test`
(INVARIANTS.yml) n'avait AUCUN test pytest — régression silencieuse possible
sur le seul gate TDD du framework. Couvre : résolution de mode (env/CI),
détection prod-path, détection nouveau symbole par langage, et main()
end-to-end (payload hook monkeypatché).
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

mod = importlib.import_module("sdd_hooks.enforce_tdd")

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402


# ---------------------------------------------------------------------------
# _resolve_mode
# ---------------------------------------------------------------------------

def test_mode_env_explicit_wins(monkeypatch):
    monkeypatch.setenv("SDD_TDD_MODE", "strict")
    assert mod._resolve_mode() == "strict"
    monkeypatch.setenv("SDD_TDD_MODE", "off")
    assert mod._resolve_mode() == "off"


# Décision Tech Lead 2026-11-07 : le TDD ne bloque JAMAIS le dev par défaut
# (backend → frontend → tests écrits par qa APRÈS). CoverageMin < 100 → off ;
# CoverageMin = 100 → warn (signal, la QA tranche). strict = opt-in explicite.

@pytest.mark.parametrize("cov", [0, 50, 80, 99])
def test_mode_default_off_when_coverage_below_100(monkeypatch, cov):
    monkeypatch.delenv("SDD_TDD_MODE", raising=False)
    monkeypatch.setattr(mod, "_coverage_min", lambda: cov)
    assert mod._resolve_mode() == "off"


def test_mode_default_warn_when_coverage_100(monkeypatch):
    monkeypatch.delenv("SDD_TDD_MODE", raising=False)
    monkeypatch.setattr(mod, "_coverage_min", lambda: 100)
    assert mod._resolve_mode() == "warn"


@pytest.mark.parametrize("ci", [True, False])
def test_mode_default_never_strict_even_in_ci(monkeypatch, ci):
    monkeypatch.delenv("SDD_TDD_MODE", raising=False)
    monkeypatch.setattr(mod, "is_ci", lambda: ci)
    monkeypatch.setattr(mod, "_coverage_min", lambda: 100)
    assert mod._resolve_mode() != "strict"


def test_mode_explicit_strict_wins_over_coverage(monkeypatch):
    monkeypatch.setenv("SDD_TDD_MODE", "strict")
    monkeypatch.setattr(mod, "_coverage_min", lambda: 80)
    assert mod._resolve_mode() == "strict"


def test_coverage_min_reads_stack_md(monkeypatch, tmp_path):
    stack = tmp_path / "stack.md"
    stack.write_text("## Project Config\nCoverageMin: 100\n", encoding="utf-8")
    import sdd_lib.layered_config as lc
    import sdd_lib.project_config as pc
    monkeypatch.setattr(lc, "read_layered_config", lambda **_: {})
    monkeypatch.setattr(pc, "stack_md_path", lambda: stack)
    assert mod._coverage_min() == 100


def test_coverage_min_defaults_to_80_on_error(monkeypatch):
    import sdd_lib.layered_config as lc
    import sdd_lib.project_config as pc

    def boom(**_):
        raise RuntimeError("config illisible")
    monkeypatch.setattr(lc, "read_layered_config", boom)
    monkeypatch.setattr(pc, "stack_md_path", lambda: Path("/nonexistent/stack.md"))
    assert mod._coverage_min() == 80


# ---------------------------------------------------------------------------
# _is_production_path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("workspace/src/Backend/Services/AuthService.cs", True),
    ("workspace/src/App/src/pages/Login.tsx", True),
    ("workspace/src/Backend.Tests/AuthServiceTests.cs", False),
    ("workspace/src/App/src/__tests__/Login.test.tsx", False),
    ("workspace/src/Api/tests/test_main.py", False),
    ("workspace/src/Kt/src/test/kotlin/FooTest.kt", False),
    ("workspace/feats/1-Auth.md", False),
    (".sdd/python/sdd_lib/paths.py", False),
    ("workspace/src/App/node_modules/x/index.js", False),
])
def test_is_production_path(path, expected):
    assert mod._is_production_path(path) is expected


# ---------------------------------------------------------------------------
# _content_introduces_new_symbol
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext,content,expected", [
    (".cs", "public class AuthService {\n}", True),
    (".cs", "// just a comment\nvar x = 1;", False),
    (".py", "def compute_total(items):\n    return 0", True),
    (".py", "X = 1\n", False),
    (".ts", "export function login(u: string) {}", True),
    (".kt", "fun greet(name: String) = name", True),
])
def test_content_introduces_new_symbol(ext, content, expected):
    assert mod._content_introduces_new_symbol(content, ext) is expected


# ---------------------------------------------------------------------------
# main() end-to-end (payload + repo monkeypatchés)
# ---------------------------------------------------------------------------

PROD_REL = "workspace/src/Backend/Services/AuthService.cs"
NEW_SYMBOL = "public class AuthService { public void Login() {} }"


def _run_main(monkeypatch, tmp_path: Path, *, payload: dict, mode: str = "strict",
              companion_test: bool = False, companion_body: str | None = None) -> int:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / "workspace" / "src" / "Backend" / "Services").mkdir(
        parents=True, exist_ok=True)
    if companion_test:
        tests_dir = tmp_path / "workspace" / "src" / "Backend.Tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "AuthServiceTests.cs").write_text(
            companion_body if companion_body is not None else
            "public class AuthServiceTests { [Fact] public void Login_fails() {} }",
            encoding="utf-8")
    if mode is None:
        monkeypatch.delenv("SDD_TDD_MODE", raising=False)
    else:
        monkeypatch.setenv("SDD_TDD_MODE", mode)
    monkeypatch.delenv("SDD_DISABLE_TDD", raising=False)
    monkeypatch.setattr(mod, "read_hook_input", lambda: payload)
    monkeypatch.setattr(mod, "repo_root", lambda: tmp_path)
    return mod.main()


def _write_payload(path: str = PROD_REL, content: str = NEW_SYMBOL) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


def test_strict_blocks_new_symbol_without_test(monkeypatch, tmp_path, capsys):
    rc = _run_main(monkeypatch, tmp_path, payload=_write_payload())
    assert rc == HOOK_DENY
    assert "[TDD_NO_TEST_FIRST]" in capsys.readouterr().err


def test_warn_allows_but_warns(monkeypatch, tmp_path, capsys):
    rc = _run_main(monkeypatch, tmp_path, payload=_write_payload(), mode="warn")
    assert rc == HOOK_ALLOW
    assert "WARN [TDD_NO_TEST_FIRST]" in capsys.readouterr().err


def test_companion_test_allows(monkeypatch, tmp_path):
    rc = _run_main(monkeypatch, tmp_path, payload=_write_payload(),
                   companion_test=True)
    assert rc == HOOK_ALLOW


def test_test_file_itself_is_allowed(monkeypatch, tmp_path):
    payload = _write_payload(
        path="workspace/src/Backend.Tests/AuthServiceTests.cs")
    rc = _run_main(monkeypatch, tmp_path, payload=payload)
    assert rc == HOOK_ALLOW


def test_refactor_without_new_symbol_is_allowed(monkeypatch, tmp_path):
    payload = {"tool_name": "Edit", "tool_input": {
        "file_path": PROD_REL, "new_string": "var renamed = oldValue;"}}
    rc = _run_main(monkeypatch, tmp_path, payload=payload)
    assert rc == HOOK_ALLOW


def test_mode_off_is_noop(monkeypatch, tmp_path):
    rc = _run_main(monkeypatch, tmp_path, payload=_write_payload(), mode="off")
    assert rc == HOOK_ALLOW


def test_disable_env_bypasses_with_audit_warn(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SDD_TDD_MODE", "strict")
    monkeypatch.setenv("SDD_DISABLE_TDD", "1")
    monkeypatch.setattr(mod, "read_hook_input", lambda: _write_payload())
    monkeypatch.setattr(mod, "repo_root", lambda: tmp_path)
    assert mod.main() == HOOK_ALLOW
    assert "[TDD_BYPASSED]" in capsys.readouterr().err


def test_non_write_tool_is_allowed(monkeypatch, tmp_path):
    payload = {"tool_name": "Read", "tool_input": {"file_path": PROD_REL}}
    rc = _run_main(monkeypatch, tmp_path, payload=payload)
    assert rc == HOOK_ALLOW


# ---------------------------------------------------------------------------
# Audit sécurité 2026-11
# ---------------------------------------------------------------------------

def test_empty_companion_test_does_not_count(monkeypatch, tmp_path):
    rc = _run_main(monkeypatch, tmp_path, payload=_write_payload(), companion_test=True,
                   companion_body="public class AuthServiceTests { }")
    assert rc == HOOK_DENY


@pytest.mark.parametrize("content", [
    "internal sealed class AuthService { }",
    "class AuthService { }",
    "private static void Helper() { }",
])
def test_internal_and_private_symbols_detected(content):
    assert mod._content_introduces_new_symbol(content, ".cs") is True


def test_kotlin_internal_fun_detected():
    assert mod._content_introduces_new_symbol("internal fun compute(x: Int) = x", ".kt")


@pytest.mark.parametrize("cov", [80, 100])
@pytest.mark.parametrize("agent", ["dev-backend", "dev-frontend"])
def test_dev_subagent_never_blocked_by_default(monkeypatch, tmp_path, cov, agent):
    """Le TDD n'interbloque plus dev-* (qui n'a pas le droit d'écrire de tests)."""
    monkeypatch.setattr(mod, "is_ci", lambda: True)
    monkeypatch.setattr(mod, "_coverage_min", lambda: cov)
    payload = {**_write_payload(), "agent_id": "a1", "agent_type": agent}
    assert _run_main(monkeypatch, tmp_path, payload=payload, mode=None) == HOOK_ALLOW


def test_coverage_100_warns_without_blocking(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mod, "_coverage_min", lambda: 100)
    payload = {**_write_payload(), "agent_id": "a1", "agent_type": "dev-backend"}
    assert _run_main(monkeypatch, tmp_path, payload=payload, mode=None) == HOOK_ALLOW
    assert "WARN [TDD_NO_TEST_FIRST]" in capsys.readouterr().err


def test_coverage_below_100_is_silent(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mod, "_coverage_min", lambda: 80)
    payload = {**_write_payload(), "agent_id": "a1", "agent_type": "dev-backend"}
    assert _run_main(monkeypatch, tmp_path, payload=payload, mode=None) == HOOK_ALLOW
    assert "TDD_NO_TEST_FIRST" not in capsys.readouterr().err


def test_main_session_default_never_blocks(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "_coverage_min", lambda: 100)
    assert _run_main(monkeypatch, tmp_path, payload=_write_payload(), mode=None) == HOOK_ALLOW
