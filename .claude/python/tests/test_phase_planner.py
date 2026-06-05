"""Tests pour phase_planner.py (v6.4.1 méta-orchestrateur conditionnel)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdd_scripts.phase_planner import (
    PHASE_COST_ESTIMATE,
    _bool_flag,
    _decide_a11y,
    _decide_code_review,
    _decide_perf,
    _decide_security_scan,
    _decide_spec_compliance,
    _decide_threat_model,
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


class TestDecideA11y:
    """v7.0.0-alpha (audit MAJ-6) — agent retiré, fonction réduite à un stub.
    Toutes les branches granulaires de l'ancien code sont écrasées : peu importe
    les flags d'entrée, le verdict est uniformément enabled=False, agent_removed=True.
    """

    def test_a11y_stub_always_disabled(self) -> None:
        for kwargs in (
            {},  # no kwargs (stub accepts anything)
            {"a11y_mode": "off"},
            {"a11y_mode": "manual"},
            {"a11y_mode": "full", "has_frontend_stack": True, "has_frontend_code": True},
            {"a11y_mode": "full", "has_frontend_stack": False, "has_frontend_code": False},
        ):
            ph = _decide_a11y(**kwargs)
            assert ph["enabled"] is False
            assert ph["agent_removed"] is True
            assert "agent removed v7.0.0" in ph["skip_reason"]
            assert "axe-core" in ph["replacement"]
            assert ph["estimated_tokens"] == 0


class TestDecidePerf:
    """v7.0.0-alpha (audit MAJ-6) — agent retiré, stub. Cf. TestDecideA11y."""

    def test_perf_stub_always_disabled(self) -> None:
        for kwargs in (
            {},
            {"perf_mode": "off"},
            {"perf_mode": "manual", "has_perf_ac": False},
            {"perf_mode": "manual", "has_perf_ac": True, "has_backend_code": True, "has_frontend_code": True},
            {"perf_mode": "full", "has_perf_ac": False, "has_backend_code": True, "has_frontend_code": True},
        ):
            ph = _decide_perf(**kwargs)
            assert ph["enabled"] is False
            assert ph["agent_removed"] is True
            assert "Lighthouse" in ph["skip_reason"] or "wrk" in ph["skip_reason"]
            assert ph["estimated_tokens"] == 0


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


class TestDecideThreatModel:
    def test_off(self) -> None:
        stacks = {"backend": "dotnet-minimalapi", "frontend": "react", "ui": None, "auth": None}
        ph = _decide_threat_model(
            security_mode="off",
            threat_model_enabled=True,
            has_security_ac=False,
            stacks=stacks,
        )
        assert ph["enabled"] is False

    def test_manual_no_security_ac(self) -> None:
        stacks = {"backend": "dotnet-minimalapi", "frontend": "react", "ui": None, "auth": None}
        ph = _decide_threat_model(
            security_mode="manual",
            threat_model_enabled=True,
            has_security_ac=False,
            stacks=stacks,
        )
        assert ph["enabled"] is False

    def test_manual_with_security_ac_disabled_v7(self) -> None:
        """v7.0.0 : threat_model agent retiré (governance-major-auditors-trim).
        Même avec security_mode=full + has_security_ac=True + stacks actifs,
        la phase est TOUJOURS enabled=False avec agent_removed=True.
        Remplacement : template humain templates/threat-model.template.md."""
        stacks = {"backend": "dotnet-minimalapi", "frontend": "react", "ui": None, "auth": None}
        ph = _decide_threat_model(
            security_mode="manual",
            threat_model_enabled=True,
            has_security_ac=True,
            stacks=stacks,
        )
        assert ph["enabled"] is False
        assert ph.get("agent_removed") is True
        assert "replacement" in ph

    def test_no_stacks(self) -> None:
        stacks = {"backend": None, "frontend": None, "ui": None, "auth": None}
        ph = _decide_threat_model(
            security_mode="full",
            threat_model_enabled=True,
            has_security_ac=True,
            stacks=stacks,
        )
        assert ph["enabled"] is False


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
        # v7.0.0 : threat_model, a11y_audit, perf_audit RETIRÉS (agent_removed=True).
        # Restent actifs : code_review, security_scan, spec_compliance.
        assert result["phases"]["threat_model"]["enabled"] is False
        assert result["phases"]["threat_model"].get("agent_removed") is True
        # v7.0.0 P2 fix : agent_removed implies enabled=False (no spawn happens
        # regardless of upstream gates). The agent_removed flag explains the
        # forced disable to consumers reading the plan.
        assert result["phases"]["a11y_audit"]["enabled"] is False
        assert result["phases"]["a11y_audit"].get("agent_removed") is True
        assert result["phases"]["code_review"]["enabled"] is True
        assert result["phases"]["security_scan"]["enabled"] is True
        assert result["phases"]["perf_audit"]["enabled"] is False
        assert result["phases"]["perf_audit"].get("agent_removed") is True
        assert result["phases"]["spec_compliance"]["enabled"] is True
        # Phases véritablement actionnables (sans agent_removed) = 3
        active = [k for k, ph in result["phases"].items()
                  if ph["enabled"] and not ph.get("agent_removed")]
        assert len(active) == 3

    def test_plan_backend_only_skips_a11y(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # v7.0.0-alpha (audit MAJ-6) — a11y agent retiré, raison uniforme.
        ws = _make_workspace(
            tmp_path,
            stack_md=STACK_BACKEND_ONLY,
            feat_content=FEAT_BASIC,
            backend_code_files=["AuthService.cs"],
        )
        monkeypatch.chdir(ws)

        result = plan(feat_number=1)

        assert result["phases"]["a11y_audit"]["enabled"] is False
        assert result["phases"]["a11y_audit"]["agent_removed"] is True

    def test_plan_all_manual_no_ac_skips_optional(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tous en manual + FEAT sans mention sec/perf → 5 phases skipped."""
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
        assert result["summary"]["phases_skipped"] == 6
        # Tokens saved = sum of all phase costs
        expected_saved = sum(PHASE_COST_ESTIMATE.values())
        assert result["summary"]["estimated_tokens_saved"] == expected_saved

    def test_plan_manual_with_perf_ac_surfaces_replacement(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v7.0.0 P2 fix : PerfMode=manual + AC mentionne LCP USED to force
        perf_audit enabled. Now the agent is removed — phase stays disabled
        but skip_reason surfaces Lighthouse CI / wrk-k6 so the Tech Lead
        knows to verify the perf AC via the CI replacement instead."""
        ws = _make_workspace(
            tmp_path,
            stack_md=STACK_ALL_MANUAL,
            feat_content=FEAT_WITH_PERF,
            backend_code_files=["AuthService.cs"],
            frontend_code_files=["LoginForm.tsx"],
        )
        monkeypatch.chdir(ws)

        result = plan(feat_number=1)

        assert result["phases"]["perf_audit"]["enabled"] is False
        assert result["phases"]["perf_audit"].get("agent_removed") is True
        skip_reason = result["phases"]["perf_audit"]["skip_reason"]
        assert "Lighthouse" in skip_reason or "wrk" in skip_reason
        assert result["runtime_state"]["has_perf_ac"] is True

    def test_plan_manual_with_security_ac_forces_threat_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SecurityMode=manual + AC mentionne JWT → threat_model + security_scan enabled."""
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
        # v7.0.0 : threat_model agent retiré — phase reste False même avec AC sécurité
        assert result["phases"]["threat_model"]["enabled"] is False
        assert result["phases"]["threat_model"].get("agent_removed") is True
        assert result["phases"]["security_scan"]["enabled"] is True
        # Perf reste skippé car pas d'AC perf
        assert result["phases"]["perf_audit"]["enabled"] is False

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
        """Code généré absent → code_review + security_scan + perf_audit skip."""
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
        # v7.0.0 : threat_model agent retiré — always False with agent_removed
        assert result["phases"]["threat_model"]["enabled"] is False
        assert result["phases"]["threat_model"].get("agent_removed") is True
        # a11y skip car pas de frontend code
        assert result["phases"]["a11y_audit"]["enabled"] is False
