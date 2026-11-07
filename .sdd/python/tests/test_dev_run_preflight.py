"""Tests du preflight mécanique de /dev-run (`dev_run_args.py --preflight`),
lot « orchestration mécanique » 2026-11-07 : run, readiness enregistrée,
phases dev sautées mécaniquement (desktop sans backend), dev_run running."""
from __future__ import annotations

from pathlib import Path

import pytest

from sdd_lib.console_db import connect, ensure_initialized, upsert_run, upsert_run_phase
from sdd_lib.paths import console_db_path
from sdd_scripts import dev_run_args as D

DESKTOP = "## Project Config\nAppName: Desk\nMaxParallel: 2\n\n## Active Tech Specs\n - .sdd/stacks/desktop/wpf.md\n"
BACKFRONT = ("## Project Config\nAppName: A\nBackendName: B\n\n## Active Tech Specs\n"
             " - .sdd/stacks/backend/dotnet-minimalapi.md\n - .sdd/stacks/frontend/react.md\n")


def _repo(tmp_path: Path, monkeypatch, stack: str, decision: str | None = "GO") -> Path:
    root = tmp_path / "repo"
    for d in (".sdd/agents", ".sdd/commands", "workspace/feats", "workspace/us",
              "workspace/stack", "workspace/.sys/.validation"):
        (root / d).mkdir(parents=True)
    (root / "workspace" / "stack" / "stack.md").write_text(stack, encoding="utf-8")
    (root / "workspace" / "feats" / "1-Demo.md").write_text("# FEAT\n## Acceptance Criteria\n- AC-1: x\n",
                                                            encoding="utf-8")
    (root / "workspace" / "us" / "1-1-Voir.md").write_text("# US", encoding="utf-8")
    if decision:
        (root / "workspace" / ".sys" / ".validation" / "1-readiness.md").write_text(
            f"**Decision deterministe** : {decision}\n", encoding="utf-8")
    monkeypatch.setenv("SDD_REPO_ROOT", str(root))
    monkeypatch.delenv("SDD_RUN_ID", raising=False)
    return root


def _phases(root: Path, run_id: str) -> dict[str, str]:
    with connect(console_db_path(root)) as conn:
        return {r["phase"]: r["status"] for r in conn.execute(
            "SELECT phase, status FROM run_phases WHERE run_id = ?", (run_id,))}


def test_desktop_skips_backend_and_api_gate(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, DESKTOP)
    out = D.preflight(D.parse_input_string("1"), root)
    assert set(out["skipped_phases"]) == {"dev_backend", "api_gate"}
    assert out["max_parallel"] == 2
    ph = _phases(root, out["run_id"])
    assert ph["dev_backend"] == "skip" and ph["api_gate"] == "skip"
    assert ph["readiness"] == "pass" and ph["dev_run"] == "running"
    assert "dev_frontend" not in ph


def test_back_front_skips_nothing(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, BACKFRONT, decision="WARN")
    out = D.preflight(D.parse_input_string("1 --max-parallel 4"), root)
    assert out["skipped_phases"] == [] and out["max_parallel"] == 4
    assert _phases(root, out["run_id"])["readiness"] == "warn"


def test_nogo_without_force_stops(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, BACKFRONT, decision="NO-GO")
    with pytest.raises(D.PreflightStop) as exc:
        D.preflight(D.parse_input_string("1"), root)
    assert exc.value.cls == "[READINESS_NO_GO]"


def test_nogo_with_force_records_warn_and_audit(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, BACKFRONT, decision="NO-GO")
    out = D.preflight(D.parse_input_string("1 --force"), root)
    assert _phases(root, out["run_id"])["readiness"] == "warn"
    log = root / "workspace" / ".sys" / ".audit" / "force-bypass.log"
    assert "/dev-run 1 --force readiness=NO-GO" in log.read_text(encoding="utf-8")


def test_reuses_running_sdd_full_run(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, BACKFRONT)
    db = console_db_path(root)
    ensure_initialized(db)
    with connect(db) as conn:
        upsert_run(conn, run_id="full-1", command="/sdd-full", feat_n=1,
                   started_at="2026-11-07T00:00:00Z", status="running")
        upsert_run_phase(conn, run_id="full-1", phase="readiness", status="pass")
    out = D.preflight(D.parse_input_string("1"), root)
    assert out["run_id"] == "full-1" and not out["run_created"]


def test_no_us_stops(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, BACKFRONT)
    (root / "workspace" / "us" / "1-1-Voir.md").unlink()
    with pytest.raises(D.PreflightStop) as exc:
        D.preflight(D.parse_input_string("1"), root)
    assert exc.value.cls == "[US_NOT_FOUND]"


def test_cli_preflight_then_end(tmp_path, monkeypatch, capsys):
    # Gate de livraison (2026-11-07) : `--end pass` n'est enregistré que si la
    # preuve build/readiness existe (faux module central — câblage seul).
    from tests._delivery_fake import install_fake_gate
    install_fake_gate(monkeypatch).prove(1, "build", "readiness")
    root = _repo(tmp_path, monkeypatch, DESKTOP)
    assert D.main(["--input", "1", "--preflight"]) == 0
    capsys.readouterr()
    assert D.main(["--input", "1", "--end", "pass"]) == 0
    with connect(console_db_path(root)) as conn:
        st = conn.execute("SELECT status FROM run_phases WHERE phase='dev_run'").fetchone()[0]
    assert st == "pass"
