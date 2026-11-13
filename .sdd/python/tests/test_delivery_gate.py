"""Gate de livraison fondée sur des preuves (audit 2026-11-07).

Prouve que :
  - la livraison est bloquée si le build est absent / en échec / périmé /
    si ses artefacts ont disparu ou changé ;
  - sdd-full est bloqué si les tests n'ont pas été exécutés (0 test, tous
    ignorés) ou échouent, si la couverture est sous le seuil ou non mesurée,
    si spec-compliance est RED (ou YELLOW avec finding bloquant) ;
  - sdd-poc et sdd-deploy restent autorisés avec le build seul ;
  - un workflow inconnu est refusé ;
  - ni les payloads run_phases mensongers, ni une ligne SQL forgée, ni un
    HMAC altéré, ni une relance opportuniste (échec puis succès sur le même
    état), ni les variables SDD_ALLOW_* / SDD_BYPASS_* / SDD_FORCE* ne
    débloquent quoi que ce soit — et ces variables sont consignées.

Isolation : faux dépôt sous tmp_path ($SDD_REPO_ROOT), dossier utilisateur
sous tmp_path (clé HMAC), console.db et piste d'audit redirigées par le
conftest. Les commandes de build/test sont des scripts Python factices
déclarés via DeliveryGate.BuildCommand / DeliveryGate.TestCommand.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import delivery_gate as dg  # noqa: E402
from sdd_scripts import delivery_gate as cli  # noqa: E402
from sdd_scripts import verify_build, verify_tests  # noqa: E402

FEAT = 7

_FAKE_BUILD = r'''
import pathlib, sys
mode = sys.argv[1]
out = pathlib.Path("App") / "bin" / "Debug"
out.mkdir(parents=True, exist_ok=True)
(out / "App.dll").write_bytes(b"fake-assembly-" + mode.encode())
sys.exit(0 if mode == "ok" else 1)
'''

_FAKE_TESTS = r'''
import pathlib, sys
rd = pathlib.Path(sys.argv[1]); total, failed, skipped, rate = map(float, sys.argv[2:6])
rd.mkdir(parents=True, exist_ok=True)
executed = int(total - skipped)
(rd / "results.trx").write_text(
  '<?xml version="1.0"?><TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">'
  '<ResultSummary outcome="x"><Counters total="%d" executed="%d" passed="%d" failed="%d" '
  'error="0" timeout="0" aborted="0" notExecuted="%d"/></ResultSummary></TestRun>'
  % (total, executed, executed - failed, failed, skipped), encoding="utf-8")
if rate >= 0:
    (rd / "coverage.cobertura.xml").write_text(
      '<?xml version="1.0"?><coverage line-rate="%s" lines-covered="%d" lines-valid="100"/>'
      % (rate, int(rate * 100)), encoding="utf-8")
sys.exit(1 if failed else 0)
'''


# ---------------------------------------------------------------------------
# Faux dépôt
# ---------------------------------------------------------------------------

class Repo:
    def __init__(self, base: Path):
        self.root = base / "repo"
        self.tools = base / "tools"
        self.ws = self.root / "workspace"
        self.src = self.ws / "src"
        for d in (self.root / ".sdd" / "agents", self.root / ".sdd" / "commands",
                  self.src / "App", self.ws / "stack", self.ws / "feats", self.ws / "us",
                  self.ws / ".sys" / ".validation", self.tools):
            d.mkdir(parents=True, exist_ok=True)
        (self.src / "App" / "App.csproj").write_text("<Project/>", encoding="utf-8")
        (self.src / "App" / "Program.cs").write_text("class P {}", encoding="utf-8")
        (self.tools / "fake_build.py").write_text(_FAKE_BUILD, encoding="utf-8")
        (self.tools / "fake_tests.py").write_text(_FAKE_TESTS, encoding="utf-8")
        self.configure()

    def configure(self, *, build: str = "ok", total: int = 5, failed: int = 0,
                  skipped: int = 0, rate: float = 0.9, coverage_min: int | None = 80) -> None:
        py, tools = sys.executable, self.tools
        lines = ["# Stack", "", "## Project Config", "AppName: App"]
        if coverage_min is not None:
            lines.append(f"CoverageMin: {coverage_min}")
        lines += [
            f'DeliveryGate.BuildCommand: `"{py}" "{tools / "fake_build.py"}" {build}`',
            f'DeliveryGate.TestCommand: `"{py}" "{tools / "fake_tests.py"}" "{{results_dir}}" '
            f'{total} {failed} {skipped} {rate}`',
            "",
        ]
        (self.ws / "stack" / "stack.md").write_text("\n".join(lines), encoding="utf-8")

    def touch_source(self, text: str = "// edit") -> None:
        p = self.src / "App" / "Program.cs"
        p.write_text(p.read_text(encoding="utf-8") + "\n" + text, encoding="utf-8")

    def spec_report(self, verdict: str = "GREEN", serious: int = 0, total_acs: int = 3,
                    feat: int = FEAT) -> Path:
        p = self.ws / ".sys" / ".validation" / f"{FEAT}-spec-compliance.json"
        p.write_text(json.dumps({
            "feat": feat, "generated_at": "2026-11-07T00:00:00Z",
            "config": {"mode": "manual", "fail_on": "serious"},
            "summary": {"verdict": verdict, "total_acs": total_acs, "verified": total_acs,
                        "issues": {"critical": 0, "serious": serious, "moderate": 0,
                                   "minor": 0}},
            "us": []}), encoding="utf-8")
        return p


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    r = Repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SDD_REPO_ROOT", str(r.root))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    for k in list(os.environ):
        if any(k.upper().startswith(p) for p in dg.BYPASS_ENV_PREFIXES):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    return r


def _auth(repo: Repo, workflow: str) -> dg.GateDecision:
    return dg.authorize_delivery(feat_n=FEAT, workflow=workflow, run_id="run-t",
                                 project_roots=dg.default_project_roots())


def _build(repo: Repo) -> int:
    return verify_build.main(["--feat-number", str(FEAT), "--run-id", "run-t"])


def _tests(repo: Repo, coverage: bool = True) -> int:
    argv = ["--feat-number", str(FEAT), "--run-id", "run-t"]
    return verify_tests.main(argv + (["--coverage"] if coverage else []))


def _readiness(monkeypatch: pytest.MonkeyPatch, decision: str) -> int:
    rc = 0 if decision in ("GO", "WARN") else 1
    monkeypatch.setattr(cli, "_run_readiness",
                        lambda n: (rc, {"decision": decision, "errors": [], "warnings": []},
                                   "validate_readiness.py (stub)"))
    return cli.main(["record-readiness", "--feat-number", str(FEAT)])


def _audit_lines(tmp_path: Path) -> list[dict]:
    from sdd_lib.paths import audit_dir_path
    p = audit_dir_path() / dg.AUDIT_LOG_NAME
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# SSoT des exigences
# ---------------------------------------------------------------------------

def test_workflow_requirements_ssot():
    req = dg.WORKFLOW_REQUIREMENTS
    assert set(req) == {"sdd-full", "sdd-poc", "dev-run", "sdd-deploy", "qa-generate", "sdd-review"}
    assert set(req["sdd-full"]) == {"readiness", "build", "tests", "coverage", "spec_compliance"}
    assert req["sdd-poc"] == ("build",)
    assert req["sdd-deploy"] == ("build",)
    assert set(req["dev-run"]) == {"readiness", "build"}
    assert set(req["qa-generate"]) == {"build", "tests", "coverage"}
    assert set(req["sdd-review"]) == {"build", "tests", "spec_compliance"}
    for checks in req.values():
        assert set(checks) <= set(dg.KNOWN_CHECKS)


def test_authorize_has_no_force_parameter():
    import inspect
    params = set(inspect.signature(dg.authorize_delivery).parameters)
    assert params == {"feat_n", "workflow", "run_id", "project_roots"}


def test_cli_has_no_way_to_declare_a_result():
    for argv in (["record", "--feat-number", "1", "--check", "build", "--passed"],
                 ["authorize", "--feat-number", "1", "--workflow", "sdd-poc", "--force"],
                 ["record-spec", "--feat-number", "1", "--passed", "1"]):
        with pytest.raises(SystemExit):
            cli.main(argv)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def test_build_missing_blocks(repo):
    dec = _auth(repo, "sdd-poc")
    assert not dec.allowed and dec.missing == ["build"]


def test_build_failed_blocks(repo):
    repo.configure(build="ko")
    assert _build(repo) == 2
    dec = _auth(repo, "sdd-poc")
    assert not dec.allowed and dec.failed == ["build"]


def test_build_ok_authorizes_poc_and_deploy_but_not_full(repo):
    assert _build(repo) == 0
    assert _auth(repo, "sdd-poc").allowed
    assert _auth(repo, "sdd-deploy").allowed
    full = _auth(repo, "sdd-full")
    assert not full.allowed
    assert set(full.missing) == {"readiness", "tests", "coverage", "spec_compliance"}


def test_build_evidence_carries_real_execution_elements(repo):
    assert _build(repo) == 0
    rows = dg._fetch_rows(FEAT, "build")
    d = json.loads(rows[-1]["details_json"])
    assert rows[-1]["producer"] == "verify_build.py" and rows[-1]["hmac"]
    assert "duration_s" in d and d["artifacts"]
    art = d["artifacts"][0]
    assert art["path"].endswith("App.dll") and len(art["sha256"]) == 64


def test_build_stale_after_source_change(repo):
    assert _build(repo) == 0
    repo.touch_source()
    dec = _auth(repo, "sdd-poc")
    assert not dec.allowed and dec.stale == ["build"]


def test_generated_dirs_do_not_affect_tree_hash(repo):
    h1 = dg.compute_tree_hash([repo.src])
    for d in ("bin", "obj", "node_modules", "coverage", "TestResults"):
        (repo.src / "App" / d).mkdir(parents=True, exist_ok=True)
        (repo.src / "App" / d / "x.txt").write_text("gen", encoding="utf-8")
    assert dg.compute_tree_hash([repo.src]) == h1
    repo.touch_source()
    assert dg.compute_tree_hash([repo.src]) != h1


def test_artifact_deleted_or_modified_blocks(repo):
    assert _build(repo) == 0
    dll = repo.src / "App" / "bin" / "Debug" / "App.dll"
    dll.write_bytes(b"tampered")
    dec = _auth(repo, "sdd-poc")
    assert not dec.allowed and dec.failed == ["build"]
    assert any("modifié" in r for r in dec.reasons)
    dll.unlink()
    dec = _auth(repo, "sdd-poc")
    assert not dec.allowed and any("absent" in r for r in dec.reasons)


def test_build_exit0_without_artifact_is_not_a_pass(repo):
    (repo.tools / "fake_build.py").write_text("import sys; sys.exit(0)", encoding="utf-8")
    assert _build(repo) == 2
    assert not _auth(repo, "sdd-poc").allowed


# ---------------------------------------------------------------------------
# Relance : échec puis succès
# ---------------------------------------------------------------------------

def test_fail_then_pass_on_same_tree_is_unstable(repo):
    repo.configure(build="ko")
    assert _build(repo) == 2
    repo.configure(build="ok")          # stack.md hors workspace/src : même état des sources
    assert _build(repo) == 0
    dec = _auth(repo, "sdd-poc")
    assert not dec.allowed and dec.failed == ["build"]
    assert any("instable" in r for r in dec.reasons)
    assert len(dg._fetch_rows(FEAT, "build")) == 2   # les deux preuves sont conservées


def test_fail_then_source_change_then_pass_is_allowed(repo):
    repo.configure(build="ko")
    assert _build(repo) == 2
    repo.touch_source("// fix")
    repo.configure(build="ok")
    assert _build(repo) == 0
    assert _auth(repo, "sdd-poc").allowed


# ---------------------------------------------------------------------------
# Tests + couverture
# ---------------------------------------------------------------------------

def test_zero_tests_executed_blocks_full(repo):
    repo.configure(total=4, skipped=4)
    assert _build(repo) == 0
    assert _tests(repo) == 2
    dec = _auth(repo, "qa-generate")
    assert not dec.allowed and "tests" in dec.failed


def test_failing_tests_block(repo):
    repo.configure(total=5, failed=1)
    assert _build(repo) == 0
    assert _tests(repo) == 2
    dec = _auth(repo, "qa-generate")
    assert "tests" in dec.failed and not dec.allowed


def test_test_report_missing_blocks(repo):
    (repo.tools / "fake_tests.py").write_text("import sys; sys.exit(0)", encoding="utf-8")
    assert _build(repo) == 0
    assert _tests(repo) == 2
    dec = _auth(repo, "qa-generate")
    assert "tests" in dec.failed and "coverage" in dec.failed


def test_tests_evidence_has_counts_and_report_hash(repo):
    assert _build(repo) == 0
    assert _tests(repo) == 0
    d = json.loads(dg._fetch_rows(FEAT, "tests")[-1]["details_json"])
    assert d["executed"] == 5 and d["failed"] == 0 and len(d["report_sha256"]) == 64
    assert d["reports"][0]["kind"] == "trx"


def test_coverage_below_threshold_blocks(repo):
    repo.configure(rate=0.5)
    assert _build(repo) == 0
    assert _tests(repo) == 2
    dec = _auth(repo, "qa-generate")
    assert dec.failed == ["coverage"]


def test_coverage_not_measurable_is_never_a_pass(repo):
    repo.configure(rate=-1)
    assert _build(repo) == 0
    assert _tests(repo) == 2
    assert "coverage" in _auth(repo, "qa-generate").failed


def test_coverage_min_missing_is_never_a_pass(repo):
    repo.configure(coverage_min=None)
    assert _build(repo) == 0
    assert _tests(repo) == 2
    assert "coverage" in _auth(repo, "qa-generate").failed


# ---------------------------------------------------------------------------
# Spec compliance + readiness + parcours complet
# ---------------------------------------------------------------------------

def _all_green(repo, monkeypatch):
    assert _build(repo) == 0
    assert _tests(repo) == 0
    repo.spec_report("🟢 GREEN")
    assert cli.main(["record-spec", "--feat-number", str(FEAT)]) == 0
    assert _readiness(monkeypatch, "GO") == 0


def test_sdd_full_allowed_with_all_evidence(repo, monkeypatch):
    _all_green(repo, monkeypatch)
    dec = _auth(repo, "sdd-full")
    assert dec.allowed, dec.reasons
    assert _auth(repo, "dev-run").allowed


def test_spec_compliance_red_blocks_full(repo, monkeypatch):
    _all_green(repo, monkeypatch)
    repo.spec_report("RED")
    assert cli.main(["record-spec", "--feat-number", str(FEAT)]) == 2
    dec = _auth(repo, "sdd-full")
    assert not dec.allowed and "spec_compliance" in dec.failed


@pytest.mark.parametrize("verdict,serious,acs,ok", [
    ("YELLOW", 0, 3, True), ("YELLOW", 1, 3, False), ("GREEN", 0, 0, False),
    ("UNKNOWN", 0, 3, False),
    # format réel du reviewer (audit 2026-11-07) : « 🟡 WARN » = YELLOW
    ("🟡 WARN", 0, 3, True), ("🟡 WARN", 1, 3, False), ("🟢 GREEN", 0, 3, True)])
def test_spec_report_evaluation(verdict, serious, acs, ok):
    payload = {"feat": FEAT, "config": {"fail_on": "serious"},
               "summary": {"verdict": verdict, "total_acs": acs,
                           "issues": {"critical": 0, "serious": serious}}}
    assert cli.evaluate_spec_report(payload, FEAT)[0] is ok


def test_spec_report_of_other_feat_rejected():
    payload = {"feat": FEAT + 1, "summary": {"verdict": "GREEN", "total_acs": 2, "issues": {}}}
    assert cli.evaluate_spec_report(payload, FEAT)[0] is False


def test_readiness_nogo_then_warn_without_input_change_blocks(repo, monkeypatch):
    (repo.ws / "feats" / f"{FEAT}-Demo.md").write_text("# FEAT", encoding="utf-8")
    assert _readiness(monkeypatch, "NO-GO") == 2
    assert _readiness(monkeypatch, "WARN") == 0
    assert _build(repo) == 0
    dec = _auth(repo, "dev-run")
    assert not dec.allowed and dec.failed == ["readiness"]
    assert any("instable" in r for r in dec.reasons)
    # seul un changement des entrées lève le NO-GO
    (repo.ws / "feats" / f"{FEAT}-Demo.md").write_text("# FEAT corrigée", encoding="utf-8")
    assert _auth(repo, "dev-run").stale == ["readiness"]
    assert _readiness(monkeypatch, "WARN") == 0
    assert _auth(repo, "dev-run").allowed


def test_readiness_really_executes_validate_readiness(repo):
    # Pas de FEAT dans le faux dépôt → validate_readiness.py rend NO-GO.
    assert cli.main(["record-readiness", "--feat-number", str(FEAT)]) == 2
    row = dg._fetch_rows(FEAT, "readiness")[-1]
    assert row["passed"] == 0 and json.loads(row["details_json"])["decision"] == "NO-GO"


# ---------------------------------------------------------------------------
# Anti-auto-certification
# ---------------------------------------------------------------------------

def test_unknown_workflow_blocked(repo, monkeypatch):
    _all_green(repo, monkeypatch)
    dec = _auth(repo, "sdd-yolo")
    assert not dec.allowed and dec.required == ()


def test_lying_run_phases_payload_authorizes_nothing(repo):
    from sdd_lib.console_db import connect, ensure_initialized, upsert_run, upsert_run_phase
    ensure_initialized()
    with connect() as conn:
        upsert_run(conn, run_id="run-t", command="sdd-full", feat_n=FEAT, status="pass")
        for phase in ("readiness", "dev_run", "qa", "spec_compliance", "build"):
            upsert_run_phase(conn, run_id="run-t", phase=phase, status="pass",
                             payload={"buildVerified": True,
                                      "qa": {"executed": True, "verdict": "pass"}})
    for wf in ("sdd-full", "sdd-poc", "dev-run", "sdd-deploy"):
        assert not _auth(repo, wf).allowed


def _db():
    from sdd_lib.console_db import default_db_path
    return sqlite3.connect(str(default_db_path()))


def test_sql_inserted_evidence_is_worthless(repo):
    dg._fetch_rows(FEAT, "build")  # crée la table
    tree = dg.compute_tree_hash(dg.default_project_roots())
    with _db() as conn:
        conn.execute(
            "INSERT INTO delivery_evidence (ts, feat_n, run_id, check_name, passed, exit_code,"
            " command, details_json, tree_hash, producer, hmac) VALUES"
            " ('2026-11-07T00:00:00.000Z', ?, 'r', 'build', 1, 0, 'x', '{\"artifacts\":[]}',"
            " ?, 'verify_build.py', NULL)", (FEAT, tree))
    dec = _auth(repo, "sdd-poc")
    assert not dec.allowed and dec.failed == ["build"]
    assert any("non authentifiée" in r for r in dec.reasons)


def test_altered_hmac_or_row_blocks(repo):
    assert _build(repo) == 0
    assert _auth(repo, "sdd-poc").allowed
    with _db() as conn:
        conn.execute("UPDATE delivery_evidence SET exit_code = 0, command = 'other'")
    dec = _auth(repo, "sdd-poc")
    assert not dec.allowed and any("non authentifiée" in r for r in dec.reasons)


def test_failure_rewritten_as_pass_in_sql_blocks(repo):
    repo.configure(build="ko")
    assert _build(repo) == 2
    with _db() as conn:
        conn.execute("UPDATE delivery_evidence SET passed = 1, exit_code = 0")
    assert not _auth(repo, "sdd-poc").allowed


@pytest.mark.parametrize("var", ["SDD_ALLOW_FORCE", "SDD_FORCE", "SDD_BYPASS_TWO_STAGE",
                                 "SDD_ALLOW_ACCEPTANCE_BYPASS", "SDD_ALLOW_PHASE_SKIP"])
def test_bypass_env_never_changes_decision_and_is_audited(repo, monkeypatch, tmp_path, var):
    blocked_before = _auth(repo, "sdd-poc")
    monkeypatch.setenv(var, "1")
    blocked = _auth(repo, "sdd-poc")
    assert blocked.allowed is blocked_before.allowed is False
    assert blocked.missing == ["build"]
    assert any(var in r for r in blocked.reasons)
    events = [e for e in _audit_lines(tmp_path) if e["event"] == "bypass_env_ignored"]
    assert events and var in events[-1]["variables"]
    # une livraison autorisée le reste, sans que la variable n'y soit pour rien
    assert _build(repo) == 0
    assert _auth(repo, "sdd-poc").allowed


def test_hmac_key_lives_outside_repo(repo, monkeypatch):
    assert _build(repo) == 0
    assert dg.key_path().is_file()
    assert repo.root not in dg.key_path().parents
    monkeypatch.setenv("USERPROFILE", str(repo.root))
    monkeypatch.setenv("HOME", str(repo.root))
    with pytest.raises(dg.DeliveryGateError):
        dg._load_key(create=True)


def test_record_evidence_rejects_unknown_producer(repo):
    with pytest.raises(ValueError):
        dg._record_evidence(feat_n=FEAT, check="build", run_id=None, passed=True, exit_code=0,
                            command="x", details={}, tree_hash="0", producer="orchestrator")
    assert not hasattr(dg, "record_evidence")


def test_cli_authorize_blocked_prints_error_3l(repo):
    proc = subprocess.run(
        [sys.executable, str(_PY_ROOT / "sdd_scripts" / "delivery_gate.py"), "authorize",
         "--feat-number", str(FEAT), "--workflow", "sdd-full", "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, cwd=str(repo.root))
    assert proc.returncode == 2
    all_lines = proc.stderr.strip().splitlines()
    i = next(k for k, ln in enumerate(all_lines) if ln.startswith("ERROR: delivery-gate"))
    lines = all_lines[i:i + 3]
    assert lines[0].startswith("ERROR: delivery-gate")
    assert lines[1].startswith("CAUSE: [DELIVERY_GATE_BLOCKED]")
    assert lines[2].startswith("FIX:")
    assert json.loads(proc.stdout)["allowed"] is False


def test_cli_authorize_allowed_exit0(repo):
    assert _build(repo) == 0
    proc = subprocess.run(
        [sys.executable, str(_PY_ROOT / "sdd_scripts" / "delivery_gate.py"), "authorize",
         "--feat-number", str(FEAT), "--workflow", "sdd-poc"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, cwd=str(repo.root))
    assert proc.returncode == 0, proc.stderr
