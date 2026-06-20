"""Unit tests for sdd_lib.stderr (M1)."""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.stderr import error_block, warn


def test_warn_writes_to_stderr(capsys):
    warn("hello")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "hello\n"


def test_warn_handles_unicode(capsys):
    warn("héllo é à ç")
    captured = capsys.readouterr()
    assert "héllo é à ç" in captured.err


def test_warn_empty_string(capsys):
    warn("")
    captured = capsys.readouterr()
    assert captured.err == "\n"


def test_error_block_format(capsys):
    error_block("dev-backend 1-2 build failed", "[BUILD_CORRECTIBLE] missing import", "add using statement")
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "ERROR: dev-backend 1-2 build failed"
    assert lines[1] == "CAUSE: [BUILD_CORRECTIBLE] missing import"
    assert lines[2] == "FIX: add using statement"


def test_error_block_preserves_brackets(capsys):
    error_block("test", "[CODE_ABC] detail", "fix it")
    captured = capsys.readouterr()
    assert "[CODE_ABC]" in captured.err
