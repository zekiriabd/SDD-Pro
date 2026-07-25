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


def test_mode_default_warn_interactive(monkeypatch):
    monkeypatch.delenv("SDD_TDD_MODE", raising=False)
    monkeypatch.setattr(mod, "is_ci", lambda: False)
    assert mod._resolve_mode() == "warn"


def test_mode_default_strict_in_ci(monkeypatch):
    monkeypatch.delenv("SDD_TDD_MODE", raising=False)
    monkeypatch.setattr(mod, "is_ci", lambda: True)
    assert mod._resolve_mode() == "strict"


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
    (".claude/python/sdd_lib/paths.py", False),
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
              companion_test: bool = False) -> int:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / "workspace" / "src" / "Backend" / "Services").mkdir(
        parents=True, exist_ok=True)
    if companion_test:
        tests_dir = tmp_path / "workspace" / "src" / "Backend.Tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "AuthServiceTests.cs").write_text(
            "public class AuthServiceTests {}", encoding="utf-8")
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
