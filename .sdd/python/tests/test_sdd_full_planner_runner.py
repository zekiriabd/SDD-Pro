"""Tests du runner `/sdd-full` piloté par l'état réel (lot « orchestration
mécanique », 2026-11-07).

`sdd_full_planner.py next-action --feat N` lit console.db (`runs`,
`run_phases`, `events`) + le disque et rend la prochaine action ; `record`
écrit le résultat. Ces tests parcourent la boucle complète sans LLM :
chaque action rendue est « exécutée » en enregistrant son résultat, et on
vérifie la séquence des phases et les règles load-bearing (readiness strict,
--force, plan-review, gates manuelles, Flyway, anti-cumul, QA bloquante).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdd_lib.console_db import connect, ensure_initialized, upsert_run
from sdd_lib.paths import console_db_path
from sdd_scripts import sdd_full_planner as P

STACK = """## Project Config
AppName: App
BackendName: Api
QAMode: tests+coverage
ReviewMode: full
MaxParallel: 3
{extra}

## Active Tech Specs
 - .sdd/stacks/backend/dotnet-minimalapi.md
 - .sdd/stacks/frontend/react.md
"""


def _repo(tmp_path: Path, monkeypatch, *, extra: str = "", feat: str = "1-Auth.md",
          us: tuple[str, ...] = ("1-1-Login.md",)) -> Path:
    root = tmp_path / "repo"
    (root / ".sdd" / "agents").mkdir(parents=True)
    (root / ".sdd" / "commands").mkdir(parents=True)
    ws = root / "workspace"
    for d in ("feats", "us", "stack", "plans"):
        (ws / d).mkdir(parents=True)
    (ws / "stack" / "stack.md").write_text(STACK.format(extra=extra), encoding="utf-8")
    (ws / "feats" / feat).write_text("# FEAT", encoding="utf-8")
    for u in us:
        (ws / "us" / u).write_text("# US", encoding="utf-8")
    monkeypatch.setenv("SDD_REPO_ROOT", str(root))
    monkeypatch.delenv("SDD_RUN_ID", raising=False)
    monkeypatch.delenv("SDD_ALLOW_FORCE", raising=False)
    return root


def _new_run(root: Path, feat_n: int = 1, run_id: str = "run-1") -> str:
    db = console_db_path(root)
    ensure_initialized(db)
    with connect(db) as conn:
        upsert_run(conn, run_id=run_id, command="/sdd-full", feat_n=feat_n,
                   started_at="2026-11-07T00:00:00Z", status="running")
    return run_id


def _flags(**kw) -> dict:
    f = P.default_flags()
    f.update(kw)
    return f


def _next(root: Path, **flags) -> dict:
    return P.compute_next_action(root, 1, _flags(feat_number=1, **flags))


def _rec(root: Path, phase: str, status: str, payload: dict | None = None) -> None:
    P.record_phase(root, "run-1", phase, status, payload)


# --------------------------------------------------------------------------- #
# Flags
# --------------------------------------------------------------------------- #

def test_parse_flags_strict():
    f = P.parse_sdd_full_flags("3 --force --manual-gates=us,plan --rebuild-arch")
    assert f["feat_number"] == 3 and f["force"] and f["rebuild_arch"]
    assert f["manual_gates"] == ["us", "plan"]
    assert P.parse_sdd_full_flags("2 --manual-gates")["manual_gates"] == list(P.MANUAL_GATE_TOKENS)


@pytest.mark.parametrize("raw", ["1 --manual-gates=foo", "1 --unknown-flag"])
def test_parse_flags_rejects_garbage(raw):
    with pytest.raises(ValueError):
        P.parse_sdd_full_flags(raw)


# --------------------------------------------------------------------------- #
# Boucle nominale
# --------------------------------------------------------------------------- #

_FAMILY_BY_STEP = {"verify-build": ("build",), "verify-tests": ("tests", "coverage"),
                   "record-spec": ("spec_compliance",), "record-readiness": ("readiness",)}


def test_nominal_loop_reaches_done(tmp_path, monkeypatch):
    # Gate de livraison (2026-11-07) : les étapes verify_* / record-* sont
    # planifiées explicitement ; « exécuter » l'une d'elles = le faux module
    # central reçoit la preuve (en réel : verify_build.py / verify_tests.py).
    from tests._delivery_fake import install_fake_gate
    gate = install_fake_gate(monkeypatch)
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    seen = []
    a: dict = {}
    for _ in range(30):
        a = _next(root)
        seen.append(a["phase_id"] or a["action"])
        if a["action"] == "done":
            break
        assert a["action"] in ("skill", "script", "procedure"), a
        rp = a["run_phase"]
        if a["phase_id"] in _FAMILY_BY_STEP:
            gate.prove(1, *_FAMILY_BY_STEP[a["phase_id"]])
        elif rp == "readiness":
            _rec(root, "readiness", "pass", {"decision": "GO"})
        elif rp:
            _rec(root, rp, "pass")
        else:  # spec-book
            P.record_step(root, "run-1", P.SPEC_BOOK_STEP, "pass")
    assert seen == ["feat-validate", "dev-run", "verify-build", "doc-refresh", "qa-generate",
                    "verify-tests", "auditors", "spec-postdev", "record-spec", "sdd-review",
                    "record-readiness", "spec-book", "done"]
    phases = P.read_db_state(root, 1, "run-1")["phases"]
    assert phases["us_generate"]["status"] == "skip"  # US présentes → skip auto
    assert phases["plan"]["status"] == "skip"
    assert a["final_status"] == "success"


def test_us_generate_when_no_us(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, us=())
    _new_run(root)
    a = _next(root)
    assert a["action"] == "skill" and a["skill"] == "/us-generate"


def test_feat_not_found_stops(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    a = P.compute_next_action(root, 9, _flags(feat_number=9))
    assert a["action"] == "stop" and a["error"] == "[FEAT_NOT_FOUND]"


# --------------------------------------------------------------------------- #
# Readiness — tableau de décision
# --------------------------------------------------------------------------- #

def test_readiness_warn_without_force_stops(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    _rec(root, "readiness", "warn", {"decision": "WARN"})
    a = _next(root)
    assert a["action"] == "stop" and a["error"] == "[READINESS_WARN]"


def test_readiness_nogo_with_force_requires_plan_review(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    _rec(root, "readiness", "fail", {"decision": "NO-GO"})
    a = _next(root, force=True)
    assert a["action"] == "skill" and a["skill"] == "/dev-plan"


def test_force_no_plan_on_warn_goes_to_dev_run(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    _rec(root, "readiness", "warn", {"decision": "WARN"})
    monkeypatch.setenv("SDD_ALLOW_FORCE", "1")  # 2 bypass cumulés
    a = _next(root, force=True, no_plan_on_warn=True)
    assert a["skill"] == "/dev-run"


def test_plan_review_checkpoint_when_plans_present(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, extra="PlanReviewDefault: true")
    _new_run(root)
    _rec(root, "readiness", "pass", {"decision": "GO"})
    (root / "workspace" / "plans" / "1-1-Login.back.md").write_text("plan", encoding="utf-8")
    a = _next(root)
    assert a["action"] == "checkpoint" and "ok" in a["options"]
    _rec(root, "plan", "pass")
    assert _next(root)["skill"] == "/dev-run"


def test_plan_review_requests_dev_plan_when_no_plans(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, extra="PlanReviewDefault: true")
    _new_run(root)
    _rec(root, "readiness", "pass", {"decision": "GO"})
    assert _next(root)["skill"] == "/dev-plan"


def test_no_validate_records_readiness_skip(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    a = _next(root, no_validate=True)
    assert a["skill"] == "/dev-run"
    assert any(e["phase"] == "readiness" and e["status"] == "skip" for e in a["auto_recorded"])


def test_force_cumul_rejected(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    a = _next(root, force=True, no_validate=True)
    assert a["action"] == "stop" and a["error"] == "[FORCE_CUMUL_REJECTED]"


# --------------------------------------------------------------------------- #
# Gates manuelles, Flyway, QA bloquante
# --------------------------------------------------------------------------- #

def test_manual_gate_after_us_asks_then_stops_pending(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    a = _next(root, manual_gates=["us"])
    assert a["action"] == "gate" and a["gate"] == "afterUS"
    status = root / "workspace" / "console" / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps({"gates": {"1": {"afterUS": {"decision": "pending"}}}}),
                      encoding="utf-8")
    a = _next(root, manual_gates=["us"])
    assert a["action"] == "stop" and a["resumable"]
    status.write_text(json.dumps({"gates": {"1": {"afterUS": {"decision": "validated"}}}}),
                      encoding="utf-8")
    assert _next(root, manual_gates=["us"])["skill"] == "/feat-validate"


def test_flyway_feat_forces_rebuild_arch_and_sentinel(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, feat="1-Flyway-Migration.md")
    _new_run(root)
    _rec(root, "readiness", "pass", {"decision": "GO"})
    a = _next(root)
    assert a["skill"] == "/dev-run" and "--rebuild-arch" in a["args"]
    assert (root / "workspace" / ".sys" / ".state" / P.FLYWAY_SENTINEL).is_file()


def test_qa_red_blocking_by_default(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    assert P.status_from_verdict("qa", "RED", {"QaFailOnSddFull": True}) == "fail"
    assert P.status_from_verdict("qa", "RED", {"QaFailOnSddFull": False}) == "warn"
    _new_run(root)
    for ph, st in (("readiness", "pass"), ("dev_run", "pass"), ("doc_refresh", "pass"),
                   ("qa", "fail")):
        _rec(root, ph, st)
    a = _next(root)
    assert a["action"] == "stop" and a["error"] == "[PHASE_FAILED]"


def test_qamode_off_skips_qa(tmp_path, monkeypatch):
    # QAMode off : la phase qa est `skip`, mais /sdd-full exige toujours la
    # preuve tests (gate de livraison 2026-11-07) → verify_tests planifié.
    from tests._delivery_fake import install_fake_gate
    gate = install_fake_gate(monkeypatch)
    gate.prove(1, "build")
    root = _repo(tmp_path, monkeypatch, extra="QAMode: off")
    _new_run(root)
    for ph in ("readiness", "dev_run", "doc_refresh"):
        _rec(root, ph, "pass")
    a = _next(root)
    assert a["phase_id"] == "verify-tests" and "--coverage" in a["args"]
    assert any(e["phase"] == "qa" and e["status"] == "skip" for e in a["auto_recorded"])
    gate.prove(1, "tests", "coverage")
    a = _next(root)
    assert a["phase_id"] == "auditors" and a["run_phase"] == "auditor_batch"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli_record_and_next_action(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    rc = P.main(["record", "--feat", "1", "--root", str(root), "--phase", "readiness",
                 "--verdict", "GO"])
    assert rc == 0
    capsys.readouterr()
    rc = P.main(["next-action", "--feat", "1", "--root", str(root), "--json",
                 "--state-inline", "{}"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skill"] == "/dev-run" and out["run_id"] == "run-1"


def test_cli_record_without_run_fails(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    rc = P.main(["record", "--feat", "1", "--root", str(root), "--phase", "qa",
                 "--status", "pass"])
    assert rc == 1


def test_cli_args_writes_state(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    rc = P.main(["args", "--root", str(root), "--input", "1 --plan --rebuild-arch"])
    assert rc == 0
    flags = P.load_args_state(root, 1)
    assert flags["plan"] and flags["rebuild_arch"]


def test_forced_nogo_rerecorded_as_warn_for_hook(tmp_path, monkeypatch):
    """--force sur NO-GO : readiness réécrite `warn` (payload NO-GO, forced) —
    c'est ce que lit enforce_phase_order avant d'autoriser dev-*."""
    root = _repo(tmp_path, monkeypatch)
    _new_run(root)
    _rec(root, "readiness", "fail", {"decision": "NO-GO"})
    _next(root, force=True)
    ph = P.read_db_state(root, 1, "run-1")["phases"]["readiness"]
    assert ph["status"] == "warn" and ph["payload"]["forced"] is True
