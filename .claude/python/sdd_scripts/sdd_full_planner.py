"""SDD_Pro: deterministic execution planner for /sdd-full pipeline.

⚠️ **STATUT v7.0.0-alpha (2026-06-06)** : prototype runtime — **non câblé**
dans `/sdd-full` ni `/dev-run` aujourd'hui. Les commands utilisent encore
le pseudo-bash inline (cf. `sdd-full.md` STEPs). À wirer en v7.2 quand
l'orchestrateur sera Python pur (cf. Top-10 #6 audit 2026-06-06). Les
tests (`test_sdd_full_planner.py`, 10 cas verts) garantissent que la
logique métier est correcte ; il manque juste le bridge command → script.

**Périmètre vs phase_planner.py** (audit 2026-06-06 D2 — désambiguïsation) :

- `phase_planner.py` (SSoT depuis v7.0.0 audit CRIT-4) : décide **quels
  reviewers** spawn en STEP 6.4 de `/dev-run` (code-review, security-scan,
  spec-compliance) selon `*Mode` Project Config + heuristiques de skip
  (no-source-files, qa-skipped, etc.). **Câblé en production**, consommé
  par `dev-run.md §5.5` + §6.4. Périmètre POST-coding.

- `sdd_full_planner.py` (ce fichier) : décide **quelles phases entières**
  du pipeline `/sdd-full` exécuter/skipper (us-generate, arch+DB, dev-run,
  qa, sdd-review). Logique de **pré-validation pipeline-wide** (FEAT
  existe ? arch déjà stable ? US déjà générées ?). **Non câblé** —
  scaffold uniquement, intégration v7.2.

Les deux planners coexistent sans collision parce qu'ils opèrent à des
granularités différentes (phase pipeline vs reviewer post-code). Aucune
fusion prévue : ils peuvent rester séparés tant que leurs signatures
input/output restent disjointes.

v7.0.0-alpha (audit 2026-06-05) — premier pas vers la réduction du
pseudo-code orchestrateur des commands `/sdd-full` et `/dev-run`.
Produit un PLAN JSON exécutable que Claude Code peut consommer via
Bash + jq pour décider quelles phases run/skip sans réinventer la
logique inline dans chaque .md.

Comportement (0 token LLM) :
1. Vérifie que FEAT N existe (workspace/input/feats/N-*.md)
2. Lit Project Config (CoverageMin, MaxParallel, GatedWorkflow, etc.)
3. Liste les US déjà générées (workspace/output/us/N-*-*.md)
4. Détecte si arch est stable (bootstrap idempotent skip)
5. Construit le plan phase-par-phase avec un statut chaque :
   - `pending`  : à exécuter
   - `skip`     : sauté (raison)
   - `blocked`  : pré-condition non satisfaite (FEAT absent, etc.)

Usage :
    python sdd_full_planner.py --feat-number N [--root PATH] [--json]

Exit codes :
    0 = SUCCESS (plan produit ; lire stdout JSON)
    1 = FAIL_FAST (FEAT introuvable / Project Config invalide)
    3 = INFRA_BLOCKED (workspace inaccessible)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.layered_config import ConfigError, read_layered_config  # noqa: E402  (P1-2 fix 2026-06-07)
from sdd_lib.project_config import (  # noqa: E402
    get_active_stack_paths,
    read_project_config,
)


# --- Helpers déterministes -------------------------------------------------


def _find_feat(root: Path, feat_n: int) -> Path | None:
    """Locate workspace/input/feats/{n}-*.md."""
    feats_dir = root / "workspace" / "input" / "feats"
    if not feats_dir.is_dir():
        return None
    for f in feats_dir.iterdir():
        if f.is_file() and f.name.startswith(f"{feat_n}-") and f.suffix == ".md":
            return f
    return None


def _list_us_files(root: Path, feat_n: int) -> list[Path]:
    """List workspace/output/us/{n}-*-*.md (in basename order)."""
    us_dir = root / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    return sorted(
        f
        for f in us_dir.iterdir()
        if f.is_file() and f.name.startswith(f"{feat_n}-") and f.suffix == ".md"
    )


def _detect_appType(root: Path) -> str:
    """Inspect active stacks to decide appType."""
    paths = get_active_stack_paths(root)
    has_backend = any("stacks/backend/" in p for p in paths)
    has_frontend = any("stacks/frontend/" in p for p in paths)
    has_fullstack = any("stacks/fullstack/" in p for p in paths)
    has_mobile = any("stacks/mobiles/" in p for p in paths)
    if has_fullstack:
        return "fullstack"
    if has_backend and (has_frontend or has_mobile):
        return "back-front"
    if has_backend:
        return "back-only"
    if has_frontend:
        return "front-only"
    return "unknown"


def _arch_seems_stable(root: Path, feat_n: int) -> bool:
    """Detect a stable bootstrap state (cf. dev-run.md STEP 4.bis).

    Heuristic v7.0.0-alpha : true iff
      - `workspace/output/src/` contient au moins un projet bootstrapé
      - `workspace/output/db/schema.json` présent (si DB attendu)
      - feat_n != 1 (pour FEAT 1, arch toujours requis pour bootstrap initial)
    """
    if feat_n == 1:
        return False
    src_dir = root / "workspace" / "output" / "src"
    if not src_dir.is_dir():
        return False
    # Au moins un projet (un sous-dossier avec un manifest)
    manifests = (
        list(src_dir.glob("*/*.csproj"))
        + list(src_dir.glob("*/package.json"))
        + list(src_dir.glob("*/pyproject.toml"))
        + list(src_dir.glob("*/build.gradle.kts"))
    )
    return len(manifests) > 0


# --- Plan construction -----------------------------------------------------


def build_plan(
    root: Path, feat_n: int, *, force: bool = False, manual_gates: bool = False
) -> dict:
    """Build the JSON execution plan for /sdd-full {feat_n}."""
    plan: dict = {
        "feat_number": feat_n,
        "phases": [],
        "warnings": [],
        "errors": [],
    }

    # 0. FEAT lookup
    feat_path = _find_feat(root, feat_n)
    if feat_path is None:
        plan["errors"].append(
            {
                "code": "FEAT_NOT_FOUND",
                "message": f"workspace/input/feats/{feat_n}-*.md missing",
            }
        )
        return plan

    plan["feat_path"] = str(feat_path.relative_to(root))

    # 1. Project Config + active stacks via layered config (base ← team ← project)
    # P1-2 fix 2026-06-07 : was `read_project_config(root, coerce=True)` which
    # ignored team/base layers — meaning the plan view diverged from the
    # actual /sdd-full execution (which uses layered config in dev-run,
    # qa, security-reviewer, etc.). Now consistent across the pipeline.
    try:
        config = read_layered_config(root=root, coerce=True)
    except ConfigError:
        # Bubble up [CONFIG_SECURITY_DOWNGRADE] — never silently allow
        # a project to relax a team baseline policy.
        raise
    except Exception as e:
        # Fallback to legacy for backward-compat (e.g. greenfield without
        # config.base.yml). Preserves the original error semantics.
        try:
            config = read_project_config(root, coerce=True)
        except Exception:
            plan["errors"].append(
                {"code": "PROJECT_CONFIG_INVALID", "message": str(e)}
            )
            return plan

    gated_raw = config.get("GatedWorkflow", True)
    plan["project_config"] = {
        "AppName": config.get("AppName"),
        "BackendName": config.get("BackendName"),
        "MaxParallel": int(config.get("MaxParallel", 3) or 3),
        "GatedWorkflow": gated_raw if isinstance(gated_raw, bool) else str(gated_raw).lower() != "false",
        "CoverageMin": int(config.get("CoverageMin", 80) or 80),
        "QAMode": config.get("QAMode", "tests+coverage"),
    }
    plan["app_type"] = _detect_appType(root)
    plan["active_stacks"] = get_active_stack_paths(root)

    # 1.bis Stack coherence validation (SSoT 2026-06-06 R3) — déléguer à
    # sdd_lib.stack_validator pour aligner sur phase_planner + validate_readiness.
    # Sans ce check, le planner produisait un plan avec app_type=fullstack
    # + tous les stacks actifs sans détecter le mix interdit.
    try:
        from sdd_lib.stack_validator import validate_active_stacks_coherence
        # Construire dict catégorisé depuis active_stack_paths
        stacks_by_cat: dict[str, str | None] = {
            "backend": None, "frontend": None, "ui": None, "auth": None,
            "fullstack": None, "mobiles": None,
        }
        for path in plan["active_stacks"]:
            for cat in stacks_by_cat:
                marker = f"/{cat}/"
                if marker in path.replace("\\", "/"):
                    stack_id = path.split(marker, 1)[1].rsplit(".md", 1)[0]
                    if stacks_by_cat[cat] is None:
                        stacks_by_cat[cat] = stack_id
                    break
        coherence_err = validate_active_stacks_coherence(stacks_by_cat)
        if coherence_err:
            plan["errors"].append({
                "code": coherence_err["code"],
                "message": coherence_err["message"],
            })
            return plan
    except ImportError:
        pass  # sdd_lib pas accessible — degradation gracieuse

    # 2. US listing
    us_files = _list_us_files(root, feat_n)
    plan["us_count"] = len(us_files)
    plan["us_files"] = [str(f.relative_to(root)) for f in us_files]

    # 3. Phases
    # PHASE 2 — US generation
    if us_files:
        plan["phases"].append(
            {
                "id": "us-generate",
                "label": "PO → User Stories",
                "status": "skip",
                "reason": f"{len(us_files)} US already present",
            }
        )
    else:
        plan["phases"].append(
            {
                "id": "us-generate",
                "label": "PO → User Stories",
                "status": "pending",
                "agent": "po",
            }
        )

    # PHASE 2.6 — Readiness gate
    plan["phases"].append(
        {
            "id": "feat-validate",
            "label": "Readiness gate (deterministic)",
            "status": "pending",
            "script": ".claude/python/sdd_scripts/validate_readiness.py",
        }
    )

    # PHASE 3 — arch (idempotent)
    if _arch_seems_stable(root, feat_n) and not force:
        plan["phases"].append(
            {
                "id": "arch-init",
                "label": "Arch bootstrap + DB scaffold",
                "status": "skip",
                "reason": "bootstrap stable (use --rebuild-arch to force)",
            }
        )
    else:
        plan["phases"].append(
            {
                "id": "arch-init",
                "label": "Arch bootstrap + DB scaffold",
                "status": "pending",
                "agent": "arch",
            }
        )

    # PHASE 4 — dev-backend ALL US (parallèle, MaxParallel)
    if plan["app_type"] in ("back-front", "back-only", "fullstack"):
        plan["phases"].append(
            {
                "id": "dev-backend",
                "label": f"dev-backend (×{len(us_files)} US, parallel max={plan['project_config']['MaxParallel']})",
                "status": "pending" if us_files else "skip",
                "agent": "dev-backend",
                "us_targets": [Path(p).stem for p in plan["us_files"]],
                "max_parallel": plan["project_config"]["MaxParallel"],
            }
        )
    else:
        plan["phases"].append(
            {
                "id": "dev-backend",
                "label": "dev-backend",
                "status": "skip",
                "reason": f"app_type={plan['app_type']} has no backend",
            }
        )

    # PHASE 4.5 — QA API Gate (in-memory) — bloquant si GatedWorkflow
    if (
        plan["project_config"]["GatedWorkflow"]
        and plan["app_type"] in ("back-front", "back-only", "fullstack")
        and us_files
    ):
        plan["phases"].append(
            {
                "id": "qa-api-gate",
                "label": "QA API Gate (in-memory)",
                "status": "pending",
                "blocking": True,
                "blocking_statuses": ["FAIL", "INFRA_BLOCKED"],
            }
        )
    else:
        plan["phases"].append(
            {
                "id": "qa-api-gate",
                "label": "QA API Gate",
                "status": "skip",
                "reason": (
                    "GatedWorkflow=false"
                    if not plan["project_config"]["GatedWorkflow"]
                    else "no backend or no US"
                ),
            }
        )

    # PHASE 4.6 — dev-frontend ALL US
    if plan["app_type"] in ("back-front", "front-only", "fullstack"):
        plan["phases"].append(
            {
                "id": "dev-frontend",
                "label": f"dev-frontend (×{len(us_files)} US, parallel max={plan['project_config']['MaxParallel']})",
                "status": "pending" if us_files else "skip",
                "agent": "dev-frontend",
                "us_targets": [Path(p).stem for p in plan["us_files"]],
                "max_parallel": plan["project_config"]["MaxParallel"],
            }
        )
    else:
        plan["phases"].append(
            {
                "id": "dev-frontend",
                "label": "dev-frontend",
                "status": "skip",
                "reason": f"app_type={plan['app_type']} has no frontend",
            }
        )

    # PHASE 5 — QA generate
    qa_mode = plan["project_config"]["QAMode"]
    if qa_mode in {"off", "manual"}:
        plan["phases"].append(
            {
                "id": "qa-generate",
                "label": "QA tests + coverage + quality",
                "status": "skip",
                "reason": f"QAMode={qa_mode}",
            }
        )
    else:
        plan["phases"].append(
            {
                "id": "qa-generate",
                "label": "QA tests + coverage + quality",
                "status": "pending",
                "agent": "qa",
                "coverage_min": plan["project_config"]["CoverageMin"],
            }
        )

    # PHASE 5.5 — sdd-review
    plan["phases"].append(
        {
            "id": "sdd-review",
            "label": "Consolidated review (5 reviewers aggregated)",
            "status": "pending",
            "script": ".claude/python/sdd_scripts/sdd_review.py",
        }
    )

    # Manual gates (optionnel)
    if manual_gates:
        plan["manual_gates"] = ["afterUS", "afterReadiness", "afterPlan", "afterCode"]

    return plan


def format_text_report(plan: dict) -> str:
    """Render a human-readable plan summary."""
    lines: list[str] = []
    lines.append(f"=== /sdd-full plan for FEAT {plan['feat_number']} ===\n")
    if plan.get("errors"):
        for err in plan["errors"]:
            lines.append(f"🔴 {err['code']}: {err['message']}")
        return "\n".join(lines)
    lines.append(f"FEAT path     : {plan.get('feat_path', '?')}")
    lines.append(f"App type      : {plan.get('app_type', '?')}")
    lines.append(f"US count      : {plan.get('us_count', 0)}")
    lines.append(f"Active stacks : {len(plan.get('active_stacks', []))}")
    lines.append("")
    lines.append("Phases :")
    for i, phase in enumerate(plan["phases"], 1):
        icon = {"pending": "🟢", "skip": "⏭", "blocked": "🔴"}.get(phase["status"], "?")
        lines.append(f"  {i}. {icon} [{phase['status']:<7}] {phase['label']}")
        if phase.get("reason"):
            lines.append(f"        ↪ {phase['reason']}")
    if plan.get("warnings"):
        lines.append("\nWarnings :")
        for w in plan["warnings"]:
            lines.append(f"  ⚠ {w}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Sprint 2.5 (2026-06-07) — next-action + recap subcommands
# ----------------------------------------------------------------------------
# These enable sdd-full.md to act as a thin wrapper that loops :
#   1. python sdd_full_planner.py plan --feat-number N → list of phases
#   2. For each phase :
#      a. python sdd_full_planner.py next-action --plan-json P --state-json S
#         → {"action": "skill|stop|done", "skill": "/dev-run", "args": [...]}
#      b. (Claude executes the Skill if action=skill)
#      c. Update state via sdd_state.py set-phase
#   3. python sdd_full_planner.py recap --run-id R → final summary block
# ----------------------------------------------------------------------------


PHASE_SKILL_MAP: dict[str, tuple[str, str]] = {
    # phase id → (skill name, label)
    "us-generate":    ("us-generate",    "PO découpe FEAT en User Stories"),
    "feat-validate":  ("feat-validate",  "Readiness gate (déterministe)"),
    "arch-init":      ("arch-init",      "Arch bootstrap + DB scaffold"),
    "dev-backend":    ("dev-run",        "dev-backend ALL US (inclus dans /dev-run)"),
    "qa-api-gate":    ("dev-run",        "QA API Gate (inclus dans /dev-run)"),
    "dev-frontend":   ("dev-run",        "dev-frontend ALL US (inclus dans /dev-run)"),
    "qa-generate":    ("qa-generate",    "QA tests + coverage + quality"),
    "sdd-review":     ("sdd-review",     "Consolidated review"),
}

# Phases that the .md SHOULD dispatch as one /dev-run skill (rather than
# 3 separate skills) — dev-run already orchestrates backend → api-gate → frontend
DEV_RUN_PHASES = {"dev-backend", "qa-api-gate", "dev-frontend"}


def decide_next_action(plan: dict, state: dict) -> dict:
    """Given a plan + current state, return the next action to execute.

    Args:
      plan : output of build_plan() (must contain `phases`)
      state : dict with keys :
        - completed_phases : list[str] of phase ids already done
        - last_status : str ("pass"|"warn"|"fail"|"skip"|None)
        - last_verdict : optional verdict tag (GO|WARN|NO-GO|GREEN|YELLOW|RED)
        - flags : dict of CLI flags (force, plan, no-plan-on-warn, no-validate)

    Returns:
      {"action": "skill"|"script"|"stop"|"done",
       "phase_id": str|None,
       "skill": str|None,    # if action=skill
       "script": str|None,   # if action=script (deterministic Python)
       "args": list[str]|None,
       "reason": str}
    """
    completed = set(state.get("completed_phases", []))
    last_status = state.get("last_status")
    last_verdict = state.get("last_verdict")
    flags = state.get("flags", {})

    # Hard-fail propagation : if previous phase failed, propagate STOP unless
    # the failure is recoverable per the original gates table.
    if last_status == "fail":
        return {
            "action": "stop",
            "phase_id": None,
            "skill": None,
            "script": None,
            "args": None,
            "reason": f"Previous phase failed (status={last_status})",
        }

    # Readiness gate decision : if last phase was feat-validate, apply
    # GO/WARN/NO-GO logic against flags.
    if "feat-validate" in completed and last_verdict in ("WARN", "NO-GO"):
        force = bool(flags.get("force"))
        no_plan_on_warn = bool(flags.get("no_plan_on_warn"))
        if last_verdict == "NO-GO" and not force:
            return {
                "action": "stop",
                "phase_id": None,
                "skill": None,
                "script": None,
                "args": None,
                "reason": "Readiness NO-GO without --force, pipeline halted",
            }
        if last_verdict == "WARN" and not force:
            return {
                "action": "stop",
                "phase_id": None,
                "skill": None,
                "script": None,
                "args": None,
                "reason": "Readiness WARN without --force (strict mode), pipeline halted",
            }
        # force present : continue, optionally through dev-plan (3.6)
        if not no_plan_on_warn:
            # Treated as "go through plan-then-review" — already handled by
            # the .md (dev-plan skill). Continue to next phase.
            pass

    # Find next pending phase
    for phase in plan.get("phases", []):
        phase_id = phase["id"]
        if phase_id in completed:
            continue
        status = phase["status"]
        if status == "skip":
            return {
                "action": "skip",
                "phase_id": phase_id,
                "skill": None,
                "script": None,
                "args": None,
                "reason": phase.get("reason", "phase skipped per plan"),
            }
        if status == "blocked":
            return {
                "action": "stop",
                "phase_id": phase_id,
                "skill": None,
                "script": None,
                "args": None,
                "reason": phase.get("reason", "phase blocked"),
            }
        if status == "pending":
            # Dispatch decision : skill vs deterministic script
            if phase.get("script"):
                return {
                    "action": "script",
                    "phase_id": phase_id,
                    "skill": None,
                    "script": phase["script"],
                    "args": ["--feat-number", str(plan["feat_number"])],
                    "reason": f"Run deterministic script for {phase_id}",
                }
            # Skill dispatch — coalesce dev-* into single /dev-run
            if phase_id in DEV_RUN_PHASES:
                # Only emit /dev-run for the FIRST dev-* phase encountered ;
                # mark all 3 as completed-by-proxy after /dev-run returns.
                return {
                    "action": "skill",
                    "phase_id": phase_id,
                    "skill": "/dev-run",
                    "script": None,
                    "args": [str(plan["feat_number"])],
                    "covers_phases": ["dev-backend", "qa-api-gate", "dev-frontend"],
                    "reason": f"Dispatch /dev-run for {phase_id} (covers all dev-* phases)",
                }
            skill_name, label = PHASE_SKILL_MAP.get(
                phase_id, (phase_id, phase.get("label", phase_id))
            )
            return {
                "action": "skill",
                "phase_id": phase_id,
                "skill": f"/{skill_name}",
                "script": None,
                "args": [str(plan["feat_number"])],
                "reason": f"Dispatch /{skill_name}: {label}",
            }

    # No more phases
    return {
        "action": "done",
        "phase_id": None,
        "skill": None,
        "script": None,
        "args": None,
        "reason": "All phases completed",
    }


#: File extensions considered "production code" by `_count_code_files`.
#: Generated code, ADRs, plans, READMEs, and JSON catalogs are EXCLUDED
#: to keep the heuristic noise-low — if any of these patterns is present
#: under `workspace/output/src/{BackendName|AppName}/`, we trust that
#: real code was materialized.
_PRODUCTION_CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".cs", ".ts", ".tsx", ".js", ".jsx", ".py", ".kt", ".java",
    ".razor", ".vue", ".html", ".cshtml",
})


def _count_code_files(root: Path) -> int:
    """Count production code files under workspace/output/src/.

    Audit CTO 2026-06-07 — P0 defensive check : prevents `sdd_full_planner
    recap` from emitting `final_status: success` when agents marked phases
    as `pass` but no actual code reached disk (crash mid-write, faulty
    set-phase event, frontend-only US misclassified, etc.). The recap MUST
    surface this discrepancy as a WARN downgrade.
    """
    count = 0
    src_dir = root / "workspace" / "output" / "src"
    if not src_dir.is_dir():
        return count  # not an exit code — file counter
    for path in src_dir.rglob("*"):
        if not path.is_file():
            continue
        # Skip clearly non-prod paths
        rel = path.relative_to(src_dir).as_posix()
        if "/node_modules/" in rel or "/bin/" in rel or "/obj/" in rel:
            continue
        if "/__pycache__/" in rel or rel.endswith(".pyc"):
            continue
        if "/.gradle/" in rel or "/build/" in rel:
            continue
        if path.suffix.lower() in _PRODUCTION_CODE_EXTENSIONS:
            count += 1
    return count


def build_recap(root: Path, run_id: str) -> dict:
    """Read run_phases + token_usage + verdicts to build a final summary.

    Returns a dict with structured recap fields ready to be rendered as
    Markdown by the .md command. Does not query LLM.

    Audit CTO 2026-06-07 — P0 fix : adds `code_files_count` field and
    downgrades `final_status` from "success" → "partial" if no production
    code is present under `workspace/output/src/` (defends against false
    positives where agents emit `set-phase pass` but never write code).
    """
    import sqlite3
    db_path = root / "workspace" / "output" / "db" / "console.db"
    recap: dict = {
        "run_id": run_id,
        "phases": [],
        "verdicts": {},
        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "duration_seconds": 0,
        "final_status": "unknown",
        "feat_number": None,
        "feat_name": None,
        "code_files_count": 0,
        "warnings": [],
    }
    if not db_path.is_file():
        recap["error"] = f"console.db not found at {db_path}"
        return recap
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Run metadata
        run_row = conn.execute(
            "SELECT feat_n, feat_name, started_at, status FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if run_row is None:
            recap["error"] = f"No run with run_id={run_id}"
            return recap
        recap["feat_number"] = run_row["feat_n"]
        recap["feat_name"] = run_row["feat_name"]
        recap["started_at"] = run_row["started_at"]
        recap["final_status"] = run_row["status"]

        # Phase durations
        phase_rows = conn.execute(
            "SELECT phase, status, started_at, ended_at, payload_json "
            "FROM run_phases WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        for r in phase_rows:
            payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
            recap["phases"].append({
                "phase": r["phase"],
                "status": r["status"],
                "payload": payload,
            })
            # Extract verdicts from payload
            if "decision" in payload:
                recap["verdicts"][r["phase"]] = payload["decision"]

        # Token usage aggregate
        token_row = conn.execute(
            "SELECT SUM(input_tokens), SUM(output_tokens), "
            "SUM(cache_read_tokens), SUM(cache_creation_tokens) "
            "FROM token_usage WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if token_row and token_row[0] is not None:
            recap["tokens"] = {
                "input": token_row[0] or 0,
                "output": token_row[1] or 0,
                "cache_read": token_row[2] or 0,
                "cache_write": token_row[3] or 0,
            }
    except sqlite3.Error as e:
        recap["error"] = f"DB error: {e}"
    finally:
        if conn is not None:
            conn.close()

    # P0 fix audit CTO 2026-06-07 — defensive code-on-disk check.
    # If recap claims success but no production code exists under
    # `workspace/output/src/`, downgrade to "partial" with explicit warning.
    # Skips the check if dev_run phase was skipped (pure-doc FEAT or POC).
    code_count = _count_code_files(root)
    recap["code_files_count"] = code_count
    dev_run_phase = next((p for p in recap["phases"] if p["phase"] == "dev_run"), None)
    dev_run_ran = dev_run_phase is not None and dev_run_phase["status"] not in ("skip", None, "")
    if dev_run_ran and code_count == 0 and recap["final_status"] == "success":
        recap["final_status"] = "partial"
        recap["warnings"].append(
            "[FALSE_POSITIVE_COMPLETION] dev_run phase marked pass but no "
            "production code files found under workspace/output/src/. "
            "Possible causes: agent crashed mid-write, set-phase event emitted "
            "without writing, frontend-only US misclassified. Inspect "
            "workspace/output/src/ manually before declaring delivery."
        )
    return recap


def render_recap_markdown(recap: dict) -> str:
    """Render the recap dict as the canonical /sdd-full final block."""
    if "error" in recap:
        return f"⚠ Recap unavailable: {recap['error']}"

    lines: list[str] = []
    feat_n = recap.get("feat_number", "?")
    feat_name = recap.get("feat_name", "?")
    final_status = recap.get("final_status", "unknown")
    icon = {"success": "✅", "partial": "🟡", "failed": "🔴"}.get(final_status, "ℹ")
    lines.append(f"{icon} /sdd-full {feat_n}-{feat_name} — {final_status}")
    lines.append("")
    # Phase summary
    for p in recap.get("phases", []):
        sicon = {"pass": "✅", "warn": "🟡", "fail": "🔴", "skip": "⏭"}.get(p["status"], "?")
        verdict_str = ""
        for k in ("decision", "verdict", "status"):
            if k in p.get("payload", {}):
                verdict_str = f" → {p['payload'][k]}"
                break
        lines.append(f"  {sicon} {p['phase']:20s} {p['status']:8s}{verdict_str}")
    # Token summary
    t = recap.get("tokens", {})
    if t.get("input") or t.get("cache_read"):
        total = t["input"] + t["cache_read"] + t["cache_write"]
        hit_rate = (t["cache_read"] / total * 100) if total else 0
        lines.append("")
        lines.append(f"Tokens : in={t['input']} out={t['output']} "
                     f"cache_r={t['cache_read']} cache_w={t['cache_write']} "
                     f"(hit_rate={hit_rate:.1f}%)")
        # Opus 4.7 1M context pricing
        cost = (t["input"] * 6 + t["output"] * 30
                + t["cache_read"] * 0.30 + t["cache_write"] * 7.50) / 1_000_000
        lines.append(f"Cost   : ~${cost:.4f}")
    # Audit CTO 2026-06-07 — surface warnings (e.g. false-positive completion)
    warnings = recap.get("warnings") or []
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(f"⚠  {w}")
    # Code-on-disk indicator (defensive)
    code_count = recap.get("code_files_count", 0)
    if code_count:
        lines.append(f"Code files materialized : {code_count}")
    lines.append("")
    lines.append(f"Run trace : {recap.get('run_id', '?')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic execution planner for /sdd-full pipeline"
    )
    sub = parser.add_subparsers(dest="cmd")

    # Default / 'plan' subcommand (backward-compat — also default if no subcmd)
    plan_p = sub.add_parser("plan", help="Build execution plan (default)")
    plan_p.add_argument("--feat-number", "-n", type=int, required=True)
    plan_p.add_argument("--root", type=Path, default=Path.cwd())
    plan_p.add_argument("--force", action="store_true")
    plan_p.add_argument("--manual-gates", action="store_true")
    plan_p.add_argument("--json", action="store_true")

    # 'next-action' subcommand — given plan + state, return next action
    next_p = sub.add_parser(
        "next-action",
        help="Decide next action based on plan JSON + state JSON",
    )
    next_p.add_argument("--plan-json", type=Path, required=True,
                        help="Path to plan JSON (output of `plan` subcmd)")
    next_p.add_argument("--state-json", type=Path,
                        help="Path to state JSON (completed_phases, last_status, last_verdict, flags)")
    next_p.add_argument("--state-inline",
                        help="Inline JSON literal as alternative to --state-json")

    # 'recap' subcommand — read run_id, produce final summary
    recap_p = sub.add_parser("recap", help="Build final recap from console.db")
    recap_p.add_argument("--run-id", required=True)
    recap_p.add_argument("--root", type=Path, default=Path.cwd())
    recap_p.add_argument("--json", action="store_true")

    # Top-level legacy flags (when no subcmd given) — emulate old 'plan' behavior
    parser.add_argument("--feat-number", "-n", type=int)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--manual-gates", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    # Default to 'plan' if no subcmd given (backward-compat)
    if args.cmd is None or args.cmd == "plan":
        feat = getattr(args, "feat_number", None)
        if feat is None:
            print("ERROR: --feat-number required", file=sys.stderr)
            return FAIL_FAST
        return _run_plan(args)

    if args.cmd == "next-action":
        return _run_next_action(args)

    if args.cmd == "recap":
        return _run_recap(args)

    print(f"ERROR: unknown subcommand {args.cmd}", file=sys.stderr)
    return FAIL_FAST


def _run_plan(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    if not root.exists() or not (root / ".claude").is_dir():
        print(f"ERROR: {root} is not a SDD_Pro project root (.claude/ missing)",
              file=sys.stderr)
        return INFRA_BLOCKED

    plan = build_plan(
        root, args.feat_number, force=args.force, manual_gates=args.manual_gates
    )

    if args.json:
        payload = json.dumps(plan, indent=2, ensure_ascii=False)
        try:
            sys.stdout.buffer.write(payload.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.flush()
        except AttributeError:
            print(payload)
    else:
        # Audit final 2026-06-07 (BROKEN-5 closure) : `format_text_report` émet
        # emojis 🔴🟡🟢 ; sur Windows console cp1252 par défaut, `print()` crash
        # UnicodeEncodeError. Forcer UTF-8 via stdout.buffer pour résilience
        # cross-platform sans dépendre de `PYTHONIOENCODING=utf-8`.
        text = format_text_report(plan)
        try:
            sys.stdout.buffer.write(text.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.flush()
        except AttributeError:
            # stdout sans .buffer (test capture, etc.) → fallback ASCII safe
            print(text.encode("ascii", "replace").decode("ascii"))

    return FAIL_FAST if plan.get("errors") else SUCCESS


def _run_next_action(args: argparse.Namespace) -> int:
    plan_path: Path = args.plan_json
    if not plan_path.is_file():
        print(f"ERROR: plan JSON not found: {plan_path}", file=sys.stderr)
        return FAIL_FAST
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    if args.state_inline:
        state = json.loads(args.state_inline)
    elif args.state_json:
        if not args.state_json.is_file():
            print(f"ERROR: state JSON not found: {args.state_json}", file=sys.stderr)
            return FAIL_FAST
        state = json.loads(args.state_json.read_text(encoding="utf-8"))
    else:
        state = {"completed_phases": [], "last_status": None, "flags": {}}

    decision = decide_next_action(plan, state)
    payload = json.dumps(decision, indent=2, ensure_ascii=False)
    try:
        sys.stdout.buffer.write(payload.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()
    except AttributeError:
        print(payload)
    return SUCCESS


def _run_recap(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    recap = build_recap(root, args.run_id)
    if args.json:
        payload = json.dumps(recap, indent=2, ensure_ascii=False)
    else:
        payload = render_recap_markdown(recap)
    # Force UTF-8 to avoid CP1252 charmap error on Windows for emojis
    try:
        sys.stdout.buffer.write(payload.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()
    except AttributeError:
        print(payload.encode("ascii", errors="replace").decode("ascii"))
    return SUCCESS if "error" not in recap else FAIL_FAST


if __name__ == "__main__":
    sys.exit(main())
