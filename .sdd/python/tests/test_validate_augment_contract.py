"""Tests for sdd_hooks.validate_augment_contract — preserves/adds parser."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_hooks.validate_augment_contract import (
    _find_block_for_file,
    _parse_id_list,
    _path_in_plan,
)


PLAN_SAMPLE = """---
us: 1-2-Auth
family: backend
---

# Plan technique backend — 1-2-Auth

## Files

- path: workspace/src/SimBackend/Services/AuthService.cs
  operation: augment
  layer: Service
  preserves: [AUTH-LOGIN-V1, AUTH-SESSION]
  adds: [AUTH-REFRESH-V2]
  covers_acs: [AC-1, AC-3]

- path: workspace/src/SimBackend/Endpoints/AuthEndpoints.cs
  operation: create
  layer: Endpoint
  adds: [AUTH-ENDPOINT-LOGIN]
  covers_acs: [AC-2]

- path: workspace/src/SimBackend/DTOs/LoginDto.cs
  operation: create
  layer: DTO
  covers_acs: [AC-1]
"""


class TestPathInPlan(unittest.TestCase):
    def test_full_path_match(self):
        self.assertTrue(_path_in_plan(
            PLAN_SAMPLE,
            "workspace/src/SimBackend/Services/AuthService.cs",
            "AuthService.cs",
        ))

    def test_filename_match_when_full_path_absent(self):
        self.assertTrue(_path_in_plan(PLAN_SAMPLE, "different/path.cs", "AuthService.cs"))

    def test_no_match_returns_false(self):
        self.assertFalse(_path_in_plan(PLAN_SAMPLE, "Unknown/File.cs", "File.cs"))


class TestFindBlockForFile(unittest.TestCase):
    def test_finds_block_by_full_path(self):
        block = _find_block_for_file(
            PLAN_SAMPLE,
            "workspace/src/SimBackend/Services/AuthService.cs",
            "AuthService.cs",
        )
        self.assertIsNotNone(block)
        self.assertIn("preserves: [AUTH-LOGIN-V1", block)
        self.assertNotIn("AuthEndpoints", block)

    def test_finds_block_by_filename_leaf(self):
        block = _find_block_for_file(
            PLAN_SAMPLE,
            "elsewhere/AuthEndpoints.cs",
            "AuthEndpoints.cs",
        )
        self.assertIsNotNone(block)
        self.assertIn("AUTH-ENDPOINT-LOGIN", block)

    def test_returns_none_for_unknown_file(self):
        block = _find_block_for_file(PLAN_SAMPLE, "Unknown.cs", "Unknown.cs")
        self.assertIsNone(block)

    def test_isolates_block_at_eof(self):
        block = _find_block_for_file(
            PLAN_SAMPLE,
            "workspace/src/SimBackend/DTOs/LoginDto.cs",
            "LoginDto.cs",
        )
        self.assertIsNotNone(block)
        self.assertIn("covers_acs: [AC-1]", block)


class TestParseIdList(unittest.TestCase):
    def test_extracts_preserves_list(self):
        block = """- path: foo
  preserves: [AUTH-LOGIN-V1, AUTH-SESSION]
  adds: [AUTH-REFRESH-V2]
"""
        self.assertEqual(_parse_id_list(block, "preserves"), ["AUTH-LOGIN-V1", "AUTH-SESSION"])

    def test_extracts_adds_list(self):
        block = "  adds: [AUTH-REFRESH-V2]\n"
        self.assertEqual(_parse_id_list(block, "adds"), ["AUTH-REFRESH-V2"])

    def test_missing_key_returns_empty(self):
        block = "  covers_acs: [AC-1]\n"
        self.assertEqual(_parse_id_list(block, "preserves"), [])

    def test_strips_quotes_and_whitespace(self):
        block = "  preserves: [ 'ID1' , \"ID2\" , ID3 ]\n"
        self.assertEqual(_parse_id_list(block, "preserves"), ["ID1", "ID2", "ID3"])

    def test_empty_list(self):
        block = "  preserves: []\n"
        self.assertEqual(_parse_id_list(block, "preserves"), [])


if __name__ == "__main__":
    unittest.main()


class TestWriteIsCovered(unittest.TestCase):
    """Audit sécurité 2026-11 : un Write qui écrase un fichier augment est vérifié."""

    def test_write_overwrite_dropping_preserved_id_denies(self):
        import tempfile
        from unittest import mock
        from sdd_hooks import validate_augment_contract as vac
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "workspace" / "plans").mkdir(parents=True)
            (root / "workspace" / "plans" / "1-2-Auth.back.md").write_text(PLAN_SAMPLE, encoding="utf-8")
            target = root / "workspace" / "src" / "SimBackend" / "Services" / "AuthService.cs"
            target.parent.mkdir(parents=True)
            target.write_text("class AuthService { AUTH-REFRESH-V2 }", encoding="utf-8")
            payload = {"tool_name": "Write", "tool_input": {"file_path": str(target)}}
            with mock.patch.object(vac, "read_hook_input", lambda: payload), \
                    mock.patch.object(vac, "repo_root", lambda: root):
                self.assertEqual(vac.main(), 2)


class TestIdentifierShapes(unittest.TestCase):
    """Faux positifs 2026-11-13 : identifiants qualifiés, constructeurs, entrées en prose."""

    CODE = (
        "public sealed class PayrollAutomationService(IPayrollSessionService session)\n"
        "{\n    public Task RetrieveAsync() => Task.CompletedTask;\n"
        "    private Task ApplyTaxCardAsync() => Task.CompletedTask;\n}\n"
    )

    def _present(self, declared: str) -> bool:
        from sdd_hooks.validate_augment_contract import _identifier_present
        return _identifier_present(declared, self.CODE)

    def test_plain_token(self):
        self.assertTrue(self._present("RetrieveAsync"))

    def test_qualified_member(self):
        self.assertTrue(self._present("PayrollAutomationService.RetrieveAsync"))

    def test_qualified_member_with_signature(self):
        self.assertTrue(self._present("PayrollAutomationService.RetrieveAsync(PortalCredentials)"))

    def test_constructor(self):
        self.assertTrue(self._present("PayrollAutomationService.ctor(IPayrollSessionService)"))

    def test_prose_entry_with_backticks(self):
        self.assertTrue(self._present(
            "`ApplyTaxCardAsync` : « Dernière collecte · le JJ/MM/AAAA » ou « Jamais lancée » — FAIT"))

    def test_missing_member_still_detected(self):
        self.assertFalse(self._present("PayrollAutomationService.SendAsync"))

    def test_missing_constructor_still_detected(self):
        self.assertFalse(self._present("AutreService.ctor(IPayrollSessionService)"))

    def test_missing_backtick_token_still_detected(self):
        self.assertFalse(self._present("`SupprimeAsync` : libellé — FAIT"))

    def test_member_matches_whole_word_only(self):
        self.assertFalse(self._present("Type.Retrieve"))
