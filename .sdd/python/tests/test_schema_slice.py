"""Tests for sdd_lib.schema_slice (Levier 4 — per-US schema slicing).

Coverage:
- Entity extraction from US text (word-boundary, case-insensitive)
- FK transitive closure
- Empty / fallback semantics
- slice_for_us end-to-end on synthetic schema + US
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.schema_slice import (  # noqa: E402
    extract_entity_names_from_us,
    extract_slice,
    slice_for_us,
)

pytestmark = pytest.mark.smoke


def _make_schema() -> dict:
    return {
        "extracted_at": "2026-06-08T00:00:00Z",
        "database_type": "SqlServer",
        "database_name": "Test",
        "tables": [
            {
                "name": "User",
                "primary_key": ["UserId"],
                "columns": [{"name": "UserId", "type": "int", "nullable": False}],
                "foreign_keys": [],
                "indexes": [],
            },
            {
                "name": "Session",
                "primary_key": ["SessionId"],
                "columns": [
                    {"name": "SessionId", "type": "int", "nullable": False},
                    {"name": "UserId", "type": "int", "nullable": False},
                ],
                "foreign_keys": [
                    {"column": "UserId", "ref_table": "User", "ref_column": "UserId"}
                ],
                "indexes": [],
            },
            {
                "name": "Permission",
                "primary_key": ["PermissionId"],
                "columns": [{"name": "PermissionId", "type": "int", "nullable": False}],
                "foreign_keys": [],
                "indexes": [],
            },
            {
                "name": "AuditLog",
                "primary_key": ["AuditLogId"],
                "columns": [
                    {"name": "AuditLogId", "type": "int", "nullable": False},
                    {"name": "SessionId", "type": "int", "nullable": False},
                ],
                "foreign_keys": [
                    {"column": "SessionId", "ref_table": "Session", "ref_column": "SessionId"}
                ],
                "indexes": [],
            },
        ],
    }


class TestExtractEntityNames(unittest.TestCase):
    def test_word_boundary_case_insensitive(self):
        candidates = {"User", "Session", "Permission"}
        hits = extract_entity_names_from_us("As a user I want to log in.", candidates)
        self.assertEqual(hits, {"User"})

    def test_no_false_match_on_substring(self):
        # "BebeRdv" must NOT match "Bebe" (word boundary)
        candidates = {"Bebe", "BebeRdv"}
        hits = extract_entity_names_from_us("The Bebe entity is needed.", candidates)
        self.assertEqual(hits, {"Bebe"})

    def test_empty_text_returns_empty(self):
        self.assertEqual(extract_entity_names_from_us("", {"User"}), set())

    def test_empty_candidates_returns_empty(self):
        self.assertEqual(extract_entity_names_from_us("User", set()), set())

    def test_multiple_hits(self):
        candidates = {"User", "Session", "Permission"}
        hits = extract_entity_names_from_us(
            "Create a User, attach Session and a Permission.", candidates,
        )
        self.assertEqual(hits, {"User", "Session", "Permission"})


class TestExtractSlice(unittest.TestCase):
    def test_empty_entities_returns_full_schema_unchanged(self):
        schema = _make_schema()
        sliced = extract_slice(schema, set())
        self.assertEqual(sliced, schema)

    def test_seed_entity_only_without_closure(self):
        schema = _make_schema()
        sliced = extract_slice(schema, {"User"}, include_referenced=False)
        names = [t["name"] for t in sliced["tables"]]
        self.assertEqual(names, ["User"])

    def test_fk_transitive_closure_outgoing(self):
        # Session → User : asking for Session also pulls User
        schema = _make_schema()
        sliced = extract_slice(schema, {"Session"}, include_referenced=True)
        names = set(t["name"] for t in sliced["tables"])
        self.assertEqual(names, {"Session", "User"})

    def test_fk_transitive_two_hops(self):
        # AuditLog → Session → User
        schema = _make_schema()
        sliced = extract_slice(schema, {"AuditLog"}, include_referenced=True)
        names = set(t["name"] for t in sliced["tables"])
        self.assertEqual(names, {"AuditLog", "Session", "User"})

    def test_unknown_entity_falls_back_to_full(self):
        # Entity name that doesn't exist in schema → fallback to full
        schema = _make_schema()
        sliced = extract_slice(schema, {"NonExistent"})
        self.assertEqual(sliced, schema)

    def test_slice_metadata_populated(self):
        schema = _make_schema()
        sliced = extract_slice(schema, {"Session"}, include_referenced=True)
        meta = sliced["_slice_metadata"]
        self.assertEqual(meta["seed_entities"], ["Session"])
        self.assertEqual(meta["transitive_entities"], ["User"])
        self.assertEqual(meta["total_tables_in_slice"], 2)
        self.assertEqual(meta["total_tables_in_source"], 4)

    def test_top_level_fields_preserved(self):
        schema = _make_schema()
        sliced = extract_slice(schema, {"User"})
        self.assertEqual(sliced["database_type"], "SqlServer")
        self.assertEqual(sliced["database_name"], "Test")
        self.assertEqual(sliced["extracted_at"], "2026-06-08T00:00:00Z")

    def test_isolated_entity_no_fk_pull(self):
        # Permission has no FK in either direction
        schema = _make_schema()
        sliced = extract_slice(schema, {"Permission"}, include_referenced=True)
        names = [t["name"] for t in sliced["tables"]]
        self.assertEqual(names, ["Permission"])


class TestSliceForUs(unittest.TestCase):
    def test_end_to_end_user_session(self):
        with tempfile.TemporaryDirectory() as td:
            schema_path = Path(td) / "schema.json"
            us_path = Path(td) / "1-1-Login.md"
            schema_path.write_text(json.dumps(_make_schema()), encoding="utf-8")
            us_path.write_text(
                "# US 1-1-Login\n\n"
                "As a user I want to create a Session on login.",
                encoding="utf-8",
            )
            sliced, matched = slice_for_us(schema_path, us_path)
            self.assertEqual(matched, {"User", "Session"})
            names = set(t["name"] for t in sliced["tables"])
            # User + Session (Session FK pulls User which is already seeded)
            self.assertEqual(names, {"User", "Session"})

    def test_no_match_returns_full_schema_with_empty_matched(self):
        with tempfile.TemporaryDirectory() as td:
            schema_path = Path(td) / "schema.json"
            us_path = Path(td) / "2-1-Email.md"
            schema_path.write_text(json.dumps(_make_schema()), encoding="utf-8")
            us_path.write_text("# US 2-1-Email\n\nSend a transactional email.",
                               encoding="utf-8")
            sliced, matched = slice_for_us(schema_path, us_path)
            self.assertEqual(matched, set())
            self.assertEqual(len(sliced["tables"]), 4)  # full

    def test_missing_schema_raises(self):
        with tempfile.TemporaryDirectory() as td:
            us = Path(td) / "1-1-x.md"
            us.write_text("test", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                slice_for_us(Path(td) / "nope.json", us)

    def test_malformed_schema_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            schema_path = Path(td) / "schema.json"
            us_path = Path(td) / "1-1-x.md"
            schema_path.write_text("not json {{{", encoding="utf-8")
            us_path.write_text("test", encoding="utf-8")
            with self.assertRaises(ValueError):
                slice_for_us(schema_path, us_path)


if __name__ == "__main__":
    unittest.main()
