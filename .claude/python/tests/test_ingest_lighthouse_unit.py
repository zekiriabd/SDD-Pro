"""Unit tests for ingest_lighthouse.py — Lighthouse JSON → qa_performance.

Covers:
    - Single LHR file vs `.lighthouseci/` directory of N runs
    - Median run picking
    - Audit extraction → [PERF_*] classes against thresholds
    - Threshold overrides via CLI
    - Bundle size tiers (serious vs moderate)
    - Render-blocking resources detail flattening
    - Verdict computation + exit codes (1/2/3/4 + --no-fail)
    - INP fallback to TBT when not present
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

from sdd_scripts import ingest_lighthouse as il  # noqa: E402


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    yield tmp_path


def _db(repo: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(repo / "workspace" / "output" / "db" / "console.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _make_lhr(score=0.9, lcp=2000, cls=0.05, inp=120, ttfb=400,
              total_bytes=300_000, render_blocking=None, url="http://x") -> dict:
    """Build a minimal valid LHR (Lighthouse Result) dict."""
    audits = {
        "largest-contentful-paint": {"numericValue": lcp, "numericUnit": "millisecond"},
        "cumulative-layout-shift":  {"numericValue": cls},
        "interaction-to-next-paint": {"numericValue": inp, "numericUnit": "millisecond"},
        "server-response-time":     {"numericValue": ttfb, "numericUnit": "millisecond"},
        "total-byte-weight":        {"numericValue": total_bytes, "numericUnit": "byte"},
    }
    if render_blocking is not None:
        audits["render-blocking-resources"] = {
            "score": 0.5,
            "details": {"items": render_blocking},
        }
    return {
        "finalDisplayedUrl": url,
        "categories": {"performance": {"score": score}},
        "audits": audits,
    }


def _write_lhr(path: Path, lhr: dict) -> Path:
    path.write_text(json.dumps(lhr), encoding="utf-8")
    return path


# ---------- _gather_lhr_files ----------


def test_gather_lhr_files_single_file(tmp_path):
    p = tmp_path / "lhr.json"
    p.write_text("{}", encoding="utf-8")
    assert il._gather_lhr_files(p) == [p]


def test_gather_lhr_files_directory_with_lhci_pattern(tmp_path):
    d = tmp_path / ".lighthouseci"
    d.mkdir()
    (d / "lhr-1.json").write_text("{}", encoding="utf-8")
    (d / "lhr-2.json").write_text("{}", encoding="utf-8")
    (d / "manifest.json").write_text("{}", encoding="utf-8")
    files = il._gather_lhr_files(d)
    assert len(files) == 2
    assert all(f.name.startswith("lhr-") for f in files)


def test_gather_lhr_files_returns_empty_for_missing_path(tmp_path):
    assert il._gather_lhr_files(tmp_path / "nope") == []


# ---------- _pick_median_lhr ----------


def test_pick_median_lhr_single():
    lhr = {"categories": {"performance": {"score": 0.9}}}
    assert il._pick_median_lhr([lhr]) is lhr


def test_pick_median_lhr_three_runs():
    a = {"categories": {"performance": {"score": 0.5}}, "audits": {}}
    b = {"categories": {"performance": {"score": 0.8}}, "audits": {}}
    c = {"categories": {"performance": {"score": 0.95}}, "audits": {}}
    picked = il._pick_median_lhr([a, c, b])
    # Sorted by score: 0.5, 0.8, 0.95 → median idx 1 → 0.8
    assert picked is b


def test_pick_median_lhr_empty_list_returns_empty_dict():
    assert il._pick_median_lhr([]) == {}


# ---------- extract_issues — thresholds ----------


def test_extract_issues_green_when_metrics_under_threshold():
    lhr = _make_lhr(lcp=1500, cls=0.05, inp=100, ttfb=300, total_bytes=200_000)
    issues = il.extract_issues(lhr, {
        "lcp_ms": 2500, "cls": 0.1, "inp_ms": 200, "ttfb_ms": 600,
        "bundle_kb_serious": 1500, "bundle_kb_moderate": 500,
    })
    assert issues == []


def test_extract_issues_lcp_too_high():
    lhr = _make_lhr(lcp=3000)
    issues = il.extract_issues(lhr, {
        "lcp_ms": 2500, "cls": 0.1, "inp_ms": 200, "ttfb_ms": 600,
        "bundle_kb_serious": 1500, "bundle_kb_moderate": 500,
    })
    lcp_issue = next((i for i in issues if i["issue_class"] == "PERF_LCP_TOO_HIGH"), None)
    assert lcp_issue is not None
    assert lcp_issue["severity"] == "critical"
    assert lcp_issue["metric_value"] == 3000
    assert lcp_issue["metric_unit"] == "ms"


def test_extract_issues_cls_too_high():
    lhr = _make_lhr(cls=0.2)
    issues = il.extract_issues(lhr, {
        "lcp_ms": 2500, "cls": 0.1, "inp_ms": 200, "ttfb_ms": 600,
        "bundle_kb_serious": 1500, "bundle_kb_moderate": 500,
    })
    cls_issue = next((i for i in issues if i["issue_class"] == "PERF_CLS_TOO_HIGH"), None)
    assert cls_issue is not None
    assert cls_issue["severity"] == "serious"


def test_extract_issues_inp_fallback_to_tbt():
    """When interaction-to-next-paint is absent, TBT is used."""
    lhr = _make_lhr()
    del lhr["audits"]["interaction-to-next-paint"]
    lhr["audits"]["total-blocking-time"] = {"numericValue": 300}
    issues = il.extract_issues(lhr, {
        "lcp_ms": 2500, "cls": 0.1, "inp_ms": 200, "ttfb_ms": 600,
        "bundle_kb_serious": 1500, "bundle_kb_moderate": 500,
    })
    inp_issue = next((i for i in issues if i["issue_class"] == "PERF_INP_TOO_HIGH"), None)
    assert inp_issue is not None
    assert inp_issue["metric"] == "TBT"


def test_extract_issues_bundle_serious_tier():
    lhr = _make_lhr(total_bytes=2_000_000)   # ~1953 KB > 1500 KB
    issues = il.extract_issues(lhr, {
        "lcp_ms": 2500, "cls": 0.1, "inp_ms": 200, "ttfb_ms": 600,
        "bundle_kb_serious": 1500, "bundle_kb_moderate": 500,
    })
    bundle = next((i for i in issues if "BUNDLE" in i["issue_class"]), None)
    assert bundle is not None
    assert bundle["issue_class"] == "PERF_BUNDLE_TOO_LARGE"
    assert bundle["severity"] == "serious"


def test_extract_issues_bundle_moderate_tier():
    lhr = _make_lhr(total_bytes=700_000)   # ~684 KB → moderate (500-1500)
    issues = il.extract_issues(lhr, {
        "lcp_ms": 2500, "cls": 0.1, "inp_ms": 200, "ttfb_ms": 600,
        "bundle_kb_serious": 1500, "bundle_kb_moderate": 500,
    })
    bundle = next((i for i in issues if "BUNDLE" in i["issue_class"]), None)
    assert bundle is not None
    assert bundle["issue_class"] == "PERF_BUNDLE_LARGE"
    assert bundle["severity"] == "moderate"


def test_extract_issues_render_blocking_per_item():
    lhr = _make_lhr(render_blocking=[
        {"url": "https://x/a.js", "wastedMs": 250},
        {"url": "https://x/b.css", "wastedMs": 100},
    ])
    issues = il.extract_issues(lhr, {
        "lcp_ms": 2500, "cls": 0.1, "inp_ms": 200, "ttfb_ms": 600,
        "bundle_kb_serious": 1500, "bundle_kb_moderate": 500,
    })
    blocking = [i for i in issues if i["issue_class"] == "PERF_RENDER_BLOCKING"]
    assert len(blocking) == 2
    assert blocking[0]["severity"] == "serious"
    assert "a.js" in blocking[0]["file_path"]
    assert blocking[0]["metric_value"] == 250


# ---------- compute_verdict ----------


def test_verdict_green_when_no_issues():
    assert il.compute_verdict([], "serious") == "green"


def test_verdict_red_for_critical():
    assert il.compute_verdict([{"severity": "critical"}], "serious") == "red"


def test_verdict_warn_for_minor_only():
    assert il.compute_verdict([{"severity": "minor"}], "serious") == "warn"


# ---------- main() — exit codes & DB ----------


def test_main_missing_report_exits_1(fake_repo, capsys):
    rc = il.main(["--report", "nope/", "--feat", "1"])
    assert rc == 1
    assert "[QA_PRECONDITION_FAILED]" in capsys.readouterr().err


def test_main_empty_directory_exits_1(fake_repo, capsys):
    (fake_repo / "empty").mkdir()
    rc = il.main(["--report", str(fake_repo / "empty"), "--feat", "1"])
    assert rc == 1
    assert "no lhr" in capsys.readouterr().err.lower()


def test_main_bad_json_exits_2(fake_repo, capsys):
    path = fake_repo / "lhr.json"
    path.write_text("{garbage", encoding="utf-8")
    rc = il.main(["--report", str(path), "--feat", "1"])
    assert rc == 2
    assert "[QA_OUTPUT_INVALID]" in capsys.readouterr().err


def test_main_bad_schema_no_audits_exits_3(fake_repo, capsys):
    path = _write_lhr(fake_repo / "lhr.json",
                      {"categories": {}, "finalDisplayedUrl": "x"})
    rc = il.main(["--report", str(path), "--feat", "1"])
    assert rc == 3
    assert "missing 'audits'" in capsys.readouterr().err


def test_main_root_not_object_exits_3(fake_repo, capsys):
    path = fake_repo / "lhr.json"
    path.write_text(json.dumps(["not an object"]), encoding="utf-8")
    rc = il.main(["--report", str(path), "--feat", "1"])
    assert rc == 3


def test_main_green_inserts_no_rows_and_records_marker(fake_repo):
    path = _write_lhr(fake_repo / "lhr.json", _make_lhr())
    rc = il.main(["--report", str(path), "--feat", "21"])
    assert rc == 0
    with _db(fake_repo) as conn:
        rows = list(conn.execute("SELECT * FROM qa_performance WHERE feat_n=21"))
        runs = list(conn.execute(
            "SELECT auditor, verdict, findings_count FROM auditor_runs WHERE feat_n=21"
        ))
    assert rows == []
    assert len(runs) == 1
    assert runs[0]["auditor"] == "perf"
    assert runs[0]["verdict"] == "green"
    assert runs[0]["findings_count"] == 0


def test_main_red_verdict_exits_4_and_inserts_rows(fake_repo):
    """A single critical LCP violation should trigger exit 4."""
    path = _write_lhr(fake_repo / "lhr.json", _make_lhr(lcp=4000))
    rc = il.main(["--report", str(path), "--feat", "22"])
    assert rc == 4
    with _db(fake_repo) as conn:
        rows = list(conn.execute(
            "SELECT issue_class, severity, metric, metric_value, verdict "
            "FROM qa_performance WHERE feat_n=22"
        ))
    assert len(rows) == 1
    assert rows[0]["issue_class"] == "PERF_LCP_TOO_HIGH"
    assert rows[0]["severity"] == "critical"
    assert rows[0]["metric"] == "LCP"
    assert rows[0]["metric_value"] == 4000
    assert rows[0]["verdict"] == "red"


def test_main_red_with_no_fail_exits_0(fake_repo):
    path = _write_lhr(fake_repo / "lhr.json", _make_lhr(lcp=4000))
    rc = il.main(["--report", str(path), "--feat", "23", "--no-fail"])
    assert rc == 0


def test_main_directory_with_multiple_runs_picks_median(fake_repo):
    d = fake_repo / ".lighthouseci"
    d.mkdir()
    _write_lhr(d / "lhr-1.json", _make_lhr(score=0.5, lcp=4000))   # bad
    _write_lhr(d / "lhr-2.json", _make_lhr(score=0.8, lcp=2200))   # median
    _write_lhr(d / "lhr-3.json", _make_lhr(score=0.95, lcp=1800))  # best
    rc = il.main(["--report", str(d), "--feat", "24"])
    assert rc == 0   # median has LCP < threshold → green
    with _db(fake_repo) as conn:
        runs = list(conn.execute(
            "SELECT payload_json FROM auditor_runs WHERE feat_n=24"
        ))
    payload = json.loads(runs[0]["payload_json"])
    assert payload["runs"] == 3
    assert payload["source"] == "lighthouse"


def test_main_threshold_override(fake_repo):
    """Lowering --lcp-ms triggers RED on metrics that were green at default."""
    path = _write_lhr(fake_repo / "lhr.json", _make_lhr(lcp=2000))
    rc = il.main(["--report", str(path), "--feat", "25", "--lcp-ms", "1500"])
    assert rc == 4
    with _db(fake_repo) as conn:
        row = conn.execute(
            "SELECT threshold FROM qa_performance WHERE feat_n=25"
        ).fetchone()
    assert row["threshold"] == 1500.0


def test_main_replaces_prior_rows(fake_repo):
    """Re-running ingest_lighthouse wipes prior rows for same FEAT."""
    path = _write_lhr(fake_repo / "lhr.json", _make_lhr(lcp=4000))
    il.main(["--report", str(path), "--feat", "26", "--no-fail"])
    # Second run with clean metrics
    _write_lhr(path, _make_lhr())
    il.main(["--report", str(path), "--feat", "26"])
    with _db(fake_repo) as conn:
        rows = list(conn.execute("SELECT * FROM qa_performance WHERE feat_n=26"))
    assert rows == []   # green run wiped the red one


def test_main_json_output_format(fake_repo, capsys):
    path = _write_lhr(fake_repo / "lhr.json", _make_lhr())
    rc = il.main(["--report", str(path), "--feat", "27", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["feat"] == 27
    assert payload["source"] == "lighthouse"
    assert payload["runs"] == 1
    assert payload["performance_score"] == 0.9
