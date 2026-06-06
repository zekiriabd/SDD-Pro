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


if __name__ == "__main__":
    unittest.main()
