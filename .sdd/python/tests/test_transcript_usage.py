"""Lot « mesure exacte des tokens et des coûts » (audit tokens 2026-11-07).

Couvre :
  * `sdd_lib.transcript_usage` — lecture JSONL, déduplication par
    `message.id` (un message streamé = N lignes, même usage), ventilation par
    modèle, localisation des transcripts sous-agent ;
  * `sdd_hooks.record_token_usage` — SubagentStop (somme de TOUS les tours,
    `agent_type`, modèle réel, idempotent), Stop (orchestrateur upserté),
    PostToolUse (plus aucune ligne) ;
  * `sdd_hooks.preflight_cost_cap` — orchestrateur compté, ligne non
    attribuée jamais bloquante en CI ;
  * `sdd_hooks.statusline` — coût calculé sur le schéma réel ;
  * `sdd_scripts.context_budget` — 3,5 o/token, coût par modèle, budgets auditeurs.

Toutes les données vivent sous `tmp_path` (faux dépôt + `$SDD_REPO_ROOT`).
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import pricing  # noqa: E402
from sdd_lib.transcript_usage import (  # noqa: E402
    locate_session_transcript,
    locate_subagent_transcript,
    read_transcript_usage,
)

# --------------------------------------------------------------------------- #
# Fabrique de transcripts synthétiques (format réel observé 2026-11-06)
# --------------------------------------------------------------------------- #


def _assistant(msg_id: str, model: str, inp: int, out: int, cc: int = 0, cr: int = 0,
               uuid: str | None = None, session: str = "sess-1",
               agent_id: str | None = None) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid or f"u-{msg_id}-{os.urandom(3).hex()}",
        "sessionId": session,
        "agentId": agent_id,
        "timestamp": "2026-11-06T23:11:28.227Z",
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_creation_input_tokens": cc,
                "cache_read_input_tokens": cr,
                "cache_creation": {"ephemeral_5m_input_tokens": cc,
                                   "ephemeral_1h_input_tokens": 0},
            },
        },
    }


def _user(text: str, session: str = "sess-1", agent_id: str | None = None) -> dict:
    return {"type": "user", "uuid": f"u-{os.urandom(3).hex()}", "sessionId": session,
            "agentId": agent_id, "message": {"role": "user", "content": text}}


def _write(path: Path, records: list[dict], extra_lines: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
        for line in extra_lines or []:
            fh.write(line + "\n")
    return path


def _subagent_records(agent_id: str = "a1") -> list[dict]:
    """2 messages distincts, chacun streamé en 3 lignes (texte, thinking, tool)."""
    recs = [_user("dispatch dev-backend sur l'US 3-2-Login", agent_id=agent_id)]
    for _ in range(3):
        recs.append(_assistant("msg_A", "claude-opus-5-5[1m]", 2, 500, cc=40_000,
                               agent_id=agent_id))
    for _ in range(3):
        recs.append(_assistant("msg_B", "claude-opus-5-5", 3, 700, cc=1_000, cr=40_000,
                               agent_id=agent_id))
    return recs


# --------------------------------------------------------------------------- #
# Lecteur
# --------------------------------------------------------------------------- #


class TestReader:
    def test_dedup_by_message_id_sums_all_turns(self, tmp_path):
        f = _write(tmp_path / "agent-a1.jsonl", _subagent_records())
        u = read_transcript_usage(f)
        assert u.found
        assert u.turns == 2  # 6 lignes → 2 messages
        t = u.total
        assert (t.input_tokens, t.output_tokens) == (5, 1200)
        assert t.cache_creation_input_tokens == 41_000
        assert t.cache_read_input_tokens == 40_000
        assert t.ephemeral_5m_input_tokens == 41_000

    def test_model_suffix_is_canonicalized(self, tmp_path):
        u = read_transcript_usage(_write(tmp_path / "t.jsonl", _subagent_records()))
        assert list(u.by_model) == ["claude-opus-5-5"]
        assert u.primary_model == "claude-opus-5-5"

    def test_last_occurrence_wins(self, tmp_path):
        recs = [_assistant("msg_X", "claude-sonnet-5-5", 1, 10),
                _assistant("msg_X", "claude-sonnet-5-5", 1, 99)]
        u = read_transcript_usage(_write(tmp_path / "t.jsonl", recs))
        assert u.total.output_tokens == 99 and u.turns == 1

    def test_per_model_split(self, tmp_path):
        recs = [_assistant("m1", "claude-opus-5-5", 10, 1),
                _assistant("m2", "claude-haiku-5-5", 20, 2),
                _assistant("m3", "claude-opus-5-5", 30, 3)]
        u = read_transcript_usage(_write(tmp_path / "t.jsonl", recs))
        assert u.by_model["claude-opus-5-5"].input_tokens == 40
        assert u.by_model["claude-haiku-5-5"].turns == 1

    def test_malformed_lines_and_non_usage_records_ignored(self, tmp_path):
        recs = [_user("bonjour"), {"type": "summary", "summary": "x"},
                _assistant("m1", "claude-opus-5-5", 1, 1)]
        u = read_transcript_usage(_write(tmp_path / "t.jsonl", recs,
                                         extra_lines=["pas du json", "{partiel:"]))
        assert u.turns == 1
        assert u.first_user_text == "bonjour"
        assert u.session_id == "sess-1"

    def test_message_without_id_falls_back_to_uuid(self, tmp_path):
        r1 = _assistant("ignored", "claude-opus-5-5", 1, 1, uuid="U1")
        r2 = _assistant("ignored", "claude-opus-5-5", 1, 1, uuid="U2")
        for r in (r1, r2):
            del r["message"]["id"]
        u = read_transcript_usage(_write(tmp_path / "t.jsonl", [r1, r2]))
        assert u.turns == 2

    def test_missing_file(self, tmp_path):
        u = read_transcript_usage(tmp_path / "nope.jsonl")
        assert not u.found and u.turns == 0


class TestLocate:
    def _layout(self, tmp_path):
        main = _write(tmp_path / "sess-1.jsonl", [_assistant("m0", "claude-fable-5-1", 1, 1)])
        a1 = _write(tmp_path / "sess-1" / "subagents" / "agent-a1.jsonl", _subagent_records("a1"))
        a2 = _write(tmp_path / "sess-1" / "subagents" / "agent-a2.jsonl", _subagent_records("a2"))
        os.utime(a1, (1_000_000_000, 1_000_000_000))
        return main, a1, a2

    def test_agent_transcript_path_wins(self, tmp_path):
        main, a1, _ = self._layout(tmp_path)
        p, how = locate_subagent_transcript({"agent_transcript_path": str(a1),
                                             "transcript_path": str(main), "agent_id": "a2"})
        assert p == a1 and how == "agent_transcript_path"

    def test_transcript_path_plus_agent_id(self, tmp_path):
        main, a1, _ = self._layout(tmp_path)
        p, how = locate_subagent_transcript({"transcript_path": str(main), "agent_id": "a1"})
        assert p == a1 and how == "transcript_path+agent_id"

    def test_latest_fallback(self, tmp_path):
        main, _, a2 = self._layout(tmp_path)
        p, how = locate_subagent_transcript({"transcript_path": str(main)})
        assert p == a2 and how == "latest-under-subagents"

    def test_not_found(self, tmp_path):
        assert locate_subagent_transcript({})[0] is None
        assert locate_session_transcript({"transcript_path": str(tmp_path / "x.jsonl")}) is None


# --------------------------------------------------------------------------- #
# Hook record_token_usage (in-process, faux dépôt)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    for d in (".sdd/agents", ".sdd/commands", ".claude/agents", ".claude/commands", "workspace"):
        (repo / d).mkdir(parents=True)
    monkeypatch.setenv("SDD_REPO_ROOT", str(repo))
    monkeypatch.setenv("SDD_RUN_ID", "run-test-1")
    monkeypatch.setenv("SDD_TOKEN_USAGE_MODE", "record")
    monkeypatch.delenv("SDD_CONSOLE_DB_PATH", raising=False)
    monkeypatch.delenv("SDD_CONSOLE_DB_PATH_MODE", raising=False)
    from sdd_hooks import record_token_usage as mod
    from sdd_lib import console_db
    monkeypatch.setattr(mod, "_MODE_CACHE", None)
    monkeypatch.setattr(mod, "_SESSION_ID", None)  # main() le pose ; restauré après le test
    monkeypatch.setattr(mod, "repo_root", lambda: repo)
    monkeypatch.setattr(console_db.core, "repo_root", lambda: repo)
    return repo


def _run_hook(payload: dict) -> int:
    from sdd_hooks import record_token_usage as mod
    with mock.patch.object(mod, "read_hook_input", return_value=payload):
        return mod.main()


def _rows(repo: Path) -> list[sqlite3.Row]:
    db = repo / "workspace" / "db" / "console.db"
    if not db.is_file():
        return []
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM token_usage ORDER BY id").fetchall()
    finally:
        conn.close()


class TestHookSubagentStop:
    def test_records_full_transcript_with_real_model(self, fake_repo, tmp_path):
        logs = tmp_path / "logs"
        main = _write(logs / "sess-1.jsonl", [])
        a1 = _write(logs / "sess-1" / "subagents" / "agent-a1.jsonl", _subagent_records())
        rc = _run_hook({"hook_event_name": "SubagentStop", "agent_type": "dev-backend",
                        "agent_id": "a1", "agent_transcript_path": str(a1),
                        "transcript_path": str(main), "session_id": "sess-1"})
        assert rc == 0
        rows = _rows(fake_repo)
        assert len(rows) == 1
        r = rows[0]
        assert r["agent"] == "dev-backend"  # agent_type, pas « SubagentStop »
        assert r["model"] == "claude-opus-5-5"
        assert (r["input_tokens"], r["output_tokens"]) == (5, 1200)
        assert r["cache_creation_tokens"] == 41_000 and r["cache_read_tokens"] == 40_000
        assert r["run_id"] == "run-test-1"
        assert (r["feat_n"], r["us_id"]) == (3, "3-2")  # tiré du prompt du sous-agent

    def test_idempotent_on_double_fire(self, fake_repo, tmp_path):
        a1 = _write(tmp_path / "s" / "subagents" / "agent-a1.jsonl", _subagent_records())
        payload = {"hook_event_name": "SubagentStop", "agent_type": "qa",
                   "agent_id": "a1", "agent_transcript_path": str(a1)}
        _run_hook(payload)
        _run_hook(payload)
        assert len(_rows(fake_repo)) == 1

    def test_no_transcript_writes_nothing_and_warns(self, fake_repo, capsys):
        _run_hook({"hook_event_name": "SubagentStop", "agent_type": "po", "agent_id": "zz"})
        assert _rows(fake_repo) == []
        assert "transcript introuvable" in capsys.readouterr().err

    def test_journal_marks_transcript_source(self, fake_repo, tmp_path):
        a1 = _write(tmp_path / "s" / "subagents" / "agent-a1.jsonl", _subagent_records())
        _run_hook({"hook_event_name": "SubagentStop", "agent_type": "qa",
                   "agent_id": "a1", "agent_transcript_path": str(a1)})
        conn = sqlite3.connect(str(fake_repo / "workspace" / "db" / "console.db"))
        try:
            notes, src = conn.execute(
                "SELECT notes, pricing_source FROM agent_journal").fetchone()
        finally:
            conn.close()
        assert "usage_source=transcript" in notes and src == "known"


class TestHookPostToolUse:
    def test_async_launch_writes_no_zero_row(self, fake_repo):
        _run_hook({"hook_event_name": "PostToolUse", "tool_name": "Agent",
                   "tool_input": {"subagent_type": "po", "prompt": "us-generate 1"},
                   "tool_response": {"status": "async_launched"}})
        assert _rows(fake_repo) == []

    def test_sync_usage_is_not_a_source(self, fake_repo):
        """`tool_response.usage` = dernier appel seulement → jamais compté."""
        _run_hook({"hook_event_name": "PostToolUse", "tool_name": "Agent",
                   "tool_input": {"subagent_type": "dev-backend"},
                   "tool_response": {"usage": {"input_tokens": 5000, "output_tokens": 800}}})
        assert _rows(fake_repo) == []


class TestHookStop:
    def test_orchestrator_upserted_not_duplicated(self, fake_repo, tmp_path):
        main = tmp_path / "logs" / "sess-9.jsonl"
        _write(main, [_assistant("m1", "claude-fable-5-1", 10, 100, cr=1000, session="sess-9")])
        payload = {"hook_event_name": "Stop", "session_id": "sess-9", "transcript_path": str(main)}
        _run_hook(payload)
        _run_hook(payload)  # même transcript : aucune nouvelle ligne
        rows = _rows(fake_repo)
        assert len(rows) == 1 and rows[0]["agent"] == "orchestrator"
        assert rows[0]["model"] == "claude-fable-5-1"
        # La session progresse : la MÊME ligne est mise à jour.
        _write(main, [_assistant("m1", "claude-fable-5-1", 10, 100, cr=1000, session="sess-9"),
                      _assistant("m2", "claude-fable-5-1", 5, 50, cr=2000, session="sess-9")])
        _run_hook(payload)
        rows = _rows(fake_repo)
        assert len(rows) == 1
        assert (rows[0]["input_tokens"], rows[0]["output_tokens"]) == (15, 150)
        assert rows[0]["cache_read_tokens"] == 3000

    def test_new_run_gets_only_the_delta(self, fake_repo, tmp_path, monkeypatch):
        main = tmp_path / "logs" / "sess-7.jsonl"
        _write(main, [_assistant("m1", "claude-fable-5-1", 10, 100, session="sess-7")])
        payload = {"hook_event_name": "Stop", "session_id": "sess-7", "transcript_path": str(main)}
        _run_hook(payload)
        monkeypatch.setenv("SDD_RUN_ID", "run-test-2")
        _write(main, [_assistant("m1", "claude-fable-5-1", 10, 100, session="sess-7"),
                      _assistant("m2", "claude-fable-5-1", 1, 7, session="sess-7")])
        _run_hook(payload)
        by_run = {r["run_id"]: r for r in _rows(fake_repo)}
        assert by_run["run-test-1"]["output_tokens"] == 100
        assert by_run["run-test-2"]["output_tokens"] == 7


# --------------------------------------------------------------------------- #
# preflight_cost_cap (subprocess, faux dépôt)
# --------------------------------------------------------------------------- #

COST_CAP = _PY_ROOT / "sdd_hooks" / "preflight_cost_cap.py"
_CI_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "JENKINS_URL",
            "BUILDKITE", "TRAVIS", "TF_BUILD", "BITBUCKET_BUILD_NUMBER")


def _seed(repo: Path, rows: list[tuple[str, str | None, int, int]]) -> None:
    from sdd_lib import console_db
    db = repo / "workspace" / "db" / "console.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    console_db.ensure_initialized(db)
    with console_db.connect(db) as conn:
        console_db.upsert_run(conn, run_id="run-cc", command="/t", status="running")
        for agent, model, inp, out in rows:
            console_db.insert_token_usage(conn, agent=agent, model=model, run_id="run-cc",
                                          input_tokens=inp, output_tokens=out)


def _cost_cap(repo: Path, ci: bool) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _CI_VARS}
    for k in ("SDD_DISABLE_COST_CAP", "SDD_CONSOLE_DB_PATH", "SDD_CONSOLE_DB_PATH_MODE",
              "SDD_ALLOW_UNKNOWN_PRICING"):
        env.pop(k, None)
    env.update({"SDD_REPO_ROOT": str(repo), "SDD_RUN_ID": "run-cc",
                "PYTHONIOENCODING": "utf-8"})
    if ci:
        env["CI"] = "true"
    return subprocess.run(
        [sys.executable, str(COST_CAP)],
        input=json.dumps({"tool_name": "Agent", "tool_input": {"subagent_type": "dev-backend"}}),
        env=env, capture_output=True, text=True, encoding="utf-8", check=False,
    )


class TestCostCap:
    def test_unattributed_row_does_not_deny_in_ci(self, tmp_path):
        repo = tmp_path / "r"
        for d in (".claude/agents", ".claude/commands", "workspace"):
            (repo / d).mkdir(parents=True)
        _seed(repo, [("SubagentStop", None, 10, 10), ("unknown", "bogus-model", 10, 10)])
        r = _cost_cap(repo, ci=True)
        assert r.returncode == 0, r.stderr
        assert "[PRICING_UNKNOWN]" in r.stderr and "jamais bloquant" in r.stderr

    def test_orchestrator_row_counts_toward_cap(self, tmp_path):
        repo = tmp_path / "r"
        for d in (".claude/agents", ".claude/commands", "workspace"):
            (repo / d).mkdir(parents=True)
        # Fable 5.1 : 5M input × $10 = $50 → cap $50 atteint par l'orchestrateur seul.
        _seed(repo, [("orchestrator", "claude-fable-5-1", 5_000_000, 0)])
        r = _cost_cap(repo, ci=False)
        assert r.returncode == 2, r.stderr
        assert "[COST_CAP_EXCEEDED]" in r.stderr

    def test_unknown_model_priced_conservatively(self, tmp_path):
        repo = tmp_path / "r"
        for d in (".claude/agents", ".claude/commands", "workspace"):
            (repo / d).mkdir(parents=True)
        # 1M input inconnu : Sonnet aurait donné $3 ; conservateur = $10 → 5M = $50.
        _seed(repo, [("unknown", None, 5_000_000, 0)])
        r = _cost_cap(repo, ci=True)
        assert r.returncode == 2, r.stderr
        assert "[COST_CAP_EXCEEDED]" in r.stderr


# --------------------------------------------------------------------------- #
# statusline
# --------------------------------------------------------------------------- #


class TestStatusline:
    def _db(self, tmp_path) -> Path:
        from sdd_lib import console_db
        db = tmp_path / "console.db"
        console_db.ensure_initialized(db)
        with console_db.connect(db) as conn:
            console_db.upsert_run(conn, run_id="run-s", command="/sdd-full", status="running")
            console_db.insert_token_usage(conn, agent="dev-backend", model="claude-opus-5-5",
                                          run_id="run-s", feat_n=4, input_tokens=1_000_000,
                                          output_tokens=100_000)
            console_db.insert_token_usage(conn, agent="orchestrator", model="claude-fable-5-1",
                                          run_id="run-s", cache_read_tokens=1_000_000)
        return db

    def test_cost_is_computed_from_real_schema(self, tmp_path):
        from sdd_hooks.statusline import compute_status, format_status
        from sdd_lib import console_db
        db = self._db(tmp_path)
        with console_db.connect_ro(db) as conn:
            st = compute_status(conn, "run-s")
        expected = 4.00 + 0.1 * 20.00 + 0.25  # opus-5-5 in/out + fable-5-1 cache read
        assert st["cost_usd"] == pytest.approx(expected, abs=1e-4)
        assert st["tokens"] == 2_100_000 and st["feat_n"] == 4
        line = format_status(st)
        assert "F4" in line and "$6.25" in line

    def test_errors_are_not_swallowed(self, tmp_path, monkeypatch, capsys):
        from sdd_hooks import statusline
        bad = tmp_path / "console.db"
        bad.write_bytes(b"pas une base sqlite" * 20)
        monkeypatch.setattr("sdd_lib.console_db.default_db_path", lambda: bad)
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        assert statusline.main() == 0
        assert "[TELEMETRY_UNAVAILABLE]" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# context_budget
# --------------------------------------------------------------------------- #


class TestContextBudget:
    def test_auditor_budgets_are_a_real_barrier(self):
        from sdd_scripts.context_budget import BYTES_PER_TOKEN, DEFAULT_BUDGETS
        assert BYTES_PER_TOKEN == 3.5
        for a in ("code-reviewer", "arch-reviewer", "security-reviewer",
                  "spec-compliance-reviewer", "adversarial-reviewer"):
            assert DEFAULT_BUDGETS[a] <= 600_000, a
            assert DEFAULT_BUDGETS[a] / BYTES_PER_TOKEN < 200_000, a

    def test_cost_uses_model_pricing(self):
        from sdd_scripts.context_budget import estimate_input_cost
        assert estimate_input_cost("claude-opus-5-5", 1_000_000) == pytest.approx(4.00)
        assert estimate_input_cost("claude-haiku-5-5", 1_000_000) == pytest.approx(0.10)
        assert estimate_input_cost(None, 1_000_000, usd_per_million=3.0) == pytest.approx(3.0)
        assert estimate_input_cost("bogus-xyz", 1_000_000) == pytest.approx(
            pricing.CONSERVATIVE_PRICING["input"])

    def test_resolve_agent_model_explicit_wins(self):
        from sdd_scripts.context_budget import resolve_agent_model
        assert resolve_agent_model("po", "claude-haiku-5-5") == "claude-haiku-5-5"


# --------------------------------------------------------------------------- #
# Lot données/états (2026-11-07) — session_id + ConsoleDbUnavailable
# --------------------------------------------------------------------------- #


class TestSessionScopingAndDbUnavailable:
    def test_cost_cap_passes_session_id_to_run_id(self, monkeypatch):
        from sdd_hooks import preflight_cost_cap as pcc
        seen = {}

        def fake(force_new=False, session_id=None):
            seen["sid"] = session_id
            return "run-x"

        monkeypatch.setattr(pcc, "get_or_create_run_id", fake)
        monkeypatch.setattr(pcc, "_SESSION_ID", "sess-42")
        assert pcc._current_run_id() == "run-x"
        assert seen["sid"] == "sess-42"

    def test_record_hook_passes_session_id_to_run_id(self, monkeypatch):
        from sdd_hooks import record_token_usage as mod
        import sdd_lib.run_id as rid
        seen = {}

        def fake(force_new=False, session_id=None):
            seen["sid"] = session_id
            return "run-y"

        monkeypatch.setattr(rid, "get_or_create_run_id", fake)
        monkeypatch.setattr(mod, "_SESSION_ID", "sess-43")
        assert mod._resolve_run_id() == "run-y"
        assert seen["sid"] == "sess-43"

    def test_console_db_unavailable_is_infra_blocked_deny(self, monkeypatch, capsys):
        from sdd_hooks import preflight_cost_cap as pcc
        from sdd_lib import console_db

        def boom(*_a, **_k):
            raise console_db.ConsoleDbUnavailable("WAL verrouillé (test)")

        pcc._COST_CACHE.clear()
        monkeypatch.setattr(pcc, "_SESSION_ID", None)  # main() le pose ; restauré après le test
        monkeypatch.setattr("sdd_lib.console_db.connect_ro", boom)
        monkeypatch.setattr("sdd_lib.console_db.default_db_path",
                            lambda: Path(__file__))  # « existe »
        monkeypatch.setattr(pcc, "get_or_create_run_id", lambda *a, **k: "run-z")
        monkeypatch.setattr(pcc, "_resolve_cap", lambda: 50.0)
        monkeypatch.setattr(pcc, "read_hook_input", lambda: {
            "tool_name": "Agent", "session_id": "s", "tool_input": {"subagent_type": "po"}})
        for var in _CI_VARS:
            monkeypatch.delenv(var, raising=False)
        assert pcc.main() == 2
        err = capsys.readouterr().err
        assert "[INFRA_BLOCKED]" in err and "ConsoleDbUnavailable" in err
