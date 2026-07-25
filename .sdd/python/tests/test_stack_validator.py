"""Tests for sdd_lib.stack_validator — SSoT coherence (2026-06-06)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.stack_validator import validate_active_stacks_coherence  # noqa: E402


class TestStackValidator(unittest.TestCase):

    def test_valid_back_front_combo(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": "node-express", "frontend": "react",
            "ui": "shadcn", "auth": "auth-local",
            "fullstack": None, "mobiles": None,
        })
        self.assertIsNone(err)

    def test_valid_fullstack_solo(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": None, "frontend": None,
            "ui": None, "auth": None,
            "fullstack": "next", "mobiles": None,
        })
        self.assertIsNone(err)

    def test_valid_mobile_solo(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": None, "frontend": None,
            "ui": None, "auth": None,
            "fullstack": None, "mobiles": "kotlin-android",
        })
        self.assertIsNone(err)

    def test_valid_mobile_with_backend(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": "dotnet-minimalapi", "frontend": None,
            "ui": None, "auth": "azure-ad",
            "fullstack": None, "mobiles": "maui",
        })
        self.assertIsNone(err)

    def test_empty_stacks_raises(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": None, "frontend": None,
            "ui": None, "auth": None,
            "fullstack": None, "mobiles": None,
        })
        self.assertIsNotNone(err)
        self.assertEqual(err["code"], "STACK_MALFORMED")
        self.assertIn("aucun stack actif", err["message"])

    def test_fullstack_plus_backend_invalid(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": "node-express", "frontend": None,
            "ui": None, "auth": None,
            "fullstack": "next", "mobiles": None,
        })
        self.assertIsNotNone(err)
        self.assertEqual(err["code"], "STACK_MALFORMED")
        self.assertIn("mix interdit", err["message"])

    def test_fullstack_plus_frontend_invalid(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": None, "frontend": "react",
            "ui": "shadcn", "auth": None,
            "fullstack": "next", "mobiles": None,
        })
        self.assertIsNotNone(err)
        self.assertEqual(err["code"], "STACK_MALFORMED")

    def test_frontend_plus_mobile_invalid(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": None, "frontend": "react",
            "ui": "shadcn", "auth": None,
            "fullstack": None, "mobiles": "maui",
        })
        self.assertIsNotNone(err)
        self.assertEqual(err["code"], "STACK_MALFORMED")
        self.assertIn("frontendKind", err["message"])

    def test_fullstack_plus_mobile_invalid(self) -> None:
        err = validate_active_stacks_coherence({
            "backend": None, "frontend": None,
            "ui": None, "auth": None,
            "fullstack": "next", "mobiles": "kotlin-android",
        })
        self.assertIsNotNone(err)
        self.assertEqual(err["code"], "STACK_MALFORMED")


if __name__ == "__main__":
    unittest.main()
