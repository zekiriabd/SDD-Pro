"""Unit tests for gate_decide.py (direct import, contributes to coverage).

Complement of test_gate_decide.py which uses subprocess (integration only —
subprocess coverage tracking via sitecustomize fails on Windows even with
COVERAGE_PROCESS_START set, so the existing tests show as 0% covered).

These tests import gate_decide directly, monkeypatching sys.argv to drive
main() and using SDD_REPO_ROOT env override to isolate console.db side
effects to a tmp directory.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure .claude/python/ is on sys.path (conftest also does this).
_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import gate_decide  # noqa: E402


# ---------- fixtures ----------


@pytest.fixture()
def isolated_repo(tmp_path, monkeypatch):
    """Tmp repo with .claude/ marker + SDD_REPO_ROOT override.

    Makes console.db side effects atterrir dans tmp_path/workspace/output/db/.
    """
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    yield tmp_path


@pytest.fixture()
def status_path(tmp_path):
    return tmp_path / "status.json"


# ---------- pure helpers (no DB, no FS lock) ----------


def test_read_status_returns_skeleton_when_file_missing(tmp_path):
    p = tmp_path / "absent.json"
    out = gate_decide.read_status(p)
    assert out["version"] == 1
    assert out["FEATs"] == {}
    assert out["gates"] == {}
    assert "updatedAt" in out


def test_read_status_returns_skeleton_when_empty(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("", encoding="utf-8")
    out = gate_decide.read_status(p)
    assert out["FEATs"] == {} and out["gates"] == {}


def test_read_status_returns_skeleton_when_whitespace(tmp_path):
    p = tmp_path / "ws.json"
    p.write_text("   \n  ", encoding="utf-8")
    out = gate_decide.read_status(p)
    assert out["gates"] == {}


def test_read_status_recovers_from_corrupt_json(tmp_path):
    p = tmp_path / "corrupt.json"
    p.write_text("{not json", encoding="utf-8")
    out = gate_decide.read_status(p)
    assert out["version"] == 1
    assert out["gates"] == {}


def test_read_status_recovers_when_top_level_not_dict(tmp_path):
    p = tmp_path / "list.json"
    p.write_text('[1, 2, 3]', encoding="utf-8")
    out = gate_decide.read_status(p)
    assert isinstance(out, dict)
    assert out["gates"] == {}


def test_read_status_preserves_existing_gates(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text(json.dumps({"version": 1, "gates": {"1": {"afterUS": {"decision": "validated"}}}}), encoding="utf-8")
    out = gate_decide.read_status(p)
    assert out["gates"]["1"]["afterUS"]["decision"] == "validated"


def test_write_status_atomic_replace_and_sets_updatedAt(tmp_path):
    p = tmp_path / "out.json"
    status = {"version": 1, "FEATs": {}, "gates": {}}
    gate_decide.write_status(p, status)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "updatedAt" in data
    # tmp file should be cleaned up
    assert not list(tmp_path.glob("*.tmp.*"))


def test_ensure_gate_creates_nested_dicts():
    status = {"version": 1, "gates": {}}
    g = gate_decide.ensure_gate(status, "1", "afterUS")
    assert g == {}
    assert status["gates"]["1"]["afterUS"] is g
    # Mutating the returned dict reflects in status
    g["decision"] = "pending"
    assert status["gates"]["1"]["afterUS"]["decision"] == "pending"


def test_ensure_gate_idempotent_returns_existing():
    status = {"version": 1, "gates": {"2": {"afterPlan": {"decision": "validated"}}}}
    g = gate_decide.ensure_gate(status, "2", "afterPlan")
    assert g["decision"] == "validated"


def test_get_gate_returns_none_when_gates_missing():
    assert gate_decide.get_gate({"version": 1}, "1", "afterUS") is None


def test_get_gate_returns_none_when_gates_not_dict():
    assert gate_decide.get_gate({"gates": "broken"}, "1", "afterUS") is None


def test_get_gate_returns_none_when_feat_key_missing():
    assert gate_decide.get_gate({"gates": {"2": {}}}, "1", "afterUS") is None


def test_get_gate_returns_none_when_feat_not_dict():
    assert gate_decide.get_gate({"gates": {"1": "bad"}}, "1", "afterUS") is None


def test_get_gate_returns_none_when_phase_missing():
    assert gate_decide.get_gate({"gates": {"1": {"afterPlan": {"decision": "validated"}}}}, "1", "afterUS") is None


def test_get_gate_returns_dict_when_present():
    g = gate_decide.get_gate({"gates": {"1": {"afterUS": {"decision": "validated"}}}}, "1", "afterUS")
    assert g == {"decision": "validated"}


def test_get_gate_returns_none_when_phase_not_dict():
    assert gate_decide.get_gate({"gates": {"1": {"afterUS": "broken"}}}, "1", "afterUS") is None


# ---------- main() — drive via sys.argv monkeypatching ----------


def _run_main(monkeypatch, args: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["gate_decide.py"] + args)
    return gate_decide.main()


def test_main_read_none_when_file_missing(monkeypatch, capsys, isolated_repo, status_path):
    rc = _run_main(monkeypatch, [
        "read", "--feat-num", "1", "--phase", "afterUS",
        "--status-file", str(status_path),
    ])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "none"


def test_main_read_json_when_file_missing(monkeypatch, capsys, isolated_repo, status_path):
    rc = _run_main(monkeypatch, [
        "read", "--feat-num", "1", "--phase", "afterUS",
        "--status-file", str(status_path), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload == {"decision": "none"}


def test_main_is_resolved_returns_1_when_file_missing(monkeypatch, isolated_repo, status_path):
    rc = _run_main(monkeypatch, [
        "is-resolved", "--feat-num", "1", "--phase", "afterUS",
        "--status-file", str(status_path),
    ])
    assert rc == 1


def test_main_is_resolved_returns_1_when_gate_pending(monkeypatch, isolated_repo, status_path):
    _run_main(monkeypatch, [
        "pose-pending", "--feat-num", "1", "--phase", "afterUS",
        "--status-file", str(status_path),
    ])
    rc = _run_main(monkeypatch, [
        "is-resolved", "--feat-num", "1", "--phase", "afterUS",
        "--status-file", str(status_path),
    ])
    assert rc == 1


def test_main_is_resolved_returns_0_when_validated(monkeypatch, isolated_repo, status_path):
    _run_main(monkeypatch, ["pose-pending", "--feat-num", "1", "--phase", "afterUS", "--status-file", str(status_path)])
    _run_main(monkeypatch, [
        "set", "--feat-num", "1", "--phase", "afterUS",
        "--decision", "validated", "--answered-by", "test@x",
        "--status-file", str(status_path),
    ])
    rc = _run_main(monkeypatch, [
        "is-resolved", "--feat-num", "1", "--phase", "afterUS",
        "--status-file", str(status_path),
    ])
    assert rc == 0


def test_main_is_resolved_returns_0_when_skipped(monkeypatch, isolated_repo, status_path):
    _run_main(monkeypatch, ["pose-pending", "--feat-num", "9", "--phase", "afterPlan", "--status-file", str(status_path)])
    _run_main(monkeypatch, [
        "set", "--feat-num", "9", "--phase", "afterPlan",
        "--decision", "skipped", "--answered-by", "user@y",
        "--status-file", str(status_path),
    ])
    rc = _run_main(monkeypatch, [
        "is-resolved", "--feat-num", "9", "--phase", "afterPlan",
        "--status-file", str(status_path),
    ])
    assert rc == 0


def test_main_pose_pending_creates_gate_with_askedAt(monkeypatch, capsys, isolated_repo, status_path):
    rc = _run_main(monkeypatch, [
        "pose-pending", "--feat-num", "5", "--phase", "afterCode",
        "--status-file", str(status_path),
    ])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "pending"
    data = json.loads(status_path.read_text(encoding="utf-8"))
    g = data["gates"]["5"]["afterCode"]
    assert g["decision"] == "pending"
    assert "askedAt" in g
    # answeredAt/By cleared (or absent)
    assert "answeredAt" not in g
    assert "answeredBy" not in g


def test_main_pose_pending_json_output(monkeypatch, capsys, isolated_repo, status_path):
    _run_main(monkeypatch, [
        "pose-pending", "--feat-num", "5", "--phase", "afterCode",
        "--status-file", str(status_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["decision"] == "pending"
    assert "askedAt" in payload


def test_main_set_clears_pending_and_records_answer(monkeypatch, capsys, isolated_repo, status_path):
    _run_main(monkeypatch, ["pose-pending", "--feat-num", "2", "--phase", "afterReadiness", "--status-file", str(status_path)])
    capsys.readouterr()  # clear pose-pending output
    rc = _run_main(monkeypatch, [
        "set", "--feat-num", "2", "--phase", "afterReadiness",
        "--decision", "validated", "--answered-by", "lead@team",
        "--status-file", str(status_path),
    ])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "validated"
    g = json.loads(status_path.read_text(encoding="utf-8"))["gates"]["2"]["afterReadiness"]
    assert g["decision"] == "validated"
    assert g["answeredBy"] == "lead@team"
    assert "answeredAt" in g


def test_main_set_json_output(monkeypatch, capsys, isolated_repo, status_path):
    _run_main(monkeypatch, ["pose-pending", "--feat-num", "3", "--phase", "afterUS", "--status-file", str(status_path)])
    capsys.readouterr()  # clear pose-pending output
    _run_main(monkeypatch, [
        "set", "--feat-num", "3", "--phase", "afterUS",
        "--decision", "skipped", "--answered-by", "x@y",
        "--status-file", str(status_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["decision"] == "skipped"
    assert payload["answeredBy"] == "x@y"


def test_main_read_after_pose_returns_pending(monkeypatch, capsys, isolated_repo, status_path):
    _run_main(monkeypatch, ["pose-pending", "--feat-num", "7", "--phase", "afterUS", "--status-file", str(status_path)])
    capsys.readouterr()  # clear
    rc = _run_main(monkeypatch, [
        "read", "--feat-num", "7", "--phase", "afterUS",
        "--status-file", str(status_path),
    ])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "pending"


def test_main_read_json_returns_full_gate(monkeypatch, capsys, isolated_repo, status_path):
    _run_main(monkeypatch, ["pose-pending", "--feat-num", "7", "--phase", "afterUS", "--status-file", str(status_path)])
    capsys.readouterr()
    _run_main(monkeypatch, [
        "read", "--feat-num", "7", "--phase", "afterUS",
        "--status-file", str(status_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["decision"] == "pending"
    assert "askedAt" in payload


def test_main_invalid_phase_choice_aborts(monkeypatch, isolated_repo, status_path):
    """argparse exits with SystemExit on invalid choice."""
    with pytest.raises(SystemExit):
        _run_main(monkeypatch, [
            "read", "--feat-num", "1", "--phase", "invalidPhase",
            "--status-file", str(status_path),
        ])


def test_iso_now_format():
    """Sanity of the canonical timestamp helper used in askedAt/answeredAt."""
    import re
    from sdd_lib.paths import iso_now
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", iso_now())


def test_acquire_release_lock_roundtrip(tmp_path):
    """acquire_lock + release_lock should not raise on a clean tmp path."""
    lock = tmp_path / ".status.lock"
    gate_decide.acquire_lock(lock)
    assert lock.exists()
    gate_decide.release_lock(lock)
    assert not lock.exists()
