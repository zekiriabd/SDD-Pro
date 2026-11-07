"""Câblage des points de sortie sur le gate de livraison (2026-11-07).

SSoT : `.sdd/docs/delivery-gates.md`. Ces tests prouvent que :
  - le planner /sdd-full et la clôture de run refusent la livraison quand une
    preuve manque, même si `run_phases` déclare tout `pass` (y compris
    `buildVerified: true` / `executed: true` dans les payloads) ;
  - /sdd-poc livre avec la seule preuve build (pas de QA imposée) ;
  - `--force`, WARN, `--no-validate`, `--resume` ne débloquent jamais ;
  - `enforce_phase_order` bloque un reviewer après un dev_run warn sans build
    vérifié ;
  - module central absent → refus (fail-closed).

Le module central est remplacé par un faux (`tests/_delivery_fake.py`,
injecté dans `sys.modules`) : on teste le CÂBLAGE, pas la production des
preuves. Isolation : faux repo sous tmp_path (`SDD_REPO_ROOT`), console.db et
audit sous ce faux repo — jamais le vrai `workspace/`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

from sdd_lib.console_db import connect, ensure_initialized, get_run, upsert_run, upsert_run_phase
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY
from sdd_lib.paths import audit_dir_path, console_db_path
from sdd_scripts import sdd_full_planner as P
from tests._delivery_fake import install_fake_gate

ALL_SDD_FULL = ("build", "tests", "coverage", "spec_compliance", "readiness")

STACK = """## Project Config
AppName: App
BackendName: Api
QAMode: tests+coverage
ReviewMode: full
MaxParallel: 3

## Active Tech Specs
 - .sdd/stacks/backend/dotnet-minimalapi.md
 - .sdd/stacks/frontend/react.md
"""

#: run_phases d'un /sdd-full « tout vert » déclaré par l'orchestrateur.
DECLARED_ALL_PASS: dict[str, tuple[str, dict]] = {
    "us_generate": ("skip", {}),
    "readiness": ("pass", {"decision": "GO"}),
    "plan": ("skip", {}),
    "dev_run": ("pass", {"buildVerified": True}),
    "doc_refresh": ("pass", {}),
    "qa": ("pass", {"executed": True, "coverage": 91}),
    "auditor_batch": ("pass", {}),
    "feat_validate_postdev": ("pass", {}),
    "sdd_review": ("pass", {}),
}


@pytest.fixture()
def repo(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "repo"
    for d in (".sdd/agents", ".sdd/commands", "workspace/feats", "workspace/us",
              "workspace/stack", "workspace/plans", "workspace/.sys/.validation"):
        (root / d).mkdir(parents=True)
    (root / "workspace" / "stack" / "stack.md").write_text(STACK, encoding="utf-8")
    (root / "workspace" / "feats" / "1-Auth.md").write_text("# FEAT", encoding="utf-8")
    (root / "workspace" / "us" / "1-1-Login.md").write_text("# US", encoding="utf-8")
    monkeypatch.setenv("SDD_REPO_ROOT", str(root))
    for var in ("SDD_RUN_ID", "SDD_ALLOW_FORCE", "SDD_ALLOW_PHASE_SKIP"):
        monkeypatch.delenv(var, raising=False)
    assert str(console_db_path(root)).startswith(str(tmp_path))
    assert str(audit_dir_path(root)).startswith(str(tmp_path))
    return root


@pytest.fixture()
def gate(monkeypatch):
    return install_fake_gate(monkeypatch)


def _new_run(root: Path, command: str = "/sdd-full", run_id: str = "run-1",
             phases: dict[str, tuple[str, dict]] | None = None) -> str:
    db = console_db_path(root)
    ensure_initialized(db)
    with connect(db) as conn:
        upsert_run(conn, run_id=run_id, command=command, feat_n=1,
                   started_at="2026-11-07T00:00:00Z", status="running")
        for ph, (st, payload) in (phases or {}).items():
            upsert_run_phase(conn, run_id=run_id, phase=ph, status=st,
                             started_at="2026-11-07T00:00:01Z",
                             ended_at="2026-11-07T00:00:02Z", payload=payload)
    return run_id


def _next(root: Path, **flags) -> dict:
    f = P.default_flags()
    f.update(feat_number=1, **flags)
    return P.compute_next_action(root, 1, f)


def _run_row(root: Path, run_id: str = "run-1"):
    with connect(console_db_path(root)) as conn:
        return dict(get_run(conn, run_id))


# --------------------------------------------------------------------------- #
# Planner /sdd-full
# --------------------------------------------------------------------------- #

def test_planner_refuses_done_when_declared_all_pass_without_evidence(repo, gate):
    _new_run(repo, phases=DECLARED_ALL_PASS)
    a = _next(repo)
    assert a["action"] == "script" and a["phase_id"] == "verify-build"
    assert a["script"].endswith("verify_build.py") and "--run-id" in a["args"]


def test_planner_sdd_full_requires_tests_even_if_qa_declared_pass(repo, gate):
    _new_run(repo, phases=DECLARED_ALL_PASS)
    gate.prove(1, "build", "spec_compliance", "readiness")
    a = _next(repo)
    assert a["phase_id"] == "verify-tests" and "--coverage" in a["args"]
    assert a["action"] != "done"


def test_planner_plans_each_missing_proof_then_delivers(repo, gate):
    _new_run(repo, phases=DECLARED_ALL_PASS)
    order = []
    for family in (("build",), ("tests", "coverage"), ("spec_compliance",), ("readiness",)):
        a = _next(repo)
        assert a["action"] == "script", a
        order.append(a["phase_id"])
        gate.prove(1, *family)
    assert order == ["verify-build", "verify-tests", "record-spec", "record-readiness"]
    a = _next(repo)
    assert a["phase_id"] == P.SPEC_BOOK_STEP  # post-gate best-effort
    P.record_step(repo, "run-1", P.SPEC_BOOK_STEP, "pass")
    a = _next(repo)
    assert a["action"] == "done" and a["delivery_gate"]["allowed"] is True
    assert "--status completed" in a["end_run"]


def test_planner_failed_proof_stops_and_closes_failed(repo, gate):
    _new_run(repo, phases=DECLARED_ALL_PASS)
    gate.fail(1, "build")
    a = _next(repo)
    assert a["action"] == "stop" and a["error"] == "[DELIVERY_GATE_BLOCKED]"
    assert "--status failed" in a["end_run"]


def test_planner_verify_step_failure_without_evidence_stops(repo, gate):
    _new_run(repo, phases=DECLARED_ALL_PASS)
    P.record_step(repo, "run-1", "verify-build", "fail")
    a = _next(repo)
    assert a["action"] == "stop" and a["error"] == "[DELIVERY_GATE_BLOCKED]"


def test_force_on_readiness_warn_advances_but_never_delivers(repo, gate, monkeypatch):
    monkeypatch.setenv("SDD_ALLOW_FORCE", "1")  # --force + --no-plan-on-warn (cumul tracé)
    _new_run(repo, phases={"readiness": ("warn", {"decision": "WARN"})})
    a = _next(repo, force=True, no_plan_on_warn=True)
    assert a["action"] == "skill" and a["skill"] == "/dev-run"  # le pipeline avance
    _new_run(repo, run_id="run-1", phases=DECLARED_ALL_PASS)  # tout déclaré pass ensuite
    gate.fail(1, "tests")
    gate.prove(1, "build")
    a = _next(repo, force=True, no_plan_on_warn=True)
    assert a["action"] == "stop" and a["error"] == "[DELIVERY_GATE_BLOCKED]"
    log = audit_dir_path(repo) / "force-bypass.log"
    assert "SANS EFFET sur le gate de livraison" in log.read_text(encoding="utf-8")


def test_no_validate_cannot_deliver(repo, gate):
    phases = dict(DECLARED_ALL_PASS)
    phases["readiness"] = ("skip", {"decision": "GO", "bypass": "--no-validate"})
    _new_run(repo, phases=phases)
    gate.prove(1, "build", "tests", "coverage", "spec_compliance")
    a = _next(repo, no_validate=True)
    assert a["action"] == "stop" and a["error"] == "[DELIVERY_GATE_BLOCKED]"
    assert "--no-validate" in a["reason"]


def test_resume_replans_verify_despite_previous_pass(repo, gate):
    _new_run(repo, phases=DECLARED_ALL_PASS)
    for step in ("verify-build", "verify-tests", "record-spec", "record-readiness"):
        P.record_step(repo, "run-1", step, "pass")  # statuts antérieurs déclarés
    a = _next(repo, resume=True)
    assert a["phase_id"] == "verify-build" and a["action"] == "script"
    gate.prove(1, *ALL_SDD_FULL)
    gate.stale(1, "build")  # arbre modifié depuis la preuve
    a = _next(repo, resume=True)
    assert a["phase_id"] == "verify-build"


# --------------------------------------------------------------------------- #
# Clôture de run (run_close / sdd_state end-run / set-phase finale)
# --------------------------------------------------------------------------- #

def test_run_close_downgrades_declared_success_without_evidence(repo, gate):
    from sdd_scripts.run_close import close_run
    _new_run(repo, phases=DECLARED_ALL_PASS)
    res = close_run("run-1", "completed", "GREEN")
    assert res["delivery_blocked"] and res["run_status"] == "failed"
    row = _run_row(repo)
    assert row["status"] == "failed" and "[DELIVERY_GATE_BLOCKED]" in row["error_message"]
    assert json.loads(row["params_json"])["verdict"] == "RED"


def test_run_close_partial_also_gated(repo, gate):
    from sdd_scripts.run_close import close_run
    _new_run(repo, phases=DECLARED_ALL_PASS)
    gate.prove(1, "build")
    assert close_run("run-1", "partial")["run_status"] == "failed"


def test_run_close_allows_with_full_evidence(repo, gate):
    from sdd_scripts.run_close import close_run
    _new_run(repo, phases=DECLARED_ALL_PASS)
    gate.prove(1, *ALL_SDD_FULL)
    res = close_run("run-1", "completed", "GREEN")
    assert res["run_status"] == "completed" and not res.get("delivery_blocked")


def test_run_close_cli_exit_2_when_blocked(repo, gate, capsys):
    from sdd_scripts import run_close
    _new_run(repo)
    assert run_close.main(["--run-id", "run-1", "--status", "completed"]) == 2
    assert "[DELIVERY_GATE_BLOCKED]" in capsys.readouterr().err


def test_sdd_poc_delivers_with_build_only(repo, gate):
    from sdd_scripts.run_close import close_run
    _new_run(repo, command="/sdd-poc", phases={"dev_run": ("pass", {})})
    gate.prove(1, "build")
    assert close_run("run-1", "completed")["run_status"] == "completed"
    assert gate.calls[-1]["workflow"] == "sdd-poc"


def test_sdd_poc_without_build_refused(repo, gate):
    from sdd_scripts.run_close import close_run
    _new_run(repo, command="/sdd-poc", phases={"dev_run": ("pass", {"buildVerified": True})})
    assert close_run("run-1", "completed")["run_status"] == "failed"


def test_failed_close_is_not_gated(repo, gate):
    from sdd_scripts.run_close import close_run
    _new_run(repo)
    assert close_run("run-1", "failed")["run_status"] == "failed"
    assert gate.calls == []


def test_non_delivery_run_unchanged(repo, gate):
    from sdd_scripts.run_close import close_run
    _new_run(repo, command="hook")
    assert close_run("run-1", "completed")["run_status"] == "completed"
    assert gate.calls == []


def test_sdd_state_end_run_and_final_phase_gated(repo, gate):
    from sdd_scripts import sdd_state
    _new_run(repo, phases=DECLARED_ALL_PASS)
    ns = argparse.Namespace(run_id="run-1", status="success", verdict="GREEN")
    assert sdd_state.action_end_run(ns) == 2
    assert _run_row(repo)["status"] == "failed"
    _new_run(repo, run_id="run-2", phases=DECLARED_ALL_PASS)
    ns = argparse.Namespace(run_id="run-2", phase="sdd_review", status="pass", payload_json="")
    assert sdd_state.action_set_phase(ns) == 2
    assert _run_row(repo, "run-2")["status"] == "failed"


def test_module_absent_fails_closed(repo, monkeypatch):
    from sdd_scripts.run_close import close_run
    monkeypatch.setitem(sys.modules, "sdd_lib.delivery_gate", None)  # ImportError
    _new_run(repo, phases=DECLARED_ALL_PASS)
    res = close_run("run-1", "completed")
    assert res["run_status"] == "failed" and "indisponible" in res["error"]


# --------------------------------------------------------------------------- #
# dev_run_args --end
# --------------------------------------------------------------------------- #

def test_dev_run_end_pass_without_build_records_fail(repo, gate, capsys):
    from sdd_scripts import dev_run_args as D
    _new_run(repo, command="/dev-run", phases={"readiness": ("pass", {}),
                                               "dev_run": ("running", {})})
    assert D.main(["--input", "1", "--end", "pass", "--run-id", "run-1"]) == 2
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["delivery_blocked"] and out["status"] == "fail"
    with connect(console_db_path(repo)) as conn:
        st = conn.execute("SELECT status FROM run_phases WHERE phase='dev_run'").fetchone()[0]
    assert st == "fail"
    assert _run_row(repo)["status"] == "failed"


def test_dev_run_end_warn_with_build_and_readiness_ok(repo, gate, capsys):
    from sdd_scripts import dev_run_args as D
    _new_run(repo, command="/dev-run", phases={"dev_run": ("running", {})})
    gate.prove(1, "build", "readiness")
    assert D.main(["--input", "1", "--end", "warn", "--run-id", "run-1"]) == 0


# --------------------------------------------------------------------------- #
# Hook enforce_phase_order
# --------------------------------------------------------------------------- #

def _hook_payload(agent: str, prompt: str) -> dict:
    return {"tool_name": "Agent", "session_id": "s", "tool_use_id": "t1",
            "tool_input": {"subagent_type": agent, "prompt": prompt, "description": "x"}}


@pytest.fixture()
def hook(repo, monkeypatch):
    from sdd_hooks import enforce_phase_order as H
    monkeypatch.setattr(H, "sdd_agent_registry", lambda root: {
        "qa", "spec-compliance-reviewer", "code-reviewer", "security-reviewer",
        "arch-reviewer", "adversarial-reviewer", "dev-backend", "dev-frontend"})
    monkeypatch.setattr(H, "note_denied", lambda root, tid: None)
    return H


def test_reviewer_blocked_after_dev_run_warn_without_build(repo, gate, hook, monkeypatch):
    _new_run(repo, phases={"readiness": ("pass", {}), "dev_run": ("warn", {}),
                           "qa": ("skip", {})})
    code, msg = hook.evaluate(_hook_payload("spec-compliance-reviewer", "Audit FEAT 1"), repo)
    assert code == HOOK_DENY and "[DELIVERY_EVIDENCE_MISSING]" in msg
    monkeypatch.setenv("SDD_ALLOW_PHASE_SKIP", "1")  # aucun bypass sur la preuve
    code, _ = hook.evaluate(_hook_payload("code-reviewer", "Review FEAT 1"), repo)
    assert code == HOOK_DENY


def test_reviewer_blocked_on_declared_build_not_verified_even_with_evidence(repo, gate, hook):
    _new_run(repo, phases={"dev_run": ("warn", {"buildVerified": False}), "qa": ("skip", {})})
    gate.prove(1, "build")
    code, msg = hook.evaluate(_hook_payload("spec-compliance-reviewer", "Audit FEAT 1"), repo)
    assert code == HOOK_DENY and "buildVerified=false" in msg


def test_stage_b_reviewer_needs_tests_proof_when_qa_declared(repo, gate, hook):
    _new_run(repo, phases={"dev_run": ("pass", {}), "qa": ("warn", {"executed": True})})
    gate.prove(1, "build")
    code, msg = hook.evaluate(_hook_payload("code-reviewer", "Review FEAT 1"), repo)
    assert code == HOOK_DENY and "preuve tests" in msg
    gate.prove(1, "tests")
    assert hook.evaluate(_hook_payload("code-reviewer", "Review FEAT 1"), repo)[0] == HOOK_ALLOW


def test_api_gate_qa_inside_dev_run_unchanged(repo, gate, hook):
    _new_run(repo, phases={"readiness": ("pass", {}), "dev_run": ("running", {})})
    assert hook.evaluate(_hook_payload("qa", "API gate FEAT 1"), repo)[0] == HOOK_ALLOW


def test_reviewer_allowed_with_build_proof(repo, gate, hook):
    _new_run(repo, phases={"dev_run": ("warn", {}), "qa": ("skip", {})})
    gate.prove(1, "build")
    assert hook.evaluate(_hook_payload("spec-compliance-reviewer",
                                       "Audit FEAT 1"), repo)[0] == HOOK_ALLOW
