"""Unit tests for ingest_axe.py — axe-core JSON → qa_a11y bridge.

Covers:
    - default rule → class mapping (10 canonical [A11Y_*] classes)
    - fallback class for unknown axe rule id
    - WCAG inference from tags
    - verdict computation against threshold (red/warn/green)
    - exit codes (1 missing file, 2 bad JSON, 3 bad schema, 4 RED gating)
    - --no-fail coerces exit 0 even on RED
    - DB row insertion + auditor_runs presence marker

Strategy: writes synthetic axe-report.json under tmp_path, redirects
SDD_REPO_ROOT, calls main(), asserts (a) exit code, (b) DB rows, (c)
auditor_runs marker.
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

from sdd_scripts import ingest_axe as ia  # noqa: E402


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    yield tmp_path


def _db(repo: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(repo / "workspace" / "output" / "db" / "console.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _write_axe(repo: Path, body) -> Path:
    path = repo / "axe-report.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


# ---------- _classify_violation ----------


def test_classify_known_rule_image_alt():
    cls, sev, wcag = ia._classify_violation("image-alt", "critical", [])
    assert cls == "A11Y_MISSING_ALT"
    assert sev == "critical"
    assert wcag == "1.1.1"


def test_classify_known_rule_button_name():
    cls, sev, wcag = ia._classify_violation("button-name", "serious", [])
    assert cls == "A11Y_BUTTON_NO_LABEL"
    assert sev == "serious"
    assert wcag == "2.4.6"


def test_classify_unknown_rule_fallback_with_wcag_from_tags():
    cls, sev, wcag = ia._classify_violation(
        "color-contrast", "serious", ["cat.color", "wcag2aa", "wcag143"]
    )
    assert cls == "A11Y_RULE_COLOR_CONTRAST"
    assert sev == "serious"
    assert wcag == "1.4.3"


def test_classify_unknown_rule_no_wcag_tags():
    cls, sev, wcag = ia._classify_violation("custom-rule", None, [])
    assert cls == "A11Y_RULE_CUSTOM_RULE"
    assert sev == "moderate"   # default when impact missing
    assert wcag is None


def test_classify_unknown_rule_invalid_impact_falls_back():
    cls, sev, _ = ia._classify_violation("custom-rule", "bogus", [])
    assert sev == "moderate"


# ---------- _infer_wcag_from_tags ----------


def test_infer_wcag_from_tags_basic():
    assert ia._infer_wcag_from_tags(["wcag111"]) == "1.1.1"
    assert ia._infer_wcag_from_tags(["wcag22aa", "wcag255"]) == "2.5.5"
    assert ia._infer_wcag_from_tags(["best-practice"]) is None
    assert ia._infer_wcag_from_tags([]) is None


# ---------- parse_axe_report ----------


def test_parse_axe_report_cli_array_shape():
    report = [{
        "url": "http://localhost:4173",
        "violations": [{
            "id": "image-alt",
            "impact": "critical",
            "tags": ["wcag2a", "wcag111"],
            "help": "Images must have alternate text",
            "nodes": [
                {"target": ["img.hero"], "failureSummary": "Fix all:\n  Element has no alt"},
                {"target": ["img.logo"]},
            ],
        }],
    }]
    issues = ia.parse_axe_report(report)
    assert len(issues) == 2
    assert all(it["issue_class"] == "A11Y_MISSING_ALT" for it in issues)
    assert all(it["severity"] == "critical" for it in issues)
    assert all(it["wcag"] == "1.1.1" for it in issues)
    # Message includes rule id and target
    assert "image-alt" in issues[0]["message"]
    assert "@img.hero" in issues[0]["message"]


def test_parse_axe_report_single_object_shape():
    report = {
        "url": "http://localhost:4173",
        "violations": [{"id": "label", "impact": "critical", "tags": ["wcag131"], "nodes": []}],
    }
    issues = ia.parse_axe_report(report)
    assert len(issues) == 1
    assert issues[0]["issue_class"] == "A11Y_INPUT_NO_LABEL"
    # When no nodes, URL becomes file_path
    assert issues[0]["file_path"] == "http://localhost:4173"


def test_parse_axe_report_invalid_root_raises():
    with pytest.raises(ValueError):
        ia.parse_axe_report("not an object")


def test_parse_axe_report_no_violations_yields_empty():
    assert ia.parse_axe_report({"url": "x", "violations": []}) == []


# ---------- compute_verdict ----------


def test_verdict_green_when_no_issues():
    assert ia.compute_verdict([], "serious") == "green"


def test_verdict_red_when_above_threshold():
    issues = [{"severity": "critical"}]
    assert ia.compute_verdict(issues, "serious") == "red"


def test_verdict_warn_when_below_threshold():
    issues = [{"severity": "minor"}, {"severity": "moderate"}]
    assert ia.compute_verdict(issues, "serious") == "warn"


def test_verdict_red_when_at_threshold():
    issues = [{"severity": "serious"}]
    assert ia.compute_verdict(issues, "serious") == "red"


def test_verdict_respects_lower_threshold():
    issues = [{"severity": "moderate"}]
    assert ia.compute_verdict(issues, "moderate") == "red"


# ---------- main() — exit codes & DB ----------


def test_main_missing_file_exits_1(fake_repo, capsys):
    rc = ia.main(["--report", "nonexistent.json", "--feat", "1"])
    assert rc == 1
    out = capsys.readouterr()
    assert "[QA_PRECONDITION_FAILED]" in out.err


def test_main_bad_json_exits_2(fake_repo, capsys):
    path = fake_repo / "axe-report.json"
    path.write_text("{not json", encoding="utf-8")
    rc = ia.main(["--report", str(path), "--feat", "1"])
    assert rc == 2
    out = capsys.readouterr()
    assert "[QA_OUTPUT_INVALID]" in out.err


def test_main_bad_schema_exits_3(fake_repo, capsys):
    path = _write_axe(fake_repo, "not an object or array")
    rc = ia.main(["--report", str(path), "--feat", "1"])
    assert rc == 3
    out = capsys.readouterr()
    assert "[QA_OUTPUT_INVALID]" in out.err


def test_main_red_verdict_exits_4_and_inserts_rows(fake_repo):
    path = _write_axe(fake_repo, [{
        "url": "http://x",
        "violations": [{
            "id": "image-alt", "impact": "critical", "tags": ["wcag111"],
            "help": "alt required",
            "nodes": [{"target": ["img"], "failureSummary": "no alt"}],
        }],
    }])
    rc = ia.main(["--report", str(path), "--feat", "7"])
    assert rc == 4   # critical violation, default threshold=serious → RED gate

    with _db(fake_repo) as conn:
        rows = list(conn.execute(
            "SELECT issue_class, severity, wcag, verdict FROM qa_a11y WHERE feat_n=7"
        ))
    assert len(rows) == 1
    assert rows[0]["issue_class"] == "A11Y_MISSING_ALT"
    assert rows[0]["severity"] == "critical"
    assert rows[0]["wcag"] == "1.1.1"
    assert rows[0]["verdict"] == "red"


def test_main_red_verdict_with_no_fail_exits_0(fake_repo):
    path = _write_axe(fake_repo, [{
        "url": "http://x",
        "violations": [{
            "id": "image-alt", "impact": "critical", "tags": ["wcag111"],
            "nodes": [{"target": ["img"]}],
        }],
    }])
    rc = ia.main(["--report", str(path), "--feat", "8", "--no-fail"])
    assert rc == 0


def test_main_green_verdict_exits_0(fake_repo):
    path = _write_axe(fake_repo, [{"url": "http://x", "violations": []}])
    rc = ia.main(["--report", str(path), "--feat", "9"])
    assert rc == 0
    with _db(fake_repo) as conn:
        runs = list(conn.execute(
            "SELECT auditor, verdict, findings_count FROM auditor_runs WHERE feat_n=9"
        ))
    assert len(runs) == 1
    assert runs[0]["auditor"] == "a11y"
    assert runs[0]["verdict"] == "green"
    assert runs[0]["findings_count"] == 0


def test_main_warn_below_threshold_exits_0(fake_repo):
    """Minor-only violations → warn verdict → exit 0 (non-bloquant)."""
    path = _write_axe(fake_repo, [{
        "url": "http://x",
        "violations": [{
            "id": "custom-thing", "impact": "minor", "tags": [],
            "nodes": [{"target": ["x"]}],
        }],
    }])
    rc = ia.main(["--report", str(path), "--feat", "10"])
    assert rc == 0
    with _db(fake_repo) as conn:
        verdict = conn.execute(
            "SELECT verdict FROM qa_a11y WHERE feat_n=10 LIMIT 1"
        ).fetchone()["verdict"]
    assert verdict == "warn"


def test_main_replaces_prior_rows(fake_repo):
    """Re-running ingest_axe wipes prior rows for the same FEAT (idempotent)."""
    path = _write_axe(fake_repo, [{
        "url": "http://x",
        "violations": [{"id": "image-alt", "impact": "critical", "tags": ["wcag111"],
                        "nodes": [{"target": ["img1"]}]}],
    }])
    ia.main(["--report", str(path), "--feat", "5", "--no-fail"])

    # Second run with a different violation set
    path.write_text(json.dumps([{
        "url": "http://x",
        "violations": [{"id": "label", "impact": "critical", "tags": ["wcag131"],
                        "nodes": [{"target": ["input1"]}]}],
    }]), encoding="utf-8")
    ia.main(["--report", str(path), "--feat", "5", "--no-fail"])

    with _db(fake_repo) as conn:
        rows = list(conn.execute(
            "SELECT issue_class FROM qa_a11y WHERE feat_n=5"
        ))
    assert len(rows) == 1
    assert rows[0]["issue_class"] == "A11Y_INPUT_NO_LABEL"


def test_main_delete_json_flag_removes_artifact(fake_repo):
    path = _write_axe(fake_repo, [{"url": "x", "violations": []}])
    rc = ia.main(["--report", str(path), "--feat", "11", "--delete-json"])
    assert rc == 0
    assert not path.exists()


def test_main_json_output_format(fake_repo, capsys):
    path = _write_axe(fake_repo, [{"url": "x", "violations": []}])
    rc = ia.main(["--report", str(path), "--feat", "12", "--json"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["feat"] == 12
    assert payload["verdict"] == "green"
    assert payload["source"] == "axe-core"
