"""Unit tests for sdd_lib.hook_input (M1)."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.hook_input import (
    get_file_path,
    get_nested,
    get_subagent_type,
    get_tool_name,
    read_hook_input,
)


def _set_stdin(monkeypatch, payload: str):
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))


def test_read_hook_input_valid_json(monkeypatch):
    _set_stdin(monkeypatch, json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}))
    out = read_hook_input()
    assert out["tool_name"] == "Edit"
    assert out["tool_input"]["file_path"] == "a.py"


def test_read_hook_input_empty_stdin(monkeypatch):
    _set_stdin(monkeypatch, "")
    assert read_hook_input() == {}


def test_read_hook_input_whitespace_only(monkeypatch):
    _set_stdin(monkeypatch, "   \n\t  ")
    assert read_hook_input() == {}


def test_read_hook_input_invalid_json_regex_fallback(monkeypatch):
    # Truncated JSON: regex fallback should extract file_path and tool_name
    _set_stdin(monkeypatch, '{"tool_name": "Write", "tool_input": {"file_path": "x.py"')
    out = read_hook_input()
    assert out.get("tool_name") == "Write"
    assert out.get("tool_input", {}).get("file_path") == "x.py"


def test_read_hook_input_list_not_dict(monkeypatch):
    _set_stdin(monkeypatch, "[1, 2, 3]")
    assert read_hook_input() == {}


def test_get_nested_simple():
    payload = {"a": {"b": {"c": 42}}}
    assert get_nested(payload, "a", "b", "c") == 42


def test_get_nested_missing_returns_default():
    assert get_nested({"a": 1}, "b", default="x") == "x"
    assert get_nested({"a": 1}, "a", "b", default=None) is None


def test_get_nested_wrong_type():
    assert get_nested({"a": "str"}, "a", "b", default="d") == "d"


def test_get_file_path_via_tool_input():
    assert get_file_path({"tool_input": {"file_path": "foo.py"}}) == "foo.py"


def test_get_file_path_via_root_fallback():
    assert get_file_path({"file_path": "bar.py"}) == "bar.py"


def test_get_file_path_missing():
    assert get_file_path({}) is None
    assert get_file_path({"tool_input": {}}) is None


def test_get_file_path_empty_string():
    assert get_file_path({"file_path": "   "}) is None
    assert get_file_path({"tool_input": {"file_path": ""}}) is None


def test_get_tool_name():
    assert get_tool_name({"tool_name": "Edit"}) == "Edit"
    assert get_tool_name({"tool_name": ""}) is None
    assert get_tool_name({}) is None


def test_get_subagent_type_via_tool_input():
    assert get_subagent_type({"tool_input": {"subagent_type": "po"}}) == "po"


def test_get_subagent_type_root_fallback():
    assert get_subagent_type({"subagent_type": "arch"}) == "arch"


def test_get_subagent_type_missing():
    assert get_subagent_type({}) is None
