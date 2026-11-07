"""Tests du hook PreToolUse(Agent) `enforce_phase_order` (lot orchestration
mécanique, 2026-11-07) : séquencement readiness → dev_run → qa → reviewers
lu dans console.db `run_phases`."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sdd_lib.console_db import connect, ensure_initialized, upsert_run, upsert_run_phase
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY
from sdd_lib.paths import console_db_path
from sdd_hooks import enforce_phase_order as H

_PY_ROOT = Path(__file__).resolve().parent.parent
HOOK = _PY_ROOT / "sdd_hooks" / "enforce_phase_order.py"


@pytest.fixture()
def repo(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "repo"
    for d in (".sdd/agents", ".sdd/commands", "workspace/us", "workspace/feats"):
        (root / d).mkdir(parents=True)
    for a in ("dev-backend", "dev-frontend", "qa", "code-reviewer", "po",
              "spec-compliance-reviewer", "adversarial-reviewer"):
        (root / ".sdd" / "agents" / f"{a}.md").write_text(f"name: {a}\n", encoding="utf-8")
    monkeypatch.setenv("SDD_REPO_ROOT", str(root))
    for v in ("SDD_ALLOW_PHASE_SKIP", "SDD_RUN_ID"):
        monkeypatch.delenv(v, raising=False)
    return root


def _run(root: Path, phases: dict[str, str], feat_n: int = 1) -> None:
    db = console_db_path(root)
    ensure_initialized(db)
    with connect(db) as conn:
        upsert_run(conn, run_id="r1", command="/sdd-full", feat_n=feat_n,
                   started_at="2026-11-07T00:00:00Z", status="running")
        for ph, st in phases.items():
            upsert_run_phase(conn, run_id="r1", phase=ph, status=st)


def _payload(agent: str, prompt: str = "Implémenter US 1-2-Login (FEAT 1)") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "s1",
            "tool_use_id": "t1",
            "tool_input": {"subagent_type": agent, "prompt": prompt, "description": "x"}}


def test_non_sdd_agent_allowed(repo):
    assert H.evaluate(_payload("general-purpose"), repo)[0] == HOOK_ALLOW


def test_sdd_agent_without_rule_allowed(repo):
    assert H.evaluate(_payload("po", "découper"), repo)[0] == HOOK_ALLOW


def test_dev_backend_denied_without_readiness(repo):
    _run(repo, {"us_generate": "pass"})
    code, msg = H.evaluate(_payload("dev-backend"), repo)
    assert code == HOOK_DENY and "[PHASE_ORDER_VIOLATION]" in msg and "readiness" in msg


def test_dev_backend_denied_without_any_run(repo):
    code, msg = H.evaluate(_payload("dev-backend"), repo)
    assert code == HOOK_DENY and "aucun run" in msg


@pytest.mark.parametrize("status", ["pass", "warn", "skip"])
def test_dev_backend_allowed_with_readiness(repo, status):
    _run(repo, {"readiness": status})
    assert H.evaluate(_payload("dev-backend"), repo)[0] == HOOK_ALLOW


def test_readiness_fail_denies(repo):
    _run(repo, {"readiness": "fail"})
    assert H.evaluate(_payload("dev-frontend"), repo)[0] == HOOK_DENY


def test_qa_needs_dev_run_running_ok(repo):
    _run(repo, {"readiness": "pass"})
    assert H.evaluate(_payload("qa", "API gate FEAT 1"), repo)[0] == HOOK_DENY
    _run(repo, {"dev_run": "running"})
    assert H.evaluate(_payload("qa", "API gate FEAT 1"), repo)[0] == HOOK_ALLOW


def test_spec_reviewer_needs_dev_run_done(repo, monkeypatch):
    # statut déclaré nécessaire + preuve build (gate de livraison 2026-11-07)
    from tests._delivery_fake import install_fake_gate
    install_fake_gate(monkeypatch).prove(1, "build")
    _run(repo, {"readiness": "pass", "dev_run": "running"})
    assert H.evaluate(_payload("spec-compliance-reviewer", "Audit FEAT 1"), repo)[0] == HOOK_DENY
    _run(repo, {"dev_run": "pass"})
    assert H.evaluate(_payload("spec-compliance-reviewer", "Audit FEAT 1"), repo)[0] == HOOK_ALLOW


def test_reviewers_need_qa(repo, monkeypatch):
    from tests._delivery_fake import install_fake_gate
    install_fake_gate(monkeypatch).prove(1, "build")
    _run(repo, {"readiness": "pass", "dev_run": "pass"})
    assert H.evaluate(_payload("code-reviewer", "Review FEAT 1"), repo)[0] == HOOK_DENY
    _run(repo, {"qa": "skip"})
    assert H.evaluate(_payload("adversarial-reviewer", "FEAT 1"), repo)[0] == HOOK_ALLOW


def test_feat_not_extractable_denied(repo):
    _run(repo, {"readiness": "pass"})
    code, msg = H.evaluate(_payload("dev-backend", "implémente le login"), repo)
    assert code == HOOK_DENY and "FEAT identifiable" in msg


def test_feat_extraction_patterns():
    assert H.extract_feat(_payload("x", "args=\"3-2\"")) == 3
    assert H.extract_feat(_payload("x", "Audit FEAT 12 — AC")) == 12
    assert H.extract_feat(_payload("x", "US 4-1-Consulter-Fiche")) == 4
    assert H.extract_feat(_payload("x", "rien")) is None


def test_bypass_is_audit_logged(repo, monkeypatch):
    monkeypatch.setenv("SDD_ALLOW_PHASE_SKIP", "1")
    code, msg = H.evaluate(_payload("dev-backend"), repo)
    assert code == HOOK_ALLOW and "BYPASSED" in msg
    log = repo / "workspace" / ".sys" / ".audit" / "bypass.log"
    assert "SDD_ALLOW_PHASE_SKIP=1" in log.read_text(encoding="utf-8")


def test_unreadable_db_is_infra_blocked(repo):
    db = console_db_path(repo)
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"this is not a sqlite database at all" * 10)
    code, msg = H.evaluate(_payload("dev-backend"), repo)
    assert code == HOOK_DENY and "[INFRA_BLOCKED]" in msg


def test_poc_feat_allows_dev_without_readiness(repo):
    (repo / "workspace" / "us" / "1-1-Demo.md").write_text(
        "---\ngenerated-by: feat_to_pseudo_us.py\n---\n# US", encoding="utf-8")
    assert H.evaluate(_payload("dev-backend", "US 1-1-Demo"), repo)[0] == HOOK_ALLOW


def test_plan_mode_accepts_disk_readiness(repo):
    rep = repo / "workspace" / ".sys" / ".validation" / "1-readiness.md"
    rep.parent.mkdir(parents=True)
    rep.write_text("**Decision deterministe** : WARN\n", encoding="utf-8")
    p = _payload("dev-backend", "dev-backend:plan pour US 1-2 (mode plan)")
    assert H.evaluate(p, repo)[0] == HOOK_ALLOW


def test_subprocess_exit_code(repo):
    env = {k: v for k, v in os.environ.items()}
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(_payload("dev-backend")),
                          capture_output=True, text=True, env=env, check=False)
    assert proc.returncode == HOOK_DENY
    assert "[PHASE_ORDER_VIOLATION]" in proc.stderr
