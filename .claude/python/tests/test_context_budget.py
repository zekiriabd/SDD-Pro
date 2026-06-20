"""Unit + integration tests for context_budget.py.

Coverage:
- is_unbounded_glob: wildcard sans borne FEAT/US → True ; bornée → False ; ADR whitelist → False
- is_excluded: node_modules/bin/obj/extensions binaires → True ; source → False
- resolve_pattern: substitution {n}, {n}-{m}, {AppName}, {Project}
- expand_files: glob simple, fichier direct, dossier
- Integration : subprocess avec fake repo
  - pass : reads dans budget → exit 0, ledger JSONL écrit
  - fail BUDGET_EXCEEDED : agent avec budget artificiellement bas → exit 1
  - fail UNBOUNDED_GLOB : loader.yml avec glob non borné → exit 1
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "context_budget.py"

# Import direct pour unit tests des pure functions
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))
from sdd_scripts.context_budget import (  # noqa: E402
    CURRENT_AGENTS,
    DEFAULT_BUDGETS,
    is_unbounded_glob,
    is_excluded,
    resolve_pattern,
    expand_files,
)


class TestIsUnboundedGlob(unittest.TestCase):
    def test_pattern_without_wildcard_is_bounded(self) -> None:
        self.assertFalse(is_unbounded_glob("workspace/input/stack/stack.md"))

    def test_wildcard_with_feat_marker_is_bounded(self) -> None:
        self.assertFalse(is_unbounded_glob("workspace/output/us/{n}-*.md"))

    def test_wildcard_with_us_marker_is_bounded(self) -> None:
        self.assertFalse(is_unbounded_glob("workspace/output/us/{n}-{m}-*.md"))

    def test_wildcard_with_appname_marker_is_bounded(self) -> None:
        self.assertFalse(is_unbounded_glob("workspace/output/src/{AppName}/**/*.cs"))

    def test_wildcard_with_project_marker_is_bounded(self) -> None:
        self.assertFalse(is_unbounded_glob("workspace/output/src/{Project}/**/*.md"))

    def test_adr_whitelist_is_bounded(self) -> None:
        self.assertFalse(
            is_unbounded_glob("workspace/output/.sys/.context/adrs/ADR-*.md")
        )

    def test_naked_wildcard_is_unbounded(self) -> None:
        self.assertTrue(is_unbounded_glob("workspace/output/**/*.md"))

    def test_naked_glob_in_src_is_unbounded(self) -> None:
        self.assertTrue(is_unbounded_glob("workspace/output/src/**/*.cs"))


class TestIsExcluded(unittest.TestCase):
    def test_node_modules_excluded(self) -> None:
        self.assertTrue(is_excluded("workspace/output/src/app/node_modules/foo.js"))

    def test_bin_excluded(self) -> None:
        self.assertTrue(is_excluded("workspace/output/src/Backend/bin/Debug/foo.dll"))

    def test_obj_excluded(self) -> None:
        self.assertTrue(is_excluded("workspace/output/src/Backend/obj/project.assets.json"))

    def test_dll_extension_excluded(self) -> None:
        self.assertTrue(is_excluded("workspace/output/foo.dll"))

    def test_png_extension_excluded(self) -> None:
        self.assertTrue(is_excluded("workspace/input/ui/logo.png"))

    def test_source_md_not_excluded(self) -> None:
        self.assertFalse(is_excluded("workspace/output/us/1-1-Auth.md"))

    def test_source_cs_not_excluded(self) -> None:
        self.assertFalse(is_excluded("workspace/output/src/Backend/Program.cs"))


class TestResolvePattern(unittest.TestCase):
    def test_substitute_feat_number(self) -> None:
        result = resolve_pattern(
            "workspace/output/us/{n}-1-Foo.md",
            config={}, us_id="", feat_number=3, root=REPO_ROOT,
        )
        self.assertEqual(result, ["workspace/output/us/3-1-Foo.md"])

    def test_substitute_us_id(self) -> None:
        result = resolve_pattern(
            "workspace/output/us/{n}-{m}-Auth.md",
            config={}, us_id="1-2", feat_number=0, root=REPO_ROOT,
        )
        self.assertEqual(result, ["workspace/output/us/1-2-Auth.md"])

    def test_substitute_appname(self) -> None:
        result = resolve_pattern(
            "workspace/output/src/{AppName}/CLAUDE.md",
            config={"AppName": "MyFront"}, us_id="", feat_number=0, root=REPO_ROOT,
        )
        self.assertEqual(result, ["workspace/output/src/MyFront/CLAUDE.md"])

    def test_substitute_project_expands_multiple(self) -> None:
        result = resolve_pattern(
            "workspace/output/src/{Project}/CLAUDE.md",
            config={"AppName": "Front", "BackendName": "Back", "LibName": "Lib"},
            us_id="", feat_number=0, root=REPO_ROOT,
        )
        self.assertEqual(set(result), {
            "workspace/output/src/Front/CLAUDE.md",
            "workspace/output/src/Back/CLAUDE.md",
            "workspace/output/src/Lib/CLAUDE.md",
        })

    def test_unresolved_placeholder_returns_empty(self) -> None:
        result = resolve_pattern(
            "workspace/output/src/{UnknownVar}/foo.md",
            config={}, us_id="", feat_number=0, root=REPO_ROOT,
        )
        self.assertEqual(result, [])


class TestExpandFiles(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        # Crée 3 fichiers test
        (self.root / "a.md").write_text("aaa", encoding="utf-8")
        (self.root / "b.md").write_text("bbb", encoding="utf-8")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "c.md").write_text("ccc", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_direct_file_match(self) -> None:
        result = expand_files("a.md", self.root)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "a.md")

    def test_glob_at_root(self) -> None:
        result = expand_files("*.md", self.root)
        names = sorted(p.name for p in result)
        self.assertIn("a.md", names)
        self.assertIn("b.md", names)

    def test_recursive_glob(self) -> None:
        result = expand_files("**/*.md", self.root)
        names = sorted(p.name for p in result)
        # Au moins le fichier sub/c.md doit être trouvé
        self.assertIn("c.md", names)

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(expand_files("does_not_exist.md", self.root), [])


def _setup_fake_repo(root: Path, agent: str, reads_patterns: list[str]) -> None:
    """Crée un repo factice minimal avec .claude/loader.yml + Project Config + fichiers ciblés."""
    claude_dir = root / ".claude"
    claude_dir.mkdir(parents=True)
    # loader.yml minimal avec un agent
    reads_block = "\n".join(f"    - {p}" for p in reads_patterns)
    (claude_dir / "loader.yml").write_text(
        f"{agent}:\n  reads:\n{reads_block}\n",
        encoding="utf-8",
    )
    # stack.md minimal avec Project Config (lu par read_project_config)
    stack_dir = root / "workspace" / "input" / "stack"
    stack_dir.mkdir(parents=True)
    (stack_dir / "stack.md").write_text(
        "## Project Config\n"
        "AppName: TestApp\n"
        "BackendName: TestBack\n"
        "AppNamespace: Test.NS\n"
        "\n"
        "## Active Tech Specs\n",
        encoding="utf-8",
    )


def _run_budget(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT)] + args
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))


class TestIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.fake_repo = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_pass_within_budget(self) -> None:
        """Agent avec reads bornés et fichiers petits → exit 0 + ledger écrit."""
        _setup_fake_repo(self.fake_repo, "po", ["workspace/input/stack/stack.md"])
        out_file = self.fake_repo / "ledger.jsonl"
        result = _run_budget(
            [
                "--agent", "po",
                "--repo-root", str(self.fake_repo),
                "--out-file", str(out_file),
                "--json",
            ],
            cwd=self.fake_repo,
        )
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr}")
        # Ledger doit exister + contenir une ligne JSON parseable
        self.assertTrue(out_file.is_file())
        line = out_file.read_text(encoding="utf-8").strip().splitlines()[0]
        record = json.loads(line)
        self.assertEqual(record["agent"], "po")
        self.assertEqual(record["result"], "pass")
        self.assertEqual(record["errors"], [])

    def test_unbounded_glob_rejected(self) -> None:
        """Loader avec glob sans borne FEAT → exit 1 + UNBOUNDED_GLOB."""
        _setup_fake_repo(self.fake_repo, "po", ["workspace/output/**/*.md"])
        out_file = self.fake_repo / "ledger.jsonl"
        result = _run_budget(
            [
                "--agent", "po",
                "--repo-root", str(self.fake_repo),
                "--out-file", str(out_file),
                "--json",
            ],
            cwd=self.fake_repo,
        )
        self.assertEqual(result.returncode, 1, msg=f"stdout={result.stdout}")
        record = json.loads(out_file.read_text(encoding="utf-8").strip().splitlines()[-1])
        codes = [e["code"] for e in record["errors"]]
        self.assertIn("UNBOUNDED_GLOB", codes)

    def test_allow_unbounded_globs_flag_bypasses(self) -> None:
        """--allow-unbounded-globs bypass le check UNBOUNDED_GLOB."""
        _setup_fake_repo(self.fake_repo, "po", ["workspace/output/**/*.md"])
        out_file = self.fake_repo / "ledger.jsonl"
        result = _run_budget(
            [
                "--agent", "po",
                "--repo-root", str(self.fake_repo),
                "--out-file", str(out_file),
                "--allow-unbounded-globs",
                "--json",
            ],
            cwd=self.fake_repo,
        )
        # Pas de UNBOUNDED_GLOB ; reste pass car aucun fichier réel ne matche
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr}")

    def test_budget_exceeded(self) -> None:
        """Fichier énorme dans reads → exit 1 + BUDGET_EXCEEDED."""
        # Patch DEFAULT_BUDGETS via env n'est pas supporté ; on génère un fichier > 60_000 bytes (budget po)
        _setup_fake_repo(self.fake_repo, "po", ["workspace/input/stack/stack.md"])
        huge = "X" * 80_000
        (self.fake_repo / "workspace" / "input" / "stack" / "stack.md").write_text(
            "## Project Config\nAppName: T\nBackendName: B\nAppNamespace: T\n\n"
            "## Active Tech Specs\n\n" + huge,
            encoding="utf-8",
        )
        out_file = self.fake_repo / "ledger.jsonl"
        result = _run_budget(
            [
                "--agent", "po",
                "--repo-root", str(self.fake_repo),
                "--out-file", str(out_file),
                "--json",
            ],
            cwd=self.fake_repo,
        )
        self.assertEqual(result.returncode, 1, msg=f"stdout={result.stdout}")
        record = json.loads(out_file.read_text(encoding="utf-8").strip().splitlines()[-1])
        codes = [e["code"] for e in record["errors"]]
        self.assertIn("BUDGET_EXCEEDED", codes)


class TestDefaultBudgetsCoverage(unittest.TestCase):
    """Non-regression : tout agent listé dans CURRENT_AGENTS DOIT avoir un
    budget dans DEFAULT_BUDGETS — sinon KeyError au runtime (security audit
    2026-06-06 sur constitutioner manquant).
    """

    def test_every_current_agent_has_default_budget(self) -> None:
        missing = [a for a in CURRENT_AGENTS if a not in DEFAULT_BUDGETS]
        self.assertEqual(
            missing, [],
            f"Agents in CURRENT_AGENTS but missing from DEFAULT_BUDGETS: {missing}. "
            "Add entries to DEFAULT_BUDGETS to prevent runtime KeyError."
        )


if __name__ == "__main__":
    unittest.main()
