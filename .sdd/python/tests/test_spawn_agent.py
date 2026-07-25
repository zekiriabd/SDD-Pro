"""Tests du wrapper spawn_agent (Phase 3.2 — orchestration sous-agents multi-harnais).

100 % offline : le runner subprocess est INJECTÉ (`SpawnConfig.runner`), aucun
CLI codex/gemini/claude réel n'est appelé, aucun token requis.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

from sdd_lib.spawn_agent import (  # noqa: E402
    AgentSpec,
    RunResult,
    SpawnConfig,
    _build_argv,
    build_prompt,
    extract_json,
    spawn_agent,
    spawn_many,
    validate_schema,
)

SCHEMA = {
    "type": "object",
    "required": ["stories"],
    "properties": {
        "stories": {
            "type": "array",
            "items": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
        }
    },
}


def _runner(stdout="", exit_code=0, stderr=""):
    return lambda argv, timeout, cwd: RunResult(exit_code, stdout, stderr)


def _spec():
    return AgentSpec("Tu es PO", "Découpe la FEAT", SCHEMA, label="po")


# --------------------------------------------------------------------- #
# Extraction / validation JSON                                         #
# --------------------------------------------------------------------- #


def test_extract_json_strict_fenced_and_balanced():
    assert extract_json('{"a":1}') == {"a": 1}
    assert extract_json('bla\n```json\n{"a":1}\n```\nfin') == {"a": 1}
    assert extract_json('log line\n{"a":{"b":2}} trailing') == {"a": {"b": 2}}
    assert extract_json("pas de json") is None


def test_validate_schema_detects_missing_and_type():
    assert validate_schema({"stories": [{"id": "x"}]}, SCHEMA) == []
    assert validate_schema({}, SCHEMA)  # required manquant
    assert validate_schema({"stories": [{"id": 1}]}, SCHEMA)  # id doit être string


def test_build_prompt_includes_schema_and_correction():
    p = build_prompt("SYS", "TASK", SCHEMA, correction="refais")
    assert "SYS" in p and "TASK" in p and "Correction" in p and "STRICT" in p


# --------------------------------------------------------------------- #
# argv par harnais                                                     #
# --------------------------------------------------------------------- #


def test_argv_codex():
    argv = _build_argv(SpawnConfig(harness="codex", model="gpt-5.2"), "P")
    expected = "codex.cmd" if os.name == "nt" else "codex"
    assert argv[:2] == [expected, "exec"] and "--model" in argv and argv[-1] == "P"


def test_argv_gemini():
    argv = _build_argv(SpawnConfig(harness="gemini-cli", model="gemini-3-flash"), "P")
    assert argv[0] == "gemini" and "-p" in argv and "-m" in argv


def test_argv_claude():
    argv = _build_argv(SpawnConfig(harness="claude-code"), "P")
    assert argv[0] == "claude" and "-p" in argv


def test_invalid_harness_rejected():
    with pytest.raises(ValueError):
        SpawnConfig(harness="bun")


# --------------------------------------------------------------------- #
# spawn_agent — chemins nominaux et d'erreur                           #
# --------------------------------------------------------------------- #


def test_spawn_ok_with_noisy_output():
    cfg = SpawnConfig(harness="codex", runner=_runner('noise\n```json\n{"stories":[{"id":"1-1"}]}\n```'))
    r = spawn_agent(_spec(), cfg)
    assert r["ok"] and r["parsed"]["stories"][0]["id"] == "1-1"
    assert r["attempts"] == 1 and r["harness"] == "codex" and r["label"] == "po"


def test_spawn_nonzero_exit():
    r = spawn_agent(_spec(), SpawnConfig(runner=_runner("x", exit_code=2)))
    assert not r["ok"] and r["error_class"] == "[NONZERO_EXIT]"


def test_spawn_empty_output():
    r = spawn_agent(_spec(), SpawnConfig(runner=_runner("   ")))
    assert not r["ok"] and r["error_class"] == "[EMPTY_OUTPUT]"


def test_spawn_binary_not_found():
    def boom(argv, timeout, cwd):
        raise FileNotFoundError()

    r = spawn_agent(_spec(), SpawnConfig(runner=boom))
    assert not r["ok"] and r["error_class"] == "[SPAWN_BINARY_NOT_FOUND]"


def test_spawn_timeout():
    def slow(argv, timeout, cwd):
        raise TimeoutError()

    r = spawn_agent(_spec(), SpawnConfig(runner=slow))
    assert not r["ok"] and r["error_class"] == "[TIMEOUT]"


def test_schema_retry_triggers_second_attempt():
    r = spawn_agent(_spec(), SpawnConfig(runner=_runner("pas de json"), schema_retry=True))
    assert not r["ok"] and r["attempts"] == 2 and r["error_class"] == "[JSON_UNPARSEABLE]"


def test_no_retry_when_disabled():
    r = spawn_agent(_spec(), SpawnConfig(runner=_runner("pas de json"), schema_retry=False))
    assert r["attempts"] == 1


def test_schema_mismatch_reports_errors():
    cfg = SpawnConfig(runner=_runner('{"stories":[{"id":1}]}'), schema_retry=False)
    r = spawn_agent(_spec(), cfg)
    assert r["error_class"] == "[SCHEMA_MISMATCH]" and r["schema_errors"]


# --------------------------------------------------------------------- #
# spawn_many — parallélisme borné, sémantique parallel()               #
# --------------------------------------------------------------------- #


def test_spawn_many_bounded_and_ordered():
    cfg = SpawnConfig(harness="codex", runner=_runner('{"stories":[{"id":"1-1"}]}'), max_parallel=3)
    specs = [AgentSpec("s", "t", SCHEMA, label=f"a{i}") for i in range(7)]
    results = spawn_many(specs, cfg)
    assert len(results) == 7
    assert [r["label"] for r in results] == [f"a{i}" for i in range(7)]
    assert all(r["ok"] for r in results)


def test_spawn_many_empty():
    assert spawn_many([], SpawnConfig(runner=_runner("{}"))) == []


def test_spawn_many_failures_are_captured_not_raised():
    def boom(argv, timeout, cwd):
        raise FileNotFoundError()

    results = spawn_many([_spec(), _spec()], SpawnConfig(runner=boom))
    assert len(results) == 2 and all(not r["ok"] for r in results)
