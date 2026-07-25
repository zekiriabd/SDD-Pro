"""Unit tests for sdd_lib/combos.py — combos.json SSoT loader."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib import combos  # noqa: E402


def _make_combos_repo(root: Path, payload: dict) -> None:
    """Create a minimal repo layout with a custom combos.json."""
    templates = root / ".claude" / "templates"
    templates.mkdir(parents=True)
    (root / ".claude" / "agents").mkdir()
    (root / ".claude" / "commands").mkdir()
    (root / "workspace").mkdir()
    (templates / "combos.json").write_text(json.dumps(payload), encoding="utf-8")


_SAMPLE_COMBOS = {
    "schemaVersion": 1,
    "combos": [
        {"id": "C1", "backend": "dotnet-minimalapi", "frontend": "react",
         "qa": ["dotnet-xunit", "node-vitest"]},
        {"id": "C2", "backend": "kotlin-spring-boot", "frontend": "react",
         "qa": ["kotlin-junit", "node-vitest"]},
    ],
    "componentLevels": {
        "_doc": "ignore me",
        "backend": {"dotnet-minimalapi": "reference", "node-express": "bench"},
        "frontend": {"react": "reference", "vue": "bench"},
    },
    "levelPriority": {
        "_doc": "ignore me",
        "reference": 4,
        "bench": 3,
        "experimental": 1,
    },
}


class TestLoadCombos(unittest.TestCase):
    def setUp(self) -> None:
        # Clear the lru_cache before each test (avoid state leak)
        combos.clear_combos_cache()

    def test_load_full_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_combos_repo(root, _SAMPLE_COMBOS)
            payload = combos.load_combos(root)
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertIn("combos", payload)
            self.assertIn("componentLevels", payload)

    def test_missing_file_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude" / "agents").mkdir(parents=True)
            (root / ".claude" / "commands").mkdir(parents=True)
            (root / "workspace").mkdir()
            # No combos.json
            with self.assertRaises(FileNotFoundError):
                combos.load_combos(root)


class TestGetValidatedCombos(unittest.TestCase):
    def setUp(self) -> None:
        combos.clear_combos_cache()

    def test_returns_combos_list(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_combos_repo(root, _SAMPLE_COMBOS)
            result = combos.get_validated_combos(root)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["id"], "C1")


class TestGetComponentLevels(unittest.TestCase):
    def setUp(self) -> None:
        combos.clear_combos_cache()

    def test_returns_categories_minus_doc(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_combos_repo(root, _SAMPLE_COMBOS)
            levels = combos.get_component_levels(root)
            # `_doc` key stripped
            self.assertNotIn("_doc", levels)
            self.assertIn("backend", levels)
            self.assertEqual(levels["backend"]["dotnet-minimalapi"], "reference")


class TestGetComponentLevel(unittest.TestCase):
    def setUp(self) -> None:
        combos.clear_combos_cache()

    def test_known_stack_returns_level(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_combos_repo(root, _SAMPLE_COMBOS)
            self.assertEqual(
                combos.get_component_level("backend", "dotnet-minimalapi", root=root),
                "reference",
            )

    def test_none_stack_returns_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_combos_repo(root, _SAMPLE_COMBOS)
            self.assertEqual(
                combos.get_component_level("backend", None, root=root),
                "missing",
            )

    def test_unknown_stack_returns_untested(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_combos_repo(root, _SAMPLE_COMBOS)
            self.assertEqual(
                combos.get_component_level("backend", "nonexistent-stack", root=root),
                "untested",
            )


class TestGetLevelPriority(unittest.TestCase):
    def setUp(self) -> None:
        combos.clear_combos_cache()

    def test_returns_int_priorities_minus_doc(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_combos_repo(root, _SAMPLE_COMBOS)
            prio = combos.get_level_priority(root)
            self.assertNotIn("_doc", prio)
            self.assertEqual(prio["reference"], 4)
            self.assertEqual(prio["bench"], 3)
            self.assertGreater(prio["reference"], prio["experimental"])


if __name__ == "__main__":
    unittest.main()
