"""Unit tests for sdd_lib.file_io (M3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.file_io import (
    FileIoError,
    read_json,
    read_text,
    write_json_atomic,
    write_text_atomic,
)


def test_read_json_valid(tmp_path):
    p = tmp_path / "data.json"
    p.write_text('{"a": 1, "b": [1, 2]}', encoding="utf-8")
    assert read_json(p) == {"a": 1, "b": [1, 2]}


def test_read_json_missing_file(tmp_path):
    with pytest.raises(FileIoError) as exc:
        read_json(tmp_path / "missing.json")
    assert "FILE_IO_READ" in str(exc.value)


def test_read_json_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(FileIoError) as exc:
        read_json(p)
    assert "FILE_IO_JSON_PARSE" in str(exc.value)


def test_write_json_atomic_creates_file(tmp_path):
    p = tmp_path / "out.json"
    write_json_atomic(p, {"hello": "world"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"hello": "world"}


def test_write_json_atomic_preserves_unicode(tmp_path):
    p = tmp_path / "uni.json"
    write_json_atomic(p, {"name": "héllo é à ç"})
    # ensure_ascii=False → accents preserved as UTF-8 bytes
    raw = p.read_text(encoding="utf-8")
    assert "héllo" in raw


def test_write_json_atomic_unserializable(tmp_path):
    class Custom:
        pass

    with pytest.raises(FileIoError) as exc:
        write_json_atomic(tmp_path / "bad.json", {"obj": Custom()})
    assert "FILE_IO_JSON_SERIALIZE" in str(exc.value)


def test_write_json_atomic_trailing_newline(tmp_path):
    p = tmp_path / "nl.json"
    write_json_atomic(p, {"a": 1})
    assert p.read_text(encoding="utf-8").endswith("\n")


def test_read_text_valid(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text("# Hello\n\nWorld", encoding="utf-8")
    assert read_text(p) == "# Hello\n\nWorld"


def test_read_text_missing(tmp_path):
    with pytest.raises(FileIoError) as exc:
        read_text(tmp_path / "missing.md")
    assert "FILE_IO_READ" in str(exc.value)


def test_write_text_atomic_creates(tmp_path):
    p = tmp_path / "out.md"
    write_text_atomic(p, "content")
    assert p.read_text(encoding="utf-8") == "content"


def test_write_text_atomic_rejects_non_utf8(tmp_path):
    with pytest.raises(FileIoError) as exc:
        write_text_atomic(tmp_path / "x.md", "data", encoding="latin-1")
    assert "FILE_IO_ENCODING" in str(exc.value)


def test_write_json_atomic_overwrites_existing(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"old": true}', encoding="utf-8")
    write_json_atomic(p, {"new": True})
    assert read_json(p) == {"new": True}
