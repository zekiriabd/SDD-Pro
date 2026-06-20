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


# ---------- adversarial (v7.2.0 R1) ----------


def test_default_path_adversarial(tmp_path):
    p = iar.default_path("adversarial", 4, tmp_path)
    assert p.name == "adversarial.json"
    assert "feat-4" in str(p)


def _make_adversarial(attacks: list[dict] | None = None,
                     coverage_warning: bool = False,
                     verdict: str = "informational") -> dict:
    attacks = attacks or []
    by_angle: dict[str, int] = {}
    for a in attacks:
        angle = a.get("angle") or "edge_case"
        by_angle[angle] = by_angle.get(angle, 0) + 1
    return {
        "feat": 1,
        "extractedAt": "2026-05-24T12:00:00Z",
        "verdict": verdict,
        "min_attacks": 5,
        "max_attacks": 10,
        "summary": {
            "attacks_total": len(attacks),
            "by_angle": by_angle,
            "coverage_warning": coverage_warning,
        },
        "attacks": attacks,
    }


def test_ingest_adversarial_inserts_validation_report(monkeypatch, fake_repo):
    body = _make_adversarial(attacks=[
        {"id": "ADV-1", "issue_class": "ADV_EDGE_CASE",   "angle": "edge_case",
         "file": "x.cs", "line": 12, "scenario": "empty input", "mitigation": "validate"},
        {"id": "ADV-2", "issue_class": "ADV_FAILURE_MODE", "angle": "failure_mode",
         "file": "y.cs", "line": 34, "scenario": "DB down", "mitigation": "circuit breaker"},
    ])
    path = _write_report(fake_repo, "adversarial", 1, body)
    rc = _run(monkeypatch, ["--type", "adversarial", "--feat", "1"])
    assert rc == 0
    # JSON deleted by default
    assert not path.exists()

    with _db(fake_repo) as conn:
        rows = list(conn.execute(
            "SELECT report_type, verdict, score, summary, payload_json, file_path "
            "FROM validation_reports WHERE feat_n=1 AND report_type='adversarial'"
        ))
    assert len(rows) == 1
    row = rows[0]
    assert row["report_type"] == "adversarial"
    assert row["verdict"] == "informational"
    assert row["score"] == 2
    assert "2 attacks" in row["summary"]
    payload = json.loads(row["payload_json"])
    assert len(payload["attacks"]) == 2
    assert payload["attacks"][0]["issue_class"] == "ADV_EDGE_CASE"
    assert payload["summary"]["by_angle"]["edge_case"] == 1
    assert payload["summary"]["by_angle"]["failure_mode"] == 1
    assert payload["summary"]["coverage_warning"] is False


def test_ingest_adversarial_empty_attacks_still_records_row(monkeypatch, fake_repo):
    """A FEAT may legitimately produce 0 adversarial findings — the row
    must still exist so callers can distinguish 'ran with 0 attacks' from
    'never ran'."""
    body = _make_adversarial(attacks=[], coverage_warning=True)
    _write_report(fake_repo, "adversarial", 2, body)
    rc = _run(monkeypatch, ["--type", "adversarial", "--feat", "2"])
    assert rc == 0
    with _db(fake_repo) as conn:
        row = conn.execute(
            "SELECT score, summary FROM validation_reports "
            "WHERE feat_n=2 AND report_type='adversarial'"
        ).fetchone()
    assert row["score"] == 0
    assert "coverage_warning=true" in row["summary"]


def test_ingest_adversarial_idempotent_re_run_replaces(monkeypatch, fake_repo):
    """Re-running ingest wipes the prior validation_reports row for the
    same (feat, report_type='adversarial') — telemetry stays current."""
    _write_report(fake_repo, "adversarial", 3, _make_adversarial(attacks=[
        {"id": "ADV-1", "issue_class": "ADV_EDGE_CASE", "angle": "edge_case"},
        {"id": "ADV-2", "issue_class": "ADV_EDGE_CASE", "angle": "edge_case"},
        {"id": "ADV-3", "issue_class": "ADV_EDGE_CASE", "angle": "edge_case"},
    ]))
    _run(monkeypatch, ["--type", "adversarial", "--feat", "3"])
    # Second run with fewer attacks
    _write_report(fake_repo, "adversarial", 3, _make_adversarial(attacks=[
        {"id": "ADV-1", "issue_class": "ADV_FAILURE_MODE", "angle": "failure_mode"},
    ]))
    _run(monkeypatch, ["--type", "adversarial", "--feat", "3"])
    with _db(fake_repo) as conn:
        rows = list(conn.execute(
            "SELECT score FROM validation_reports "
            "WHERE feat_n=3 AND report_type='adversarial'"
        ))
    assert len(rows) == 1
    assert rows[0]["score"] == 1   # second run overwrote


def test_ingest_adversarial_non_informational_verdict_coerced(
        monkeypatch, fake_repo, capsys):
    """Agent prompt drift safeguard : if the JSON declares a non-
    informational verdict, ingest coerces to 'informational' and emits a
    WARN on stderr (visible to Tech Lead but non-bloquant)."""
    body = _make_adversarial(attacks=[], verdict="red")
    _write_report(fake_repo, "adversarial", 4, body)
    rc = _run(monkeypatch, ["--type", "adversarial", "--feat", "4"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "verdict='red'" in err or "verdict=\"red\"" in err
    with _db(fake_repo) as conn:
        row = conn.execute(
            "SELECT verdict FROM validation_reports "
            "WHERE feat_n=4 AND report_type='adversarial'"
        ).fetchone()
    assert row["verdict"] == "informational"


def test_ingest_adversarial_keep_json_flag(monkeypatch, fake_repo):
    """`--keep-json` retains the source JSON (debugging)."""
    path = _write_report(fake_repo, "adversarial", 5,
                         _make_adversarial(attacks=[]))
    rc = _run(monkeypatch, ["--type", "adversarial", "--feat", "5",
                            "--keep-json"])
    assert rc == 0
    assert path.exists()


def test_ingest_adversarial_not_in_qa_tables(monkeypatch, fake_repo):
    """The adversarial canal is intentionally SEPARATE from qa_* tables —
    /sdd-review consolidated verdict must remain unaffected."""
    _write_report(fake_repo, "adversarial", 6, _make_adversarial(attacks=[
        {"id": "ADV-1", "issue_class": "ADV_FAILURE_MODE", "angle": "failure_mode"},
    ]))
    _run(monkeypatch, ["--type", "adversarial", "--feat", "6"])
    with _db(fake_repo) as conn:
        # No rows in qa_a11y / qa_code_review / qa_security / qa_performance /
        # qa_spec_compliance for this FEAT (only validation_reports).
        for tbl in ("qa_a11y", "qa_code_review", "qa_security",
                    "qa_performance", "qa_spec_compliance"):
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM {tbl} WHERE feat_n=6"
            ).fetchone()
            assert row["n"] == 0, f"{tbl} unexpectedly contains rows for feat 6"
        # And exactly one row in validation_reports
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM validation_reports "
            "WHERE feat_n=6 AND report_type='adversarial'"
        ).fetchone()["n"]
        assert n == 1
