"""Unit tests for sdd_lib.project_config (M1)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.project_config import parse_kv_block, section_body


SAMPLE_STACK_MD = """
# Stack

## Project Config

AppName: MyApp
BackendName: MyBackend
LibName: MySharedLib
QAMode: full
CoverageMin: 80

## Active Tech Specs

- .claude/stacks/backend/dotnet-minimalapi.md
- .claude/stacks/frontend/react.md

## Active Auth Specs

- .claude/stacks/auth/azure-ad.md
"""


def test_section_body_extracts_simple_section():
    body = section_body(SAMPLE_STACK_MD, "Project Config")
    assert body is not None
    assert "AppName: MyApp" in body
    assert "Active Tech Specs" not in body  # stops at next H2


def test_section_body_extracts_last_section():
    body = section_body(SAMPLE_STACK_MD, "Active Auth Specs")
    assert body is not None
    assert "azure-ad.md" in body


def test_section_body_missing_returns_none():
    assert section_body(SAMPLE_STACK_MD, "Nonexistent Section") is None


def test_section_body_empty_text():
    assert section_body("", "Project Config") is None


def test_parse_kv_block_simple():
    body = section_body(SAMPLE_STACK_MD, "Project Config")
    config = parse_kv_block(body)
    assert config["AppName"] == "MyApp"
    assert config["BackendName"] == "MyBackend"
    assert config["LibName"] == "MySharedLib"
    assert config["CoverageMin"] == "80"


def test_parse_kv_block_with_keys_filter():
    body = section_body(SAMPLE_STACK_MD, "Project Config")
    config = parse_kv_block(body, keys=("AppName", "QAMode"))
    assert set(config.keys()) == {"AppName", "QAMode"}
    assert config["AppName"] == "MyApp"


def test_parse_kv_block_strips_quotes():
    block = '''
AppName: "MyApp"
BackendName: 'Other'
'''
    config = parse_kv_block(block)
    assert config["AppName"] == "MyApp"
    assert config["BackendName"] == "Other"


def test_parse_kv_block_ignores_empty_values():
    block = "AppName: MyApp\nBackendName:   \n"
    config = parse_kv_block(block)
    assert "AppName" in config
    assert "BackendName" not in config  # empty value filtered


def test_parse_kv_block_handles_dash_prefix():
    block = "- AppName: MyApp\n* BackendName: MyBackend\n"
    config = parse_kv_block(block)
    assert config["AppName"] == "MyApp"
    assert config["BackendName"] == "MyBackend"


def test_parse_kv_block_skips_invalid_lines():
    block = """
Comment line, not a kv pair
AppName: MyApp
# Comment
BackendName: MyBackend
"""
    config = parse_kv_block(block)
    assert config == {"AppName": "MyApp", "BackendName": "MyBackend"}


def test_section_body_with_multiple_h2():
    text = "## A\n\nfoo\n\n## B\n\nbar\n\n## C\n\nbaz\n"
    body_a = section_body(text, "A")
    body_b = section_body(text, "B")
    body_c = section_body(text, "C")
    assert "foo" in body_a and "bar" not in body_a
    assert "bar" in body_b and "baz" not in body_b
    assert "baz" in body_c
