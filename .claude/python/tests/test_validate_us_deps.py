"""Tests for sdd_scripts.validate_us_deps — DAG validation + topo sort."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import validate_us_deps as vud  # noqa: E402


US_TEMPLATE = """# US-{m}: {name}

ID: {fid}-{m}-{name}
Parent FEAT: {fid}-Test
Status: Draft

## User Story
x

## Acceptance Criteria
- AC-1: cond

## Covers
- SFD-1

## Dependencies
{deps_block}
"""


def _make_us(tmp: Path, fid: int, m: int, name: str, deps: list[str] | None) -> Path:
    us_dir = tmp / "workspace" / "output" / "us"
    us_dir.mkdir(parents=True, exist_ok=True)
    if deps is None or deps == []:
        deps_block = "- NONE"
    else:
        deps_block = "\n".join(f"- {d}" for d in deps)
    path = us_dir / f"{fid}-{m}-{name}.md"
    path.write_text(
        US_TEMPLATE.format(m=m, name=name, fid=fid, deps_block=deps_block),
        encoding="utf-8",
    )
    return path


class TestParseDeps(unittest.TestCase):
    def test_none_returns_empty(self):
        content = "## Dependencies\n- NONE\n"
        self.assertEqual(vud.parse_us_deps(content), set())

    def test_none_case_insensitive(self):
        content = "## Dependencies\n- none\n- None\n"
        self.assertEqual(vud.parse_us_deps(content), set())

    def test_placeholder_ignored(self):
        content = "## Dependencies\n- <US-id ou NONE>\n"
        self.assertEqual(vud.parse_us_deps(content), set())

    def test_valid_short_ids(self):
        content = "## Dependencies\n- 1-1\n- 1-2\n- 2-3\n"
        self.assertEqual(vud.parse_us_deps(content), {"1-1", "1-2", "2-3"})

    def test_section_absent_returns_empty(self):
        content = "# US-1\n## User Story\nx\n"
        self.assertEqual(vud.parse_us_deps(content), set())

    def test_invalid_format_ignored(self):
        content = "## Dependencies\n- foo\n- 1-2\n- bar-baz\n"
        self.assertEqual(vud.parse_us_deps(content), {"1-2"})

    def test_mixed_valid_and_none(self):
        content = "## Dependencies\n- NONE\n- 1-1\n"
        self.assertEqual(vud.parse_us_deps(content), {"1-1"})


class TestShortIdFromFilename(unittest.TestCase):
    def test_parses_canonical(self):
        self.assertEqual(
            vud.short_id_from_filename(Path("1-2-Auth.md")), "1-2"
        )

    def test_multi_word_name(self):
        self.assertEqual(
            vud.short_id_from_filename(Path("3-5-Reset-Password-Flow.md")), "3-5"
        )

    def test_invalid_returns_none(self):
        self.assertIsNone(vud.short_id_from_filename(Path("README.md")))
        self.assertIsNone(vud.short_id_from_filename(Path("1.md")))


class TestBuildGraph(unittest.TestCase):
    def test_linear_chain(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            _make_us(tmp_p, 1, 1, "A", [])
            _make_us(tmp_p, 1, 2, "B", ["1-1"])
            _make_us(tmp_p, 1, 3, "C", ["1-2"])
            us_files = sorted((tmp_p / "workspace" / "output" / "us").glob("*.md"))
            graph, mapping = vud.build_graph(us_files)
            self.assertEqual(graph["1-1"], set())
            self.assertEqual(graph["1-2"], {"1-1"})
            self.assertEqual(graph["1-3"], {"1-2"})

    def test_diamond(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_us(tmp_p, 1, 1, "Root", [])
            _make_us(tmp_p, 1, 2, "Left", ["1-1"])
            _make_us(tmp_p, 1, 3, "Right", ["1-1"])
            _make_us(tmp_p, 1, 4, "Tip", ["1-2", "1-3"])
            us_files = sorted((tmp_p / "workspace" / "output" / "us").glob("*.md"))
            graph, _ = vud.build_graph(us_files)
            self.assertEqual(graph["1-4"], {"1-2", "1-3"})


class TestDetectMissing(unittest.TestCase):
    def test_no_missing(self):
        graph = {"1-1": set(), "1-2": {"1-1"}}
        self.assertEqual(vud.detect_missing(graph), {})

    def test_one_missing(self):
        graph = {"1-1": {"9-9"}, "1-2": {"1-1"}}
        self.assertEqual(vud.detect_missing(graph), {"1-1": ["9-9"]})

    def test_multiple_missing(self):
        graph = {"1-1": {"9-9", "8-8"}, "1-2": set()}
        missing = vud.detect_missing(graph)
        self.assertEqual(missing["1-1"], ["8-8", "9-9"])


class TestDetectCycles(unittest.TestCase):
    def test_no_cycle_linear(self):
        graph = {"a": set(), "b": {"a"}, "c": {"b"}}
        self.assertEqual(vud.detect_cycles(graph), [])

    def test_no_cycle_diamond(self):
        graph = {"a": set(), "b": {"a"}, "c": {"a"}, "d": {"b", "c"}}
        self.assertEqual(vud.detect_cycles(graph), [])

    def test_simple_cycle(self):
        graph = {"a": {"b"}, "b": {"a"}}
        cycles = vud.detect_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"a", "b"})

    def test_triangle_cycle(self):
        graph = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        cycles = vud.detect_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"a", "b", "c"})

    def test_self_loop(self):
        graph = {"a": {"a"}}
        cycles = vud.detect_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0], ["a"])

    def test_two_disjoint_cycles(self):
        graph = {
            "a": {"b"}, "b": {"a"},
            "c": {"d"}, "d": {"c"},
        }
        cycles = vud.detect_cycles(graph)
        self.assertEqual(len(cycles), 2)

    def test_missing_ref_not_considered_cycle(self):
        # 1-1 -> 9-9 (9-9 not in graph). Should not be flagged as a cycle.
        graph = {"1-1": {"9-9"}}
        self.assertEqual(vud.detect_cycles(graph), [])


class TestDetectOrphans(unittest.TestCase):
    def test_leaf_is_orphan(self):
        # 1-2 depends on 1-1; 1-2 has no incoming -> orphan
        graph = {"1-1": set(), "1-2": {"1-1"}}
        self.assertEqual(vud.detect_orphans(graph), ["1-2"])

    def test_no_orphans_in_cycle(self):
        # Every node has incoming edge
        graph = {"a": {"b"}, "b": {"a"}}
        self.assertEqual(vud.detect_orphans(graph), [])


class TestTopologicalSort(unittest.TestCase):
    def test_linear(self):
        graph = {"a": set(), "b": {"a"}, "c": {"b"}}
        order = vud.topological_sort(graph)
        self.assertEqual(order, ["a", "b", "c"])

    def test_cycle_returns_none(self):
        graph = {"a": {"b"}, "b": {"a"}}
        self.assertIsNone(vud.topological_sort(graph))

    def test_alphabetic_tie_break(self):
        # Two parallel roots — order should be alphabetic
        graph = {"b": set(), "a": set(), "c": {"a", "b"}}
        order = vud.topological_sort(graph)
        self.assertEqual(order, ["a", "b", "c"])

    def test_diamond_order(self):
        graph = {"r": set(), "left": {"r"}, "right": {"r"}, "tip": {"left", "right"}}
        order = vud.topological_sort(graph)
        # r first, tip last, left/right between
        self.assertEqual(order[0], "r")
        self.assertEqual(order[-1], "tip")
        self.assertEqual(set(order[1:3]), {"left", "right"})

    def test_missing_ref_treated_as_no_op(self):
        # 1-1 depends on 9-9 (missing). Topo should still complete.
        graph = {"1-1": {"9-9"}, "1-2": {"1-1"}}
        order = vud.topological_sort(graph)
        self.assertEqual(order, ["1-1", "1-2"])


class TestMainEndToEnd(unittest.TestCase):
    def _setup(self, tmp_p: Path, us_specs: list[tuple[int, int, str, list[str] | None]]) -> None:
        (tmp_p / ".claude").mkdir()
        for fid, m, name, deps in us_specs:
            _make_us(tmp_p, fid, m, name, deps)

    def test_valid_linear_feat(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup(tmp_p, [(1, 1, "A", []), (1, 2, "B", ["1-1"])])
            with mock.patch.object(vud, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["validate_us_deps.py", "--feat", "1"]):
                rc = vud.main()
            self.assertEqual(rc, 0)

    def test_cycle_returns_3(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup(tmp_p, [(1, 1, "A", ["1-2"]), (1, 2, "B", ["1-1"])])
            with mock.patch.object(vud, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["validate_us_deps.py", "--feat", "1"]):
                rc = vud.main()
            self.assertEqual(rc, 3)

    def test_missing_returns_4(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup(tmp_p, [(1, 1, "A", ["9-9"])])
            with mock.patch.object(vud, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["validate_us_deps.py", "--feat", "1"]):
                rc = vud.main()
            self.assertEqual(rc, 4)

    def test_no_us_returns_1(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            with mock.patch.object(vud, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["validate_us_deps.py", "--feat", "1"]):
                rc = vud.main()
            self.assertEqual(rc, 1)

    def test_topo_mode_prints_order(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup(tmp_p, [
                (1, 1, "A", []),
                (1, 2, "B", ["1-1"]),
                (1, 3, "C", ["1-2"]),
            ])
            with mock.patch.object(vud, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["validate_us_deps.py", "--feat", "1", "--topo"]):
                rc = vud.main()
            self.assertEqual(rc, 0)

    def test_topo_mode_on_cycle_returns_3(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup(tmp_p, [(1, 1, "A", ["1-2"]), (1, 2, "B", ["1-1"])])
            with mock.patch.object(vud, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["validate_us_deps.py", "--feat", "1", "--topo"]):
                rc = vud.main()
            self.assertEqual(rc, 3)

    def test_invalid_us_id_returns_2(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup(tmp_p, [(1, 1, "A", [])])
            with mock.patch.object(vud, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["validate_us_deps.py", "--us-id", "bad"]):
                rc = vud.main()
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
