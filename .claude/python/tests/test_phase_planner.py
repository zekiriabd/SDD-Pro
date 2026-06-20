"""Tests pour phase_planner.py (v6.4.1 méta-orchestrateur conditionnel)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdd_scripts.phase_planner import (
    PHASE_COST_ESTIMATE,
    _bool_flag,
    _decide_code_review,
    _decide_security_scan,
    _decide_spec_compliance,
    _normalize_mode,
    plan,
)


# -----------------------------------------------------------------------------
# Helpers : créer un workspace minimal dans tmp_path
# -----------------------------------------------------------------------------


def _make_workspace(
    tmp_path: Path,
    *,
    stack_md: str,
    feat_content: str | None = None,
    us_contents: list[str] | None = None,
    backend_code_files: list[str] | None = None,
    frontend_code_files: list[str] | None = None,
    app_name: str = "AppFront",
    backend_name: str = "AppBack",
) -> Path:
    """Construit un workspace minimal SDD_Pro pour tests.

    v7.0.1 fix : `_looks_like_repo_root()` requires `.claude/agents/` +
    `.claude/commands/` + `workspace/` (strict check). Creating only
    `.claude/` made tests walk up to the real repo and pollute
    workspace/output/db/console.db.
    """
    workspace = tmp_path
    # Markers complets pour repo_root() detection (cf. sdd_lib/paths.py
    # _looks_like_repo_root strict check post-mortem 2026-05-21).
    (workspace / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    (workspace / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
    (workspace / "workspace" / "input" / "stack").mkdir(parents=True, exist_ok=True)
    (workspace / "workspace" / "input" / "stack" / "stack.md").write_text(stack_md, encoding="utf-8")

    if feat_content is not None:
        feats_dir = workspace / "workspace" / "input" / "feats"
        feats_dir.mkdir(parents=True, exist_ok=True)
        (feats_dir / "1-TestFeat.md").write_text(feat_content, encoding="utf-8")

    if us_contents:
        us_dir = workspace / "workspace" / "output" / "us"
        us_dir.mkdir(parents=True, exist_ok=True)
        for idx, content in enumerate(us_contents, start=1):
            (us_dir / f"1-{idx}-TestUS.md").write_text(content, encoding="utf-8")

    if backend_code_files:
        be_dir = workspace / "workspace" / "output" / "src" / backend_name / "Services"
        be_dir.mkdir(parents=True, exist_ok=True)
        for fn in backend_code_files:
            (be_dir / fn).write_text("// stub", encoding="utf-8")

    if frontend_code_files:
        fe_dir = workspace / "workspace" / "output" / "src" / app_name / "src" / "components"
        fe_dir.mkdir(parents=True, exist_ok=True)
        for fn in frontend_code_files:
            (fe_dir / fn).write_text("// stub", encoding="utf-8")

    return workspace


STACK_FULLSTACK = """# Stack
## Project Config
AppName: AppFront
BackendName: AppBack
A11yMode: full
CodeReviewMode: full
SecurityMode: full
SecurityThreatModelEnabled: true
SecurityScanEnabled: true
PerfMode: full
SpecComplianceMode: full

## Active Tech Specs
 - .claude/stacks/backend/dotnet-minimalapi.md
 - .claude/stacks/frontend/react.md

## Active UI Specs
 - .claude/stacks/ui/shadcn.md

## Active Auth Specs
 - .claude/stacks/auth/auth-local.md
"""

STACK_BACKEND_ONLY = """# Stack
## Project Config
AppName: AppFront
BackendName: AppBack
A11yMode: full
CodeReviewMode: full
SecurityMode: full
PerfMode: manual

## Active Tech Specs
 - .claude/stacks/backend/dotnet-minimalapi.md
"""

STACK_ALL_MANUAL = """# Stack
## Project Config
AppName: AppFront
BackendName: AppBack
A11yMode: manual
CodeReviewMode: manual
SecurityMode: manual
PerfMode: manual

## Active Tech Specs
 - .claude/stacks/backend/dotnet-minimalapi.md
 - .claude/stacks/frontend/react.md
"""

STACK_ALL_OFF = """# Stack
## Project Config
AppName: AppFront
BackendName: AppBack
A11yMode: off
CodeReviewMode: off
SecurityMode: off
PerfMode: off

## Active Tech Specs
 - .claude/stacks/backend/dotnet-minimalapi.md
"""

FEAT_BASIC = """# FEAT 1
## Acceptance Criteria
- AC-1: l'utilisateur peut faire X
"""

FEAT_WITH_PERF = """# FEAT 1
## Acceptance Criteria
- AC-1: l'utilisateur peut faire X
- AC-7: LCP < 2s sur 4G
"""

FEAT_WITH_SECURITY = """# FEAT 1
## Acceptance Criteria
- AC-1: l'utilisateur peut se connecter
- AC-2: le mot de passe est haché avec salt (bcrypt)
- AC-3: JWT expiration 15 min
"""


# -----------------------------------------------------------------------------
# Tests des helpers
# -----------------------------------------------------------------------------


class TestHelpers:
    def test_normalize_mode_valid(self) -> None:
        assert _normalize_mode("full") == "full"
        assert _normalize_mode("OFF") == "off"
        assert _normalize_mode("  Manual  ") == "manual"

    def test_normalize_mode_invalid_returns_default(self) -> None:
        assert _normalize_mode("invalid") == "manual"
        assert _normalize_mode(None) == "manual"
        assert _normalize_mode(None, default="full") == "full"

    def test_bool_flag_true_variants(self) -> None:
        for val in ("true", "1", "yes", "ON", "True"):
            assert _bool_flag(val) is True

    def test_bool_flag_false_variants(self) -> None:
        for val in ("false", "0", "no"):
            assert _bool_flag(val) is False

    def test_bool_flag_default(self) -> None:
        assert _bool_flag(None, default=True) is True
        assert _bool_flag(None, default=False) is False


# -----------------------------------------------------------------------------
# Tests des décideurs par phase
# -----------------------------------------------------------------------------


# Sprint immédiat 2026-06-07 — TestDecideA11y / TestDecidePerf supprimés.
# Les fonctions `_decide_a11y` et `_decide_perf` ont été retirées de
# phase_planner.py (agent_removed=True n'avait plus de consommateur depuis
# que dev-run.md §6.4.1 ne lit plus que les 3 phases actives). Substance
# tests : voir Git history pre-2026-06-07 si besoin de réintroduire.


class TestDecideSecurityScan:
    def test_security_off_disabled(self) -> None:
        ph = _decide_security_scan(
            security_mode="off",
            scan_enabled=True,
            has_security_ac=False,
            has_backend_code=True,
            has_frontend_code=True,
        )
        assert ph["enabled"] is False

    def test_security_manual_no_ac_disabled(self) -> None:
        ph = _decide_security_scan(
            security_mode="manual",
            scan_enabled=True,
            has_security_ac=False,
            has_backend_code=True,
            has_frontend_code=True,
        )
        assert ph["enabled"] is False

    def test_security_manual_with_ac_enabled(self) -> None:
        """Override : AC explicite force l'invocation même en manual."""
        ph = _decide_security_scan(
            security_mode="manual",
            scan_enabled=True,
            has_security_ac=True,
            has_backend_code=True,
            has_frontend_code=True,
        )
        assert ph["enabled"] is True

    def test_security_scan_disabled_flag(self) -> None:
        ph = _decide_security_scan(
            security_mode="full",
            scan_enabled=False,
            has_security_ac=False,
            has_backend_code=True,
            has_frontend_code=True,
        )
        assert ph["enabled"] is False
        assert "SecurityScanEnabled=false" in ph["skip_reason"]


class TestDecideCodeReview:
    def test_off(self) -> None:
        ph = _decide_code_review(code_review_mode="off", has_backend_code=True, has_frontend_code=True)
        assert ph["enabled"] is False

    def test_manual(self) -> None:
        ph = _decide_code_review(code_review_mode="manual", has_backend_code=True, has_frontend_code=True)
        assert ph["enabled"] is False

    def test_full_enabled(self) -> None:
        ph = _decide_code_review(code_review_mode="full", has_backend_code=True, has_frontend_code=True)
        assert ph["enabled"] is True

    def test_no_code(self) -> None:
        ph = _decide_code_review(code_review_mode="full", has_backend_code=False, has_frontend_code=False)
        assert ph["enabled"] is False


class TestDecideSpecCompliance:
    """v6.5.2 — spec-compliance-reviewer phase decision."""

    def test_off(self) -> None:
        ph = _decide_spec_compliance(
            spec_compliance_mode="off",
            has_backend_code=True,
            has_frontend_code=True,
        )
        assert ph["enabled"] is False
        assert "off" in ph["skip_reason"]

    def test_manual_default(self) -> None:
        ph = _decide_spec_compliance(
            spec_compliance_mode="manual",
            has_backend_code=True,
            has_frontend_code=True,
        )
        assert ph["enabled"] is False
        assert "manual" in ph["skip_reason"]

    def test_full_enabled(self) -> None:
        ph = _decide_spec_compliance(
            spec_compliance_mode="full",
            has_backend_code=True,
            has_frontend_code=True,
        )
        assert ph["enabled"] is True
        assert ph["estimated_tokens"] == PHASE_COST_ESTIMATE["spec_compliance"]

    def test_full_backend_only(self) -> None:
        ph = _decide_spec_compliance(
            spec_compliance_mode="full",
            has_backend_code=True,
            has_frontend_code=False,
        )
        assert ph["enabled"] is True

    def test_full_frontend_only(self) -> None:
        ph = _decide_spec_compliance(
            spec_compliance_mode="full",
            has_backend_code=False,
            has_frontend_code=True,
        )
        assert ph["enabled"] is True

    def test_full_no_code_skipped(self) -> None:
        ph = _decide_spec_compliance(
            spec_compliance_mode="full",
            has_backend_code=False,
            has_frontend_code=False,
        )
        assert ph["enabled"] is False
        assert "aucun code production" in ph["skip_reason"]


# Sprint immédiat 2026-06-07 — TestDecideThreatModel supprimé.
# `_decide_threat_model` retiré de phase_planner.py — substance dans Git history.


# -----------------------------------------------------------------------------
# Tests d'intégration plan() avec workspace réel
# -----------------------------------------------------------------------------


class TestPlanIntegration:
    def test_plan_fullstack_all_full(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cas nominal : tous les modes full, code généré présent → toutes phases enabled."""
        ws = _make_workspace(
            tmp_path,
            stack_md=STACK_FULLSTACK,
            feat_content=FEAT_BASIC,
            us_contents=[FEAT_BASIC],
            backend_code_files=["AuthService.cs"],
            frontend_code_files=["LoginForm.tsx"],
        )
        monkeypatch.chdir(ws)

        result = plan(feat_number=1)

        assert "error" not in result
        # v7.0.0+ (post-Sprint-immédiat 2026-06-07) : 3 phases dans l'output.
        # threat_model/a11y_audit/perf_audit RETIRÉS du JSON (code mort éliminé).
        assert set(result["phases"].keys()) == {"code_review", "security_scan", "spec_compliance"}
        assert result["phases"]["code_review"]["enabled"] is True
        assert result["phases"]["security_scan"]["enabled"] is True
        assert result["phases"]["spec_compliance"]["enabled"] is True
        # Phases véritablement actionnables = 3
        active = [k for k, ph in result["phases"].items() if ph["enabled"]]
        assert len(active) == 3

    def test_plan_all_manual_no_ac_skips_optional(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tous en manual + FEAT sans mention sec → 3 phases skipped."""
        ws = _make_workspace(
            tmp_path,
            stack_md=STACK_ALL_MANUAL,
            feat_content=FEAT_BASIC,
            backend_code_files=["AuthService.cs"],
            frontend_code_files=["LoginForm.tsx"],
        )
        monkeypatch.chdir(ws)

        result = plan(feat_number=1)

        assert result["summary"]["phases_enabled"] == 0
        # Post-Sprint immédiat : 3 phases au total (vs 6 avant)
        assert result["summary"]["phases_skipped"] == 3
        # Tokens saved = sum of all phase costs
        expected_saved = sum(PHASE_COST_ESTIMATE.values())
        assert result["summary"]["estimated_tokens_saved"] == expected_saved

    def test_plan_manual_with_security_ac_enables_security_scan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SecurityMode=manual + AC mentionne JWT → security_scan enabled
        (perf_audit/threat_model retirés v7.0.0, plus de phase à activer)."""
        ws = _make_workspace(
            tmp_path,
            stack_md=STACK_ALL_MANUAL,
            feat_content=FEAT_WITH_SECURITY,
            backend_code_files=["AuthService.cs"],
            frontend_code_files=["LoginForm.tsx"],
        )
        monkeypatch.chdir(ws)

        result = plan(feat_number=1)

        assert result["runtime_state"]["has_security_ac"] is True
        assert result["phases"]["security_scan"]["enabled"] is True

    def test_plan_all_off(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        ws = _make_workspace(
            tmp_path,
            stack_md=STACK_ALL_OFF,
            feat_content=FEAT_WITH_SECURITY,  # même avec AC sec, mode off l'emporte
            backend_code_files=["AuthService.cs"],
        )
        monkeypatch.chdir(ws)

        result = plan(feat_number=1)

        for phase in result["phases"].values():
            assert phase["enabled"] is False
        assert result["summary"]["phases_enabled"] == 0

    def test_plan_no_feat_returns_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        ws = _make_workspace(
            tmp_path,
            stack_md=STACK_FULLSTACK,
            # no feat_content
        )
        monkeypatch.chdir(ws)

        result = plan(feat_number=99)

        assert "error" in result
        assert "FEAT_NOT_FOUND" in result["error"]

    def test_plan_no_dev_run_yet_skips_code_dependent_phases(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Code généré absent → toutes les phases skip (besoin de code production)."""
        ws = _make_workspace(
            tmp_path,
            stack_md=STACK_FULLSTACK,
            feat_content=FEAT_BASIC,
        )
        monkeypatch.chdir(ws)

        result = plan(feat_number=1)

        assert result["runtime_state"]["has_backend_code"] is False
        assert result["runtime_state"]["has_frontend_code"] is False
        assert result["phases"]["code_review"]["enabled"] is False
        assert result["phases"]["security_scan"]["enabled"] is False
        assert result["phases"]["spec_compliance"]["enabled"] is False
