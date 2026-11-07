"""Audit « fiabilité des données et des états » (2026-11-07) — regression tests.

Covers the 9 findings of the lot :
  1. pytest isolation of console.db ($SDD_CONSOLE_DB_PATH + conftest guard)
  2. atomic + idempotent migrations (concurrent threads AND processes)
  3. connect_ro : ConsoleDbUnavailable, immutable only with allow_stale=True
  4. atomic_write : unique temp names, concurrent writers never corrupt
  5. file_locks : compare-and-delete takeover + mtime grace
  6. run_id : per-session marker, no 3 h TTL, legacy 24 h + WARN
  7. run_end / run_close.py / sdd_state final-phase closing / stale sweep
  8. gates : console.db source of truth, status.json derived export
"""
from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import console_db  # noqa: E402
from sdd_lib import paths  # noqa: E402
from sdd_lib.console_db import core  # noqa: E402

SCRIPTS = _PY_ROOT / "sdd_scripts"


def _fresh_db(tmp_path: Path, name: str = "c.db") -> Path:
    db = tmp_path / name
    console_db.ensure_initialized(db)
    return db


# ---------------------------------------------------------------------------
# 1. Isolation
# ---------------------------------------------------------------------------

def test_default_db_path_is_under_tmp_during_tests(tmp_path):
    p = console_db.default_db_path()
    runtime = paths.runtime_console_db_path()
    assert runtime is None or p.resolve() != runtime.resolve()
    assert str(tmp_path) in str(p)


def test_override_mode_always_wins(tmp_path, monkeypatch):
    target = tmp_path / "elsewhere" / "x.db"
    monkeypatch.setenv("SDD_CONSOLE_DB_PATH", str(target))
    monkeypatch.delenv("SDD_CONSOLE_DB_PATH_MODE", raising=False)
    fake = tmp_path / "fake"
    (fake / "workspace").mkdir(parents=True)
    assert paths.console_db_path(fake) == target.resolve()


def test_fallback_mode_keeps_fake_repo_path(tmp_path, monkeypatch):
    fake = tmp_path / "fake"
    (fake / "workspace").mkdir(parents=True)
    monkeypatch.setenv("SDD_CONSOLE_DB_PATH_MODE", "fallback")
    assert paths.console_db_path(fake) == fake / "workspace" / "db" / "console.db"


def test_fallback_mode_redirects_runtime_repo(monkeypatch, tmp_path):
    root = paths._framework_repo_root()
    if root is None:
        pytest.skip("not running inside a framework checkout")
    target = tmp_path / "x.db"
    monkeypatch.setenv("SDD_CONSOLE_DB_PATH", str(target))
    monkeypatch.setenv("SDD_CONSOLE_DB_PATH_MODE", "fallback")
    assert paths.console_db_path(root) == target.resolve()


def test_subprocess_inherits_isolation(tmp_path):
    """A script launched with cwd=real repo must not resolve the runtime DB."""
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "from sdd_lib.console_db import default_db_path; print(default_db_path())") % _PY_ROOT
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(_PY_ROOT.parent.parent), check=True).stdout.strip()
    runtime = paths.runtime_console_db_path()
    assert runtime is None or Path(out).resolve() != runtime.resolve()


# ---------------------------------------------------------------------------
# 2. Migrations
# ---------------------------------------------------------------------------

def test_split_sql_statements_handles_comments_and_strings():
    sql = "-- c1\nCREATE TABLE a(x TEXT DEFAULT ';');\n-- c2\nINSERT INTO a VALUES('a;b');"
    stmts = core.split_sql_statements(sql)
    assert len(stmts) == 2
    assert "';'" in stmts[0] and "'a;b'" in stmts[1]


def test_add_column_replay_is_noop(tmp_path):
    db = _fresh_db(tmp_path)
    m5 = (core.MIGRATIONS_DIR / "0005_add-api-tests-status-column.sql").read_text(encoding="utf-8")
    with console_db.connect(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        core._execute_script_guarded(conn, m5)  # column already there → skipped
        conn.execute("COMMIT")


def test_migration_and_version_are_atomic(tmp_path, monkeypatch):
    """A failing migration leaves neither its DDL nor its version row."""
    mig = tmp_path / "migs"
    mig.mkdir()
    (mig / "0002_ok.sql").write_text("CREATE TABLE t2(x INTEGER);", encoding="utf-8")
    (mig / "0003_boom.sql").write_text(
        "CREATE TABLE t3(x INTEGER);\nINSERT INTO no_such_table VALUES(1);",
        encoding="utf-8")
    monkeypatch.setattr(core, "MIGRATIONS_DIR", mig)
    monkeypatch.setattr(core, "SCHEMA_VERSION", 3)
    db = tmp_path / "m.db"
    with pytest.raises(sqlite3.OperationalError):
        console_db.ensure_initialized(db)
    with console_db.connect(db) as conn:
        assert console_db.current_schema_version(conn) == 2
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "t2" in names and "t3" not in names


def test_concurrent_initialisation_threads(tmp_path):
    db = tmp_path / "race.db"
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()
            console_db.ensure_initialized(db)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    assert not errors, errors
    with console_db.connect(db) as conn:
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_version ORDER BY version")]
    assert versions == list(range(1, console_db.SCHEMA_VERSION + 1))


def _init_in_process(db: str) -> None:
    sys.path.insert(0, str(_PY_ROOT))
    from sdd_lib.console_db import ensure_initialized
    ensure_initialized(db)


def test_concurrent_migration_processes_from_v4(tmp_path):
    """Two processes migrating the same v4 DB never hit `duplicate column name`."""
    db = tmp_path / "proc.db"
    con = sqlite3.connect(str(db))
    con.executescript(core.load_schema_sql())
    con.execute("INSERT INTO schema_version VALUES(1, 'x')")
    for f in sorted(core.MIGRATIONS_DIR.glob("000[234]_*.sql")):
        con.executescript(f.read_text(encoding="utf-8"))
        con.execute("INSERT INTO schema_version VALUES(?, 'x')", (int(f.name[:4]),))
    con.commit()
    con.close()
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_init_in_process, args=(str(db),)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
    assert all(p.exitcode == 0 for p in procs), [p.exitcode for p in procs]
    with console_db.connect(db) as conn:
        assert console_db.current_schema_version(conn) == console_db.SCHEMA_VERSION
        cols = [r[1] for r in conn.execute("PRAGMA table_info(qa_code_review)")]
    assert cols.count("detector") == 1


# ---------------------------------------------------------------------------
# 3. connect_ro
# ---------------------------------------------------------------------------

def _fail_first_connect(real):
    calls = {"n": 0}

    def fake(target, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("unable to open database file")
        return real(target, *a, **kw)
    return fake, calls


def test_connect_ro_raises_typed_error_without_allow_stale(tmp_path):
    db = _fresh_db(tmp_path)
    fake, _ = _fail_first_connect(sqlite3.connect)
    with mock.patch.object(core.sqlite3, "connect", side_effect=fake):
        with pytest.raises(console_db.ConsoleDbUnavailable) as ei:
            with console_db.connect_ro(db):
                pass
    assert "[INFRA_BLOCKED]" in str(ei.value)
    assert isinstance(ei.value, sqlite3.OperationalError)


def test_connect_ro_allow_stale_uses_immutable(tmp_path, capsys):
    db = _fresh_db(tmp_path)
    seen: list[str] = []
    real = sqlite3.connect
    fake, _ = _fail_first_connect(real)

    def spy(target, *a, **kw):
        seen.append(target)
        return fake(target, *a, **kw)
    with mock.patch.object(core.sqlite3, "connect", side_effect=spy):
        with console_db.connect_ro(db, allow_stale=True) as conn:
            assert console_db.current_schema_version(conn) == console_db.SCHEMA_VERSION
    assert "immutable=1" in seen[-1]
    assert "STALE" in capsys.readouterr().err


def test_connect_ro_sees_committed_wal_rows(tmp_path):
    db = _fresh_db(tmp_path)
    with console_db.connect(db) as conn:
        console_db.upsert_run(conn, run_id="r-wal", command="t")
    with console_db.connect_ro(db) as ro:
        assert console_db.get_run(ro, "r-wal") is not None


# ---------------------------------------------------------------------------
# 4. atomic_write
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("modname", ["sdd_lib.atomic_write", "sdd_reverse.atomic_write_local"])
def test_concurrent_atomic_writes_never_corrupt(tmp_path, modname):
    import importlib
    mod = importlib.import_module(modname)
    target = tmp_path / "shared.txt"
    payloads = [(chr(ord("a") + i) * 20000) for i in range(8)]
    errors: list[BaseException] = []

    def worker(data: str):
        try:
            for _ in range(5):
                mod.atomic_write_text(target, data)
        except PermissionError:
            pass  # Windows sharing violation after retries — never corruption
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(p,)) for p in payloads]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    assert not errors, errors
    assert target.read_text(encoding="utf-8") in payloads
    assert not list(tmp_path.glob("*.sddtmp"))


def test_atomic_write_tmp_name_is_unique(tmp_path):
    from sdd_lib import atomic_write
    seen: list[str] = []
    real = atomic_write._replace_with_retry

    def spy(tmp, dst):
        seen.append(Path(tmp).name)
        return real(tmp, dst)
    with mock.patch.object(atomic_write, "_replace_with_retry", side_effect=spy):
        atomic_write.atomic_write_text(tmp_path / "f.txt", "1")
        atomic_write.atomic_write_text(tmp_path / "f.txt", "2")
    assert len(set(seen)) == 2
    assert all(n.startswith(".f.txt.") and n.endswith(".sddtmp") for n in seen)


def test_atomic_write_newline_semantics(tmp_path):
    from sdd_lib.atomic_write import atomic_write_text
    p = tmp_path / "n.txt"
    atomic_write_text(p, "a\nb", newline="\n")
    assert p.read_bytes() == b"a\nb"
    atomic_write_text(p, "a\nb", newline="\r\n")
    assert p.read_bytes() == b"a\r\nb"


# ---------------------------------------------------------------------------
# 5. file_locks takeover
# ---------------------------------------------------------------------------

def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_takeover_refuses_when_payload_changed(tmp_path):
    from sdd_lib.file_locks import takeover_stale_lock
    lock = tmp_path / "x.lock"
    lock.write_text("B:999:1", encoding="ascii")  # someone else's NEW payload
    _age(lock, 60)
    assert takeover_stale_lock(lock, observed_content="A:1:1", new_content="C:1:2") is False
    assert lock.read_text(encoding="ascii") == "B:999:1"


def test_takeover_refuses_fresh_empty_lock(tmp_path):
    from sdd_lib.file_locks import takeover_stale_lock
    lock = tmp_path / "x.lock"
    lock.write_text("", encoding="ascii")
    assert takeover_stale_lock(lock, observed_content="", new_content="C:1:2") is False
    _age(lock, 60)
    assert takeover_stale_lock(lock, observed_content="", new_content="C:1:2") is True
    assert lock.read_text(encoding="ascii") == "C:1:2"


def test_concurrent_stale_takeover_single_winner(tmp_path):
    from sdd_lib.file_locks import acquire_with_retry
    lock = tmp_path / "x.lock"
    lock.write_text(f"dead:1:{int(time.time() * 1000) - 3_600_000}", encoding="ascii")
    _age(lock, 3600)
    winners: list[str] = []
    guard = threading.Lock()
    barrier = threading.Barrier(6)

    def worker(i):
        barrier.wait()
        try:
            acquire_with_retry(lock, payload_prefix=f"w{i}", ttl_ms=5000,
                               retry_count=1, backoff_ms=1)
            with guard:
                winners.append(f"w{i}")
        except RuntimeError:
            pass
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert len(winners) == 1, winners


# ---------------------------------------------------------------------------
# 6. run_id per session
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    for d in (".claude/agents", ".claude/commands", "workspace"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    for var in ("SDD_RUN_ID", "CLAUDE_SESSION_ID", "SDD_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_run_id_is_per_session(fake_repo):
    from sdd_lib import run_id
    a1 = run_id.get_or_create_run_id(session_id="sess-A")
    b1 = run_id.get_or_create_run_id(session_id="sess-B")
    assert a1 != b1
    assert run_id.get_or_create_run_id(session_id="sess-A") == a1
    state = fake_repo / "workspace" / ".sys" / ".state"
    assert (state / "run-id.sess-A").read_text(encoding="utf-8").strip() == a1


def test_session_marker_has_no_ttl(fake_repo):
    from sdd_lib import run_id
    rid = run_id.get_or_create_run_id(session_id="s1")
    marker = fake_repo / "workspace" / ".sys" / ".state" / "run-id.s1"
    _age(marker, 5 * 24 * 3600)
    assert run_id.get_or_create_run_id(session_id="s1") == rid


def test_session_from_env(fake_repo, monkeypatch):
    from sdd_lib import run_id
    monkeypatch.setenv("CLAUDE_SESSION_ID", "env/sess:1")
    rid = run_id.get_or_create_run_id()
    marker = fake_repo / "workspace" / ".sys" / ".state" / "run-id.env-sess-1"
    assert marker.read_text(encoding="utf-8").strip() == rid


def test_legacy_marker_ttl_24h_and_warns(fake_repo, capsys, monkeypatch):
    from sdd_lib import run_id
    monkeypatch.setattr(run_id, "_legacy_warned", False)
    rid = run_id.get_or_create_run_id()
    assert "WARN" in capsys.readouterr().err
    marker = fake_repo / "workspace" / ".sys" / ".state" / "run-id.current"
    _age(marker, 4 * 3600)  # older than the former 3 h TTL
    assert run_id.get_or_create_run_id() == rid
    _age(marker, 25 * 3600)
    assert run_id.get_or_create_run_id() != rid


def test_clear_marker_only_for_matching_run(fake_repo):
    from sdd_lib import run_id
    rid = run_id.get_or_create_run_id(session_id="s2")
    assert run_id.clear_run_id_marker("s2", run_id="other") is False
    assert run_id.clear_run_id_marker("s2", run_id=rid) is True
    assert run_id.get_or_create_run_id(session_id="s2") != rid


# ---------------------------------------------------------------------------
# 7. run_end / stale sweep / run_close / sdd_state
# ---------------------------------------------------------------------------

def test_run_end_idempotent(tmp_path):
    db = _fresh_db(tmp_path)
    with console_db.connect(db) as conn:
        console_db.upsert_run(conn, run_id="r1", command="hook", feat_n=1)
        assert console_db.run_end(conn, "r1", "completed", "GREEN") is True
        assert console_db.run_end(conn, "r1", "completed", "GREEN") is False
        assert console_db.run_end(conn, "r1", "completed") is False
        row = console_db.get_run(conn, "r1")
        ends = conn.execute(
            "SELECT COUNT(*) FROM events WHERE run_id='r1' AND event_type='run.end'"
        ).fetchone()[0]
        assert console_db.run_end(conn, "missing", "failed") is False
        with pytest.raises(ValueError):
            console_db.run_end(conn, "r1", "bogus")
    assert row["status"] == "completed" and row["ended_at"]
    assert json.loads(row["params_json"])["verdict"] == "GREEN"
    assert ends == 1


def test_mark_stale_runs(tmp_path):
    db = _fresh_db(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    with console_db.connect(db) as conn:
        console_db.upsert_run(conn, run_id="old", command="hook", started_at=old)
        conn.execute("UPDATE runs SET updated_at=? WHERE run_id='old'", (old,))
        console_db.upsert_run(conn, run_id="fresh", command="hook")
    console_db.ensure_initialized(db)  # sweep happens here
    console_db.ensure_initialized(db)  # idempotent
    with console_db.connect(db) as conn:
        assert console_db.get_run(conn, "old")["status"] == "stale"
        assert console_db.get_run(conn, "fresh")["status"] == "running"


def test_run_close_cli(tmp_path):
    db = console_db.default_db_path()
    console_db.ensure_initialized(db)
    with console_db.connect(db) as conn:
        console_db.upsert_run(conn, run_id="rc-1", command="hook")
    cmd = [sys.executable, str(SCRIPTS / "run_close.py"), "--run-id", "rc-1",
           "--status", "partial", "--verdict", "WARN"]
    r1 = subprocess.run(cmd, capture_output=True, text=True)
    r2 = subprocess.run(cmd, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    assert json.loads(r1.stdout)["status"] == "CLOSED"
    assert json.loads(r2.stdout)["status"] == "ALREADY_CLOSED"
    r3 = subprocess.run([sys.executable, str(SCRIPTS / "run_close.py"), "--run-id", "nope",
                         "--status", "failed"], capture_output=True, text=True)
    assert r3.returncode == 1


def _state(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "sdd_state.py"), *args],
                          capture_output=True, text=True)


@pytest.mark.parametrize("command,phase_status,run_status", [
    # run hors workflow de livraison : mécanique de clôture inchangée
    ("/us-generate", "pass", "completed"), ("/us-generate", "warn", "completed"),
    ("/sdd-full", "fail", "failed"),
    # gate de livraison (2026-11-07) : /sdd-full sans preuve → jamais completed
    ("/sdd-full", "pass", "failed"), ("/sdd-full", "warn", "failed"),
])
def test_final_phase_closes_run(command, phase_status, run_status):
    r = _state("new-run", "--feat-number", "1", "--command", command)
    assert r.returncode == 0, r.stderr
    rid = r.stdout.strip()
    assert _state("set-phase", "--run-id", rid, "--phase", "qa", "--status", "pass").returncode == 0
    with console_db.connect() as conn:
        assert console_db.get_run(conn, rid)["status"] == "running"
    blocked = command == "/sdd-full" and phase_status != "fail"
    r = _state("set-phase", "--run-id", rid, "--phase", "sdd_review", "--status", phase_status)
    assert r.returncode == (2 if blocked else 0), r.stderr
    if blocked:
        assert "[DELIVERY_GATE_BLOCKED]" in r.stderr
    with console_db.connect() as conn:
        assert console_db.get_run(conn, rid)["status"] == run_status
    # end-run afterwards stays consistent (idempotent when same status)
    if run_status == "completed":
        r = _state("end-run", "--run-id", rid, "--status", "completed")
        assert "already ended" in r.stdout


# ---------------------------------------------------------------------------
# 8. gates : DB source of truth, status.json derived
# ---------------------------------------------------------------------------

def _gate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "gate_decide.py"), *args],
                          capture_output=True, text=True)


def test_gate_db_is_source_status_json_is_export(tmp_path):
    sf = tmp_path / "status.json"
    assert _gate("pose-pending", "--feat-num", "4", "--phase", "afterUS",
                 "--status-file", str(sf)).returncode == 0
    # Deleting / corrupting the export must not change the gate state.
    sf.write_text("{corrupt", encoding="utf-8")
    assert _gate("read", "--feat-num", "4", "--phase", "afterUS",
                 "--status-file", str(sf)).stdout.strip() == "pending"
    sf.unlink()
    assert _gate("read", "--feat-num", "4", "--phase", "afterUS",
                 "--status-file", str(sf)).stdout.strip() == "pending"
    assert _gate("export", "--status-file", str(sf)).returncode == 0
    data = json.loads(sf.read_text(encoding="utf-8"))
    assert data["source"] == "console.db"
    assert data["gates"]["4"]["afterUS"]["decision"] == "pending"


def test_gate_export_preserves_foreign_keys(tmp_path):
    from sdd_scripts import gate_decide
    sf = tmp_path / "status.json"
    sf.write_text(json.dumps({"version": 1, "FEATs": {"1": {"x": 1}}, "gates": {}}),
                  encoding="utf-8")
    db = console_db.default_db_path()
    console_db.ensure_initialized(db)
    with console_db.connect(db) as conn:
        console_db.insert_gate(conn, gate_name="afterPlan", decision="pending", feat_n=1)
    out = gate_decide.export_status_json(sf)
    assert out["FEATs"] == {"1": {"x": 1}}
    assert out["gates"]["1"]["afterPlan"]["decision"] == "pending"


def test_gate_legacy_console_decision_imported(tmp_path):
    """Decision written only to status.json (Node console) is imported, not lost."""
    sf = tmp_path / "status.json"
    assert _gate("pose-pending", "--feat-num", "6", "--phase", "afterCode",
                 "--status-file", str(sf)).returncode == 0
    data = json.loads(sf.read_text(encoding="utf-8"))
    g = data["gates"]["6"]["afterCode"]
    g.update({"decision": "validated", "answeredBy": "lead@ui",
              "answeredAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    sf.write_text(json.dumps(data), encoding="utf-8")
    r = _gate("is-resolved", "--feat-num", "6", "--phase", "afterCode", "--status-file", str(sf))
    assert r.returncode == 0, r.stderr
    assert "importée" in r.stderr
    with console_db.connect() as conn:
        latest = console_db.get_latest_gate(conn, feat_n=6, gate_name="afterCode")
    assert latest["decision"] == "validated" and latest["answeredBy"] == "lead@ui"


def test_gate_db_unavailable_is_infra_blocked(tmp_path, monkeypatch):
    bad = tmp_path / "not-a-db"
    bad.mkdir()  # a directory where the DB file should be → cannot open
    monkeypatch.setenv("SDD_CONSOLE_DB_PATH", str(bad))
    monkeypatch.delenv("SDD_CONSOLE_DB_PATH_MODE", raising=False)
    r = _gate("set", "--feat-num", "1", "--phase", "afterUS", "--decision", "validated",
              "--status-file", str(tmp_path / "s.json"))
    assert r.returncode == 3
    assert "[INFRA_BLOCKED]" in r.stderr
