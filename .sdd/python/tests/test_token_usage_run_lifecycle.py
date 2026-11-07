"""Cycle de vie des runs vu par le hook télémétrie (audit états 2026-11-07).

Deux défauts constatés dans la base live :
  A. `_ensure_run_row` faisait un upsert inconditionnel `status='running'`,
     `command='hook'` à chaque enregistrement de tokens → un run clos était
     rouvert et un run `sdd-full` rebaptisé `hook` (run FEAT 15 : `ended_at`
     posé mais `status='running'`).
  B. `SessionEnd` ne clôturait jamais le run ouvert par les hooks de la
     session → 13/13 runs `running`/`stale`.
"""
from __future__ import annotations

import pytest

from sdd_hooks import record_token_usage as rtu
from sdd_lib import console_db, run_id


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    for d in (".claude/agents", ".claude/commands", "workspace/db"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    for var in ("SDD_RUN_ID", "CLAUDE_SESSION_ID", "SDD_SESSION_ID", "SDD_RUN_COMMAND"):
        monkeypatch.delenv(var, raising=False)
    console_db.ensure_initialized()
    return tmp_path


def _run(rid: str):
    with console_db.connect() as conn:
        return console_db.get_run(conn, rid)


# --- A. création seule, jamais de réécriture --------------------------------

def test_ensure_run_row_creates_missing_run(fake_repo):
    with console_db.connect() as conn:
        assert rtu._ensure_run_row(conn, "new-run") == "new-run"
    row = _run("new-run")
    assert row["command"] == "hook" and row["status"] == "running"


def test_ensure_run_row_never_reopens_closed_run(fake_repo):
    with console_db.connect() as conn:
        console_db.upsert_run(conn, run_id="r-closed", command="sdd-full", feat_n=15)
        console_db.run_end(conn, "r-closed", "completed", "GREEN")
        assert rtu._ensure_run_row(conn, "r-closed") == "r-closed"
    row = _run("r-closed")
    assert row["status"] == "completed"
    assert row["command"] == "sdd-full"  # jamais rebaptisé « hook »
    assert row["ended_at"]


# --- B. SessionEnd clôt le run « hook » de la session -----------------------

def test_session_end_closes_hook_run_and_clears_marker(fake_repo, monkeypatch):
    rid = run_id.get_or_create_run_id(session_id="sess-1")
    with console_db.connect() as conn:
        rtu._ensure_run_row(conn, rid)
    monkeypatch.setattr(rtu, "_SESSION_ID", "sess-1")
    assert rtu._close_session_hook_run() is True
    assert _run(rid)["status"] == "completed"
    # marker retiré → la session suivante ouvre un NOUVEAU run
    assert run_id.get_or_create_run_id(session_id="sess-1") != rid


def test_session_end_leaves_pipeline_run_untouched(fake_repo, monkeypatch):
    monkeypatch.setenv("SDD_RUN_ID", "r-pipe")
    with console_db.connect() as conn:
        console_db.upsert_run(conn, run_id="r-pipe", command="sdd-full", feat_n=16)
    assert rtu._close_session_hook_run() is False
    assert _run("r-pipe")["status"] == "running"


def test_session_end_without_marker_creates_nothing(fake_repo, monkeypatch):
    monkeypatch.setattr(rtu, "_SESSION_ID", "sess-none")
    assert rtu._close_session_hook_run() is False
    marker = run_id._marker_path("sess-none")
    assert not marker.exists()  # aucun marker orphelin créé en fin de session


# --- C. commande déformée par Git Bash (MSYS) --------------------------------

@pytest.mark.parametrize("raw", [
    "C:/Program Files/Git/sdd-full", r"C:\Program Files\Git\sdd-full",
    "/sdd-full", "sdd-full", " /SDD-FULL ",
])
def test_workflow_for_command_survives_msys_path_mangling(raw):
    from sdd_lib.delivery_wiring import workflow_for_command
    assert workflow_for_command(raw) == "sdd-full"


def test_workflow_for_command_non_delivery_unchanged():
    from sdd_lib.delivery_wiring import workflow_for_command
    assert workflow_for_command("hook") is None
    assert workflow_for_command(None) is None


def test_open_run_restores_msys_mangled_command(fake_repo):
    from sdd_scripts import sdd_state
    rid = sdd_state.open_run(1, "C:/Program Files/Git/sdd-full")
    assert _run(rid)["command"] == "/sdd-full"
    rid2 = sdd_state.open_run(1, "sdd-full")
    assert _run(rid2)["command"] == "sdd-full"  # forme non déformée : intacte


# --- D. heuristique « run suspect » : le cache compte comme volume d'entrée ---

def test_cached_real_run_is_not_flagged_nor_deleted(tmp_path):
    """Run réel caché (input ~1 token, 249 K lus en cache) : jamais « test data ».

    Avant le correctif, seul `input_tokens` était sommé → ce run passait sous
    le plancher de 50 000 et `--clean-suspects` le SUPPRIMAIT.
    """
    from sdd_admin import verify_telemetry_health as vth

    db = tmp_path / "c.db"
    console_db.ensure_initialized(db)
    with console_db.connect(db) as conn:
        console_db.upsert_run(conn, run_id="real", command="hook")
        console_db.upsert_run(conn, run_id="fake", command="hook")
        conn.execute(
            "INSERT INTO token_usage(ts, run_id, agent, model, input_tokens, output_tokens,"
            " cache_read_tokens, cache_creation_tokens) VALUES"
            " ('2026-11-07T00:00:00Z','real','po','claude-sonnet-5-5',3,3450,249043,3423),"
            " ('2026-11-07T00:00:00Z','fake','po','claude-sonnet-5-5',10,20,0,0)"
        )
    report = vth.audit_db(db)
    sanity = [c for c in report["checks"] if c["name"] == "token_volume_sanity"]
    assert sanity and "1 runs" in sanity[0]["detail"]  # seul « fake » est signalé
    res = vth.clean_suspects(db, dry_run=True)
    assert res["suspect_run_ids"] == ["fake"]
