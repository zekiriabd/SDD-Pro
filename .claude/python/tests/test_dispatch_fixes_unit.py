"""Unit tests for dispatch_fixes.py + triage_issues.py (direct import).

Pre-populates console.db with synthetic qa_quality / qa_a11y / qa_code_review
rows then drives build_plan() and main() to validate:
- whitelist filtering (FIXABLE_* dicts)
- severity caps (max_sev gate)
- ESCALATE_ONLY_CLASSES exclusion
- owner classification via triage_issues.classify_path
- JSON output + dry-run + fixlist files written
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import dispatch_fixes as df  # noqa: E402
from sdd_scripts import triage_issues as ti  # noqa: E402


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    # Minimal stack.md so load_project_names() finds AppName/BackendName
    stack_dir = tmp_path / "workspace" / "input" / "stack"
    stack_dir.mkdir(parents=True)
    (stack_dir / "stack.md").write_text(
        "## Project Config\n"
        "AppName: WebApp\n"
        "BackendName: ApiSrv\n"
        "LibName: Shared\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    yield tmp_path


def _seed(repo: Path, table: str, rows: list[dict]) -> None:
    """Insert synthetic rows into console.db (auto-injects required fields + FK feats)."""
    from sdd_lib.console_db import connect, ensure_feat_row, ensure_initialized
    ensure_initialized()
    with connect() as conn:
        # Ensure FK targets exist for every distinct feat_n referenced.
        for n in {r["feat_n"] for r in rows if "feat_n" in r}:
            ensure_feat_row(conn, feat_n=n)
        for r in rows:
            r.setdefault("extracted_at", "2026-05-19T12:00:00Z")
            cols = ",".join(r.keys())
            placeholders = ",".join("?" * len(r))
            conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                tuple(r.values()),
            )


# ---------- triage_issues.classify_path ----------


def test_classify_path_backend(fake_repo):
    names = ti.load_project_names()
    assert ti.classify_path("workspace/output/src/ApiSrv/Foo.cs", names) == "backend"


def test_classify_path_frontend(fake_repo):
    names = ti.load_project_names()
    assert ti.classify_path("workspace/output/src/WebApp/src/Home.tsx", names) == "frontend"


def test_classify_path_shared(fake_repo):
    names = ti.load_project_names()
    assert ti.classify_path("workspace/output/src/Shared/Dto.cs", names) == "shared"


def test_classify_path_unknown_outside_src(fake_repo):
    names = ti.load_project_names()
    assert ti.classify_path("docs/README.md", names) == "unknown"


def test_classify_path_unknown_unknown_project(fake_repo):
    names = ti.load_project_names()
    assert ti.classify_path("workspace/output/src/OtherProj/X.cs", names) == "unknown"


def test_classify_path_normalizes_backslashes(fake_repo):
    names = ti.load_project_names()
    assert ti.classify_path(r"workspace\output\src\ApiSrv\Foo.cs", names) == "backend"


def test_classify_path_strips_absolute_prefix(fake_repo):
    names = ti.load_project_names()
    p = "/c/repo/workspace/output/src/ApiSrv/Foo.cs"
    assert ti.classify_path(p, names) == "backend"


def test_classify_batch_groups_by_owner(fake_repo):
    names = ti.load_project_names()
    issues = [
        {"file_path": "workspace/output/src/ApiSrv/A.cs"},
        {"file_path": "workspace/output/src/WebApp/B.tsx"},
        {"file_path": "workspace/output/src/Shared/C.cs"},
        {"file_path": "elsewhere/D.md"},
        {"file_path": ""},
    ]
    buckets = ti.classify_batch(issues, names)
    assert len(buckets["backend"]) == 1
    assert len(buckets["frontend"]) == 1
    assert len(buckets["shared"]) == 1
    assert len(buckets["unknown"]) == 2


def test_summarize_buckets(fake_repo):
    buckets = {"backend": [{"a": 1}], "frontend": [], "shared": [], "unknown": [{"x": 1}, {"y": 2}]}
    s = ti.summarize_buckets(buckets)
    assert s == {"backend": 1, "frontend": 0, "shared": 0, "unknown": 2}


# ---------- _is_class_fixable ----------


def test_is_class_fixable_quality_rule_matches():
    ok, hint = df._is_class_fixable("", "hex-hardcoded", "moderate")
    assert ok is True
    assert hint and "token" in hint.lower()


def test_is_class_fixable_quality_rule_severity_too_high():
    """hex-hardcoded capped at moderate — serious should be rejected."""
    ok, _ = df._is_class_fixable("", "hex-hardcoded", "serious")
    assert ok is False


def test_is_class_fixable_a11y_class():
    ok, hint = df._is_class_fixable("[A11Y_MISSING_ALT]", None, "critical")
    assert ok is True
    assert "alt" in hint.lower()


def test_is_class_fixable_code_review_class():
    ok, _ = df._is_class_fixable("[REVIEW_ANTI_PATTERN_KEY_INDEX]", None, "moderate")
    assert ok is True


def test_is_class_fixable_escalate_only_returns_false():
    ok, hint = df._is_class_fixable("[SEC_SQL_INJECTION]", None, "critical")
    assert ok is False
    assert hint is None


def test_is_class_fixable_unknown_returns_false():
    ok, _ = df._is_class_fixable("[UNKNOWN_CLASS]", None, "minor")
    assert ok is False


# ---------- build_plan ----------


def test_build_plan_empty_db_returns_zero(fake_repo):
    # build_plan() does NOT auto-init (main() does), so we must bootstrap
    # the schema once to keep the empty-DB scenario realistic.
    from sdd_lib.console_db import ensure_initialized
    ensure_initialized()
    plan = df.build_plan(99, dry_run=True)
    assert plan.feat_n == 99
    assert plan.total_findings == 0
    assert plan.auto_fixable == 0
    assert plan.escalated == 0


def test_build_plan_filters_to_fixable_and_groups_by_owner(fake_repo):
    _seed(fake_repo, "qa_quality", [
        {"feat_n": 1, "severity": "moderate", "issue_class": "",
         "rule": "hex-hardcoded", "file_path": "workspace/output/src/WebApp/Home.tsx",
         "line": 10, "message": "color #fff"},
        {"feat_n": 1, "severity": "info", "issue_class": "",
         "rule": "commented-code", "file_path": "workspace/output/src/ApiSrv/Foo.cs",
         "line": 20, "message": "dead block"},
    ])
    plan = df.build_plan(1, dry_run=True)
    assert plan.total_findings == 2
    assert plan.auto_fixable == 2
    assert "frontend" in plan.by_owner
    assert "backend" in plan.by_owner
    assert len(plan.by_owner["frontend"]) == 1
    assert len(plan.by_owner["backend"]) == 1


def test_build_plan_counts_escalated(fake_repo):
    _seed(fake_repo, "qa_security", [
        {"feat_n": 1, "mode": "scan", "severity": "critical",
         "issue_class": "[SEC_SQL_INJECTION]",
         "file_path": "workspace/output/src/ApiSrv/X.cs",
         "line": 5, "message": "raw sql"},
    ])
    plan = df.build_plan(1, dry_run=True)
    assert plan.escalated == 1
    assert plan.auto_fixable == 0


def test_build_plan_skips_unowned_paths(fake_repo):
    _seed(fake_repo, "qa_a11y", [
        {"feat_n": 2, "severity": "critical", "issue_class": "[A11Y_MISSING_ALT]",
         "file_path": "/somewhere/else/img.tsx", "line": 1, "message": "no alt"},
    ])
    plan = df.build_plan(2, dry_run=True)
    # Counted in total but skipped as unowned
    assert plan.total_findings == 1
    assert plan.auto_fixable == 0
    assert plan.skipped_unowned == 1


def test_build_plan_skips_findings_without_file_path(fake_repo):
    _seed(fake_repo, "qa_quality", [
        {"feat_n": 3, "severity": "moderate", "issue_class": "",
         "rule": "hex-hardcoded", "file_path": None, "line": None,
         "message": "no path"},
    ])
    plan = df.build_plan(3, dry_run=True)
    # row counted in total but not appended (no file_path)
    assert plan.total_findings == 1
    assert plan.auto_fixable == 0


def test_build_plan_writes_fixlist_files_when_not_dry_run(fake_repo):
    _seed(fake_repo, "qa_a11y", [
        {"feat_n": 1, "severity": "critical", "issue_class": "[A11Y_MISSING_ALT]",
         "file_path": "workspace/output/src/WebApp/Img.tsx", "line": 3,
         "message": "no alt"},
    ])
    plan = df.build_plan(1, dry_run=False)
    fix_dir = fake_repo / df.FIXLIST_DIR
    fixlist = fix_dir / "1-frontend.json"
    assert fixlist.is_file()
    payload = json.loads(fixlist.read_text(encoding="utf-8"))
    assert payload["owner"] == "frontend"
    assert payload["agent"] == "dev-frontend"
    assert len(payload["items"]) == 1


def test_build_plan_replaces_stale_fixlists(fake_repo):
    fix_dir = fake_repo / df.FIXLIST_DIR
    fix_dir.mkdir(parents=True)
    stale = fix_dir / "5-frontend.json"
    stale.write_text("stale content", encoding="utf-8")
    _seed(fake_repo, "qa_a11y", [
        {"feat_n": 5, "severity": "critical", "issue_class": "[A11Y_MISSING_ALT]",
         "file_path": "workspace/output/src/WebApp/X.tsx", "line": 1, "message": "x"},
    ])
    df.build_plan(5, dry_run=False)
    # Stale file replaced by the new payload
    content = stale.read_text(encoding="utf-8")
    assert content.strip().startswith("{")
    payload = json.loads(content)
    assert payload["owner"] == "frontend"


# ---------- main() CLI ----------


def _run(monkeypatch, args: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["dispatch_fixes.py"] + args)
    return df.main()


def test_main_no_fixable_returns_1(monkeypatch, fake_repo, capsys):
    rc = _run(monkeypatch, ["--feat-number", "1"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "No auto-fixable" in out or "FEAT 1" in out


def test_main_with_fixable_returns_0(monkeypatch, fake_repo, capsys):
    _seed(fake_repo, "qa_quality", [
        {"feat_n": 1, "severity": "moderate", "issue_class": "",
         "rule": "hex-hardcoded",
         "file_path": "workspace/output/src/WebApp/Home.tsx",
         "line": 10, "message": "#fff"},
    ])
    rc = _run(monkeypatch, ["--feat-number", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "FEAT 1" in out


def test_main_json_output(monkeypatch, fake_repo, capsys):
    _seed(fake_repo, "qa_a11y", [
        {"feat_n": 2, "severity": "critical", "issue_class": "[A11Y_MISSING_ALT]",
         "file_path": "workspace/output/src/WebApp/img.tsx",
         "line": 1, "message": "alt"},
    ])
    rc = _run(monkeypatch, ["--feat-number", "2", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["feat_n"] == 2
    assert payload["auto_fixable"] >= 1


def test_main_dry_run_does_not_write_fixlist(monkeypatch, fake_repo, capsys):
    _seed(fake_repo, "qa_a11y", [
        {"feat_n": 3, "severity": "critical", "issue_class": "[A11Y_MISSING_ALT]",
         "file_path": "workspace/output/src/WebApp/img.tsx",
         "line": 1, "message": "alt"},
    ])
    rc = _run(monkeypatch, ["--feat-number", "3", "--dry-run"])
    assert rc == 0
    assert not (fake_repo / df.FIXLIST_DIR / "3-frontend.json").exists()


def test_render_human_no_fixable():
    from sdd_scripts.dispatch_fixes import DispatchPlan, render_human
    plan = DispatchPlan(feat_n=1, extracted_at="now", total_findings=0,
                        auto_fixable=0, escalated=0, skipped_unowned=0)
    out = render_human(plan)
    assert "No auto-fixable" in out


def test_render_human_with_items():
    from sdd_scripts.dispatch_fixes import DispatchPlan, FixableFinding, render_human
    plan = DispatchPlan(
        feat_n=1, extracted_at="now", total_findings=5, auto_fixable=2,
        escalated=1, skipped_unowned=0,
        by_owner={"frontend": [
            FixableFinding("a11y", "[A11Y_MISSING_ALT]", None, "critical",
                           "x.tsx", 10, "no alt", "Add alt", owner="frontend"),
            FixableFinding("a11y", "[A11Y_BUTTON_NO_LABEL]", None, "serious",
                           "y.tsx", 20, "no aria", "Add aria-label", owner="frontend"),
        ]},
        issue_list_paths={"frontend": "path/to/1-frontend.json"},
    )
    out = render_human(plan)
    assert "frontend" in out
    assert "dev-frontend" in out
    assert "1-frontend.json" in out
