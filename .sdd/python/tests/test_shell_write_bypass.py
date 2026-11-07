"""test_shell_write_bypass.py — fermeture du contournement « écrire par le shell ».

Incident (session 2026-11) : `protect_framework`, `enforce_tdd` et
`block_secret_access` ne voyaient que Write/Edit/MultiEdit (ou un découpage
shell trop naïf). Un sous-agent a créé 19 fichiers `.cs` sans test via
heredoc (enforce_tdd contourné) ; un autre a écrit sous `.sdd/` par shell.

Couvre :
  * `sdd_lib.shell_write_targets` — extraction des cibles d'écriture ;
  * `protect_framework` (mode shell) — chaque forme de contournement est
    refusée pour un sous-agent ; lecture/build jamais refusés ; session
    principale = WARN (inchangé) ;
  * `enforce_tdd` (mode shell, nouveau) — même décision que le mode fichier ;
  * `block_secret_access` — lecture de `.env` par shell (cat, type,
    Get-Content, less, head, globs, heredoc d'interpréteur…).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_hooks import block_secret_access as bsa  # noqa: E402
from sdd_hooks import enforce_tdd as tdd  # noqa: E402
from sdd_hooks import protect_framework as pf  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.shell_write_targets import extract_write_targets  # noqa: E402

CI_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "JENKINS_URL",
           "BUILDKITE", "TRAVIS", "TF_BUILD", "BITBUCKET_BUILD_NUMBER")


def _sub(payload: dict) -> dict:
    return {**payload, "agent_id": "a0123", "agent_type": "dev-backend"}


def _tool(cmd: str) -> str:
    ps_markers = ("Set-", "Add-", "Out-", "New-", "Copy-", "Move-", "Remove-",
                  "Get-", "gc ", "[", "'", '"', "type ")
    return "PowerShell" if cmd.startswith(ps_markers) else "Bash"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for v in CI_VARS + ("SDD_PROTECT_FRAMEWORK_MODE", "SDD_TDD_MODE", "SDD_DISABLE_TDD",
                        "SDD_ALLOW_SECRET_ACCESS"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(pf, "SUBAGENT_STRICT_DEFAULT", True)


# =========================================================================== #
# 1. Extraction partagée
# =========================================================================== #

@pytest.mark.parametrize("cmd,path,op", [
    ("cat > a/b.cs <<'EOF'\npublic class B {}\nEOF", "a/b.cs", "redirect"),
    ("echo x 1> f.txt", "f.txt", "redirect"),
    ("printf 'a' | tee -a f.txt", "f.txt", "write"),
    ("cp /tmp/s.cs d/t.cs", "d/t.cs", "copy"),
    ("Copy-Item s.cs -Destination d/t.cs", "d/t.cs", "copy"),
    ("sed -i -e 's/a/b/' f.txt", "f.txt", "inplace"),
    ("python -c \"open('o.txt','w').write('1')\"", "o.txt", "inline"),
    ("[System.IO.File]::WriteAllText('o.txt', 'x')", "o.txt", "inline"),
    ("Set-Content -Path o.txt -Value 1", "o.txt", "write"),
    ("git checkout -- src/x", "src/x", "git"),
    ("find build -name '*.tmp' -delete", "build/", "delete"),
])
def test_extract_targets(cmd, path, op):
    got = [(t.path, t.op) for t in extract_write_targets(cmd)]
    assert (path, op) in got


def test_extract_heredoc_content_and_cd_tracking():
    ts = extract_write_targets("cd a/b && cat > c.cs <<EOF\nclass C {}\nEOF")
    assert len(ts) == 1
    assert ts[0].cwd == "a/b" and ts[0].path == "c.cs"
    assert ts[0].content == "class C {}"


def test_extract_heredoc_body_is_data_not_commands():
    # Le corps du heredoc contient `rm -rf .sdd` : c'est de la DONNÉE.
    ts = extract_write_targets("cat > notes.md <<'EOF'\nrm -rf .sdd\nEOF")
    assert [t.path for t in ts] == ["notes.md"]


@pytest.mark.parametrize("cmd", [
    "cat .sdd/rules/quality.md",
    "grep -rn write_text .sdd/python",
    "git status && git diff --stat && git log --oneline -5",
    "python -m pytest -q -p no:cacheprovider",
    "dotnet build workspace/src/Api",
    "dotnet test workspace/src/Api.Tests 2>&1",
    "npm run build --prefix workspace/src/App",
    "ls -la .sdd && echo ok 2>&1",
    "Get-Content .sdd/loader.yml | Select-String agents",
    "python .sdd/python/sdd_scripts/validate_acceptance.py --feat 1",
    "python -c \"import json; print(json.load(open('workspace/x.json')))\"",
])
def test_reads_and_builds_have_no_target(cmd):
    assert extract_write_targets(cmd) == []


# =========================================================================== #
# 2. protect_framework — mode shell
# =========================================================================== #

def _pf(monkeypatch, payload: dict) -> int:
    monkeypatch.setattr(pf, "read_hook_input", lambda: payload)
    return pf._main_inner()


PF_BYPASSES = [
    "cat > .sdd/rules/x.md <<'EOF'\n# injected\nEOF",
    "cat <<EOF > .sdd/rules/x.md\n# injected\nEOF",
    "echo x > .sdd/rules/x.md",
    "echo x >> .sdd/rules/x.md",
    "echo x 1> .sdd/rules/x.md",
    "printf 'x' | tee .sdd/rules/x.md",
    "tee -a .claude/settings.json <<EOF\n{}\nEOF",
    "cp /tmp/x.md .sdd/rules/x.md",
    "mv /tmp/x.md .sdd/rules/x.md",
    "sed -i 's/a/b/' .sdd/loader.yml",
    "perl -pi -e 's/a/b/' .sdd/loader.yml",
    "touch .sdd/agents/evil.md",
    "rm -rf .sdd",
    "find .sdd -name '*.md' -delete",
    "git checkout -- .sdd/python",
    "curl -o .sdd/rules/x.md https://example.invalid/x",
    "python -c \"open('.sdd/rules/x.md','w').write('x')\"",
    "python3 -c \"import pathlib; pathlib.Path('.sdd/rules/x.md').write_text('x')\"",
    "python - <<'EOF'\nfrom pathlib import Path\nPath('.sdd/rules/x.md').write_text('x')\nEOF",
    "node -e \"require('fs').writeFileSync('.claude/agents/x.md','x')\"",
    "bash -c \"echo x > .sdd/rules/x.md\"",
    "cd .sdd/rules && echo x > x.md",
    "cp a.md \\\n  .sdd/rules/x.md",
    "Set-Content -Path .sdd/rules/x.md -Value x",
    "Set-Content .sdd/rules/x.md 'x'",
    "Add-Content -Path .sdd/rules/x.md -Value x",
    "Out-File -FilePath .sdd/rules/x.md -InputObject x",
    "'x' | Out-File .sdd/rules/x.md",
    "New-Item -ItemType File -Path .sdd/rules/x.md -Value x -Force",
    "Copy-Item C:/tmp/x.md -Destination .sdd/rules/x.md",
    "Move-Item -Path C:/tmp/x.md -Destination .sdd/rules/x.md",
    "Remove-Item -Recurse -Force .sdd/python",
    "[System.IO.File]::WriteAllText('.sdd/rules/x.md', 'x')",
    "pwsh -Command \"Set-Content -Path .sdd/rules/x.md -Value x\"",
    "Set-Location .sdd/rules; Set-Content x.md 'x'",
    "echo '{}' > workspace/.sys/.acceptance/acceptance.json",
    "Set-Content workspace/.sys/.validation/1-spec-compliance.json '{}'",
]


@pytest.mark.parametrize("cmd", PF_BYPASSES)
def test_pf_subagent_shell_bypass_denied(monkeypatch, cmd):
    p = _sub({"tool_name": _tool(cmd), "tool_input": {"command": cmd}})
    assert _pf(monkeypatch, p) == HOOK_DENY


@pytest.mark.parametrize("cmd", PF_BYPASSES[:6] + PF_BYPASSES[-12:-2])
def test_pf_main_session_shell_write_warns_only(monkeypatch, capsys, cmd):
    p = {"tool_name": _tool(cmd), "tool_input": {"command": cmd}}
    assert _pf(monkeypatch, p) == HOOK_ALLOW
    assert "WARNING" in capsys.readouterr().err


@pytest.mark.parametrize("cmd", [
    "cat .sdd/rules/quality.md",
    "grep -rn FRAMEWORK_OWNED .sdd/python/sdd_hooks",
    "git status && git diff -- .sdd",
    "python -m pytest .sdd/python/tests -q",
    "python .sdd/python/sdd_admin/framework_smoke.py --strict",
    "dotnet build workspace/src/Api > build.log 2>&1",
    "cp .sdd/templates/feat.template.md workspace/feats/1-Auth.md",
    "cat > workspace/notes.md <<'EOF'\nrm -rf .sdd ; echo x > .sdd/rules/x.md\nEOF",
    "Get-Content .sdd/loader.yml",
    "ls .sdd && echo ok 2>&1",
    "cd .claude/worktrees/agent-1 && echo x > notes.txt",
])
def test_pf_reads_and_builds_allowed(monkeypatch, cmd):
    p = _sub({"tool_name": _tool(cmd), "tool_input": {"command": cmd}})
    assert _pf(monkeypatch, p) == HOOK_ALLOW


def test_pf_relative_write_resolved_from_payload_cwd(monkeypatch):
    repo = pf.repo_root()
    cwd = repo / ".sdd" / "rules"
    p = _sub({"tool_name": "Bash", "cwd": str(cwd),
              "tool_input": {"command": "echo x > injected.md"}})
    assert _pf(monkeypatch, p) == HOOK_DENY


def test_pf_cwd_outside_repo_is_not_protected(monkeypatch, tmp_path):
    # Un `.sdd/` relatif résolu HORS du dépôt (worktree, scratch) n'est pas
    # le framework du dépôt.
    p = _sub({"tool_name": "Bash", "cwd": str(tmp_path),
              "tool_input": {"command": "echo x > .sdd/rules/x.md"}})
    assert _pf(monkeypatch, p) == HOOK_ALLOW


def test_pf_shell_gate_artifact_declared_in_loader_allowed(monkeypatch):
    # Même exception `loader.yml writes:` qu'en mode fichier.
    p = {"tool_name": "Bash", "agent_id": "a", "agent_type": "spec-compliance-reviewer",
         "tool_input": {"command": "echo '{}' > workspace/.sys/.validation/3-spec-compliance.json"}}
    assert _pf(monkeypatch, p) == HOOK_ALLOW


def test_pf_shell_deny_uses_file_mode_message(monkeypatch, capsys):
    p = _sub({"tool_name": "Bash", "tool_input": {"command": "echo x > .sdd/rules/x.md"}})
    assert _pf(monkeypatch, p) == HOOK_DENY
    err = capsys.readouterr().err
    assert "CAUSE: [FRAMEWORK_PROTECTED]" in err and ".sdd/rules/x.md" in err


def test_pf_mode_off_still_bypasses_shell(monkeypatch, capsys):
    monkeypatch.setenv("SDD_PROTECT_FRAMEWORK_MODE", "off")
    p = _sub({"tool_name": "Bash", "tool_input": {"command": "rm -rf .sdd"}})
    assert _pf(monkeypatch, p) == HOOK_ALLOW
    assert "BYPASS" in capsys.readouterr().err


# =========================================================================== #
# 3. enforce_tdd — mode shell
# =========================================================================== #

PROD = "workspace/src/Api/Services/FooService.cs"
CLS = "public class FooService\n{\n    public int Run() => 1;\n}"


@pytest.fixture
def tdd_repo(tmp_path, monkeypatch):
    (tmp_path / "workspace" / "src" / "Api" / "Services").mkdir(parents=True)
    (tmp_path / "workspace" / "src" / "Api.Tests").mkdir(parents=True)
    monkeypatch.setattr(tdd, "repo_root", lambda: tmp_path)
    return tmp_path


def _tdd(monkeypatch, payload: dict) -> int:
    monkeypatch.setattr(tdd, "read_hook_input", lambda: payload)
    return tdd.main()


def _tdd_bypasses(root: Path) -> list[str]:
    src = root / "tmp_FooService.cs"
    src.write_text(CLS, encoding="utf-8")
    txt = root / "draft.txt"
    txt.write_text(CLS, encoding="utf-8")
    s, t = src.as_posix(), txt.as_posix()
    return [
        f"cat > {PROD} <<'EOF'\n{CLS}\nEOF",
        f"cat <<EOF > {PROD}\n{CLS}\nEOF",
        f"tee {PROD} <<'EOF'\n{CLS}\nEOF",
        f"echo 'public class FooService {{}}' > {PROD}",
        f"printf 'public class FooService {{}}' | tee {PROD}",
        f"Set-Content -Path {PROD} -Value 'public class FooService {{}}'",
        f"Set-Content {PROD} 'public class FooService {{}}'",
        f"'public class FooService {{}}' | Out-File -FilePath {PROD}",
        f"Set-Content -Path {PROD} -Value @'\n{CLS}\n'@",
        f"New-Item -ItemType File -Path {PROD} -Value 'public class FooService {{}}'",
        f"cp {s} {PROD}",
        f"Copy-Item {s} -Destination {PROD}",
        f"mv {t} {PROD}",
        f"python -c \"import pathlib; pathlib.Path('{PROD}').write_text('x')\"",
        f"python - <<'EOF'\nopen('{PROD}', 'w').write('''{CLS}''')\nEOF",
        f"[System.IO.File]::WriteAllText('{PROD}', 'public class FooService {{}}')",
        f"bash -c \"echo 'public class FooService {{}}' > {PROD}\"",
        f"cd workspace/src/Api/Services && cat > FooService.cs <<'EOF'\n{CLS}\nEOF",
    ]


def test_tdd_subagent_shell_bypasses_denied(tdd_repo, monkeypatch, capsys):
    for cmd in _tdd_bypasses(tdd_repo):
        p = _sub({"tool_name": _tool(cmd), "tool_input": {"command": cmd}})
        assert _tdd(monkeypatch, p) == HOOK_DENY, cmd
        assert "[TDD_NO_TEST_FIRST]" in capsys.readouterr().err, cmd


def test_tdd_main_session_shell_warns_only(tdd_repo, monkeypatch, capsys):
    cmd = f"cat > {PROD} <<'EOF'\n{CLS}\nEOF"
    assert _tdd(monkeypatch, {"tool_name": "Bash", "tool_input": {"command": cmd}}) == HOOK_ALLOW
    assert "WARN [TDD_NO_TEST_FIRST]" in capsys.readouterr().err


def test_tdd_shell_allowed_when_companion_test_exists(tdd_repo, monkeypatch):
    (tdd_repo / "workspace/src/Api.Tests/FooServiceTests.cs").write_text(
        "public class FooServiceTests { [Fact] public void Runs() {} }", encoding="utf-8")
    cmd = f"cat > {PROD} <<'EOF'\n{CLS}\nEOF"
    assert _tdd(monkeypatch, _sub({"tool_name": "Bash", "tool_input": {"command": cmd}})) == HOOK_ALLOW


def test_tdd_shell_test_and_prod_in_same_batch_allowed(tdd_repo, monkeypatch):
    cmd = ("cat > workspace/src/Api.Tests/FooServiceTests.cs <<'EOF'\n"
           "public class FooServiceTests { [Fact] public void Runs() {} }\nEOF\n"
           f"cat > {PROD} <<'EOF'\n{CLS}\nEOF")
    assert _tdd(monkeypatch, _sub({"tool_name": "Bash", "tool_input": {"command": cmd}})) == HOOK_ALLOW


def test_tdd_shell_empty_test_skeleton_does_not_count(tdd_repo, monkeypatch):
    cmd = ("cat > workspace/src/Api.Tests/FooServiceTests.cs <<'EOF'\n"
           "public class FooServiceTests { }\nEOF\n"
           f"cat > {PROD} <<'EOF'\n{CLS}\nEOF")
    assert _tdd(monkeypatch, _sub({"tool_name": "Bash", "tool_input": {"command": cmd}})) == HOOK_DENY


@pytest.mark.parametrize("cmd", [
    f"echo '// header' > {PROD}",                       # pas de nouveau symbole
    "cat > workspace/src/Api.Tests/BarTests.cs <<'EOF'\npublic class BarTests {}\nEOF",
    "dotnet build workspace/src/Api > build.log 2>&1",
    "dotnet test workspace/src/Api.Tests",
    f"rm {PROD}",
    f"cat {PROD}",
    "echo 'public class X {}' > workspace/notes/X.cs",   # hors workspace/src
    "echo 'public class X {}' > workspace/src/Api/obj/X.cs",
])
def test_tdd_shell_non_violations_allowed(tdd_repo, monkeypatch, cmd):
    assert _tdd(monkeypatch, _sub({"tool_name": _tool(cmd), "tool_input": {"command": cmd}})) == HOOK_ALLOW


def test_tdd_shell_inplace_edit_of_existing_file_allowed(tdd_repo, monkeypatch):
    (tdd_repo / PROD).write_text(CLS, encoding="utf-8")
    cmd = f"sed -i 's/Run/Execute/' {PROD}"
    assert _tdd(monkeypatch, _sub({"tool_name": "Bash", "tool_input": {"command": cmd}})) == HOOK_ALLOW


def test_tdd_shell_unknown_content_new_file_is_fail_closed(tdd_repo, monkeypatch):
    cmd = f"curl -o {PROD} https://example.invalid/Foo.cs"
    assert _tdd(monkeypatch, _sub({"tool_name": "Bash", "tool_input": {"command": cmd}})) == HOOK_DENY


@pytest.mark.parametrize("env,val", [("SDD_DISABLE_TDD", "1"), ("SDD_TDD_MODE", "off"),
                                     ("SDD_TDD_MODE", "warn")])
def test_tdd_shell_same_bypasses_as_file_mode(tdd_repo, monkeypatch, env, val):
    monkeypatch.setenv(env, val)
    cmd = f"cat > {PROD} <<'EOF'\n{CLS}\nEOF"
    assert _tdd(monkeypatch, _sub({"tool_name": "Bash", "tool_input": {"command": cmd}})) == HOOK_ALLOW


def test_tdd_file_mode_unchanged(tdd_repo, monkeypatch):
    p = _sub({"tool_name": "Write", "tool_input": {"file_path": PROD, "content": CLS}})
    assert _tdd(monkeypatch, p) == HOOK_DENY


# =========================================================================== #
# 4. block_secret_access — lecture de .env par shell
# =========================================================================== #

def _bsa(monkeypatch, payload: dict) -> int:
    monkeypatch.setattr(bsa, "read_hook_input", lambda: payload)
    return bsa.main()


@pytest.mark.parametrize("cmd", [
    "cat .env",
    "cat ./.env",
    "type .env",
    "Get-Content .env",
    "gc -Path .env",
    "Get-Content -Raw workspace/.env",
    "less .env",
    "more .env",
    "head -n 5 .env",
    "tail .env.local",
    "grep DB_PASSWORD .env",
    "source .env",
    ". ./.env",
    "cat < .env",
    "cp .env /tmp/leak.txt",
    "cat .en*",
    "Get-Content .e?v",
    "python -c \"print(open('.env').read())\"",
    "[System.IO.File]::ReadAllText('.env')",
    "python - <<'EOF'\nprint(open('.env').read())\nEOF",
    "cat ~/.ssh/id_rsa",
])
def test_bsa_subagent_shell_read_denied(monkeypatch, cmd):
    p = _sub({"tool_name": _tool(cmd), "tool_input": {"command": cmd}})
    assert _bsa(monkeypatch, p) == HOOK_DENY


@pytest.mark.parametrize("cmd", [
    "cat .env.example",
    "cat README.md",
    "git status",
    "ls -la",
    "python -m pytest -q",
    # Heredoc de DONNÉES qui mentionne des noms sensibles : pas une lecture.
    "cat > workspace/notes.md <<'EOF'\nNe jamais lire .env ni id_rsa\nEOF",
])
def test_bsa_subagent_shell_non_secret_allowed(monkeypatch, cmd):
    p = _sub({"tool_name": _tool(cmd), "tool_input": {"command": cmd}})
    assert _bsa(monkeypatch, p) == HOOK_ALLOW


def test_bsa_main_session_shell_read_warns_only(monkeypatch, capsys):
    p = {"tool_name": "Bash", "tool_input": {"command": "cat .env"}}
    assert _bsa(monkeypatch, p) == HOOK_ALLOW
    assert "SECRET_ACCESS_FORBIDDEN" in capsys.readouterr().err


# =========================================================================== #
# 5. Câblage : les 3 hooks écoutent Bash|PowerShell
# =========================================================================== #

def test_three_hooks_wired_on_shell_matcher():
    import json
    from sdd_lib.paths import repo_root
    settings = json.loads((repo_root() / ".claude" / "settings.json").read_text(encoding="utf-8"))
    groups = [g for g in settings["hooks"]["PreToolUse"] if g.get("matcher") == "Bash|PowerShell"]
    assert groups, "matcher Bash|PowerShell absent"
    cmds = " ".join(h["command"] for g in groups for h in g["hooks"])
    for hook in ("protect_framework", "enforce_tdd", "block_secret_access"):
        assert f"sdd_hooks.{hook}" in cmds, hook
