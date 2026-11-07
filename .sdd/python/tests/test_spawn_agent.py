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
    GEMINI_STDIN_MARKER,
    AgentSpec,
    RunResult,
    SpawnConfig,
    _build_argv,
    _build_invocation,
    _classify_os_error,
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
    return lambda argv, timeout, cwd, stdin_text=None: RunResult(exit_code, stdout, stderr)


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


def test_argv_codex_legacy_argv_transport():
    argv = _build_argv(SpawnConfig(harness="codex", model="gpt-5.2", prompt_transport="argv"), "P")
    expected = "codex.cmd" if os.name == "nt" else "codex"
    assert argv[:2] == [expected, "exec"] and "--model" in argv and argv[-1] == "P"


def test_argv_gemini_legacy_argv_transport():
    argv = _build_argv(
        SpawnConfig(harness="gemini-cli", model="gemini-3-flash", prompt_transport="argv"), "P"
    )
    assert argv[0] == "gemini" and "-p" in argv and "-m" in argv and "P" in argv


def test_argv_claude_legacy_argv_transport():
    argv = _build_argv(SpawnConfig(harness="claude-code", prompt_transport="argv"), "P")
    assert argv[0] == "claude" and argv[1:3] == ["-p", "P"]


# --- transport stdin (défaut depuis l'audit 2026-11-07 : WinError 206) --- #


def test_stdin_transport_is_default():
    assert SpawnConfig().prompt_transport == "stdin"


def test_invocation_codex_stdin_uses_dash_and_keeps_prompt_out_of_argv():
    big = "X" * 40_000  # > 32 Ko : aurait levé WinError 206 en argv
    argv, stdin_text = _build_invocation(SpawnConfig(harness="codex", model="gpt-5.2"), big)
    assert argv[-1] == "-" and "--model" in argv
    assert big not in argv and stdin_text == big


def test_invocation_claude_stdin_has_no_positional_prompt():
    argv, stdin_text = _build_invocation(SpawnConfig(harness="claude-code", model="m"), "PROMPT")
    assert argv[:2] == ["claude", "-p"] and "PROMPT" not in argv
    assert "--model" in argv and stdin_text == "PROMPT"


def test_invocation_gemini_stdin_passes_short_marker():
    argv, stdin_text = _build_invocation(SpawnConfig(harness="gemini-cli", model="g"), "PROMPT")
    assert argv[:3] == ["gemini", "-p", GEMINI_STDIN_MARKER]
    assert "PROMPT" not in argv and stdin_text == "PROMPT"


def test_invocation_argv_transport_has_no_stdin():
    _argv, stdin_text = _build_invocation(SpawnConfig(harness="codex", prompt_transport="argv"), "P")
    assert stdin_text is None


def test_invalid_transport_rejected():
    with pytest.raises(ValueError):
        SpawnConfig(prompt_transport="pipe")


def test_runner_receives_full_prompt_on_stdin():
    seen = {}

    def capture(argv, timeout, cwd, stdin_text):
        seen["argv"], seen["stdin"] = argv, stdin_text
        return RunResult(0, '{"stories":[{"id":"1-1"}]}')

    r = spawn_agent(_spec(), SpawnConfig(harness="codex", runner=capture))
    assert r["ok"]
    assert "Tu es PO" in seen["stdin"] and "Découpe la FEAT" in seen["stdin"]
    assert all("Tu es PO" not in a for a in seen["argv"])


def test_legacy_three_arg_runner_still_works_in_argv_transport():
    def legacy(argv, timeout, cwd):
        return RunResult(0, '{"stories":[{"id":"1-1"}]}')

    r = spawn_agent(_spec(), SpawnConfig(runner=legacy, prompt_transport="argv"))
    assert r["ok"]


def test_legacy_three_arg_runner_refused_in_stdin_transport():
    """Un runner qui ne peut pas transmettre stdin ne doit pas spawner à vide."""
    def legacy(argv, timeout, cwd):
        return RunResult(0, "{}")

    results = spawn_many([_spec()], SpawnConfig(runner=legacy))
    assert results[0]["error_class"] == "[SPAWN_INTERNAL_ERROR]"
    assert "stdin" in results[0]["detail"]


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
    def boom(argv, timeout, cwd, stdin_text=None):
        raise FileNotFoundError()

    r = spawn_agent(_spec(), SpawnConfig(runner=boom))
    assert not r["ok"] and r["error_class"] == "[SPAWN_BINARY_NOT_FOUND]"


def test_spawn_timeout():
    def slow(argv, timeout, cwd, stdin_text=None):
        raise TimeoutError()

    r = spawn_agent(_spec(), SpawnConfig(runner=slow))
    assert not r["ok"] and r["error_class"] == "[TIMEOUT]"


# --- OSError de spawn (WinError 206 / E2BIG) : classé, jamais propagé --- #


def _winerror_206() -> OSError:
    exc = OSError(22, "The filename or extension is too long")
    exc.winerror = 206  # type: ignore[attr-defined]
    return exc


def test_classify_os_error():
    import errno

    assert _classify_os_error(_winerror_206()) == "[SPAWN_ARGV_TOO_LONG]"
    assert _classify_os_error(OSError(errno.E2BIG, "Argument list too long")) == "[SPAWN_ARGV_TOO_LONG]"
    assert _classify_os_error(PermissionError(13, "denied")) == "[SPAWN_OS_ERROR]"


def test_spawn_argv_too_long_is_classified_with_3l_report():
    def boom(argv, timeout, cwd, stdin_text=None):
        raise _winerror_206()

    r = spawn_agent(_spec(), SpawnConfig(harness="claude-code", runner=boom, prompt_transport="argv"))
    assert not r["ok"] and r["error_class"] == "[SPAWN_ARGV_TOO_LONG]"
    lines = r["error_report"].splitlines()
    assert lines[0].startswith("ERROR: spawn_agent po (claude-code) failed")
    assert lines[1].startswith("CAUSE: [SPAWN_ARGV_TOO_LONG]")
    assert lines[2].startswith("FIX:") and "stdin" in lines[2]
    assert r["attempts"] == 1  # pas de retry schéma sur une erreur OS


def test_spawn_generic_os_error_is_classified():
    def boom(argv, timeout, cwd, stdin_text=None):
        raise PermissionError(13, "Permission denied")

    r = spawn_agent(_spec(), SpawnConfig(runner=boom))
    assert not r["ok"] and r["error_class"] == "[SPAWN_OS_ERROR]"
    assert "PermissionError" in r["detail"]


def test_spawn_many_os_error_captured_not_raised():
    def boom(argv, timeout, cwd, stdin_text=None):
        raise _winerror_206()

    results = spawn_many([_spec(), _spec()], SpawnConfig(runner=boom))
    assert [r["error_class"] for r in results] == ["[SPAWN_ARGV_TOO_LONG]"] * 2


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
    def boom(argv, timeout, cwd, stdin_text=None):
        raise FileNotFoundError()

    results = spawn_many([_spec(), _spec()], SpawnConfig(runner=boom))
    assert len(results) == 2 and all(not r["ok"] for r in results)
