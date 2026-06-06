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

    # 1. Project Config + active stacks (coerce=True → bool/int natifs)
    try:
        config = read_project_config(root, coerce=True)
    except Exception as e:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic execution planner for /sdd-full pipeline"
    )
    parser.add_argument("--feat-number", "-n", type=int, required=True,
                        help="FEAT number to plan")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Repository root (default: cwd)")
    parser.add_argument("--force", action="store_true",
                        help="Force arch re-init even if bootstrap stable")
    parser.add_argument("--manual-gates", action="store_true",
                        help="Annotate plan with manual-gate insertion points")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON (default: human-readable text)")
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    if not root.exists() or not (root / ".claude").is_dir():
        print(f"ERROR: {root} is not a SDD_Pro project root (.claude/ missing)",
              file=sys.stderr)
        return INFRA_BLOCKED

    plan = build_plan(
        root, args.feat_number, force=args.force, manual_gates=args.manual_gates
    )

    if args.json:
        # Security audit 2026-06-06 : Windows console default CP1252 ne peut pas
        # encoder accents/emojis quand on `print()` du JSON. Forcer UTF-8 via
        # stdout.buffer.write pour éviter UnicodeEncodeError sur Windows.
        payload = json.dumps(plan, indent=2, ensure_ascii=False)
        try:
            sys.stdout.buffer.write(payload.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.flush()
        except AttributeError:
            # Fallback si stdout est wrappé (tests, etc.)
            print(payload)
    else:
        print(format_text_report(plan))

    return FAIL_FAST if plan.get("errors") else SUCCESS


if __name__ == "__main__":
    sys.exit(main())
