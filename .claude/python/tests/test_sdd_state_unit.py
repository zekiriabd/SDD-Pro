"""Unit tests for sdd_state.py (direct import, contributes to coverage).

Complement of test_sdd_state.py which uses subprocess (integration only).
Same isolation pattern as test_gate_decide_unit.py: SDD_REPO_ROOT env override
+ sys.argv monkeypatching for main() entrypoint.

Note on iso_now_ms() ordering — sdd_state uses millisecond timestamps so
two events in a single test can have identical ts; we explicitly do not
rely on event ordering in assertions.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import sdd_state  # noqa: E402


# ---------- fixtures ----------


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    """Tmp directory with `.claude/` marker + SDD_REPO_ROOT override."""
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    yield tmp_path


@pytest.fixture()
def db_path(fake_repo) -> Path:
    return fake_repo / "workspace" / "output" / "db" / "console.db"


def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _run_main(monkeypatch, args: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["sdd_state.py"] + args)
    return sdd_state.main()


# ---------- parse_payload ----------


def test_parse_payload_empty_returns_none():
    assert sdd_state.parse_payload("") is None


def test_parse_payload_whitespace_returns_none():
    assert sdd_state.parse_payload("   \n  ") is None


def test_parse_payload_valid_json_returns_dict():
    assert sdd_state.parse_payload('{"k": 1}') == {"k": 1}


def test_parse_payload_valid_array_returns_list():
    assert sdd_state.parse_payload("[1, 2]") == [1, 2]


def test_parse_payload_invalid_wraps_as_raw():
    assert sdd_state.parse_payload("not json {") == {"raw": "not json {"}


# ---------- get_feat_name ----------


def test_get_feat_name_returns_none_when_feats_dir_missing(fake_repo):
    assert sdd_state.get_feat_name(1) is None


def test_get_feat_name_returns_name_when_single_match(fake_repo):
    feats = fake_repo / "workspace" / "input" / "feats"
    feats.mkdir(parents=True)
    (feats / "1-Auth.md").write_text("# x", encoding="utf-8")
    assert sdd_state.get_feat_name(1) == "Auth"


def test_get_feat_name_returns_none_when_multiple_matches(fake_repo):
    feats = fake_repo / "workspace" / "input" / "feats"
    feats.mkdir(parents=True)
    (feats / "1-Auth.md").write_text("# x", encoding="utf-8")
    (feats / "1-Login.md").write_text("# y", encoding="utf-8")
    assert sdd_state.get_feat_name(1) is None


def test_get_feat_name_returns_none_when_no_match(fake_repo):
    feats = fake_repo / "workspace" / "input" / "feats"
    feats.mkdir(parents=True)
    (feats / "2-Other.md").write_text("# x", encoding="utf-8")
    assert sdd_state.get_feat_name(1) is None


def test_get_feat_name_complex_name(fake_repo):
    feats = fake_repo / "workspace" / "input" / "feats"
    feats.mkdir(parents=True)
    (feats / "12-Multi-Word-Name.md").write_text("# x", encoding="utf-8")
    assert sdd_state.get_feat_name(12) == "Multi-Word-Name"


# ---------- _row_to_dict ----------


def test_row_to_dict_with_no_phases():
    fake = {
        "run_id": "abc", "feat_n": 1, "feat_name": "X", "command": "/cmd",
        "tags_json": None, "started_at": "T1", "updated_at": "T2",
        "ended_at": None, "status": "running", "current_phase": "x",
    }
    out = sdd_state._row_to_dict(fake)
    assert out["runId"] == "abc"
    assert out["FeatNumber"] == 1
    assert out["tags"] == []
    assert out["phases"] == {}


def test_row_to_dict_with_phases_and_tags():
    fake = {
        "run_id": "abc", "feat_n": 1, "feat_name": "X", "command": "/cmd",
        "tags_json": '["a","b"]', "started_at": "T1", "updated_at": "T2",
        "ended_at": None, "status": "running", "current_phase": "x",
    }
    phases = [
        {"phase": "ph1", "status": "pass", "started_at": "T1", "ended_at": "T2", "payload_json": '{"k":1}'},
        {"phase": "ph2", "status": "running", "started_at": "T3", "ended_at": None, "payload_json": None},
    ]
    out = sdd_state._row_to_dict(fake, phases)
    assert out["tags"] == ["a", "b"]
    assert out["phases"]["ph1"]["status"] == "pass"
    assert out["phases"]["ph1"]["payload"] == {"k": 1}
    assert out["phases"]["ph2"]["payload"] is None


# ---------- action_new_run via main() ----------


def test_new_run_rejects_zero_feat_number(monkeypatch, fake_repo, capsys):
    rc = _run_main(monkeypatch, ["new-run", "--feat-number", "0", "--command", "/x"])
    assert rc == 1
    assert "feat-number" in capsys.readouterr().err.lower()


def test_new_run_returns_runid_and_persists(monkeypatch, fake_repo, db_path, capsys):
    rc = _run_main(monkeypatch, [
        "new-run", "--feat-number", "1", "--command", "/sdd-full", "--tags", "alpha,beta",
    ])
    assert rc == 0
    run_id = capsys.readouterr().out.strip()
    # Sprint 1.1 fix (2026-06-06) : run_id format is now {YYYYMMDDTHHmmss}-{4-hex}
    # (unified with hook telemetry via sdd_lib.run_id.get_or_create_run_id).
    # Accept legacy uuid4().hex[:12] (12-hex) for backward-compat.
    assert re.match(r"^[0-9a-f]{12}$", run_id) or re.match(
        r"^[0-9]{8}T[0-9]{6}-[0-9a-f]{4}$", run_id
    )
    assert db_path.exists()
    with _open_db(db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row["feat_n"] == 1
        assert row["command"] == "/sdd-full"
        assert row["status"] == "running"
        tags = json.loads(row["tags_json"])
        assert tags == ["alpha", "beta"]
        evts = conn.execute(
            "SELECT * FROM events WHERE run_id = ? AND event_type = 'run.start'",
            (run_id,),
        ).fetchall()
        assert len(evts) == 1


def test_new_run_empty_tags_normalized(monkeypatch, fake_repo, db_path, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "2", "--command", "/x", "--tags", ""])
    run_id = capsys.readouterr().out.strip()
    with _open_db(db_path) as conn:
        row = conn.execute("SELECT tags_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        # Tags rendered as either null or [] depending on console_db impl
        assert row["tags_json"] in (None, "[]")


def test_new_run_default_command_when_empty(monkeypatch, fake_repo, db_path, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "3", "--command", ""])
    run_id = capsys.readouterr().out.strip()
    with _open_db(db_path) as conn:
        row = conn.execute("SELECT command FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row["command"] == "unknown"


# ---------- action_set_phase ----------


def test_set_phase_unknown_run_id_returns_1(monkeypatch, fake_repo, capsys):
    # Initialize DB by doing a no-op new-run first (otherwise ensure_initialized creates empty)
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    capsys.readouterr()
    rc = _run_main(monkeypatch, [
        "set-phase", "--run-id", "doesnotexist", "--phase", "ph1", "--status", "start",
    ])
    assert rc == 1
    assert "Unknown runId" in capsys.readouterr().err


def test_set_phase_start_creates_running_phase(monkeypatch, fake_repo, db_path, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run_id = capsys.readouterr().out.strip()
    rc = _run_main(monkeypatch, [
        "set-phase", "--run-id", run_id, "--phase", "backend", "--status", "start",
    ])
    assert rc == 0
    with _open_db(db_path) as conn:
        ph = conn.execute(
            "SELECT * FROM run_phases WHERE run_id = ? AND phase = ?", (run_id, "backend"),
        ).fetchone()
        assert ph["status"] == "running"
        assert ph["started_at"]


def test_set_phase_pass_sets_ended_at(monkeypatch, fake_repo, db_path, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run_id = capsys.readouterr().out.strip()
    _run_main(monkeypatch, [
        "set-phase", "--run-id", run_id, "--phase", "backend", "--status", "start",
    ])
    _run_main(monkeypatch, [
        "set-phase", "--run-id", run_id, "--phase", "backend", "--status", "pass",
        "--payload-json", '{"tests":47}',
    ])
    with _open_db(db_path) as conn:
        ph = conn.execute(
            "SELECT * FROM run_phases WHERE run_id = ? AND phase = ?", (run_id, "backend"),
        ).fetchone()
        assert ph["status"] == "pass"
        assert ph["ended_at"]
        payload = json.loads(ph["payload_json"])
        assert payload["tests"] == 47


def test_set_phase_fail_emits_phase_end_event(monkeypatch, fake_repo, db_path, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run_id = capsys.readouterr().out.strip()
    _run_main(monkeypatch, [
        "set-phase", "--run-id", run_id, "--phase", "qa", "--status", "fail",
    ])
    with _open_db(db_path) as conn:
        evts = conn.execute(
            "SELECT * FROM events WHERE run_id = ? AND event_type = 'phase.end'",
            (run_id,),
        ).fetchall()
        assert len(evts) == 1


# ---------- action_end_run ----------


def test_end_run_unknown_id_returns_1(monkeypatch, fake_repo, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    capsys.readouterr()
    rc = _run_main(monkeypatch, ["end-run", "--run-id", "no-such-id"])
    assert rc == 1


def test_end_run_success_sets_status_and_event(monkeypatch, fake_repo, db_path, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run_id = capsys.readouterr().out.strip()
    rc = _run_main(monkeypatch, ["end-run", "--run-id", run_id, "--status", "success"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ended status=success" in out
    assert "durationMs=" in out
    with _open_db(db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row["status"] == "success"
        assert row["ended_at"]
        evts = conn.execute(
            "SELECT * FROM events WHERE run_id = ? AND event_type = 'run.end'",
            (run_id,),
        ).fetchall()
        assert len(evts) == 1


def test_end_run_failed_status(monkeypatch, fake_repo, db_path, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run_id = capsys.readouterr().out.strip()
    _run_main(monkeypatch, ["end-run", "--run-id", run_id, "--status", "failed"])
    with _open_db(db_path) as conn:
        row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row["status"] == "failed"


# ---------- action_get_run / show-run / list-runs ----------


def test_get_run_returns_1_when_no_runs(monkeypatch, fake_repo, capsys):
    # Ensure DB exists but is empty: do nothing here is enough — ensure_initialized
    # is called implicitly by get-run.
    rc = _run_main(monkeypatch, ["get-run", "--feat-number", "99"])
    assert rc == 1


def test_get_run_latest_returns_most_recent_runid(monkeypatch, fake_repo, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run1 = capsys.readouterr().out.strip()
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run2 = capsys.readouterr().out.strip()
    rc = _run_main(monkeypatch, ["get-run", "--feat-number", "1", "--latest"])
    assert rc == 0
    latest = capsys.readouterr().out.strip()
    # Latest is one of the two — exact ordering depends on iso_now_ms resolution
    assert latest in (run1, run2)


def test_get_run_without_latest_prints_all_runids(monkeypatch, fake_repo, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "2", "--command", "/x"])
    _run_main(monkeypatch, ["new-run", "--feat-number", "2", "--command", "/x"])
    capsys.readouterr()
    _run_main(monkeypatch, ["get-run", "--feat-number", "2"])
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2


def test_show_run_unknown_id_returns_1(monkeypatch, fake_repo, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    capsys.readouterr()
    rc = _run_main(monkeypatch, ["show-run", "--run-id", "no-such-id"])
    assert rc == 1


def test_show_run_prints_full_state_json(monkeypatch, fake_repo, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run_id = capsys.readouterr().out.strip()
    _run_main(monkeypatch, [
        "set-phase", "--run-id", run_id, "--phase", "p1", "--status", "pass",
    ])
    capsys.readouterr()
    _run_main(monkeypatch, ["show-run", "--run-id", run_id])
    state = json.loads(capsys.readouterr().out)
    assert state["runId"] == run_id
    assert state["FeatNumber"] == 1
    assert "p1" in state["phases"]


def test_list_runs_empty_prints_placeholder(monkeypatch, fake_repo, capsys):
    rc = _run_main(monkeypatch, ["list-runs"])
    assert rc == 0
    assert "(no runs)" in capsys.readouterr().out


def test_list_runs_prints_table_with_runs(monkeypatch, fake_repo, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/cmd1"])
    _run_main(monkeypatch, ["new-run", "--feat-number", "2", "--command", "/cmd2"])
    capsys.readouterr()
    _run_main(monkeypatch, ["list-runs"])
    out = capsys.readouterr().out
    assert "runId" in out
    assert "/cmd1" in out and "/cmd2" in out


def test_list_runs_filtered_by_feat(monkeypatch, fake_repo, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/a"])
    _run_main(monkeypatch, ["new-run", "--feat-number", "2", "--command", "/b"])
    capsys.readouterr()
    _run_main(monkeypatch, ["list-runs", "--feat-number", "1"])
    out = capsys.readouterr().out
    assert "/a" in out
    assert "/b" not in out


def test_list_runs_respects_limit(monkeypatch, fake_repo, capsys):
    for _ in range(5):
        _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    capsys.readouterr()
    _run_main(monkeypatch, ["list-runs", "--limit", "2"])
    out = capsys.readouterr().out
    # 1 header line + 1 separator + 2 data rows
    data_lines = [line for line in out.splitlines() if line and "runId" not in line and "----" not in line]
    assert len(data_lines) == 2


# ---------- action_emit_event ----------


def test_emit_event_with_known_run(monkeypatch, fake_repo, db_path, capsys):
    _run_main(monkeypatch, ["new-run", "--feat-number", "1", "--command", "/x"])
    run_id = capsys.readouterr().out.strip()
    rc = _run_main(monkeypatch, [
        "emit-event", "--run-id", run_id, "--event-type", "custom.event",
        "--payload-json", '{"k":1}',
    ])
    assert rc == 0
    with _open_db(db_path) as conn:
        evts = conn.execute(
            "SELECT * FROM events WHERE run_id = ? AND event_type = 'custom.event'",
            (run_id,),
        ).fetchall()
        assert len(evts) == 1
        payload = json.loads(evts[0]["payload_json"])
        assert payload == {"k": 1}


def test_emit_event_with_unknown_run_still_inserts_with_feat_0(monkeypatch, fake_repo, db_path):
    # Need to initialize DB first by triggering a no-op
    from sdd_lib.console_db import ensure_initialized
    ensure_initialized()
    rc = _run_main(monkeypatch, [
        "emit-event", "--run-id", "unknown-id", "--event-type", "orphan.event",
    ])
    assert rc == 0
    with _open_db(db_path) as conn:
        evts = conn.execute(
            "SELECT * FROM events WHERE event_type = 'orphan.event'",
        ).fetchall()
        assert len(evts) == 1
        assert evts[0]["feat_n"] == 0


# ---------- should-skip-step (audit CTO 2026-06-07 — gate shell-safe) ----------
# These tests pin the contract of the new `should-skip-step` subcommand which
# replaced the broken bash `[ "$RT" > "STEP_X" ]` in sdd-full.md.
# Exit 0 = SKIP this step ; Exit 1 = RUN this step.


def test_should_skip_step_target_before_current_runs(monkeypatch, fake_repo):
    # RESUME_TARGET=STEP_2 (early), current=STEP_4 (later) → RUN (we haven't
    # reached resume target yet from a forward-iteration POV).
    rc = _run_main(monkeypatch, [
        "should-skip-step", "--target", "STEP_3", "--current", "STEP_4",
    ])
    assert rc == 1  # RUN


def test_should_skip_step_target_after_current_skips(monkeypatch, fake_repo):
    # RESUME_TARGET=STEP_4 (later), current=STEP_2 (earlier) → SKIP (already done).
    rc = _run_main(monkeypatch, [
        "should-skip-step", "--target", "STEP_4", "--current", "STEP_3",
    ])
    assert rc == 0  # SKIP


def test_should_skip_step_target_equals_current_runs(monkeypatch, fake_repo):
    # RESUME_TARGET=STEP_4, current=STEP_4 → RUN (resume here).
    rc = _run_main(monkeypatch, [
        "should-skip-step", "--target", "STEP_4", "--current", "STEP_4",
    ])
    assert rc == 1  # RUN


def test_should_skip_step_decimal_steps_handled_correctly(monkeypatch, fake_repo):
    # Critical: STEP_3.5 must compare correctly vs STEP_4 (was broken in bash
    # lex compare which would treat STEP_3.5 > STEP_4 as false negative on '.').
    # Pipeline order (audit final 2026-06-07 CRIT-1 fix — labels alignés sdd-full.md) :
    #   STEP_3 → STEP_3.5 → STEP_3.6 → STEP_4 (arch+dev_run) → STEP_4.5 → STEP_4.8
    rc = _run_main(monkeypatch, [
        "should-skip-step", "--target", "STEP_4", "--current", "STEP_3.5",
    ])
    assert rc == 0  # SKIP — STEP_3.5 is before STEP_4 in pipeline order


def test_should_skip_step_step_end_skips_everything(monkeypatch, fake_repo):
    # Special sentinel : STEP_END means all phases done.
    rc = _run_main(monkeypatch, [
        "should-skip-step", "--target", "STEP_END", "--current", "STEP_4.8",
    ])
    assert rc == 0  # SKIP


def test_should_skip_step_unknown_label_defaults_to_run(monkeypatch, fake_repo):
    # Unknown step label → can't gate, default to RUN (safe).
    rc = _run_main(monkeypatch, [
        "should-skip-step", "--target", "STEP_4", "--current", "STEP_NONSENSE",
    ])
    assert rc == 1  # RUN

    rc = _run_main(monkeypatch, [
        "should-skip-step", "--target", "STEP_NONSENSE", "--current", "STEP_4",
    ])
    assert rc == 1  # RUN
