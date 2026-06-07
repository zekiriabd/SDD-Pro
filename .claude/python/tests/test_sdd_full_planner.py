"""Tests for sdd_full_planner.py (v7.0.0-alpha)."""
from __future__ import annotations

import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_scripts import sdd_full_planner  # noqa: E402


def _make_project(
    root: Path,
    *,
    stack_md: str = "",
    feats: list[str] | None = None,
    us: list[str] | None = None,
) -> None:
    """Create a minimal SDD_Pro layout."""
    (root / ".claude").mkdir()
    (root / "workspace" / "input" / "feats").mkdir(parents=True)
    (root / "workspace" / "input" / "stack").mkdir(parents=True)
    (root / "workspace" / "output" / "us").mkdir(parents=True)
    (root / "workspace" / "input" / "stack" / "stack.md").write_text(stack_md, encoding="utf-8")
    for f in feats or []:
        (root / "workspace" / "input" / "feats" / f).write_text("# FEAT", encoding="utf-8")
    for u in us or []:
        (root / "workspace" / "output" / "us" / u).write_text("# US", encoding="utf-8")


_STACK_C1_MIN = """## Project Config
AppName: TestApp
BackendName: TestApi
MaxParallel: 3
CoverageMin: 80
QAMode: tests+coverage
GatedWorkflow: true

## Active Tech Specs
 - .claude/stacks/backend/dotnet-minimalapi.md
 - .claude/stacks/frontend/react.md

## Active UI Specs
 - .claude/stacks/ui/shadcn.md

## Active QA Specs
 - .claude/stacks/qa/dotnet-xunit.md
"""


class TestSddFullPlanner(unittest.TestCase):
    def test_missing_feat_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root, stack_md=_STACK_C1_MIN)
            plan = sdd_full_planner.build_plan(root, feat_n=99)
            self.assertEqual(len(plan["errors"]), 1)
            self.assertEqual(plan["errors"][0]["code"], "FEAT_NOT_FOUND")

    def test_back_front_plan_includes_api_gate_blocking(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(
                root,
                stack_md=_STACK_C1_MIN,
                feats=["1-Auth.md"],
                us=["1-1-Login.md", "1-2-Reset.md"],
            )
            plan = sdd_full_planner.build_plan(root, feat_n=1)
            self.assertEqual(plan["app_type"], "back-front")
            self.assertEqual(plan["us_count"], 2)
            phase_ids = [p["id"] for p in plan["phases"]]
            self.assertEqual(
                phase_ids,
                [
                    "us-generate",
                    "feat-validate",
                    "arch-init",
                    "dev-backend",
                    "qa-api-gate",
                    "dev-frontend",
                    "qa-generate",
                    "sdd-review",
                ],
            )
            gate = next(p for p in plan["phases"] if p["id"] == "qa-api-gate")
            self.assertTrue(gate["blocking"])
            self.assertIn("FAIL", gate["blocking_statuses"])

    def test_us_generate_skipped_when_us_exist(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(
                root,
                stack_md=_STACK_C1_MIN,
                feats=["1-Auth.md"],
                us=["1-1-Login.md"],
            )
            plan = sdd_full_planner.build_plan(root, feat_n=1)
            us_phase = next(p for p in plan["phases"] if p["id"] == "us-generate")
            self.assertEqual(us_phase["status"], "skip")

    def test_arch_skipped_when_bootstrap_stable_and_feat_gt1(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root, stack_md=_STACK_C1_MIN, feats=["2-X.md"])
            # Simulate stable bootstrap : csproj présent
            project_dir = root / "workspace" / "output" / "src" / "TestApi"
            project_dir.mkdir(parents=True)
            (project_dir / "TestApi.csproj").write_text("<Project />")
            plan = sdd_full_planner.build_plan(root, feat_n=2)
            arch = next(p for p in plan["phases"] if p["id"] == "arch-init")
            self.assertEqual(arch["status"], "skip")

    def test_arch_runs_for_feat1_always(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root, stack_md=_STACK_C1_MIN, feats=["1-A.md"])
            plan = sdd_full_planner.build_plan(root, feat_n=1)
            arch = next(p for p in plan["phases"] if p["id"] == "arch-init")
            self.assertEqual(arch["status"], "pending")

    def test_api_gate_skipped_when_gated_workflow_false(self) -> None:
        stack = _STACK_C1_MIN.replace("GatedWorkflow: true", "GatedWorkflow: false")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root, stack_md=stack, feats=["1-A.md"], us=["1-1-X.md"])
            plan = sdd_full_planner.build_plan(root, feat_n=1)
            gate = next(p for p in plan["phases"] if p["id"] == "qa-api-gate")
            self.assertEqual(gate["status"], "skip")
            self.assertIn("GatedWorkflow=false", gate["reason"])

    def test_qa_skipped_when_qamode_off(self) -> None:
        stack = _STACK_C1_MIN.replace("QAMode: tests+coverage", "QAMode: off")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root, stack_md=stack, feats=["1-A.md"], us=["1-1-X.md"])
            plan = sdd_full_planner.build_plan(root, feat_n=1)
            qa = next(p for p in plan["phases"] if p["id"] == "qa-generate")
            self.assertEqual(qa["status"], "skip")
            self.assertIn("QAMode=off", qa["reason"])

    def test_dev_backend_skipped_when_no_backend_stack(self) -> None:
        stack = """## Project Config
AppName: TestApp
QAMode: tests+coverage
GatedWorkflow: true
MaxParallel: 3
CoverageMin: 80

## Active Tech Specs
 - .claude/stacks/frontend/react.md
"""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root, stack_md=stack, feats=["1-A.md"], us=["1-1-X.md"])
            plan = sdd_full_planner.build_plan(root, feat_n=1)
            self.assertEqual(plan["app_type"], "front-only")
            back = next(p for p in plan["phases"] if p["id"] == "dev-backend")
            self.assertEqual(back["status"], "skip")

    def test_main_json_output(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root, stack_md=_STACK_C1_MIN, feats=["1-A.md"], us=["1-1-X.md"])
            buf = StringIO()
            with patch("sys.stdout", buf):
                exit_code = sdd_full_planner.main(
                    ["--feat-number", "1", "--root", str(root), "--json"]
                )
            self.assertEqual(exit_code, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["feat_number"], 1)
            self.assertEqual(len(data["phases"]), 8)

    def test_manual_gates_flag_adds_gate_list(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root, stack_md=_STACK_C1_MIN, feats=["1-A.md"])
            plan = sdd_full_planner.build_plan(root, feat_n=1, manual_gates=True)
            self.assertEqual(
                plan["manual_gates"],
                ["afterUS", "afterReadiness", "afterPlan", "afterCode"],
            )


# ============================================================================
# Sprint 2.5 (2026-06-07) — tests for next-action + recap subcommands
# ============================================================================


class TestDecideNextAction(unittest.TestCase):
    """Coverage for decide_next_action() — pure function, no FS dependency."""

    def _make_plan(self, phases: list[dict], feat_n: int = 1) -> dict:
        return {"feat_number": feat_n, "phases": phases}

    def test_empty_state_returns_first_pending(self) -> None:
        plan = self._make_plan([
            {"id": "us-generate", "status": "skip", "reason": "US present"},
            {"id": "feat-validate", "status": "pending", "label": "Readiness"},
        ])
        state = {"completed_phases": [], "last_status": None, "flags": {}}
        decision = sdd_full_planner.decide_next_action(plan, state)
        # us-generate is skip → returned as skip first
        self.assertEqual(decision["action"], "skip")
        self.assertEqual(decision["phase_id"], "us-generate")

    def test_skips_completed_phases(self) -> None:
        plan = self._make_plan([
            {"id": "us-generate", "status": "pending"},
            {"id": "feat-validate", "status": "pending"},
        ])
        state = {
            "completed_phases": ["us-generate"],
            "last_status": "pass",
            "flags": {},
        }
        decision = sdd_full_planner.decide_next_action(plan, state)
        self.assertEqual(decision["phase_id"], "feat-validate")

    def test_readiness_nogo_without_force_stops(self) -> None:
        plan = self._make_plan([
            {"id": "us-generate", "status": "pending"},
            {"id": "feat-validate", "status": "pending"},
            {"id": "arch-init", "status": "pending"},
        ])
        state = {
            "completed_phases": ["us-generate", "feat-validate"],
            "last_status": "fail",
            "last_verdict": "NO-GO",
            "flags": {},
        }
        decision = sdd_full_planner.decide_next_action(plan, state)
        self.assertEqual(decision["action"], "stop")

    def test_readiness_nogo_with_force_continues(self) -> None:
        plan = self._make_plan([
            {"id": "us-generate", "status": "pending"},
            {"id": "feat-validate", "status": "pending"},
            {"id": "arch-init", "status": "pending"},
        ])
        state = {
            "completed_phases": ["us-generate", "feat-validate"],
            "last_status": "warn",  # NOT fail — fail propagates regardless
            "last_verdict": "NO-GO",
            "flags": {"force": True},
        }
        decision = sdd_full_planner.decide_next_action(plan, state)
        # With --force, NO-GO doesn't stop — pipeline continues to arch-init
        self.assertEqual(decision["action"], "skill")
        self.assertEqual(decision["phase_id"], "arch-init")

    def test_warn_without_force_stops_strict_mode(self) -> None:
        plan = self._make_plan([
            {"id": "feat-validate", "status": "pending"},
            {"id": "arch-init", "status": "pending"},
        ])
        state = {
            "completed_phases": ["feat-validate"],
            "last_status": "warn",
            "last_verdict": "WARN",
            "flags": {},
        }
        decision = sdd_full_planner.decide_next_action(plan, state)
        self.assertEqual(decision["action"], "stop")

    def test_previous_fail_stops_regardless(self) -> None:
        plan = self._make_plan([
            {"id": "us-generate", "status": "pending"},
            {"id": "feat-validate", "status": "pending"},
        ])
        state = {
            "completed_phases": ["us-generate"],
            "last_status": "fail",
            "flags": {"force": True},  # even with --force
        }
        decision = sdd_full_planner.decide_next_action(plan, state)
        self.assertEqual(decision["action"], "stop")

    def test_dev_phases_coalesced_into_dev_run(self) -> None:
        plan = self._make_plan([
            {"id": "dev-backend", "status": "pending"},
            {"id": "qa-api-gate", "status": "pending"},
            {"id": "dev-frontend", "status": "pending"},
        ])
        state = {"completed_phases": [], "last_status": "pass", "flags": {}}
        decision = sdd_full_planner.decide_next_action(plan, state)
        self.assertEqual(decision["action"], "skill")
        self.assertEqual(decision["skill"], "/dev-run")
        self.assertIn("dev-backend", decision["covers_phases"])
        self.assertIn("qa-api-gate", decision["covers_phases"])
        self.assertIn("dev-frontend", decision["covers_phases"])

    def test_script_phase_returns_script_action(self) -> None:
        plan = self._make_plan([
            {
                "id": "sdd-review",
                "status": "pending",
                "script": ".claude/python/sdd_scripts/sdd_review.py",
            },
        ])
        state = {"completed_phases": [], "last_status": "pass", "flags": {}}
        decision = sdd_full_planner.decide_next_action(plan, state)
        self.assertEqual(decision["action"], "script")
        self.assertIn("sdd_review.py", decision["script"])
        self.assertIn("--feat-number", decision["args"])

    def test_all_completed_returns_done(self) -> None:
        plan = self._make_plan([
            {"id": "us-generate", "status": "pending"},
            {"id": "feat-validate", "status": "pending"},
        ])
        state = {
            "completed_phases": ["us-generate", "feat-validate"],
            "last_status": "pass",
            "flags": {},
        }
        decision = sdd_full_planner.decide_next_action(plan, state)
        self.assertEqual(decision["action"], "done")

    def test_blocked_phase_stops(self) -> None:
        plan = self._make_plan([
            {
                "id": "arch-init",
                "status": "blocked",
                "reason": "stack.md missing AppName",
            },
        ])
        state = {"completed_phases": [], "last_status": None, "flags": {}}
        decision = sdd_full_planner.decide_next_action(plan, state)
        self.assertEqual(decision["action"], "stop")
        self.assertIn("AppName", decision["reason"])


class TestBuildRecap(unittest.TestCase):
    """Coverage for build_recap() — reads console.db."""

    def _setup_db(self, root: Path) -> Path:
        """Create a minimal console.db with one run and phases."""
        import sqlite3
        db_path = root / "workspace" / "output" / "db" / "console.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.executescript("""
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            command TEXT,
            feat_n INTEGER,
            feat_name TEXT,
            started_at TEXT,
            ended_at TEXT,
            status TEXT,
            tags_json TEXT
        );
        CREATE TABLE run_phases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            phase TEXT,
            started_at TEXT,
            ended_at TEXT,
            status TEXT,
            payload_json TEXT
        );
        CREATE TABLE token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            run_id TEXT,
            agent TEXT,
            model TEXT,
            feat_n INTEGER,
            us_id TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_creation_tokens INTEGER,
            cache_read_tokens INTEGER
        );
        """)
        conn.execute(
            "INSERT INTO runs (run_id, feat_n, feat_name, started_at, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test123", 1, "MyFeat", "2026-06-07T00:00:00Z", "success"),
        )
        conn.execute(
            "INSERT INTO run_phases (run_id, phase, status, payload_json) "
            "VALUES (?, ?, ?, ?)",
            ("test123", "us-generate", "pass", '{"usCount":2}'),
        )
        conn.execute(
            "INSERT INTO run_phases (run_id, phase, status, payload_json) "
            "VALUES (?, ?, ?, ?)",
            ("test123", "qa-generate", "pass", '{"decision":"GREEN","coverage":92}'),
        )
        conn.execute(
            "INSERT INTO token_usage (run_id, agent, input_tokens, output_tokens, "
            "cache_read_tokens, cache_creation_tokens) VALUES (?, ?, ?, ?, ?, ?)",
            ("test123", "dev-backend", 100, 200, 50000, 300),
        )
        conn.commit()
        conn.close()
        return db_path

    def test_recap_reads_run_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_db(root)
            recap = sdd_full_planner.build_recap(root, "test123")
            self.assertEqual(recap["feat_number"], 1)
            self.assertEqual(recap["feat_name"], "MyFeat")
            self.assertEqual(recap["final_status"], "success")

    def test_recap_aggregates_phases(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_db(root)
            recap = sdd_full_planner.build_recap(root, "test123")
            self.assertEqual(len(recap["phases"]), 2)
            phase_ids = [p["phase"] for p in recap["phases"]]
            self.assertIn("us-generate", phase_ids)
            self.assertIn("qa-generate", phase_ids)

    def test_recap_extracts_verdicts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_db(root)
            recap = sdd_full_planner.build_recap(root, "test123")
            self.assertEqual(recap["verdicts"].get("qa-generate"), "GREEN")

    def test_recap_aggregates_tokens(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_db(root)
            recap = sdd_full_planner.build_recap(root, "test123")
            self.assertEqual(recap["tokens"]["input"], 100)
            self.assertEqual(recap["tokens"]["cache_read"], 50000)

    def test_recap_unknown_run_id_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_db(root)
            recap = sdd_full_planner.build_recap(root, "does-not-exist")
            self.assertIn("error", recap)

    def test_recap_no_db_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            recap = sdd_full_planner.build_recap(root, "test123")
            self.assertIn("error", recap)

    def test_render_recap_markdown_with_verdicts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_db(root)
            recap = sdd_full_planner.build_recap(root, "test123")
            md = sdd_full_planner.render_recap_markdown(recap)
            self.assertIn("MyFeat", md)
            self.assertIn("GREEN", md)
            self.assertIn("test123", md)

    def test_render_recap_unicode_safe(self) -> None:
        """Recap output should contain unicode (emojis) without raising."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_db(root)
            recap = sdd_full_planner.build_recap(root, "test123")
            md = sdd_full_planner.render_recap_markdown(recap)
            # Should encode/decode cleanly as UTF-8
            md.encode("utf-8").decode("utf-8")


class TestRecapFalsePositiveDefense(unittest.TestCase):
    """Audit CTO 2026-06-07 — P0 defensive check : `build_recap` must NOT
    emit `final_status: success` when agents marked dev_run pass but no
    code is on disk.

    The check skips when dev_run was not in the recorded phases (pure-doc
    FEAT or POC that never ran dev_run).
    """

    def _make_db_with_dev_run(self, root: Path, dev_run_status: str = "pass",
                              runs_status: str = "success") -> None:
        """Setup console.db with a runs row + dev_run phase row."""
        import sqlite3
        db_path = root / "workspace" / "output" / "db" / "console.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.executescript("""
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY, command TEXT, feat_n INTEGER,
            feat_name TEXT, started_at TEXT, ended_at TEXT, status TEXT,
            tags_json TEXT
        );
        CREATE TABLE run_phases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, phase TEXT,
            started_at TEXT, ended_at TEXT, status TEXT, payload_json TEXT
        );
        CREATE TABLE token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT,
            agent TEXT, model TEXT, feat_n INTEGER, us_id TEXT,
            input_tokens INTEGER, output_tokens INTEGER,
            cache_creation_tokens INTEGER, cache_read_tokens INTEGER
        );
        """)
        conn.execute(
            "INSERT INTO runs (run_id, feat_n, feat_name, started_at, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("trun", 1, "MyFeat", "2026-06-07T00:00:00Z", runs_status),
        )
        conn.execute(
            "INSERT INTO run_phases (run_id, phase, status, payload_json) "
            "VALUES (?, ?, ?, ?)",
            ("trun", "dev_run", dev_run_status, "{}"),
        )
        conn.commit()
        conn.close()

    def test_dev_run_pass_no_code_downgrades_to_partial(self) -> None:
        """The critical case : dev_run pass + 0 code files → partial + WARN."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_db_with_dev_run(root)
            # No code files seeded under workspace/output/src/
            recap = sdd_full_planner.build_recap(root, "trun")
            self.assertEqual(recap["final_status"], "partial",
                             "Should downgrade success → partial when dev_run pass but no code")
            self.assertEqual(recap["code_files_count"], 0)
            self.assertTrue(any("FALSE_POSITIVE_COMPLETION" in w
                                for w in recap["warnings"]))

    def test_dev_run_pass_with_code_keeps_success(self) -> None:
        """Happy path : dev_run pass + code on disk → success preserved."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_db_with_dev_run(root)
            src = root / "workspace" / "output" / "src" / "MyApp"
            src.mkdir(parents=True)
            (src / "Service.cs").write_text("class Foo {}")
            (src / "Component.tsx").write_text("export const Foo = () => <div/>;")
            recap = sdd_full_planner.build_recap(root, "trun")
            self.assertEqual(recap["final_status"], "success")
            self.assertEqual(recap["code_files_count"], 2)
            self.assertEqual(recap["warnings"], [])

    def test_dev_run_skip_no_code_keeps_success(self) -> None:
        """Pure-doc FEAT : dev_run skip + 0 code is legit, no downgrade."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_db_with_dev_run(root, dev_run_status="skip")
            recap = sdd_full_planner.build_recap(root, "trun")
            self.assertEqual(recap["final_status"], "success")
            self.assertEqual(recap["warnings"], [])

    def test_node_modules_excluded_from_count(self) -> None:
        """node_modules/ generated files don't count as production code."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_db_with_dev_run(root)
            nm = root / "workspace" / "output" / "src" / "MyApp" / "node_modules" / "lodash"
            nm.mkdir(parents=True)
            (nm / "index.js").write_text("module.exports = {};")
            recap = sdd_full_planner.build_recap(root, "trun")
            # node_modules/index.js should NOT count → still 0 code files
            self.assertEqual(recap["code_files_count"], 0)
            self.assertEqual(recap["final_status"], "partial")

    def test_markdown_renders_warning(self) -> None:
        """Warnings should appear in the rendered markdown recap."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_db_with_dev_run(root)
            recap = sdd_full_planner.build_recap(root, "trun")
            md = sdd_full_planner.render_recap_markdown(recap)
            self.assertIn("FALSE_POSITIVE_COMPLETION", md)


if __name__ == "__main__":
    unittest.main()
