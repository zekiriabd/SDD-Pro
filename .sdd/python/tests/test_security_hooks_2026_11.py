"""Lot « sécurité + gouvernance réellement bloquante » (audit 2026-11).

Couvre : `_hook.py` fail-closed, `hook_input` (payloads réels sous-agent /
SubagentStop), `protect_framework` (artefacts de gate, NotebookEdit, mode
shell Bash|PowerShell, politique sous-agent), `block_secret_access`,
`preflight_secret_scan` (DENY au spawn, faux positif `${DB_PASSWORD}`) et le
garde secrets de `pre_write_lint`.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_hooks import block_secret_access as bsa  # noqa: E402
from sdd_hooks import pre_write_lint as pwl  # noqa: E402
from sdd_hooks import preflight_secret_scan as pss  # noqa: E402
from sdd_hooks import protect_framework as pf  # noqa: E402
from sdd_lib import hook_input as hi  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402

LAUNCHER = _PY_ROOT / "_hook.py"
CI_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "JENKINS_URL",
           "BUILDKITE", "TRAVIS", "TF_BUILD", "BITBUCKET_BUILD_NUMBER")

#: Ligne au format exact de workspace/src/PolEmploiAuto/appsettings.json L37/L40
#: (valeur factice) — le fichier réel avait un mot de passe en clair à ces lignes.
POLEMPLOI_LINE = ('    "NounouFlow": "Server=LAPTOP-X;Database=NounouFlow;User ID=u;'
                  'Password=Fake2002.;TrustServerCertificate=True;MultipleActiveResultSets=True;"')


def _sub(payload: dict) -> dict:
    return {**payload, "agent_id": "a0123", "agent_type": "dev-backend"}


# ── _hook.py ───────────────────────────────────────────────────────────────

def _launch(module: str, stdin: str = "{}") -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, str(LAUNCHER), module], input=stdin,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60)


def test_hook_crash_is_fail_closed():
    r = _launch("sdd_hooks.does_not_exist_xyz")
    assert r.returncode == 2
    assert "CAUSE: [HOOK_CRASH]" in r.stderr


def test_informational_hook_crash_is_exit_0(monkeypatch):
    import _hook
    assert "sdd_hooks.session_start" in _hook.INFORMATIONAL_HOOKS
    assert _hook._crash_exit_code("sdd_hooks.session_start") == 0
    assert _hook._crash_exit_code("sdd_hooks.protect_framework") == 2


def test_hook_docstring_timeout_is_600s():
    import _hook
    assert "600 s" in _hook.__doc__ and "~30s" not in _hook.__doc__


# ── hook_input ─────────────────────────────────────────────────────────────

def test_subagent_stop_payload_resolves_agent_type():
    p = {"hook_event_name": "SubagentStop", "agent_type": "qa", "agent_id": "x",
         "agent_transcript_path": "/t.jsonl"}
    assert hi.get_subagent_type(p) == "qa"
    assert hi.get_caller_agent_type(p) == "qa"
    assert hi.get_agent_transcript_path(p) == "/t.jsonl"
    assert hi.is_subagent_call(p)


def test_spawn_target_wins_over_caller():
    p = {"agent_type": "orchestrator", "agent_id": "x",
         "tool_input": {"subagent_type": "code-reviewer"}}
    assert hi.get_subagent_type(p) == "code-reviewer"
    assert hi.get_spawn_target_type(p) == "code-reviewer"
    assert hi.get_caller_agent_type(p) == "orchestrator"


def test_main_session_is_not_subagent():
    assert not hi.is_subagent_call({"tool_name": "Edit", "tool_input": {"file_path": "a"}})


def test_notebook_path_is_a_file_path():
    assert hi.get_file_path({"tool_input": {"notebook_path": "n.ipynb"}}) == "n.ipynb"


def test_regex_fallback_keeps_agent_identity():
    raw = '{"agent_id": "a1", "agent_type": "qa", "tool_name": "Write", "tool_input": {"file_path": "x"'
    assert hi.is_subagent_call(hi._regex_fallback(raw))


# ── protect_framework ──────────────────────────────────────────────────────

@pytest.fixture
def pf_env(monkeypatch):
    for v in CI_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.delenv("SDD_PROTECT_FRAMEWORK_MODE", raising=False)
    monkeypatch.setattr(pf, "SUBAGENT_STRICT_DEFAULT", True)


def _pf(monkeypatch, payload: dict) -> int:
    monkeypatch.setattr(pf, "read_hook_input", lambda: payload)
    return pf._main_inner()


def test_framework_owned_has_no_duplicates():
    assert len(pf.FRAMEWORK_OWNED) == len(set(pf.FRAMEWORK_OWNED))


def test_subagent_framework_edit_denied(pf_env, monkeypatch):
    p = _sub({"tool_name": "Edit", "tool_input": {"file_path": ".sdd/rules/quality.md"}})
    assert _pf(monkeypatch, p) == HOOK_DENY


def test_main_session_framework_edit_warns(pf_env, monkeypatch):
    p = {"tool_name": "Edit", "tool_input": {"file_path": ".sdd/rules/quality.md"}}
    assert _pf(monkeypatch, p) == HOOK_ALLOW


def test_notebook_edit_on_framework_denied(pf_env, monkeypatch):
    p = _sub({"tool_name": "NotebookEdit", "tool_input": {"notebook_path": ".sdd/python/x.ipynb"}})
    assert _pf(monkeypatch, p) == HOOK_DENY


@pytest.mark.parametrize("path", [
    "workspace/.sys/.acceptance/acceptance.json",
    "workspace/.sys/.validation/3-spec-compliance.json",
    "workspace/.sys/.audit/ownership-violations.log",
    "workspace/.sys/.state/run-id.current",
])
def test_gate_artifact_write_by_unentitled_agent_denied(pf_env, monkeypatch, path):
    p = _sub({"tool_name": "Write", "tool_input": {"file_path": path, "content": "{}"}})
    assert _pf(monkeypatch, p) == HOOK_DENY


def test_gate_artifact_declared_in_loader_writes_allowed(pf_env, monkeypatch):
    p = {"tool_name": "Write", "agent_id": "a", "agent_type": "spec-compliance-reviewer",
         "tool_input": {"file_path": "workspace/.sys/.validation/3-spec-compliance.json"}}
    assert _pf(monkeypatch, p) == HOOK_ALLOW


def test_qa_cannot_forge_acceptance_report(pf_env, monkeypatch):
    p = {"tool_name": "Write", "agent_id": "a", "agent_type": "qa",
         "tool_input": {"file_path": "workspace/.sys/.acceptance/acceptance.json"}}
    assert _pf(monkeypatch, p) == HOOK_DENY


def test_explicit_warn_overrides_subagent_strict(pf_env, monkeypatch):
    monkeypatch.setenv("SDD_PROTECT_FRAMEWORK_MODE", "warn")
    p = _sub({"tool_name": "Edit", "tool_input": {"file_path": ".sdd/rules/quality.md"}})
    assert _pf(monkeypatch, p) == HOOK_ALLOW


@pytest.mark.parametrize("cmd,denied", [
    ("echo x > .sdd/rules/foo.md", True),
    ("Set-Content -Path .claude/settings.json -Value x", True),
    ("python -c \"import pathlib; pathlib.Path('workspace/.sys/.acceptance/acceptance.json').write_text('{}')\"", True),
    ("sed -i 's/a/b/' .sdd/loader.yml", True),
    ("git checkout -- .sdd/python", True),
    ("cmd & rm .sdd/x", True),
    ("cat .sdd/rules/foo.md", False),
    ("python -m pytest .sdd/python/tests -q", False),
    ("python .sdd/python/sdd_scripts/validate_acceptance.py", False),
    ("ls .sdd && echo ok 2>&1", False),
])
def test_shell_mode(pf_env, monkeypatch, cmd, denied):
    tool = "PowerShell" if cmd.startswith("Set-") else "Bash"
    p = _sub({"tool_name": tool, "tool_input": {"command": cmd}})
    assert _pf(monkeypatch, p) == (HOOK_DENY if denied else HOOK_ALLOW)


def test_internal_exception_is_fail_closed(monkeypatch, pf_env):
    def _boom():
        raise RuntimeError("probe")
    monkeypatch.setattr(pf, "_main_inner", _boom)
    monkeypatch.delenv("SDD_PROTECT_FRAMEWORK_FAIL_OPEN", raising=False)
    assert pf.main() == HOOK_DENY


# ── block_secret_access ────────────────────────────────────────────────────

def test_polemploi_connection_string_password_detected():
    hits = bsa.find_secret_values(POLEMPLOI_LINE)
    assert hits and hits[0][0] == "Password"
    assert "Fake2002" not in json.dumps(hits)  # valeur jamais restituée en clair


@pytest.mark.parametrize("text,real", [
    ('"Password": "${DB_PASSWORD}"', False),
    ('"Default": "Server=x;Password=${DB_PASSWORD};"', False),
    (' - DB_PASSWORD: ${DB_PASSWORD}', False),
    ('"PasswordInput": "#password"', False),
    ('"SemainePaireToken": "semainePaire"', False),
    ('"Password": "hunter22"', True),
    (' - DB_PASSWORD: s3cr3t!', True),
    ('AUTH_JWT_SECRET=abcdefgh', True),
    ('url: postgres://u:pw123@h/db', True),
])
def test_secret_value_detection(text, real):
    assert bool(bsa.find_secret_values(text)) is real


@pytest.mark.parametrize("path,kind", [
    (".env", "always"), ("cfg/.env.local", "always"), (".env.example", None),
    ("a/secrets/x.txt", "always"), ("k.pem", "always"), ("C:\\u\\.ssh\\id_rsa", "always"),
    ("workspace/.sys/.secrets/k", "always"),
    ("workspace/src/A/appsettings.Development.json", "config"),
    ("workspace/src/A/src/main/resources/application.yml", "config"),
    ("workspace/src/A/config/default.json", "config"),
    ("workspace/src/A/Program.cs", None),
])
def test_secret_path_classification(path, kind):
    assert bsa.classify_secret_path(path) == kind


def _bsa(monkeypatch, payload) -> int:
    monkeypatch.setattr(bsa, "read_hook_input", lambda: payload)
    monkeypatch.delenv("SDD_ALLOW_SECRET_ACCESS", raising=False)
    return bsa.main()


def test_subagent_reading_dotenv_denied(monkeypatch):
    assert _bsa(monkeypatch, _sub({"tool_name": "Read", "tool_input": {"file_path": ".env"}})) == HOOK_DENY


def test_main_session_reading_dotenv_warns(monkeypatch, capsys):
    assert _bsa(monkeypatch, {"tool_name": "Read", "tool_input": {"file_path": ".env"}}) == HOOK_ALLOW
    assert "SECRET_ACCESS_FORBIDDEN" in capsys.readouterr().err


def test_subagent_reading_config_with_real_secret_denied(monkeypatch, tmp_path):
    cfg = tmp_path / "workspace" / "src" / "App" / "appsettings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{\n" + POLEMPLOI_LINE + "\n}\n", encoding="utf-8")
    p = _sub({"tool_name": "Read", "tool_input": {"file_path": str(cfg)}})
    assert _bsa(monkeypatch, p) == HOOK_DENY


def test_subagent_reading_config_with_placeholders_allowed(monkeypatch, tmp_path):
    cfg = tmp_path / "workspace" / "src" / "App" / "appsettings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"ConnectionStrings": {"D": "Server=h;Password=${DB_PASSWORD};"}}',
                   encoding="utf-8")
    p = _sub({"tool_name": "Read", "tool_input": {"file_path": str(cfg)}})
    assert _bsa(monkeypatch, p) == HOOK_ALLOW


@pytest.mark.parametrize("tool,cmd", [
    ("Bash", "cat .env"),
    ("PowerShell", "Get-Content .env.production"),
    ("Bash", "python -c \"print(open('secrets/api.txt').read())\""),
    ("Bash", "type C:\\Users\\me\\.ssh\\id_rsa"),
])
def test_subagent_shell_secret_read_denied(monkeypatch, tool, cmd):
    assert _bsa(monkeypatch, _sub({"tool_name": tool, "tool_input": {"command": cmd}})) == HOOK_DENY


def test_glob_on_dotenv_denied(monkeypatch):
    p = _sub({"tool_name": "Glob", "tool_input": {"pattern": "**/.env"}})
    assert _bsa(monkeypatch, p) == HOOK_DENY


# ── preflight_secret_scan ──────────────────────────────────────────────────

def test_stack_placeholder_is_not_a_secret(tmp_path):
    p = tmp_path / "stack.md"
    p.write_text("## Active Database\n - DB_PASSWORD: ${DB_PASSWORD}\n", encoding="utf-8")
    assert pss._stack_has_secrets(p) == ()


def test_stack_list_form_real_secret_detected(tmp_path):
    p = tmp_path / "stack.md"
    p.write_text("## Active Database\n - DB_PASSWORD: hunter22\n", encoding="utf-8")
    assert pss._stack_has_secrets(p) == ("DB_PASSWORD",)


def test_spawn_denied_when_agent_reads_config_with_secret(monkeypatch, tmp_path):
    ws = tmp_path / "workspace"
    cfg = ws / "src" / "Back" / "appsettings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{\n" + POLEMPLOI_LINE + "\n}\n", encoding="utf-8")
    monkeypatch.setattr(pss, "read_hook_input",
                        lambda: {"tool_name": "Agent", "tool_input": {"subagent_type": "code-reviewer"}})
    monkeypatch.setattr(pss, "_resolve_stack_md", lambda: None)
    monkeypatch.setattr(pss, "_agent_read_globs", lambda a: ["workspace/src/*/**"])
    monkeypatch.setattr(pss, "_dotenv_findings", lambda: [])
    import sdd_lib.paths as paths
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    monkeypatch.delenv("SDD_ALLOW_SECRET_IN_CONTEXT", raising=False)
    assert pss.main() == HOOK_DENY


def test_spawn_allowed_for_agent_not_reading_configs(monkeypatch, tmp_path):
    monkeypatch.setattr(pss, "read_hook_input",
                        lambda: {"tool_name": "Agent", "tool_input": {"subagent_type": "po"}})
    monkeypatch.setattr(pss, "_resolve_stack_md", lambda: None)
    monkeypatch.setattr(pss, "_agent_read_globs", lambda a: ["workspace/feats/*.md"])
    monkeypatch.setattr(pss, "_dotenv_findings", lambda: [])
    assert pss.main() == HOOK_ALLOW


# ── pre_write_lint : garde secrets ─────────────────────────────────────────

@pytest.mark.parametrize("path,content,denied", [
    ("workspace/src/App/appsettings.json", POLEMPLOI_LINE, True),
    ("workspace/src/App/appsettings.json", '"D": "Server=h;Password=${DB_PASSWORD};"', False),
    ("workspace/stack/stack.md", " - DB_PASSWORD: hunter22", True),
    ("workspace/stack/stack.md", " - DB_PASSWORD: ${DB_PASSWORD}", False),
    ("workspace/src/App/src/main/resources/application.yml", "    password: realpw123", True),
    ("workspace/src/App/Services/X.cs", 'var p = "Password=abc;";', False),
])
def test_secret_write_guard(monkeypatch, path, content, denied):
    payload = {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}
    monkeypatch.setattr(pwl, "read_hook_input", lambda: payload)
    monkeypatch.delenv("SDD_ALLOW_SECRET_IN_CONFIG", raising=False)
    rc = pwl.main()
    if denied:
        assert rc == HOOK_DENY
    else:
        assert rc == HOOK_ALLOW


def test_secret_write_guard_ignores_lint_disable(monkeypatch):
    monkeypatch.setenv("SDD_DISABLE_PRE_WRITE_LINT", "1")
    payload = {"tool_name": "Edit", "tool_input": {
        "file_path": "workspace/src/App/appsettings.json", "new_string": POLEMPLOI_LINE}}
    monkeypatch.setattr(pwl, "read_hook_input", lambda: payload)
    assert pwl.main() == HOOK_DENY
