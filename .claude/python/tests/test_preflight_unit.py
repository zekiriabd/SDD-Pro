"""Unit tests for preflight.py (direct import).

Synthesizes a workspace tree (stack.md + US + project files) in tmp and
exercises main() across the A1-A4 + B1-B5 checks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import preflight  # noqa: E402


STACK_OK = """\
## Active Tech Specs
- .claude/stacks/backend/dotnet-minimalapi.md
- .claude/stacks/frontend/react.md

## Active UI Specs
- .claude/stacks/ui/shadcn.md

## Active Auth Specs
- .claude/stacks/auth/azure-ad.md

## Project Config
AppName: WebApp
BackendName: ApiSrv
"""


@pytest.fixture()
def fake_repo(tmp_path):
    (tmp_path / ".claude").mkdir()
    yield tmp_path


def _bootstrap(repo: Path, stack: str = STACK_OK, us: list[str] | None = None,
               html: list[str] | None = None,
               project_dirs: list[str] | None = None) -> None:
    """Create stack.md + optional US files + optional html files + optional projects."""
    stack_dir = repo / "workspace" / "input" / "stack"
    stack_dir.mkdir(parents=True)
    (stack_dir / "stack.md").write_text(stack, encoding="utf-8")

    if us:
        us_dir = repo / "workspace" / "output" / "us"
        us_dir.mkdir(parents=True)
        for filename in us:
            (us_dir / filename).write_text("# US", encoding="utf-8")

    if html:
        ui_dir = repo / "workspace" / "input" / "ui"
        ui_dir.mkdir(parents=True)
        for filename in html:
            (ui_dir / filename).write_text("<!doctype html>", encoding="utf-8")

    if project_dirs:
        for name in project_dirs:
            d = repo / "workspace" / "output" / "src" / name
            d.mkdir(parents=True)
            (d / "CLAUDE.md").write_text("# proj", encoding="utf-8")
            (d / f"{name}.csproj").write_text("<Project/>", encoding="utf-8")


def _run(args: list[str]) -> tuple[int, dict]:
    """Invoke preflight.main() and return (rc, parsed_json_output)."""
    import io
    import contextlib
    buf = io.StringIO()
    saved_argv = sys.argv
    sys.argv = ["preflight.py"] + args
    try:
        with contextlib.redirect_stdout(buf):
            rc = preflight.main()
    finally:
        sys.argv = saved_argv
    return rc, json.loads(buf.getvalue().strip())


# ---------- Helper / unit functions ----------


def test_get_active_ids_skips_commented_lines():
    block = (
        "- .claude/stacks/backend/dotnet-minimalapi.md\n"
        "# - .claude/stacks/backend/python-fastapi.md\n"
        "  # - .claude/stacks/backend/node-express.md\n"
        "- .claude/stacks/backend/kotlin-spring-boot.md\n"
    )
    ids = preflight.get_active_ids(block, "backend")
    assert ids == ["dotnet-minimalapi", "kotlin-spring-boot"]


def test_extract_section_returns_block():
    # v7.0.0-alpha (audit CRIT-3) : extract_section now takes a plain
    # heading string (regex-escaped internally by sdd_lib.markdown_io).
    text = "## A\nbody A\n\n## B\nbody B\n"
    out = preflight.extract_section(text, "A")
    assert "body A" in out
    assert "body B" not in out


def test_extract_section_returns_empty_when_missing():
    assert preflight.extract_section("only text", "X") == ""


def test_detect_app_type_auto_backend_frontend():
    assert preflight.detect_app_type_auto(["dot"], ["react"], [], []) == ("back-front", "web")


def test_detect_app_type_auto_fullstack_priority():
    assert preflight.detect_app_type_auto(["x"], ["y"], ["next"], []) == ("fullstack", None)


def test_detect_app_type_auto_mobile():
    assert preflight.detect_app_type_auto([], [], [], ["maui"]) == ("back-front", "mobile")


def test_detect_app_type_auto_backend_only():
    assert preflight.detect_app_type_auto(["dot"], [], [], []) == ("back-front", None)


def test_validate_stack_combo_fullstack_with_backend_invalid():
    err = preflight.validate_stack_combo(["dot"], [], ["next"], [])
    assert err is not None
    assert "fullstack" in err.lower()


def test_validate_stack_combo_mobile_with_frontend_invalid():
    err = preflight.validate_stack_combo([], ["react"], [], ["maui"])
    assert err is not None
    assert "mobile" in err.lower()


def test_validate_stack_combo_multiple_fullstack():
    err = preflight.validate_stack_combo([], [], ["next", "nuxt"], [])
    assert err is not None and "fullstack" in err.lower()


def test_validate_stack_combo_multiple_mobile():
    err = preflight.validate_stack_combo([], [], [], ["rn", "maui"])
    assert err is not None and "mobiles" in err.lower() or "mobile" in err.lower()


def test_validate_stack_combo_valid_returns_none():
    assert preflight.validate_stack_combo(["dot"], ["react"], [], []) is None


def test_get_archi_pattern_bullet_md_syntax():
    block = "## Active Architecture Pattern\n- .claude/stacks/archi/ddd.md\n"
    val, explicit = preflight.get_archi_pattern(block)
    assert val == "DDD"
    assert explicit is True


def test_get_archi_pattern_legacy_keyvalue():
    block = "## Active Architecture Pattern\nArchitecturePattern: microservice\n"
    val, explicit = preflight.get_archi_pattern(block)
    assert val == "microservice"
    assert explicit is True


def test_get_archi_pattern_default_when_absent():
    val, explicit = preflight.get_archi_pattern("no archi here")
    assert val == "MVC"
    assert explicit is False


def test_get_archi_pattern_invalid_value():
    block = "## Active Architecture Pattern\nArchitecturePattern: notreal\n"
    val, _ = preflight.get_archi_pattern(block)
    assert val.startswith("INVALID:")


def test_get_archi_pattern_ambiguous_multiple_md():
    block = ("## Active Architecture Pattern\n"
             "- .claude/stacks/archi/mvc.md\n"
             "- .claude/stacks/archi/ddd.md\n")
    val, _ = preflight.get_archi_pattern(block)
    assert val.startswith("AMBIGUOUS:")


def test_get_explicit_app_type_legacy_value():
    txt = "## Active App Type\nAppType: mobile-maui\n"
    assert preflight.get_explicit_app_type(txt) == "mobile-maui"


def test_get_explicit_app_type_none_when_absent():
    assert preflight.get_explicit_app_type("nothing here") is None


def test_get_explicit_app_type_invalid_returns_none():
    txt = "## Active App Type\nAppType: invented\n"
    assert preflight.get_explicit_app_type(txt) is None


# ---------- main() — A-checks ----------


def test_main_invalid_arg_returns_1(fake_repo):
    _bootstrap(fake_repo)
    rc, out = _run([
        "--family", "backend", "--arg", "not-an-arg",
        "--workspace-root", str(fake_repo),
    ])
    assert rc == 1
    codes = [e["code"] for e in out["errors"]]
    assert "INVALID_ARG" in codes


def test_main_us_not_found(fake_repo):
    _bootstrap(fake_repo)
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    assert rc == 1
    assert any(e["code"] == "US_NOT_FOUND" for e in out["errors"])


def test_main_us_ambiguous(fake_repo):
    _bootstrap(fake_repo, us=["1-2-A.md", "1-2-B.md"])
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    assert rc == 1
    codes = [e["code"] for e in out["errors"]]
    assert "US_AMBIGUOUS" in codes


def test_main_stack_missing(fake_repo):
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    assert rc == 1
    assert any(e["code"] == "STACK_MISSING" for e in out["errors"])


def test_main_html_ambiguous_frontend(fake_repo):
    _bootstrap(fake_repo, us=["1-2-Foo.md"],
               html=["1-2-A.html", "1-2-B.html"])
    rc, out = _run([
        "--family", "frontend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    codes = [e["code"] for e in out["errors"]]
    assert "HTML_AMBIGUOUS" in codes


def test_main_plan_only_flag_parsed(fake_repo):
    _bootstrap(fake_repo, us=["1-2-Foo.md"], project_dirs=["ApiSrv"])
    rc, out = _run([
        "--family", "backend", "--arg", "1-2:plan",
        "--workspace-root", str(fake_repo),
    ])
    assert out["planOnly"] is True
    assert out["n"] == 1 and out["m"] == 2
    assert out["name"] == "Foo"


def test_main_happy_path_backend(fake_repo):
    _bootstrap(fake_repo, us=["1-2-Foo.md"], project_dirs=["ApiSrv"])
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    assert rc == 0, out["errors"]
    assert out["ok"] is True
    assert out["appOrBackendName"] == "ApiSrv"
    assert out["appType"] == "back-front"


def test_main_frontend_with_html_records_path(fake_repo):
    _bootstrap(fake_repo, us=["1-2-Foo.md"], html=["1-2-Foo.html"],
               project_dirs=["WebApp"])
    rc, out = _run([
        "--family", "frontend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    assert out["htmlPath"] is not None
    assert "1-2-Foo.html" in out["htmlPath"]


def test_main_missing_appname_in_project_config(fake_repo):
    stack = STACK_OK.replace("AppName: WebApp\n", "")
    _bootstrap(fake_repo, stack=stack, us=["1-2-X.md"])
    rc, out = _run([
        "--family", "frontend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    codes = [e["code"] for e in out["errors"]]
    assert "STACK_MALFORMED" in codes


def test_main_project_claude_md_missing(fake_repo):
    """ApiSrv project dir absent → STACK_DIGEST_MISSING."""
    _bootstrap(fake_repo, us=["1-2-Foo.md"])
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    codes = [e["code"] for e in out["errors"]]
    assert "STACK_DIGEST_MISSING" in codes


def test_main_project_not_init_when_no_project_file(fake_repo):
    """ApiSrv dir exists with CLAUDE.md but no .csproj → PROJECT_NOT_INIT."""
    _bootstrap(fake_repo, us=["1-2-Foo.md"])
    d = fake_repo / "workspace" / "output" / "src" / "ApiSrv"
    d.mkdir(parents=True)
    (d / "CLAUDE.md").write_text("# proj", encoding="utf-8")
    # no project file
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    codes = [e["code"] for e in out["errors"]]
    assert "PROJECT_NOT_INIT" in codes


def test_main_plan_only_downgrades_missing_project_to_warn(fake_repo):
    """In :plan mode, missing project file is WARN-level (still in errors[] with _WARN suffix)."""
    _bootstrap(fake_repo, us=["1-2-Foo.md"])
    rc, out = _run([
        "--family", "backend", "--arg", "1-2:plan",
        "--workspace-root", str(fake_repo),
    ])
    codes = [e["code"] for e in out["errors"]]
    assert "STACK_DIGEST_MISSING_WARN" in codes or "PROJECT_NOT_INIT_WARN" in codes


def test_main_ui_ds_required_when_html_present(fake_repo):
    stack = STACK_OK.replace("- .claude/stacks/ui/shadcn.md", "# - .claude/stacks/ui/shadcn.md")
    _bootstrap(fake_repo, stack=stack, us=["1-2-Foo.md"], html=["1-2-Foo.html"],
               project_dirs=["WebApp"])
    rc, out = _run([
        "--family", "frontend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    codes = [e["code"] for e in out["errors"]]
    assert "UI_DS_NOT_SELECTED" in codes


def test_main_stack_combo_invalid_fullstack_with_backend(fake_repo):
    bad_stack = """\
## Active Tech Specs
- .claude/stacks/backend/dotnet-minimalapi.md
- .claude/stacks/fullstack/next.md

## Active UI Specs

## Active Auth Specs

## Project Config
AppName: WebApp
BackendName: ApiSrv
"""
    _bootstrap(fake_repo, stack=bad_stack, us=["1-2-X.md"], project_dirs=["ApiSrv"])
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    codes = [e["code"] for e in out["errors"]]
    assert "STACK_COMBO_INVALID" in codes


def test_main_archi_pattern_explicit_ddd(fake_repo):
    stack = STACK_OK + "\n## Active Architecture Pattern\n- .claude/stacks/archi/ddd.md\n"
    _bootstrap(fake_repo, stack=stack, us=["1-2-X.md"], project_dirs=["ApiSrv"])
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    assert out["archiPattern"] == "DDD"
    assert out["archiPatternExplicit"] is True


def test_main_archi_pattern_ambiguous_errors(fake_repo):
    stack = STACK_OK + ("\n## Active Architecture Pattern\n"
                        "- .claude/stacks/archi/mvc.md\n"
                        "- .claude/stacks/archi/ddd.md\n")
    _bootstrap(fake_repo, stack=stack, us=["1-2-X.md"], project_dirs=["ApiSrv"])
    rc, out = _run([
        "--family", "backend", "--arg", "1-2",
        "--workspace-root", str(fake_repo),
    ])
    codes = [e["code"] for e in out["errors"]]
    assert "STACK_MALFORMED" in codes
