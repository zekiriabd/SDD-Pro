"""Tests du hook `enforce_max_parallel` (lot orchestration mécanique,
2026-11-07) : réservation atomique en PreToolUse, libération en
PostToolUse (foreground) / SubagentStop, péremption 2 h, Stop = sweep."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY
from sdd_hooks import enforce_max_parallel as H

_PY_ROOT = Path(__file__).resolve().parent.parent
HOOK = _PY_ROOT / "sdd_hooks" / "enforce_max_parallel.py"


@pytest.fixture()
def repo(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "repo"
    for d in (".sdd/agents", ".sdd/commands", "workspace/stack"):
        (root / d).mkdir(parents=True)
    for a in ("dev-backend", "dev-frontend", "qa"):
        (root / ".sdd" / "agents" / f"{a}.md").write_text(f"name: {a}\n", encoding="utf-8")
    (root / "workspace" / "stack" / "stack.md").write_text(
        "## Project Config\nAppName: A\nMaxParallel: 2\n", encoding="utf-8")
    monkeypatch.setenv("SDD_REPO_ROOT", str(root))
    monkeypatch.delenv("SDD_ALLOW_PARALLEL_EXCESS", raising=False)
    return root


def _p(agent: str, tid: str, event: str = "PreToolUse", session: str = "s1", **ti) -> dict:
    return {"hook_event_name": event, "tool_name": "Agent", "session_id": session,
            "tool_use_id": tid, "tool_input": {"subagent_type": agent, "prompt": "US 1-1", **ti}}


def test_max_parallel_read_from_stack(repo):
    assert H.resolve_max_parallel(repo) == 2


def test_third_parallel_spawn_denied(repo):
    assert H.on_pre(_p("dev-backend", "a"), repo)[0] == HOOK_ALLOW
    assert H.on_pre(_p("dev-backend", "b"), repo)[0] == HOOK_ALLOW
    code, msg = H.on_pre(_p("dev-backend", "c"), repo)
    assert code == HOOK_DENY and "[MAX_PARALLEL_EXCEEDED]" in msg


def test_non_sdd_agents_not_counted(repo):
    for i in range(5):
        assert H.on_pre(_p("general-purpose", f"g{i}"), repo)[0] == HOOK_ALLOW
    assert H.inflight_count(repo, "s1") == 0


def test_post_foreground_releases(repo):
    H.on_pre(_p("dev-backend", "a"), repo)
    H.on_pre(_p("dev-backend", "b"), repo)
    H.mark_started(_p("dev-backend", "a", "PostToolUse"), repo)
    assert H.inflight_count(repo, "s1") == 1
    assert H.on_pre(_p("dev-backend", "c"), repo)[0] == HOOK_ALLOW


def test_background_kept_until_subagent_stop(repo):
    H.on_pre(_p("qa", "a", run_in_background=True), repo)
    H.mark_started(_p("qa", "a", "PostToolUse", run_in_background=True), repo)
    assert H.inflight_count(repo, "s1") == 1
    H.mark_stopped({"hook_event_name": "SubagentStop", "agent_type": "qa",
                    "session_id": "s1"}, repo)
    assert H.inflight_count(repo, "s1") == 0


def test_sessions_are_isolated(repo):
    H.on_pre(_p("dev-backend", "a", session="s1"), repo)
    H.on_pre(_p("dev-backend", "b", session="s1"), repo)
    assert H.on_pre(_p("dev-backend", "c", session="s2"), repo)[0] == HOOK_ALLOW


def test_stale_entries_ignored(repo):
    old = time.time() - 3 * 3600
    H.on_pre(_p("dev-backend", "a"), repo, now=old)
    H.on_pre(_p("dev-backend", "b"), repo, now=old)
    assert H.on_pre(_p("dev-backend", "c"), repo)[0] == HOOK_ALLOW


def test_denied_by_other_hook_does_not_leak(repo):
    H.on_pre(_p("dev-backend", "a"), repo)
    H.note_denied(repo, "a")
    assert H.inflight_count(repo, "s1") == 0
    H.on_pre(_p("dev-backend", "a"), repo)  # rejeu tardif : pas de réservation
    assert H.inflight_count(repo, "s1") == 0


def test_sweep_purges_foreground(repo):
    H.on_pre(_p("dev-backend", "a"), repo)
    H.on_pre(_p("qa", "b", run_in_background=True), repo)
    H.sweep({"session_id": "s1"}, repo)
    assert H.inflight_count(repo, "s1") == 1


def test_bypass_audit_logged(repo, monkeypatch):
    H.on_pre(_p("dev-backend", "a"), repo)
    H.on_pre(_p("dev-backend", "b"), repo)
    monkeypatch.setenv("SDD_ALLOW_PARALLEL_EXCESS", "1")
    assert H.on_pre(_p("dev-backend", "c"), repo)[0] == HOOK_ALLOW
    log = repo / "workspace" / ".sys" / ".audit" / "bypass.log"
    assert "SDD_ALLOW_PARALLEL_EXCESS=1" in log.read_text(encoding="utf-8")


def test_cli_events_subprocess(repo):
    env = dict(os.environ)

    def call(event: str, payload: dict) -> int:
        return subprocess.run([sys.executable, str(HOOK), "--event", event],
                              input=json.dumps(payload), capture_output=True, text=True,
                              env=env, check=False).returncode

    assert call("pre", _p("dev-backend", "a")) == HOOK_ALLOW
    assert call("pre", _p("dev-backend", "b")) == HOOK_ALLOW
    assert call("pre", _p("dev-backend", "c")) == HOOK_DENY
    assert call("stop", {"hook_event_name": "SubagentStop", "agent_type": "dev-backend",
                         "session_id": "s1"}) == HOOK_ALLOW
    assert call("pre", _p("dev-backend", "c")) == HOOK_ALLOW
