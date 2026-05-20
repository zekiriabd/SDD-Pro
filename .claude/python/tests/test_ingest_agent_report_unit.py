"""Unit tests for ingest_agent_report.py (direct import).

Covers the 7 report types (a11y, code-review, security-scan, threat-model,
performance, spec-compliance, api-tests, arch-review) and the error paths
(missing file, bad JSON, root-not-dict, unsupported type).

Strategy: synthesize a minimal JSON report per type, run main() with
SDD_REPO_ROOT redirected to tmp, assert (a) DB rows exist, (b) JSON
file deleted by default unless --keep-json.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import ingest_agent_report as iar  # noqa: E402


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    yield tmp_path


def _db(repo: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(repo / "workspace" / "output" / "db" / "console.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _write_report(repo: Path, report_type: str, feat: int, body: dict) -> Path:
    """Write a JSON report at the canonical path for the given type."""
    path = iar.default_path(report_type, feat, repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


# ---------- default_path ----------


def test_default_path_a11y(tmp_path):
    p = iar.default_path("a11y", 3, tmp_path)
    assert p.name == "a11y-report.json"
    assert "feat-3" in str(p)


def test_default_path_code_review(tmp_path):
    p = iar.default_path("code-review", 5, tmp_path)
    assert p.name == "5-code-review.json"


def test_default_path_threat_model(tmp_path):
    p = iar.default_path("threat-model", 7, tmp_path)
    assert p.name == "7-threat-model.json"


def test_default_path_api_tests(tmp_path):
    p = iar.default_path("api-tests", 2, tmp_path)
    assert p.name == "api-tests.json"


# ---------- _flatten_issues ----------


def test_flatten_issues_already_list_passthrough():
    items = [{"a": 1}, "ignored", {"b": 2}]
    out = iar._flatten_issues(items)
    assert out == [{"a": 1}, {"b": 2}]


def test_flatten_issues_severity_nested_shape_injects_severity():
    node = {
        "critical": {"items": [{"id": "X"}]},
        "serious":  {"items": [{"id": "Y", "severity": "explicit"}]},
        "moderate": {"items": []},
        "minor":    "not a dict — skipped",
    }
    out = iar._flatten_issues(node)
    # X gets injected severity=critical, Y keeps its explicit value
    sev = {it["id"]: it["severity"] for it in out}
    assert sev == {"X": "critical", "Y": "explicit"}


def test_flatten_issues_non_dict_returns_empty():
    assert iar._flatten_issues(None) == []
    assert iar._flatten_issues("string") == []


def test_flatten_issues_fallback_nested_dict():
    node = {"region": {"items": [{"x": 1}]}}
    out = iar._flatten_issues(node)
    assert out == [{"x": 1}]


# ---------- main() — error paths ----------


def _run(monkeypatch, args: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["ingest_agent_report.py"] + args)
    return iar.main()


def test_missing_report_returns_1(monkeypatch, fake_repo, capsys):
    rc = _run(monkeypatch, ["--type", "a11y", "--feat", "1"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "[QA_PRECONDITION_FAILED]" in err


def test_bad_json_returns_2(monkeypatch, fake_repo, capsys):
    path = iar.default_path("a11y", 1, fake_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    rc = _run(monkeypatch, ["--type", "a11y", "--feat", "1"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "JSON parse error" in err


def test_non_dict_root_returns_3(monkeypatch, fake_repo, capsys):
    path = iar.default_path("a11y", 1, fake_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    rc = _run(monkeypatch, ["--type", "a11y", "--feat", "1"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "must be a JSON object" in err


# ---------- main() — happy paths per type ----------


def test_ingest_a11y_inserts_rows(monkeypatch, fake_repo):
    body = {
        "summary": {"verdict": "warn"},
        "issues": {
            "critical": {"items": [
                {"file": "x.tsx", "line": 10, "rule": "img-alt", "message": "no alt",
                 "issue_class": "[A11Y_MISSING_ALT]"},
            ]},
            "moderate": {"items": [
                {"file": "y.tsx", "line": 20, "rule": "heading-skip",
                 "message": "h1 to h3", "issue_class": "[A11Y_HEADING_SKIP]"},
            ]},
        },
    }
    path = _write_report(fake_repo, "a11y", 1, body)
    rc = _run(monkeypatch, ["--type", "a11y", "--feat", "1"])
    assert rc == 0
    assert not path.exists()  # deleted by default
    with _db(fake_repo) as conn:
        rows = conn.execute("SELECT * FROM qa_a11y WHERE feat_n = 1").fetchall()
        assert len(rows) == 2
        verdicts = {r["verdict"] for r in rows}
        assert "warn" in verdicts


def test_ingest_keep_json_preserves_file(monkeypatch, fake_repo):
    body = {"issues": [], "summary": {"verdict": "green"}}
    path = _write_report(fake_repo, "a11y", 2, body)
    rc = _run(monkeypatch, ["--type", "a11y", "--feat", "2", "--keep-json"])
    assert rc == 0
    assert path.exists()


def test_ingest_code_review_inserts_rows(monkeypatch, fake_repo):
    body = {
        "summary": {"verdict": "red"},
        "issues": [
            {"file": "Foo.cs", "line": 12, "issue_class": "[LAYER_VIOLATION]",
             "severity": "serious", "message": "DbContext in UI"},
        ],
    }
    _write_report(fake_repo, "code-review", 1, body)
    rc = _run(monkeypatch, ["--type", "code-review", "--feat", "1"])
    assert rc == 0
    with _db(fake_repo) as conn:
        rows = conn.execute("SELECT * FROM qa_code_review WHERE feat_n = 1").fetchall()
        assert len(rows) == 1


def test_ingest_security_scan(monkeypatch, fake_repo):
    body = {
        "summary": {"verdict": "red"},
        "findings": [
            {"file": "Auth.cs", "line": 5, "issue_class": "[SEC_BROKEN_AUTHZ]",
             "severity": "critical", "message": "no [Authorize]"},
        ],
    }
    _write_report(fake_repo, "security-scan", 1, body)
    rc = _run(monkeypatch, ["--type", "security-scan", "--feat", "1"])
    assert rc == 0
    with _db(fake_repo) as conn:
        rows = conn.execute(
            "SELECT * FROM qa_security WHERE feat_n = 1 AND mode = 'scan'"
        ).fetchall()
        assert len(rows) == 1


def test_ingest_threat_model_uses_stride(monkeypatch, fake_repo):
    body = {
        "threats": [
            {"id": "T1", "category": "Spoofing", "scenario": "stolen JWT"},
            {"id": "T2", "category": "Tampering", "description": "modify body"},
        ],
    }
    _write_report(fake_repo, "threat-model", 4, body)
    rc = _run(monkeypatch, ["--type", "threat-model", "--feat", "4"])
    assert rc == 0
    with _db(fake_repo) as conn:
        rows = conn.execute(
            "SELECT * FROM qa_security WHERE feat_n = 4 AND mode = 'threat-model'"
        ).fetchall()
        assert len(rows) == 2
        classes = {r["issue_class"] for r in rows}
        assert "SEC_THREAT_T1" in classes


def test_ingest_performance(monkeypatch, fake_repo):
    body = {
        "summary": {"verdict": "warn"},
        "issues": [{"issue_class": "[PERF_LCP_TOO_HIGH]", "severity": "critical",
                    "file": "Home.tsx", "message": "LCP 3.4s"}],
    }
    _write_report(fake_repo, "performance", 1, body)
    rc = _run(monkeypatch, ["--type", "performance", "--feat", "1"])
    assert rc == 0
    with _db(fake_repo) as conn:
        rows = conn.execute("SELECT * FROM qa_performance WHERE feat_n = 1").fetchall()
        assert len(rows) == 1


def test_ingest_spec_compliance_flattens_us_acs(monkeypatch, fake_repo):
    body = {
        "us": [
            {"us_id": "1-1", "acs": [
                {"ac_id": "AC-1", "ac_text": "user can login",
                 "status": "verified", "severity": "info",
                 "evidence": {"file": "Login.cs", "lines": [42, 50]}},
                {"ac_id": "AC-2", "ac_text": "wrong pw rejected",
                 "status": "not_verified", "severity": "critical",
                 "evidence": {"file": None}},
            ]},
            {"us_id": "1-2", "acs": [
                {"ac_id": "AC-1", "status": "verified",
                 "evidence": {"file": "Reset.cs", "line": 7}},
            ]},
            {"us_id": None, "acs": [{"ac_id": "X"}]},  # skipped (no us_id)
        ],
    }
    _write_report(fake_repo, "spec-compliance", 1, body)
    rc = _run(monkeypatch, ["--type", "spec-compliance", "--feat", "1"])
    assert rc == 0
    with _db(fake_repo) as conn:
        rows = conn.execute(
            "SELECT * FROM qa_spec_compliance WHERE feat_n = 1"
        ).fetchall()
        assert len(rows) == 3


def test_ingest_api_tests(monkeypatch, fake_repo):
    body = {
        "summary": {"gate_passed": True, "endpoints_total": 2,
                    "tests_total": 12, "tests_passed": 12, "tests_failed": 0},
        "endpoints": [
            {"verb": "GET", "route": "/api/x", "tests": {"total": 6, "passed": 6, "failed": 0}},
            {"verb": "POST", "route": "/api/y", "tests": {"total": 6, "passed": 6, "failed": 0}},
        ],
    }
    _write_report(fake_repo, "api-tests", 1, body)
    rc = _run(monkeypatch, ["--type", "api-tests", "--feat", "1"])
    assert rc == 0


def test_ingest_arch_review_routes_to_code_review_table(monkeypatch, fake_repo):
    body = {
        "summary": {"verdict": "warn"},
        "issues": [{"file": "Foo.cs", "line": 1, "issue_class": "[ARCH_PATTERN_VIOLATION]",
                    "severity": "moderate", "message": "Aggregate without Port"}],
    }
    _write_report(fake_repo, "arch-review", 1, body)
    rc = _run(monkeypatch, ["--type", "arch-review", "--feat", "1"])
    assert rc == 0
    with _db(fake_repo) as conn:
        rows = conn.execute(
            "SELECT * FROM qa_code_review WHERE feat_n = 1 "
            "AND issue_class LIKE 'ARCH_%' OR issue_class LIKE '[ARCH_%'"
        ).fetchall()
        assert len(rows) >= 1


def test_ingest_replace_clears_previous_rows(monkeypatch, fake_repo):
    """A second ingest of the same feat must REPLACE prior rows."""
    body1 = {"summary": {"verdict": "red"},
             "issues": [{"file": "a.tsx", "line": 1, "issue_class": "[A11Y_MISSING_ALT]",
                         "severity": "critical", "message": "first"}]}
    _write_report(fake_repo, "a11y", 9, body1)
    _run(monkeypatch, ["--type", "a11y", "--feat", "9"])
    body2 = {"summary": {"verdict": "green"},
             "issues": [{"file": "b.tsx", "line": 2, "issue_class": "[A11Y_LANG_MISSING]",
                         "severity": "serious", "message": "second"}]}
    _write_report(fake_repo, "a11y", 9, body2)
    _run(monkeypatch, ["--type", "a11y", "--feat", "9"])
    with _db(fake_repo) as conn:
        rows = conn.execute("SELECT message FROM qa_a11y WHERE feat_n = 9").fetchall()
        assert len(rows) == 1
        assert rows[0]["message"] == "second"


def test_ingest_custom_path_override(monkeypatch, fake_repo, tmp_path):
    custom = tmp_path / "custom-report.json"
    custom.write_text(json.dumps({"issues": [], "summary": {"verdict": "green"}}), encoding="utf-8")
    rc = _run(monkeypatch, ["--type", "a11y", "--feat", "1", "--path", str(custom)])
    assert rc == 0
    assert not custom.exists()


def test_ingest_db_insert_failure_returns_3(monkeypatch, fake_repo, capsys):
    """Force an exception inside the ingest function → exit code 3."""
    def boom(*a, **kw):
        raise RuntimeError("simulated")
    monkeypatch.setattr(iar, "ingest_a11y", boom)
    _write_report(fake_repo, "a11y", 1, {"issues": []})
    rc = _run(monkeypatch, ["--type", "a11y", "--feat", "1"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "DB insert failed" in err
