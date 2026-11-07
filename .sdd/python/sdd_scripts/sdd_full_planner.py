"""SDD_Pro: deterministic execution planner + runner state machine for /sdd-full.

v7.1 (lot « orchestration mécanique », 2026-11-07) — le planner devient la
**source de vérité mécanique** du pipeline `/sdd-full`. La commande Markdown
n'est plus qu'une boucle courte :

    python sdd_full_planner.py args        --input "{n} --force ..."   # STEP 0
    boucle :
      python sdd_full_planner.py next-action --feat {n} --json
      → exécuter l'action rendue (skill / script / gate / checkpoint)
      python sdd_full_planner.py record      --feat {n} --phase X --status Y
    jusqu'à action ∈ {done, stop}
    python sdd_full_planner.py recap       --run-id R

`next-action` lit l'état RÉEL :
  - console.db : `runs` (run courant de la FEAT), `run_phases` (us_generate,
    readiness, plan, arch, dev_run, qa, sdd_review + phases auxiliaires
    doc_refresh / feat_validate_postdev), `events` (`planner.step` pour les
    étapes hors vocabulaire de `sdd_state.py` : gates manuelles, spec-book) ;
  - disque : FEAT, US présentes, plans présents, rapports
    `workspace/.sys/.validation/{n}-readiness.md` et `{n}-spec-compliance.json`,
    code matérialisé sous `workspace/src/`.

Il renvoie en JSON la prochaine action exacte (commande/agent, arguments,
raison, `record_hint` = commande `record` attendue après exécution). Les
phases `skip` décidées mécaniquement (US déjà présentes, `QAMode: off`,
`--no-validate`, gate plan non déclenchée…) sont **enregistrées par le
planner lui-même** dans `run_phases` (fait déterministe, 0 token) — elles
sont listées dans `auto_recorded`.

`--state-inline` / `--state-json` / `--plan-json` (mode legacy Sprint 2.5)
sont **dépréciés** : conservés pour compat, ignorés dès que `--feat` est
fourni (l'état vient de la base).

Règles load-bearing portées par ce module (ex-STEPs de `sdd-full.md`) :
  - anti-cumul bypass `[FORCE_CUMUL_REJECTED]` (ex-STEP 1.bis / 3.6.quart) —
    via `preflight_force_cumul.evaluate` ;
  - FEAT Flyway (`(?i)flyway` dans le basename) → sentinel
    `flyway-migrate-requested.flag` + `--rebuild-arch` propagé (ex-STEP 2.flyway) ;
  - gates manuelles `afterUS/afterReadiness/afterPlan/afterCode` (ex-STEP
    1.gates / 1.gate-proc) — décision lue dans `workspace/console/status.json`
    via `gate_decide` ;
  - tableau de décision readiness GO/WARN/NO-GO × --force/--plan/
    --no-plan-on-warn/PlanReviewDefault (ex-STEP 3.5) ;
  - plan-then-review `[PLAN_REVIEW_GATE_SKIPPED]` + idempotence mtime plans
    > readiness.md (ex-STEP 3.6) ;
  - audit log `--force` (`workspace/.sys/.audit/force-bypass.log`, ex-STEP 3.7) ;
  - QA bloquante `QaFailOnSddFull` (ex-STEP 4.5), spec-compliance post-dev
    `SpecComplianceRequiredForFeatValidate` (ex-STEP 4.7), review bloquante
    `ReviewFailOnSddFull` + `ReviewMode` (ex-STEP 4.8), drift inline rules
    (ex-STEP 4.9, dans `recap`), cahier des charges best-effort (post-pipeline).

Usage :
    python sdd_full_planner.py args        --input "N [flags]" [--dry-run]
    python sdd_full_planner.py next-action --feat N [--run-id R] [flags] [--json]
    python sdd_full_planner.py record      --feat N --phase P (--status S | --verdict V)
                                           [--payload-json J] [--run-id R]
    python sdd_full_planner.py plan        --feat-number N [--json]      (vue statique)
    python sdd_full_planner.py recap       --run-id R [--json]

Exit codes :
    0 = SUCCESS (lire stdout JSON)
    1 = FAIL_FAST (FEAT introuvable / config invalide / run introuvable)
    3 = INFRA_BLOCKED (workspace ou console.db inaccessible)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.layered_config import ConfigError, read_layered_config  # noqa: E402  (P1-2 fix 2026-06-07)
from sdd_lib.project_config import (  # noqa: E402
    get_active_stack_paths,
    read_project_config,
)
from sdd_lib.console_safe import ensure_console_safe  # noqa: E402
from sdd_lib.paths import audit_dir_path, console_db_path, iso_now_ms, workspace_root  # noqa: E402


# ============================================================================
# Constantes
# ============================================================================

#: Phases canoniques de `sdd_state._PIPELINE_PHASES_ORDER` (SSoT du nommage —
#: ce module ne les redéfinit pas, il les consomme ; validation du nom par
#: `sdd_state.resolve_phase_name` au `record`).
CANONICAL_PHASES: tuple[str, ...] = (
    "us_generate", "readiness", "plan", "arch", "dev_run", "qa", "sdd_review",
)
#: Phases auxiliaires acceptées par `sdd_state.py set-phase`.
AUX_PHASES: tuple[str, ...] = ("doc_refresh", "feat_validate_postdev", "auditor_batch")

#: Étapes hors vocabulaire `sdd_state` — persistées dans `events`
#: (`event_type='planner.step'`, colonne `phase` = id de l'étape).
STEP_EVENT_TYPE = "planner.step"
SPEC_BOOK_STEP = "spec-book"

#: Statuts considérés « terminés » pour une phase (miroir `_RESUME_DONE_STATUSES`).
DONE_STATUSES = frozenset({"pass", "warn", "skip", "success"})

MANUAL_GATE_TOKENS: tuple[str, ...] = ("us", "readiness", "plan", "code")
GATE_PHASE_BY_TOKEN: dict[str, str] = {
    "us": "afterUS", "readiness": "afterReadiness",
    "plan": "afterPlan", "code": "afterCode",
}

#: Plages de progression (output-protocol.md §4) — indicatif pour la ligne chat.
PROGRESS_PCT: dict[str, int] = {
    "us_generate": 8, "readiness": 12, "plan": 15, "dev_run": 22,
    "doc_refresh": 78, "qa": 78, "feat_validate_postdev": 88,
    "sdd_review": 91, SPEC_BOOK_STEP: 99, "done": 100,
    "verify-build": 58, "verify-tests": 86, "record-spec": 90, "record-readiness": 95,
}

#: Gate de livraison (2026-11-07, SSoT `.sdd/docs/delivery-gates.md`) : workflow
#: de `authorize_delivery` porté par ce planner, et étapes de vérification
#: planifiées (seuls producteurs de preuves : verify_build / verify_tests /
#: delivery_gate record-*). Les statuts run_phases ne satisfont JAMAIS une preuve.
DELIVERY_WORKFLOW = "sdd-full"
DELIVERY_STEP_BY_FAMILY: dict[str, str] = {
    "build": "verify-build", "tests": "verify-tests", "coverage": "verify-tests",
    "spec": "record-spec", "readiness": "record-readiness",
}

FLYWAY_RE = re.compile(r"flyway", re.IGNORECASE)
FLYWAY_SENTINEL = "flyway-migrate-requested.flag"

_VERDICT_TO_STATUS: dict[str, str] = {
    "go": "pass", "green": "pass", "pass": "pass", "ok": "pass",
    "warn": "warn", "warning": "warn", "yellow": "warn",
    "no-go": "fail", "nogo": "fail", "red": "fail", "fail": "fail",
    "skip": "skip", "skipped": "skip",
}


# ============================================================================
# Flags /sdd-full (argparse strict — plus d'interprétation LLM)
# ============================================================================

def _build_flags_parser() -> argparse.ArgumentParser:
    """Argparse canonique de la surface `/sdd-full {n} [flags]`.

    Chaque flag documenté dans `commands/sdd-full.md` DOIT apparaître ici
    (smoke `test_cli_flags_declared.py`).
    """
    p = argparse.ArgumentParser(prog="/sdd-full", add_help=False)
    p.add_argument("feat_number", type=int, nargs="?", default=None)
    p.add_argument("--force", action="store_true",
                   help="assume readiness WARN/NO-GO (passe par plan-review)")
    p.add_argument("--plan", action="store_true",
                   help="plan-then-review opt-in même sur GO")
    p.add_argument("--no-plan-on-warn", action="store_true",
                   help="escape hatch : skip plan-review avec --force")
    p.add_argument("--no-validate", action="store_true",
                   help="legacy : bypass complet readiness (audit-loggué)")
    p.add_argument("--rebuild-arch", action="store_true",
                   help="force l'agent arch même si bootstrap stable")
    p.add_argument("--resume", action="store_true",
                   help="reprise après gate validée / crash (état = console.db)")
    p.add_argument("--manual-gates", nargs="?", const="all", default=None,
                   help="active les gates manuelles (toutes, ou liste us,readiness,plan,code)")
    p.add_argument("--no-manual-gates", action="store_true",
                   help="désactive toutes les gates manuelles (override Project Config)")
    return p


def parse_manual_gates_value(raw: str | None) -> list[str] | None:
    """`all` → les 4 ; `us,plan` → liste ; None → None. ValueError sur token inconnu."""
    if raw is None:
        return None
    if raw.strip().lower() in ("all", "true", ""):
        return list(MANUAL_GATE_TOKENS)
    tokens = [t.strip().lower() for t in raw.split(",") if t.strip()]
    bad = [t for t in tokens if t not in MANUAL_GATE_TOKENS]
    if bad:
        raise ValueError(
            f"[INVALID_ARG] --manual-gates : token(s) inconnu(s) {bad} "
            f"(attendu ⊆ {list(MANUAL_GATE_TOKENS)})"
        )
    return tokens


def default_flags() -> dict[str, Any]:
    return {
        "feat_number": None, "force": False, "plan": False,
        "no_plan_on_warn": False, "no_validate": False, "rebuild_arch": False,
        "resume": False, "manual_gates": None, "no_manual_gates": False,
    }


def parse_sdd_full_flags(raw: str) -> dict[str, Any]:
    """Parse « N --force --manual-gates=us,plan » → dict déterministe."""
    tokens = shlex.split(raw or "")
    parser = _build_flags_parser()
    try:
        ns, unknown = parser.parse_known_args(tokens)
    except SystemExit as exc:  # argparse → ValueError (caller décide)
        raise ValueError(f"[INVALID_ARG] argparse error (code {exc.code}) on {raw!r}") from exc
    if unknown:
        raise ValueError(f"[INVALID_ARG] flag(s) inconnu(s) : {unknown}")
    flags = default_flags()
    flags.update({
        "feat_number": ns.feat_number, "force": ns.force, "plan": ns.plan,
        "no_plan_on_warn": ns.no_plan_on_warn, "no_validate": ns.no_validate,
        "rebuild_arch": ns.rebuild_arch, "resume": ns.resume,
        "manual_gates": parse_manual_gates_value(ns.manual_gates),
        "no_manual_gates": ns.no_manual_gates,
    })
    flags["_raw"] = raw
    flags["_parsed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return flags


def args_state_path(root: Path, feat_n: int) -> Path:
    return workspace_root(root) / ".sys" / ".state" / f"sdd-full-{feat_n}.args.json"


def write_args_state(flags: dict[str, Any], root: Path) -> Path:
    n = flags.get("feat_number")
    if n is None:
        raise ValueError("feat_number is None — cannot write state file")
    out = args_state_path(root, int(n))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(flags, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def load_args_state(root: Path, feat_n: int) -> dict[str, Any]:
    """Flags persistés par `args` (STEP 0) — défauts si absent/corrompu."""
    flags = default_flags()
    flags["feat_number"] = feat_n
    p = args_state_path(root, feat_n)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k in flags:
                    if k in data:
                        flags[k] = data[k]
        except (OSError, ValueError):
            pass
    return flags


def active_tags(flags: dict[str, Any]) -> list[str]:
    """Tags csv pour `sdd_state.py new-run --tags` (ex-STEP 1.ter)."""
    tags: list[str] = []
    for key, tag in (("force", "force"), ("plan", "plan"),
                     ("no_plan_on_warn", "no-plan-on-warn"),
                     ("no_validate", "no-validate"), ("rebuild_arch", "rebuild-arch"),
                     ("resume", "resume"), ("no_manual_gates", "no-manual-gates")):
        if flags.get(key):
            tags.append(tag)
    if flags.get("manual_gates"):
        tags.append("manual-gates")
    return tags


# ============================================================================
# Helpers disque (déterministes)
# ============================================================================


def _find_feat(root: Path, feat_n: int) -> Path | None:
    """Locate workspace/feats/{n}-*.md (None si 0 ou > 1 — cf. `_find_feats`)."""
    matches = _find_feats(root, feat_n)
    return matches[0] if len(matches) == 1 else None


def _find_feats(root: Path, feat_n: int) -> list[Path]:
    feats_dir = workspace_root(root) / "feats"
    if not feats_dir.is_dir():
        return []
    return sorted(
        f for f in feats_dir.iterdir()
        if f.is_file() and f.name.startswith(f"{feat_n}-") and f.suffix == ".md"
    )


def _list_us_files(root: Path, feat_n: int) -> list[Path]:
    """List workspace/us/{n}-*-*.md (in basename order)."""
    us_dir = workspace_root(root) / "us"
    if not us_dir.is_dir():
        return []
    return sorted(
        f
        for f in us_dir.iterdir()
        if f.is_file() and f.name.startswith(f"{feat_n}-") and f.suffix == ".md"
    )


def _list_plan_files(root: Path, feat_n: int) -> list[Path]:
    plans_dir = workspace_root(root) / "plans"
    if not plans_dir.is_dir():
        return []
    return sorted(
        f for f in plans_dir.iterdir()
        if f.is_file() and f.name.startswith(f"{feat_n}-")
        and (f.name.endswith(".back.md") or f.name.endswith(".front.md"))
    )


def _detect_appType(root: Path) -> str:
    """Inspect active stacks to decide appType (desktop/mobiles = client)."""
    paths = [p.replace("\\", "/") for p in get_active_stack_paths(root)]
    has_backend = any("stacks/backend/" in p for p in paths)
    has_frontend = any("stacks/frontend/" in p for p in paths)
    has_fullstack = any("stacks/fullstack/" in p for p in paths)
    has_client = any("stacks/mobiles/" in p or "stacks/desktop/" in p for p in paths)
    if has_fullstack:
        return "fullstack"
    if has_backend and (has_frontend or has_client):
        return "back-front"
    if has_backend:
        return "back-only"
    if has_frontend or has_client:
        return "front-only"
    return "unknown"


def _arch_seems_stable(root: Path, feat_n: int) -> bool:
    """Detect a stable bootstrap state (cf. dev-run.md STEP 4.bis).

    Heuristic : true iff workspace/src/ contient au moins un projet
    bootstrapé et feat_n != 1. Le verdict fin reste celui de
    `detect_arch_shortcircuit.py`, exécuté par `/dev-run` lui-même.
    """
    if feat_n == 1:
        return False
    src_dir = workspace_root(root) / "src"
    if not src_dir.is_dir():
        return False
    manifests = (
        list(src_dir.glob("*/*.csproj"))
        + list(src_dir.glob("*/package.json"))
        + list(src_dir.glob("*/pyproject.toml"))
        + list(src_dir.glob("*/build.gradle.kts"))
        + list(src_dir.glob("*/CMakeLists.txt"))
    )
    return len(manifests) > 0


def is_flyway_feat(feat_path: Path | None) -> bool:
    return bool(feat_path) and bool(FLYWAY_RE.search(feat_path.stem))


def _read_readiness_report(root: Path, feat_n: int) -> dict[str, Any]:
    """`workspace/.sys/.validation/{n}-readiness.md` → {decision, mtime, path}."""
    report = workspace_root(root) / ".sys" / ".validation" / f"{feat_n}-readiness.md"
    out: dict[str, Any] = {"present": False, "decision": None, "mtime": None,
                           "path": str(report)}
    if not report.is_file():
        return out
    out["present"] = True
    try:
        out["mtime"] = report.stat().st_mtime
        text = report.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    m = re.search(r"[Dd][ée]cision[^:\n]*:\s*\**\s*(?:🟢|🟡|🔴)?\s*(GO|WARN|NO-GO)\b", text)
    if m:
        out["decision"] = m.group(1).upper()
    return out


def _read_spec_report(root: Path, feat_n: int) -> dict[str, Any]:
    report = workspace_root(root) / ".sys" / ".validation" / f"{feat_n}-spec-compliance.json"
    out: dict[str, Any] = {"present": False, "verdict": None, "path": str(report)}
    if not report.is_file():
        return out
    out["present"] = True
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    summary = data.get("summary") if isinstance(data, dict) else None
    raw = ""
    if isinstance(summary, dict):
        raw = str(summary.get("verdict") or "")
    if not raw and isinstance(data, dict):
        raw = str(data.get("verdict") or "")
    v = raw.strip().lower()
    if "red" in v or "\U0001f534" in v:
        out["verdict"] = "RED"
    elif "warn" in v or "yellow" in v or "\U0001f7e1" in v:
        out["verdict"] = "YELLOW"
    elif "green" in v or "\U0001f7e2" in v:
        out["verdict"] = "GREEN"
    return out


def _read_config(root: Path) -> tuple[dict[str, Any], dict | None]:
    """Layered config (base ← team ← project) avec fallback legacy.

    Returns (config, error_dict|None).
    """
    try:
        return read_layered_config(root=root, coerce=True), None
    except ConfigError:
        raise  # [CONFIG_SECURITY_DOWNGRADE] — jamais avalé
    except Exception as e:  # noqa: BLE001 — greenfield sans config.base.yml
        try:
            return read_project_config(root, coerce=True), None
        except Exception:  # noqa: BLE001
            return {}, {"code": "PROJECT_CONFIG_INVALID", "message": str(e)}


def _as_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def _as_mode(value: Any, default: str) -> str:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower()


# ============================================================================
# Plan statique (subcommand `plan` — vue, backward-compat)
# ============================================================================


def build_plan(
    root: Path, feat_n: int, *, force: bool = False, manual_gates: bool = False
) -> dict:
    """Build the JSON execution plan for /sdd-full {feat_n} (vue statique)."""
    plan: dict = {
        "feat_number": feat_n,
        "phases": [],
        "warnings": [],
        "errors": [],
    }

    # 0. FEAT lookup
    feats = _find_feats(root, feat_n)
    if not feats:
        plan["errors"].append(
            {"code": "FEAT_NOT_FOUND", "message": f"workspace/feats/{feat_n}-*.md missing"}
        )
        return plan
    if len(feats) > 1:
        plan["errors"].append(
            {"code": "FEAT_AMBIGUOUS",
             "message": f"{len(feats)} fichiers matchent workspace/feats/{feat_n}-*.md"}
        )
        return plan
    feat_path = feats[0]
    plan["feat_path"] = str(feat_path.relative_to(root))
    plan["flyway"] = is_flyway_feat(feat_path)

    # 1. Project Config + active stacks via layered config (base ← team ← project)
    config, cfg_err = _read_config(root)
    if cfg_err:
        plan["errors"].append(cfg_err)
        return plan

    gated_raw = config.get("GatedWorkflow", True)
    plan["project_config"] = {
        "AppName": config.get("AppName"),
        "BackendName": config.get("BackendName"),
        "MaxParallel": int(config.get("MaxParallel", 3) or 3),
        "GatedWorkflow": gated_raw if isinstance(gated_raw, bool) else str(gated_raw).lower() != "false",
        "CoverageMin": int(config.get("CoverageMin", 80) or 80),
        "QAMode": config.get("QAMode", "tests+coverage"),
        "ReviewMode": _as_mode(config.get("ReviewMode"), "full"),
        "PlanReviewDefault": _as_bool(config.get("PlanReviewDefault"), False),
    }
    plan["app_type"] = _detect_appType(root)
    plan["active_stacks"] = get_active_stack_paths(root)

    # 1.bis Stack coherence validation (SSoT 2026-06-06 R3)
    try:
        from sdd_lib.stack_validator import validate_active_stacks_coherence
        stacks_by_cat: dict[str, str | None] = {
            "backend": None, "frontend": None, "ui": None, "auth": None,
            "fullstack": None, "mobiles": None, "desktop": None,
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
    if us_files:
        plan["phases"].append({
            "id": "us-generate", "label": "PO → User Stories",
            "status": "skip", "reason": f"{len(us_files)} US already present",
        })
    else:
        plan["phases"].append({
            "id": "us-generate", "label": "PO → User Stories",
            "status": "pending", "agent": "po",
        })

    plan["phases"].append({
        "id": "feat-validate", "label": "Readiness gate (deterministic)",
        "status": "pending", "script": ".sdd/python/sdd_scripts/validate_readiness.py",
    })

    if _arch_seems_stable(root, feat_n) and not force and not plan["flyway"]:
        plan["phases"].append({
            "id": "arch-init", "label": "Arch bootstrap + DB scaffold",
            "status": "skip", "reason": "bootstrap stable (use --rebuild-arch to force)",
        })
    else:
        plan["phases"].append({
            "id": "arch-init", "label": "Arch bootstrap + DB scaffold",
            "status": "pending", "agent": "arch",
        })

    has_backend = plan["app_type"] in ("back-front", "back-only", "fullstack")
    has_frontend = plan["app_type"] in ("back-front", "front-only", "fullstack")
    if has_backend:
        plan["phases"].append({
            "id": "dev-backend",
            "label": f"dev-backend (×{len(us_files)} US, parallel max={plan['project_config']['MaxParallel']})",
            "status": "pending" if us_files else "skip",
            "agent": "dev-backend",
            "us_targets": [Path(p).stem for p in plan["us_files"]],
            "max_parallel": plan["project_config"]["MaxParallel"],
        })
    else:
        plan["phases"].append({
            "id": "dev-backend", "label": "dev-backend", "status": "skip",
            "reason": f"app_type={plan['app_type']} has no backend",
        })

    if plan["project_config"]["GatedWorkflow"] and has_backend and us_files:
        plan["phases"].append({
            "id": "qa-api-gate", "label": "QA API Gate (in-memory)",
            "status": "pending", "blocking": True,
            "blocking_statuses": ["FAIL", "INFRA_BLOCKED"],
        })
    else:
        plan["phases"].append({
            "id": "qa-api-gate", "label": "QA API Gate", "status": "skip",
            "reason": ("GatedWorkflow=false" if not plan["project_config"]["GatedWorkflow"]
                       else "no backend or no US"),
        })

    if has_frontend:
        plan["phases"].append({
            "id": "dev-frontend",
            "label": f"dev-frontend (×{len(us_files)} US, parallel max={plan['project_config']['MaxParallel']})",
            "status": "pending" if us_files else "skip",
            "agent": "dev-frontend",
            "us_targets": [Path(p).stem for p in plan["us_files"]],
            "max_parallel": plan["project_config"]["MaxParallel"],
        })
    else:
        plan["phases"].append({
            "id": "dev-frontend", "label": "dev-frontend", "status": "skip",
            "reason": f"app_type={plan['app_type']} has no frontend",
        })

    qa_mode = plan["project_config"]["QAMode"]
    if qa_mode in {"off", "manual"}:
        plan["phases"].append({
            "id": "qa-generate", "label": "QA tests + coverage + quality",
            "status": "skip", "reason": f"QAMode={qa_mode}",
        })
    else:
        plan["phases"].append({
            "id": "qa-generate", "label": "QA tests + coverage + quality",
            "status": "pending", "agent": "qa",
            "coverage_min": plan["project_config"]["CoverageMin"],
        })

    review_mode = plan["project_config"]["ReviewMode"]
    if review_mode in {"off", "manual"}:
        plan["phases"].append({
            "id": "sdd-review", "label": "Consolidated review",
            "status": "skip", "reason": f"ReviewMode={review_mode}",
        })
    else:
        plan["phases"].append({
            "id": "sdd-review", "label": "Consolidated review (5 reviewers aggregated)",
            "status": "pending", "script": ".sdd/python/sdd_scripts/sdd_review.py",
        })

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


# ============================================================================
# Legacy next-action (Sprint 2.5 — déprécié, conservé pour compat)
# ============================================================================


PHASE_SKILL_MAP: dict[str, tuple[str, str]] = {
    "us-generate":    ("us-generate",    "PO découpe FEAT en User Stories"),
    "feat-validate":  ("feat-validate",  "Readiness gate (déterministe)"),
    "arch-init":      ("arch-init",      "Arch bootstrap + DB scaffold"),
    "dev-backend":    ("dev-run",        "dev-backend ALL US (inclus dans /dev-run)"),
    "qa-api-gate":    ("dev-run",        "QA API Gate (inclus dans /dev-run)"),
    "dev-frontend":   ("dev-run",        "dev-frontend ALL US (inclus dans /dev-run)"),
    "qa-generate":    ("qa-generate",    "QA tests + coverage + quality"),
    "sdd-review":     ("sdd-review",     "Consolidated review"),
}

DEV_RUN_PHASES = {"dev-backend", "qa-api-gate", "dev-frontend"}


def decide_next_action(plan: dict, state: dict) -> dict:
    """[DEPRECATED Sprint 2.5] plan + état inline → prochaine action.

    Conservé pour compat (`--plan-json` + `--state-inline`). Le chemin
    nominal est `compute_next_action()` (état lu dans console.db).
    """
    completed = set(state.get("completed_phases", []))
    last_status = state.get("last_status")
    last_verdict = state.get("last_verdict")
    flags = state.get("flags", {})

    def _stop(reason: str, phase_id: str | None = None) -> dict:
        return {"action": "stop", "phase_id": phase_id, "skill": None,
                "script": None, "args": None, "reason": reason}

    if last_status == "fail":
        return _stop(f"Previous phase failed (status={last_status})")

    if "feat-validate" in completed and last_verdict in ("WARN", "NO-GO"):
        force = bool(flags.get("force"))
        if last_verdict == "NO-GO" and not force:
            return _stop("Readiness NO-GO without --force, pipeline halted")
        if last_verdict == "WARN" and not force:
            return _stop("Readiness WARN without --force (strict mode), pipeline halted")

    for phase in plan.get("phases", []):
        phase_id = phase["id"]
        if phase_id in completed:
            continue
        status = phase["status"]
        if status == "skip":
            return {"action": "skip", "phase_id": phase_id, "skill": None,
                    "script": None, "args": None,
                    "reason": phase.get("reason", "phase skipped per plan")}
        if status == "blocked":
            return _stop(phase.get("reason", "phase blocked"), phase_id)
        if status == "pending":
            if phase.get("script"):
                return {"action": "script", "phase_id": phase_id, "skill": None,
                        "script": phase["script"],
                        "args": ["--feat-number", str(plan["feat_number"])],
                        "reason": f"Run deterministic script for {phase_id}"}
            if phase_id in DEV_RUN_PHASES:
                return {"action": "skill", "phase_id": phase_id, "skill": "/dev-run",
                        "script": None, "args": [str(plan["feat_number"])],
                        "covers_phases": ["dev-backend", "qa-api-gate", "dev-frontend"],
                        "reason": f"Dispatch /dev-run for {phase_id} (covers all dev-* phases)"}
            skill_name, label = PHASE_SKILL_MAP.get(
                phase_id, (phase_id, phase.get("label", phase_id))
            )
            return {"action": "skill", "phase_id": phase_id, "skill": f"/{skill_name}",
                    "script": None, "args": [str(plan["feat_number"])],
                    "reason": f"Dispatch /{skill_name}: {label}"}

    return {"action": "done", "phase_id": None, "skill": None, "script": None,
            "args": None, "reason": "All phases completed"}


# ============================================================================
# État réel : console.db + disque
# ============================================================================


class StateUnavailable(RuntimeError):
    """console.db présente mais illisible → `[INFRA_BLOCKED]`."""


def _db_path(root: Path) -> Path:
    """console.db — `$SDD_CONSOLE_DB_PATH` gagne (géré par `sdd_lib.paths`)."""
    return console_db_path(root)


def _ro_conn(db_path: Path) -> sqlite3.Connection:
    uri = f"{db_path.as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def resolve_run_id(root: Path, feat_n: int, explicit: str | None = None) -> str | None:
    """`--run-id` > `$SDD_RUN_ID` > dernier run `running` de la FEAT > None."""
    if explicit and explicit.strip():
        return explicit.strip()
    env_id = (os.environ.get("SDD_RUN_ID") or "").strip()
    if env_id:
        return env_id
    db_path = _db_path(root)
    if not db_path.is_file():
        return None
    try:
        conn = _ro_conn(db_path)
    except sqlite3.Error as exc:
        raise StateUnavailable(f"console.db illisible : {exc}") from exc
    try:
        row = conn.execute(
            "SELECT run_id FROM runs WHERE feat_n = ? AND status = 'running' "
            "ORDER BY started_at DESC LIMIT 1",
            (feat_n,),
        ).fetchone()
        return row["run_id"] if row else None
    except sqlite3.Error as exc:
        raise StateUnavailable(f"console.db illisible : {exc}") from exc
    finally:
        conn.close()


def read_db_state(root: Path, feat_n: int, run_id: str | None) -> dict[str, Any]:
    """{run, phases{name:{status,payload,ended_at}}, steps{id:status}, db_present}."""
    state: dict[str, Any] = {"run": None, "phases": {}, "steps": {},
                             "db_present": False, "run_id": run_id}
    db_path = _db_path(root)
    if not db_path.is_file():
        return state
    state["db_present"] = True
    if not run_id:
        return state
    try:
        conn = _ro_conn(db_path)
    except sqlite3.Error as exc:
        raise StateUnavailable(f"console.db illisible : {exc}") from exc
    try:
        run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is not None:
            state["run"] = dict(run)
        for r in conn.execute(
            "SELECT phase, status, payload_json, ended_at FROM run_phases "
            "WHERE run_id = ? ORDER BY id", (run_id,),
        ).fetchall():
            payload: Any = {}
            if r["payload_json"]:
                try:
                    payload = json.loads(r["payload_json"])
                except ValueError:
                    payload = {}
            state["phases"][r["phase"]] = {
                "status": (r["status"] or "").lower(),
                "payload": payload if isinstance(payload, dict) else {},
                "ended_at": r["ended_at"],
            }
        for r in conn.execute(
            "SELECT phase, payload_json FROM events "
            "WHERE run_id = ? AND event_type = ? ORDER BY id",
            (run_id, STEP_EVENT_TYPE),
        ).fetchall():
            status = None
            if r["payload_json"]:
                try:
                    status = (json.loads(r["payload_json"]) or {}).get("status")
                except ValueError:
                    status = None
            state["steps"][r["phase"]] = (status or "pass").lower()
    except sqlite3.Error as exc:
        raise StateUnavailable(f"console.db illisible : {exc}") from exc
    finally:
        conn.close()
    return state


def resolve_manual_gates(flags: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """ex-STEP 1.gates : CLI > Project Config `ManualGates`."""
    if flags.get("no_manual_gates"):
        return []
    if flags.get("manual_gates"):
        return list(flags["manual_gates"])
    raw = config.get("ManualGates")
    if raw is None or raw == "":
        return []
    if isinstance(raw, bool):
        return list(MANUAL_GATE_TOKENS) if raw else []
    text = str(raw).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return list(MANUAL_GATE_TOKENS)
    if text in ("false", "0", "no", "off"):
        return []
    return parse_manual_gates_value(text)


def read_gate_decision(root: Path, feat_n: int, gate_phase: str) -> str:
    """Décision de gate : console.db `gates` (si l'API existe) > status.json.

    → pending|validated|skipped|none.
    """
    try:  # lot « fiabilité des états » : gates persistées en base
        from sdd_lib.console_db import get_latest_gate  # type: ignore[attr-defined]
        db_path = _db_path(root)
        if db_path.is_file():
            conn = _ro_conn(db_path)
            try:
                gate = get_latest_gate(conn, feat_n=feat_n, gate_name=gate_phase)
            finally:
                conn.close()
            if gate:
                d = str(gate.get("decision") or "none").lower()
                if d in ("pending", "validated", "skipped"):
                    return d
    except (ImportError, sqlite3.Error):
        pass
    try:
        from sdd_scripts.gate_decide import get_gate, read_status
    except ImportError:
        return "none"
    status_file = workspace_root(root) / "console" / "status.json"
    try:
        status = read_status(status_file)
    except Exception:  # noqa: BLE001 — JSON corrompu = gate non tranchée
        return "none"
    gate = get_gate(status, str(feat_n), gate_phase)
    if not gate:
        return "none"
    decision = str(gate.get("decision") or "none").lower()
    return decision if decision in ("pending", "validated", "skipped") else "none"


def collect_context(root: Path, feat_n: int, flags: dict[str, Any],
                    run_id: str | None = None) -> dict[str, Any]:
    """Agrège disque + config + console.db en un contexte de décision."""
    ctx: dict[str, Any] = {"feat_number": feat_n, "errors": [], "flags": flags}
    feats = _find_feats(root, feat_n)
    if not feats:
        ctx["errors"].append({"code": "FEAT_NOT_FOUND",
                              "message": f"workspace/feats/{feat_n}-*.md missing"})
        return ctx
    if len(feats) > 1:
        ctx["errors"].append({"code": "FEAT_AMBIGUOUS",
                              "message": f"{len(feats)} fichiers matchent workspace/feats/{feat_n}-*.md"})
        return ctx
    feat_path = feats[0]
    ctx["feat_path"] = str(feat_path.relative_to(root))
    ctx["feat_name"] = feat_path.stem.split("-", 1)[1] if "-" in feat_path.stem else feat_path.stem
    ctx["flyway"] = is_flyway_feat(feat_path)

    config, cfg_err = _read_config(root)
    if cfg_err:
        ctx["errors"].append(cfg_err)
        return ctx
    ctx["config"] = {
        "PlanReviewDefault": _as_bool(config.get("PlanReviewDefault"), False),
        "QAMode": _as_mode(config.get("QAMode"), "manual"),
        "QaFailOnSddFull": _as_bool(config.get("QaFailOnSddFull"), True),
        "ReviewMode": _as_mode(config.get("ReviewMode"), "full"),
        "ReviewFailOnSddFull": _as_bool(config.get("ReviewFailOnSddFull"), True),
        "SpecComplianceRequiredForFeatValidate": _as_bool(
            config.get("SpecComplianceRequiredForFeatValidate"), True),
        "MaxParallel": int(config.get("MaxParallel", 3) or 3),
    }
    ctx["manual_gates"] = resolve_manual_gates(flags, config)
    ctx["app_type"] = _detect_appType(root)
    ctx["us_files"] = [f.name for f in _list_us_files(root, feat_n)]
    plan_files = _list_plan_files(root, feat_n)
    ctx["plan_files"] = [f.name for f in plan_files]
    ctx["plans_mtime"] = max((f.stat().st_mtime for f in plan_files), default=None)
    ctx["readiness_report"] = _read_readiness_report(root, feat_n)
    ctx["spec_report"] = _read_spec_report(root, feat_n)
    ctx["code_files_count"] = _count_code_files(root)

    rid = resolve_run_id(root, feat_n, run_id)
    ctx.update(read_db_state(root, feat_n, rid))
    return ctx


# ============================================================================
# Enregistrement (subcommand `record`) — miroir de `sdd_state.py set-phase`
# ============================================================================


def status_from_verdict(phase: str, verdict: str, config: dict[str, Any]) -> str:
    """Verdict métier → statut run_phases, en appliquant les gates Project Config.

    - readiness : GO→pass, WARN→warn, NO-GO→fail
    - qa : RED→fail si `QaFailOnSddFull` sinon warn (bypass audit-loggué)
    - sdd_review : RED→fail si `ReviewFailOnSddFull` sinon warn
    - autres : GREEN/PASS→pass, YELLOW/WARN→warn, RED/FAIL→fail
    """
    v = (verdict or "").strip().lower()
    base = _VERDICT_TO_STATUS.get(v)
    if base is None:
        raise ValueError(f"[INVALID_ARG] verdict inconnu {verdict!r}")
    if base == "fail":
        if phase == "qa" and not config.get("QaFailOnSddFull", True):
            return "warn"
        if phase == "sdd_review" and not config.get("ReviewFailOnSddFull", True):
            return "warn"
    return base


def _append_audit_line(root: Path, filename: str, line: str) -> None:
    audit_dir = audit_dir_path(root)
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
        with open(audit_dir / filename, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")
    except OSError:
        pass  # best-effort : l'audit log ne bloque jamais le pipeline


def record_phase(root: Path, run_id: str, phase: str, status: str,
                 payload: dict[str, Any] | None = None) -> None:
    """Upsert `run_phases` + `events.phase.end` + `runs.current_phase` (comme sdd_state)."""
    from sdd_lib.console_db import (connect, ensure_initialized, get_run,
                                    insert_event, upsert_run, upsert_run_phase)
    db_path = _db_path(root)
    ensure_initialized(db_path)
    now = iso_now_ms()
    with connect(db_path) as conn:
        row = get_run(conn, run_id)
        if row is None:
            raise LookupError(f"run_id {run_id!r} inconnu dans console.db")
        existing = conn.execute(
            "SELECT started_at FROM run_phases WHERE run_id = ? AND phase = ?",
            (run_id, phase),
        ).fetchone()
        started_fallback = now if (existing is None or not existing["started_at"]) else None
        upsert_run_phase(conn, run_id=run_id, phase=phase, status=status,
                         started_at=started_fallback, ended_at=now, payload=payload)
        upsert_run(conn, run_id=run_id, command=row["command"],
                   current_phase=phase, status=row["status"])
        evt: dict[str, Any] = {"status": status, "by": "sdd_full_planner"}
        if payload:
            evt["payload"] = payload
        insert_event(conn, event_type="phase.end", ts=now, run_id=run_id,
                     feat_n=row["feat_n"], phase=phase, payload=evt)


def record_step(root: Path, run_id: str, step: str, status: str,
                payload: dict[str, Any] | None = None) -> None:
    """Étape hors vocabulaire sdd_state → `events(planner.step)`."""
    from sdd_lib.console_db import connect, ensure_initialized, get_run, insert_event
    db_path = _db_path(root)
    ensure_initialized(db_path)
    with connect(db_path) as conn:
        row = get_run(conn, run_id)
        if row is None:
            raise LookupError(f"run_id {run_id!r} inconnu dans console.db")
        evt: dict[str, Any] = {"status": status, "by": "sdd_full_planner"}
        if payload:
            evt["payload"] = payload
        insert_event(conn, event_type=STEP_EVENT_TYPE, run_id=run_id,
                     feat_n=row["feat_n"], phase=step, payload=evt)


# ============================================================================
# Moteur next-action (état réel)
# ============================================================================


def _action(kind: str, **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "action": kind, "phase_id": None, "run_phase": None, "skill": None,
        "script": None, "args": [], "command": None, "reason": "",
        "record_hint": None, "progress_pct": None, "resumable": False,
    }
    base.update(fields)
    return base


def _close_cmd(run_id: str | None, status: str, error: str | None = None) -> str | None:
    """Commande de clôture explicite du run (`run_close.py`, idempotent)."""
    if not run_id:
        return None
    cmd = (f"python .sdd/python/sdd_scripts/run_close.py --run-id {run_id} "
           f"--status {status}")
    if error:
        cmd += f" --error \"{error}\""
    return cmd


def _planner_cmd(feat_n: int) -> str:
    return f"python .sdd/python/sdd_scripts/sdd_full_planner.py record --feat {feat_n}"


def _hint(feat_n: int, phase: str, statuses: str, *, verdict: bool = False) -> str:
    sel = "--verdict {GO|WARN|NO-GO}" if phase == "readiness" else (
        "--verdict {GREEN|YELLOW|RED}" if verdict else f"--status {{{statuses}}}")
    return f"{_planner_cmd(feat_n)} --phase {phase} {sel} [--payload-json '{{...}}']"


def _phase_status(ctx: dict[str, Any], phase: str) -> str | None:
    p = ctx.get("phases", {}).get(phase)
    return p["status"] if p else None


def _phase_done(ctx: dict[str, Any], phase: str) -> bool:
    return (_phase_status(ctx, phase) or "") in DONE_STATUSES


def _readiness_decision(ctx: dict[str, Any]) -> str | None:
    """Décision readiness : payload run_phases > rapport disque > statut."""
    p = ctx.get("phases", {}).get("readiness")
    if p:
        d = str(p.get("payload", {}).get("decision") or "").upper()
        if d in ("GO", "WARN", "NO-GO"):
            return d
        if p["status"] == "skip":
            return "GO"
        return {"pass": "GO", "warn": "WARN", "fail": "NO-GO"}.get(p["status"])
    return ctx.get("readiness_report", {}).get("decision")


def _plan_trigger(ctx: dict[str, Any], decision: str | None) -> tuple[bool, str]:
    """ex-STEP 3.5 tableau de décision → (déclencheur plan-review, raison)."""
    flags = ctx["flags"]
    if decision in ("WARN", "NO-GO"):
        if flags.get("force") and not flags.get("no_plan_on_warn"):
            return True, f"readiness {decision} assumé via --force → plan-review obligatoire"
        return False, "escape hatch --no-plan-on-warn" if flags.get("force") else "readiness bloquante"
    if flags.get("plan"):
        return True, "--plan (opt-in)"
    if ctx["config"]["PlanReviewDefault"]:
        return True, "PlanReviewDefault: true (Project Config)"
    return False, "GO sans --plan ni PlanReviewDefault"


def _plans_fresh(ctx: dict[str, Any]) -> bool:
    """ex-STEP 3.6.a : ≥ 1 plan ET mtime > mtime readiness.md → déjà reviewés."""
    if not ctx.get("plan_files"):
        return False
    rm = ctx.get("readiness_report", {}).get("mtime")
    pm = ctx.get("plans_mtime")
    if rm is None:
        return True  # pas de rapport (--no-validate) : les plans présents font foi
    return bool(pm and pm > rm)


def _gate_action(ctx: dict[str, Any], token: str, label_from: str, label_to: str,
                 recorder: Any) -> dict[str, Any] | None:
    """ex-STEP 1.gate-proc : None si la gate est passée, sinon action gate/stop."""
    if token not in ctx.get("manual_gates", []):
        return None
    feat_n = ctx["feat_number"]
    gate_phase = GATE_PHASE_BY_TOKEN[token]
    decision = read_gate_decision(ctx["_root"], feat_n, gate_phase)
    if decision in ("validated", "skipped"):
        return None
    base = {
        "phase_id": f"gate-{gate_phase}", "gate": gate_phase,
        "label_from": label_from, "label_to": label_to,
        "progress_pct": PROGRESS_PCT.get({"us": "us_generate", "readiness": "readiness",
                                          "plan": "plan", "code": "doc_refresh"}[token]),
    }
    if decision == "pending":
        return _action(
            "stop", resumable=True, gate_decision="pending",
            reason=(f"gate {gate_phase} en attente de validation humaine — ouvrir la "
                    f"console (http://127.0.0.1:5173) puis `/sdd-full {feat_n} --resume`"),
            chat=f"🟡 /sdd-full {feat_n} — gate {gate_phase} en attente", **base,
        )
    return _action(
        "gate", gate_decision="none",
        reason=f"gate manuelle {gate_phase} ({label_from} → {label_to}) non tranchée",
        options={
            "validate": (f"python .sdd/python/sdd_scripts/gate_decide.py pose-pending "
                         f"--feat-num {feat_n} --phase {gate_phase}  # puis STOP"),
            "continue": (f"python .sdd/python/sdd_scripts/gate_decide.py set --feat-num {feat_n} "
                         f"--phase {gate_phase} --decision skipped --answered-by \"$SDD_USER_EMAIL\""),
        },
        **base,
    )


def _delivery_command(family: str, feat_n: int, run_id: str | None) -> tuple[str, list[str]]:
    """(script, args) de l'unique producteur légitime d'une preuve."""
    rid = ["--run-id", run_id] if run_id else []
    if family == "build":
        return ".sdd/python/sdd_scripts/verify_build.py", ["--feat-number", str(feat_n), *rid]
    if family in ("tests", "coverage"):
        return (".sdd/python/sdd_scripts/verify_tests.py",
                ["--feat-number", str(feat_n), *rid, "--coverage"])
    if family == "spec":
        return (".sdd/python/sdd_scripts/delivery_gate.py",
                ["record-spec", "--feat-number", str(feat_n), "--report",
                 f"workspace/.sys/.validation/{feat_n}-spec-compliance.json", *rid])
    return (".sdd/python/sdd_scripts/delivery_gate.py",
            ["record-readiness", "--feat-number", str(feat_n), *rid])


def delivery_evidence_action(ctx: dict[str, Any], decision: Any,
                             families: tuple[str, ...]) -> dict[str, Any] | None:
    """Action requise pour les familles de preuve `families`, ou None si prouvées.

    Seule la preuve (`authorize_delivery`) compte : un `run_phases` pass/warn,
    un payload `buildVerified`/`executed` ou un `--resume` ne la remplacent
    jamais — preuve absente ou périmée (arbre modifié) → la vérification est
    (re)planifiée ; preuve en échec → STOP `[DELIVERY_GATE_BLOCKED]`.
    """
    from sdd_lib.delivery_wiring import BLOCKED_CLASS, family_state
    feat_n = ctx["feat_number"]
    rid = ctx.get("run_id")
    flags = ctx["flags"]
    for family in families:
        state = family_state(decision, family)
        if state in ("ok", "not_required"):
            continue
        step_id = DELIVERY_STEP_BY_FAMILY[family]
        script, args = _delivery_command(family, feat_n, rid)
        command = "python " + " ".join([script, *args])
        no_validate = family == "readiness" and bool(flags.get("no_validate"))
        if state == "failed" or no_validate or ctx.get("steps", {}).get(step_id) == "fail":
            if no_validate:
                why = "--no-validate : la readiness est une preuve requise de /sdd-full"
                fix = f"relancer /sdd-full {feat_n} sans --no-validate"
            else:
                why = (f"preuve {family} en échec" if state == "failed"
                       else f"preuve {family} non produite (étape {step_id} en échec)")
                fix = (f"corriger la cause réelle puis `{command}` et /sdd-full {feat_n} "
                       f"--resume")
            if flags.get("force"):
                _append_audit_line(
                    ctx["_root"], "force-bypass.log",
                    f"{iso_now_ms()} /sdd-full {feat_n} --force SANS EFFET sur le gate de "
                    f"livraison ({family}: {state}) run={rid}")
            return _action(
                "stop", phase_id=step_id, run_phase=None, error=BLOCKED_CLASS,
                reason=f"livraison refusée — {why} ; {decision.summary()}",
                fix=fix + " ; aucun flag (--force, WARN, --resume) ne lève ce gate",
                delivery_gate=decision.to_dict(), final_status="failed",
                progress_pct=PROGRESS_PCT.get(step_id),
            )
        return _action(
            "script", phase_id=step_id, run_phase=None, script=script, args=args,
            command=command,
            reason=(f"preuve {family} {state} pour l'arbre courant — vérification RÉELLE "
                    f"exigée (statuts run_phases non probants)"),
            exit_map={"0": "pass", "2": f"fail {BLOCKED_CLASS}"},
            env={"SDD_RUN_ID": rid} if rid else {},
            record_hint=f"{_planner_cmd(feat_n)} --step {step_id} --status {{pass|fail}}",
            delivery_gate=decision.to_dict(), blocking=True,
            progress_pct=PROGRESS_PCT.get(step_id),
        )
    return None


def compute_next_action(root: Path, feat_n: int, flags: dict[str, Any], *,
                        run_id: str | None = None, persist: bool = True) -> dict[str, Any]:
    """Décide la prochaine action depuis l'état réel (console.db + disque).

    `persist=True` : les phases skip décidées mécaniquement sont écrites dans
    `run_phases` (si un run est connu) — listées dans `auto_recorded`.
    """
    try:
        ctx = collect_context(root, feat_n, flags, run_id)
    except StateUnavailable as exc:
        return _action("stop", error="[INFRA_BLOCKED]", reason=str(exc))
    ctx["_root"] = root
    auto_recorded: list[dict[str, Any]] = []
    rid = ctx.get("run_id")

    def recorder(phase: str, status: str, payload: dict[str, Any] | None = None,
                 *, step: bool = False) -> None:
        entry = {"phase": phase, "status": status, "payload": payload or {},
                 "persisted": False}
        if persist and rid and ctx.get("run") is not None:
            try:
                if step:
                    record_step(root, rid, phase, status, payload)
                else:
                    record_phase(root, rid, phase, status, payload)
                entry["persisted"] = True
            except (sqlite3.Error, LookupError, OSError) as exc:
                entry["error"] = str(exc)
        auto_recorded.append(entry)
        if step:
            ctx.setdefault("steps", {})[phase] = status
        else:
            ctx.setdefault("phases", {})[phase] = {"status": status,
                                                    "payload": payload or {}, "ended_at": None}

    _delivery: dict[str, Any] = {}

    def delivery_decision() -> Any:
        """`authorize_delivery(sdd-full)` — calculé une fois par next-action."""
        if "d" not in _delivery:
            from sdd_lib.delivery_wiring import authorize
            _delivery["d"] = authorize(feat_n=feat_n, workflow=DELIVERY_WORKFLOW,
                                       run_id=rid, root=root)
        return _delivery["d"]

    def finish(action: dict[str, Any]) -> dict[str, Any]:
        if action["action"] == "stop" and not action.get("resumable") and "end_run" not in action:
            # Clôture explicite du run (lot données/états : run_close.py idempotent)
            action["end_run"] = _close_cmd(rid, "failed", action.get("error"))
        action["feat_number"] = feat_n
        action["feat_name"] = ctx.get("feat_name")
        action["run_id"] = rid
        action["auto_recorded"] = auto_recorded
        action["state"] = {
            "phases": {k: v["status"] for k, v in ctx.get("phases", {}).items()},
            "steps": dict(ctx.get("steps", {})),
            "us_count": len(ctx.get("us_files", [])),
            "plans_count": len(ctx.get("plan_files", [])),
            "manual_gates": ctx.get("manual_gates", []),
            "flyway": ctx.get("flyway", False),
            "app_type": ctx.get("app_type"),
        }
        return action

    # 0. Préconditions bloquantes --------------------------------------------
    if ctx["errors"]:
        err = ctx["errors"][0]
        return finish(_action("stop", error=f"[{err['code']}]", reason=err["message"]))

    from sdd_scripts.preflight_force_cumul import evaluate as _cumul
    cumul = _cumul(force=bool(flags.get("force")),
                   no_plan_on_warn=bool(flags.get("no_plan_on_warn")),
                   no_validate=bool(flags.get("no_validate")))
    if cumul["decision"] == "REJECTED":
        return finish(_action(
            "stop", error="[FORCE_CUMUL_REJECTED]",
            reason=(f"{cumul['bypass_count']} bypass cumulés {cumul['bypass_active']} "
                    f"sans SDD_ALLOW_FORCE=1 (preflight_force_cumul)"),
            fix="SDD_ALLOW_FORCE=1 claude /sdd-full N ... (décision humaine tracée)",
        ))

    if rid and ctx.get("run") is None and ctx.get("db_present"):
        return finish(_action(
            "stop", error="[RUN_NOT_FOUND]",
            reason=f"run_id {rid!r} absent de console.db — relancer "
                   f"`sdd_state.py new-run --feat-number {feat_n} --command /sdd-full`",
        ))

    # Hard-fail propagation (sauf readiness : son tableau de décision gère --force)
    for ph in ("us_generate", "plan", "dev_run", "qa", "auditor_batch",
               "feat_validate_postdev", "sdd_review"):
        if _phase_status(ctx, ph) == "fail":
            return finish(_action(
                "stop", phase_id=ph, run_phase=ph, error="[PHASE_FAILED]",
                reason=f"phase {ph} enregistrée en échec — corriger puis relancer "
                       f"(idempotent) ; `--resume` reprend après les phases passées",
                final_status="failed",
            ))

    # 1. us_generate -----------------------------------------------------------
    if not _phase_done(ctx, "us_generate"):
        if ctx["us_files"]:
            recorder("us_generate", "skip",
                     {"usCount": len(ctx["us_files"]), "reason": "US déjà présentes"})
        else:
            return finish(_action(
                "skill", phase_id="us-generate", run_phase="us_generate",
                skill="/us-generate", args=[str(feat_n)],
                command=f"/us-generate {feat_n}",
                reason="aucune US sous workspace/us/ pour cette FEAT",
                record_hint=_hint(feat_n, "us_generate", "pass|fail"),
                progress_pct=PROGRESS_PCT["us_generate"],
            ))
    gate = _gate_action(ctx, "us", "PO", "Validation readiness", recorder)
    if gate:
        return finish(gate)

    # 2. readiness --------------------------------------------------------------
    if not _phase_done(ctx, "readiness"):
        if flags.get("no_validate"):
            recorder("readiness", "skip", {"decision": "GO", "bypass": "--no-validate"})
        elif _phase_status(ctx, "readiness") == "fail" and flags.get("force"):
            # NO-GO assumé via --force : statut `warn` (décision humaine tracée,
            # payload conserve decision=NO-GO) — c'est ce statut que lit le hook
            # enforce_phase_order avant d'autoriser dev-* / dev-plan.
            recorder("readiness", "warn", {"decision": "NO-GO", "forced": True})
        else:
            return finish(_action(
                "skill", phase_id="feat-validate", run_phase="readiness",
                skill="/feat-validate", args=[str(feat_n), "--json"],
                command=f"/feat-validate {feat_n} --json",
                reason="Implementation Readiness Gate (déterministe)",
                record_hint=_hint(feat_n, "readiness", ""),
                progress_pct=PROGRESS_PCT["readiness"],
            ))
    decision = _readiness_decision(ctx) or "GO"
    gate = _gate_action(ctx, "readiness", "Readiness", "Plans techniques", recorder)
    if gate:
        return finish(gate)
    if decision in ("WARN", "NO-GO") and not flags.get("force"):
        return finish(_action(
            "stop", phase_id="feat-validate", run_phase="readiness", resumable=True,
            error="[READINESS_NO_GO]" if decision == "NO-GO" else "[READINESS_WARN]",
            reason=f"readiness {decision} non assumé (mode strict)",
            report=ctx["readiness_report"]["path"],
            fix=(f"corriger le rapport puis relancer /sdd-full {feat_n} ; "
                 f"ou assumer : /sdd-full {feat_n} --force (plan-review obligatoire) ; "
                 f"escape hatch : /sdd-full {feat_n} --force --no-plan-on-warn"),
            progress_pct=PROGRESS_PCT["readiness"],
        ))

    # 3. plan-then-review -------------------------------------------------------
    trigger, trigger_reason = _plan_trigger(ctx, decision)
    if not _phase_done(ctx, "plan"):
        if not trigger:
            recorder("plan", "skip", {"reason": trigger_reason})
        elif not _plans_fresh(ctx):
            return finish(_action(
                "skill", phase_id="dev-plan", run_phase="plan",
                skill="/dev-plan", args=[str(feat_n)], command=f"/dev-plan {feat_n}",
                reason=f"plan-then-review déclenché : {trigger_reason}",
                record_hint="(aucun — relancer next-action : le checkpoint suit)",
                progress_pct=PROGRESS_PCT["plan"],
            ))
        else:
            gate = _gate_action(ctx, "plan", "Plans", "Dev", recorder)
            if gate:
                return finish(gate)
            if "plan" in ctx.get("manual_gates", []):
                recorder("plan", "pass", {"plansCount": len(ctx["plan_files"]),
                                          "via": "gate afterPlan"})
            else:
                return finish(_action(
                    "checkpoint", phase_id="plan-review", run_phase="plan",
                    reason=f"plans à relire (readiness {decision}) — checkpoint humain bloquant",
                    report=ctx["readiness_report"]["path"],
                    plans=ctx["plan_files"],
                    options={
                        "ok": f"{_planner_cmd(feat_n)} --phase plan --status pass "
                              f"--payload-json '{{\"plansCount\":{len(ctx['plan_files'])}}}'",
                        "stop": "STOP propre (plans conservés ; reprendre via /sdd-full ou /dev-run)",
                        "retry": f"/dev-plan {feat_n} puis relancer next-action",
                    },
                    progress_pct=PROGRESS_PCT["plan"],
                ))
    elif trigger and not ctx["plan_files"] and _phase_status(ctx, "plan") != "skip":
        return finish(_action(
            "stop", phase_id="plan-review", run_phase="plan",
            error="[PLAN_REVIEW_GATE_SKIPPED]",
            reason=f"plan-review requis ({trigger_reason}) mais aucun plan sous workspace/plans/",
            fix=f"invoquer /dev-plan {feat_n} puis review (ok|stop|retry)",
        ))

    # 4. dev_run (arch + back + API gate + front, two-stage auditors inclus) ----
    if not _phase_done(ctx, "dev_run"):
        args = [str(feat_n)]
        rebuild = bool(flags.get("rebuild_arch")) or bool(ctx.get("flyway"))
        if ctx.get("flyway") and persist:
            sentinel = workspace_root(root) / ".sys" / ".state" / FLYWAY_SENTINEL
            try:
                sentinel.parent.mkdir(parents=True, exist_ok=True)
                if not sentinel.is_file():
                    sentinel.write_text(
                        f"feat={feat_n}-{ctx['feat_name']}\nrequested_at={iso_now_ms()}\n",
                        encoding="utf-8")
            except OSError:
                pass
        if rebuild:
            args.append("--rebuild-arch")
        if flags.get("resume"):
            args.append("--resume")
        return finish(_action(
            "skill", phase_id="dev-run", run_phase="dev_run",
            skill="/dev-run", args=args, command="/dev-run " + " ".join(args),
            covers_phases=["arch", "dev-backend", "qa-api-gate", "dev-frontend"],
            reason=("FEAT de migration Flyway : flyway migrate + re-scaffold forcés"
                    if ctx.get("flyway") else "exécution dev (arch → back → API gate → front)"),
            env={"SDD_RUN_ID": rid} if rid else {},
            record_hint=_hint(feat_n, "dev_run", "pass|warn|fail"),
            progress_pct=PROGRESS_PCT["dev_run"],
        ))
    gate = _gate_action(ctx, "code", "Dev", "QA", recorder)
    if gate:
        return finish(gate)

    # 4.bis preuve build (verify_build.py) — quel que soit le statut dev_run déclaré
    ev = delivery_evidence_action(ctx, delivery_decision(), ("build",))
    if ev:
        return finish(ev)

    # 5. doc_refresh (INDEX ADRs, non bloquant) --------------------------------
    if not _phase_done(ctx, "doc_refresh"):
        return finish(_action(
            "script", phase_id="doc-refresh", run_phase="doc_refresh",
            script=".sdd/python/sdd_scripts/index_adrs.py", args=[],
            command="python .sdd/python/sdd_scripts/index_adrs.py",
            reason="refresh INDEX ADRs (0 token, non bloquant : exit ≠ 0 → warn)",
            record_hint=_hint(feat_n, "doc_refresh", "pass|warn"),
            progress_pct=PROGRESS_PCT["doc_refresh"], blocking=False,
        ))

    # 6. qa ----------------------------------------------------------------------
    qa_mode = ctx["config"]["QAMode"]
    if not _phase_done(ctx, "qa"):
        if qa_mode in ("off", "manual"):
            recorder("qa", "skip", {"reason": f"QAMode={qa_mode}"})
        else:
            return finish(_action(
                "skill", phase_id="qa-generate", run_phase="qa",
                skill="/qa-generate", args=[str(feat_n)], command=f"/qa-generate {feat_n}",
                reason=f"QAMode={qa_mode} — tests + coverage + quality",
                record_hint=_hint(feat_n, "qa", "", verdict=True)
                + (" (RED → fail bloquant [QA_FAIL_BLOCKING_SDD_FULL])"
                   if ctx["config"]["QaFailOnSddFull"] else " (RED → warn, QaFailOnSddFull=false)"),
                progress_pct=PROGRESS_PCT["qa"],
            ))

    # 6.ter preuve tests + coverage (verify_tests.py --coverage) — même si qa
    # est `skip` (QAMode off/manual) ou déclarée pass : /sdd-full exige des tests
    # réellement exécutés ET réussis.
    ev = delivery_evidence_action(ctx, delivery_decision(), ("tests", "coverage"))
    if ev:
        return finish(ev)

    # 6.bis auditors two-stage (Stage A spec SEUL → Stage B batch parallèle).
    # Sortis de /dev-run (lot orchestration mécanique) : l'ordre imposé par
    # enforce_phase_order est dev_run → qa → reviewers.
    if not _phase_done(ctx, "auditor_batch"):
        pp = (f"python .sdd/python/sdd_scripts/phase_planner.py --feat-number {feat_n} "
              f"--json > workspace/.sys/.state/phase-plan-{feat_n}.json")
        return finish(_action(
            "procedure", phase_id="auditors", run_phase="auditor_batch",
            reason="two-stage auditors : spec-compliance-reviewer SEUL (Stage A, producteur "
                   "unique du JSON spec) puis code/security/arch en parallèle (Stage B)",
            steps=[
                pp,
                "suivre @.sdd/rules/auditor-orchestration.md §2 (lecture phase plan ; "
                "tout disabled et ArchReviewMode≠full → record --status skip)",
                f"§3 Stage A : Agent spec-compliance-reviewer « Audit FEAT {feat_n} » — "
                "RED → record --verdict RED (STOP)",
                f"§4 Stage B : un seul message multi-Agent (code-reviewer, security-reviewer, "
                f"arch-reviewer si full), prompts « FEAT {feat_n} » — MaxParallel borné par hook",
            ],
            env={"SDD_RUN_ID": rid} if rid else {},
            record_hint=_hint(feat_n, "auditor_batch", "", verdict=True),
            progress_pct=PROGRESS_PCT["feat_validate_postdev"],
        ))

    # 7. spec-compliance post-dev (lecteur pur du JSON produit en Stage A)
    if not _phase_done(ctx, "feat_validate_postdev"):
        if not ctx["config"]["SpecComplianceRequiredForFeatValidate"]:
            recorder("feat_validate_postdev", "skip",
                     {"reason": "SpecComplianceRequiredForFeatValidate=false"})
        else:
            return finish(_action(
                "script", phase_id="spec-postdev", run_phase="feat_validate_postdev",
                script=".sdd/python/sdd_scripts/validate_readiness.py",
                args=["--feat-number", str(feat_n), "--json", "--post-dev"],
                command=(f"python .sdd/python/sdd_scripts/validate_readiness.py "
                         f"--feat-number {feat_n} --json --post-dev"),
                reason="spec-compliance gate post-dev (lecture du JSON Stage A, 0 token)",
                exit_map={"0": "pass", "1": "fail [SPEC_COMPLIANCE_RED]",
                          "2": "fail [SPEC_COMPLIANCE_REQUIRED] (JSON absent)"},
                env={"SDD_RUN_ID": rid} if rid else {},
                record_hint=_hint(feat_n, "feat_validate_postdev", "pass|fail"),
                progress_pct=PROGRESS_PCT["feat_validate_postdev"],
            ))

    # 7.bis preuve spec-compliance (delivery_gate.py record-spec) — aucun mode
    # auditeur (legacy-parallel, SDD_BYPASS_TWO_STAGE, SpecCompliance…=false) ne la saute.
    ev = delivery_evidence_action(ctx, delivery_decision(), ("spec",))
    if ev:
        return finish(ev)

    # 8. sdd_review ----------------------------------------------------------------
    review_mode = ctx["config"]["ReviewMode"]
    if not _phase_done(ctx, "sdd_review"):
        if review_mode in ("off", "manual"):
            recorder("sdd_review", "skip", {"reason": f"ReviewMode={review_mode}"})
        else:
            args = [str(feat_n)] + (["--skip-scans"] if review_mode == "read-only" else [])
            return finish(_action(
                "skill", phase_id="sdd-review", run_phase="sdd_review",
                skill="/sdd-review", args=args, command="/sdd-review " + " ".join(args),
                reason=f"ReviewMode={review_mode} — audit consolidé",
                env={"SDD_RUN_ID": rid} if rid else {},
                record_hint=_hint(feat_n, "sdd_review", "", verdict=True)
                + (" (RED → fail bloquant)" if ctx["config"]["ReviewFailOnSddFull"]
                   else " (RED → warn, ReviewFailOnSddFull=false)"),
                progress_pct=PROGRESS_PCT["sdd_review"],
            ))

    # 8.bis GATE DE LIVRAISON (point de sortie unique) -------------------------
    # La décision = UNIQUEMENT authorize_delivery (preuves). run_phases peut au
    # plus dégrader success → partial, jamais autoriser.
    decision_d = delivery_decision()
    ev = delivery_evidence_action(ctx, decision_d,
                                  ("build", "tests", "coverage", "spec", "readiness"))
    if ev:
        return finish(ev)
    if not decision_d.allowed:
        from sdd_lib.delivery_wiring import BLOCKED_CLASS
        if flags.get("force"):
            _append_audit_line(root, "force-bypass.log",
                               f"{iso_now_ms()} /sdd-full {feat_n} --force SANS EFFET sur le "
                               f"gate de livraison run={rid}")
        return finish(_action(
            "stop", phase_id="delivery-gate", error=BLOCKED_CLASS,
            reason=f"livraison refusée — {decision_d.summary()}",
            fix=(f"python .sdd/python/sdd_scripts/delivery_gate.py authorize --feat-number "
                 f"{feat_n} --workflow {DELIVERY_WORKFLOW} --json (détail) ; aucun flag "
                 f"ne lève ce gate"),
            delivery_gate=decision_d.to_dict(), final_status="failed",
        ))

    # 9. cahier des charges (best-effort, post-pipeline) --------------------------
    statuses = {k: v["status"] for k, v in ctx.get("phases", {}).items()}
    final_status = "failed" if "fail" in statuses.values() else (
        "partial" if "warn" in statuses.values() else "success")
    if SPEC_BOOK_STEP not in ctx.get("steps", {}) and final_status != "failed":
        return finish(_action(
            "skill", phase_id=SPEC_BOOK_STEP, run_phase=None, optional=True,
            skill="/spec-book", args=[str(feat_n)], command=f"/spec-book {feat_n}",
            reason="cahier des charges (idempotent, best-effort : échec = warn)",
            record_hint=f"{_planner_cmd(feat_n)} --step {SPEC_BOOK_STEP} --status {{pass|warn}}",
            progress_pct=PROGRESS_PCT[SPEC_BOOK_STEP],
        ))

    # 10. done -------------------------------------------------------------------
    end_run = _close_cmd(rid, {"success": "completed"}.get(final_status, final_status))
    return finish(_action(
        "done", final_status=final_status, end_run=end_run,
        delivery_gate=decision_d.to_dict(),
        recap=(f"python .sdd/python/sdd_scripts/sdd_full_planner.py recap --run-id {rid}"
               if rid else None),
        reason="toutes les phases sont terminées", progress_pct=PROGRESS_PCT["done"],
    ))


# ============================================================================
# Recap (console.db)
# ============================================================================

#: File extensions considered "production code" by `_count_code_files`.
_PRODUCTION_CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".cs", ".ts", ".tsx", ".js", ".jsx", ".py", ".kt", ".java",
    ".razor", ".vue", ".html", ".cshtml", ".xaml", ".swift", ".dart",
})


def _count_code_files(root: Path) -> int:
    """Count production code files under workspace/src/ (audit CTO 2026-06-07 P0)."""
    count = 0
    src_dir = workspace_root(root) / "src"
    if not src_dir.is_dir():
        return count  # not an exit code — file counter
    for path in src_dir.rglob("*"):
        if not path.is_file():
            continue
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


def _inline_rules_drift(root: Path) -> dict[str, Any]:
    """ex-STEP 4.9 : drift inline rules (best-effort, jamais bloquant)."""
    out: dict[str, Any] = {"checked": False, "drift_count": 0, "exit_code": None}
    script = root / ".sdd" / "python" / "sdd_scripts" / "validate_inline_rules.py"
    if not script.is_file():
        return out
    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--json"], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=60, cwd=str(root),
        )
    except (OSError, subprocess.SubprocessError):
        return out
    out["checked"] = True
    out["exit_code"] = proc.returncode
    try:
        data = json.loads(proc.stdout or "{}")
        drifts = data.get("drifts") or data.get("drift") or []
        out["drift_count"] = len(drifts) if isinstance(drifts, list) else int(
            data.get("drift_count") or data.get("count") or 0)
    except (ValueError, TypeError):
        out["drift_count"] = 1 if proc.returncode == 1 else 0
    return out


def build_recap(root: Path, run_id: str, *, with_drift: bool = False) -> dict:
    """Read run_phases + token_usage + verdicts to build a final summary."""
    db_path = _db_path(root)
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
            if isinstance(payload, dict) and "decision" in payload:
                recap["verdicts"][r["phase"]] = payload["decision"]

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

    code_count = _count_code_files(root)
    recap["code_files_count"] = code_count
    dev_run_phase = next((p for p in recap["phases"] if p["phase"] == "dev_run"), None)
    dev_run_ran = dev_run_phase is not None and dev_run_phase["status"] not in ("skip", None, "")
    if dev_run_ran and code_count == 0 and recap["final_status"] == "success":
        recap["final_status"] = "partial"
        recap["warnings"].append(
            "[FALSE_POSITIVE_COMPLETION] dev_run phase marked pass but no "
            "production code files found under workspace/src/. "
            "Possible causes: agent crashed mid-write, set-phase event emitted "
            "without writing, frontend-only US misclassified. Inspect "
            "workspace/src/ manually before declaring delivery."
        )

    force_log = audit_dir_path(root) / "force-bypass.log"
    recap["force_bypass_log"] = str(force_log) if force_log.is_file() else None

    if with_drift:
        drift = _inline_rules_drift(root)
        recap["inline_rules_drift"] = drift
        if drift.get("drift_count"):
            recap["warnings"].append(
                f"[DRIFT_SUSPECTED] {drift['drift_count']} drift(s) inline rules ↔ .sdd/rules/ "
                f"(validate_inline_rules.py --json)"
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
    for p in recap.get("phases", []):
        sicon = {"pass": "✅", "warn": "🟡", "fail": "🔴", "skip": "⏭"}.get(p["status"], "?")
        verdict_str = ""
        for k in ("decision", "verdict", "status"):
            if k in p.get("payload", {}):
                verdict_str = f" → {p['payload'][k]}"
                break
        lines.append(f"  {sicon} {p['phase']:20s} {str(p['status']):8s}{verdict_str}")
    t = recap.get("tokens", {})
    if t.get("input") or t.get("cache_read"):
        total = t["input"] + t["cache_read"] + t["cache_write"]
        hit_rate = (t["cache_read"] / total * 100) if total else 0
        lines.append("")
        lines.append(f"Tokens : in={t['input']} out={t['output']} "
                     f"cache_r={t['cache_read']} cache_w={t['cache_write']} "
                     f"(hit_rate={hit_rate:.1f}%)")
        cost = (t["input"] * 6 + t["output"] * 30
                + t["cache_read"] * 0.30 + t["cache_write"] * 7.50) / 1_000_000
        lines.append(f"Cost   : ~${cost:.4f}")
    warnings = recap.get("warnings") or []
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(f"⚠  {w}")
    code_count = recap.get("code_files_count", 0)
    if code_count:
        lines.append(f"Code files materialized : {code_count}")
    if recap.get("force_bypass_log"):
        lines.append(f"Bypass --force tracé : {recap['force_bypass_log']}")
    lines.append("")
    lines.append(f"Run trace : {recap.get('run_id', '?')}")
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================


def _emit(payload: str) -> None:
    try:
        sys.stdout.buffer.write(payload.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()
    except AttributeError:
        print(payload)


def _add_flag_overrides(p: argparse.ArgumentParser) -> None:
    """Flags /sdd-full acceptés directement par next-action/record (override args file)."""
    for flag in ("--force", "--plan", "--no-plan-on-warn", "--no-validate",
                 "--rebuild-arch", "--resume", "--no-manual-gates"):
        p.add_argument(flag, action="store_true", default=False)
    p.add_argument("--manual-gates", nargs="?", const="all", default=None)


def _merge_flags(root: Path, feat_n: int, ns: argparse.Namespace) -> dict[str, Any]:
    flags = load_args_state(root, feat_n)
    for key in ("force", "plan", "no_plan_on_warn", "no_validate",
                "rebuild_arch", "resume", "no_manual_gates"):
        if getattr(ns, key, False):
            flags[key] = True
    if getattr(ns, "manual_gates", None) is not None:
        flags["manual_gates"] = parse_manual_gates_value(ns.manual_gates)
    return flags


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()  # cp1252 guard (audit 2026-06-11 M15)
    parser = argparse.ArgumentParser(
        description="Deterministic planner + runner state machine for /sdd-full"
    )
    sub = parser.add_subparsers(dest="cmd")

    plan_p = sub.add_parser("plan", help="Build execution plan (vue statique)")
    plan_p.add_argument("--feat-number", "-n", type=int, required=True)
    plan_p.add_argument("--root", type=Path, default=Path.cwd())
    plan_p.add_argument("--force", action="store_true")
    plan_p.add_argument("--manual-gates", action="store_true")
    plan_p.add_argument("--json", action="store_true")

    args_p = sub.add_parser("args", help="Parse les flags /sdd-full (argparse strict)")
    args_p.add_argument("--input", "-i", type=str, default=None,
                        help="chaîne brute « N --force ... » (défaut : stdin)")
    args_p.add_argument("--root", type=Path, default=Path.cwd())
    args_p.add_argument("--dry-run", action="store_true")

    next_p = sub.add_parser(
        "next-action",
        help="Prochaine action depuis l'état réel (console.db + disque)",
    )
    next_p.add_argument("--feat", "--feat-number", "-n", dest="feat", type=int, default=None)
    next_p.add_argument("--run-id", default=None)
    next_p.add_argument("--root", type=Path, default=Path.cwd())
    next_p.add_argument("--json", action="store_true", help="(défaut — sortie JSON)")
    next_p.add_argument("--no-record", action="store_true",
                        help="ne pas persister les skips mécaniques (lecture pure)")
    _add_flag_overrides(next_p)
    next_p.add_argument("--plan-json", type=Path, default=None,
                        help="[DEPRECATED] plan JSON (mode legacy, ignoré avec --feat)")
    next_p.add_argument("--state-json", type=Path, default=None,
                        help="[DEPRECATED] état JSON (mode legacy, ignoré avec --feat)")
    next_p.add_argument("--state-inline", default=None,
                        help="[DEPRECATED] état inline sérialisé par le LLM — ignoré si la base est disponible")

    rec_p = sub.add_parser("record", help="Enregistre le résultat d'une phase / étape")
    rec_p.add_argument("--feat", "--feat-number", "-n", dest="feat", type=int, required=True)
    rec_p.add_argument("--run-id", default=None)
    rec_p.add_argument("--root", type=Path, default=Path.cwd())
    rec_p.add_argument("--phase", default=None, help="phase canonique sdd_state (us_generate, readiness, ...)")
    rec_p.add_argument("--step", default=None, help="étape hors vocabulaire (gate-afterX, spec-book)")
    rec_p.add_argument("--status", choices=["pass", "warn", "fail", "skip"], default=None)
    rec_p.add_argument("--verdict", default=None,
                       help="GO|WARN|NO-GO|GREEN|YELLOW|RED|PASS|FAIL → statut via Project Config")
    rec_p.add_argument("--payload-json", default="")
    _add_flag_overrides(rec_p)

    recap_p = sub.add_parser("recap", help="Build final recap from console.db")
    recap_p.add_argument("--run-id", required=True)
    recap_p.add_argument("--root", type=Path, default=Path.cwd())
    recap_p.add_argument("--json", action="store_true")
    recap_p.add_argument("--no-drift-check", action="store_true",
                         help="skip validate_inline_rules.py (ex-STEP 4.9)")

    # Top-level legacy flags (when no subcmd given) — emulate old 'plan' behavior
    parser.add_argument("--feat-number", "-n", type=int)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--manual-gates", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd is None or args.cmd == "plan":
        feat = getattr(args, "feat_number", None)
        if feat is None:
            print("ERROR: --feat-number required", file=sys.stderr)
            return FAIL_FAST
        return _run_plan(args)
    if args.cmd == "args":
        return _run_args(args)
    if args.cmd == "next-action":
        return _run_next_action(args)
    if args.cmd == "record":
        return _run_record(args)
    if args.cmd == "recap":
        return _run_recap(args)

    print(f"ERROR: unknown subcommand {args.cmd}", file=sys.stderr)
    return FAIL_FAST


def _check_root(root: Path) -> int | None:
    if not root.exists() or not ((root / ".sdd").is_dir() or (root / ".claude").is_dir()):
        print(f"ERROR: {root} is not a SDD_Pro project root (.sdd/ or .claude/ missing)",
              file=sys.stderr)
        return INFRA_BLOCKED
    return None


def _run_plan(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    rc = _check_root(root)
    if rc is not None:
        return rc
    plan = build_plan(root, args.feat_number, force=args.force, manual_gates=args.manual_gates)
    if args.json:
        _emit(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        text = format_text_report(plan)
        try:
            sys.stdout.buffer.write(text.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.flush()
        except AttributeError:
            print(text.encode("ascii", "replace").decode("ascii"))
    return FAIL_FAST if plan.get("errors") else SUCCESS


def _run_args(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    raw = args.input
    if raw is None:
        raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: [INVALID_ARG] no input provided (use --input or stdin)", file=sys.stderr)
        return FAIL_FAST
    try:
        flags = parse_sdd_full_flags(raw)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return FAIL_FAST
    if flags["feat_number"] is None or flags["feat_number"] < 1:
        print("ERROR: [INVALID_ARG] numéro de FEAT requis (entier ≥ 1)", file=sys.stderr)
        return FAIL_FAST
    flags["tags"] = active_tags(flags)
    _emit(json.dumps(flags, indent=2, ensure_ascii=False))
    if args.dry_run:
        return SUCCESS
    try:
        out = write_args_state(flags, root)
    except OSError as exc:
        print(f"ERROR: [INFRA_BLOCKED] cannot write state file: {exc}", file=sys.stderr)
        return INFRA_BLOCKED
    print(f"[SDD_FULL_ARGS] state written → {out.relative_to(root).as_posix()}", file=sys.stderr)
    return SUCCESS


def _run_next_action(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    if args.feat is None:
        # ---- mode legacy (déprécié) -------------------------------------
        if args.plan_json is None:
            print("ERROR: --feat N requis (ou --plan-json en mode legacy déprécié)",
                  file=sys.stderr)
            return FAIL_FAST
        print("WARN [SDD_FULL_PLANNER_LEGACY] next-action sans --feat : mode "
              "--plan-json/--state-inline déprécié (l'état devrait venir de console.db)",
              file=sys.stderr)
        if not args.plan_json.is_file():
            print(f"ERROR: plan JSON not found: {args.plan_json}", file=sys.stderr)
            return FAIL_FAST
        plan = json.loads(args.plan_json.read_text(encoding="utf-8"))
        if args.state_inline:
            state = json.loads(args.state_inline)
        elif args.state_json:
            if not args.state_json.is_file():
                print(f"ERROR: state JSON not found: {args.state_json}", file=sys.stderr)
                return FAIL_FAST
            state = json.loads(args.state_json.read_text(encoding="utf-8"))
        else:
            state = {"completed_phases": [], "last_status": None, "flags": {}}
        _emit(json.dumps(decide_next_action(plan, state), indent=2, ensure_ascii=False))
        return SUCCESS

    rc = _check_root(root)
    if rc is not None:
        return rc
    if args.state_inline or args.state_json or args.plan_json:
        print("WARN [SDD_FULL_PLANNER_LEGACY] --state-inline/--state-json/--plan-json "
              "ignorés : l'état est lu dans console.db (--feat fourni)", file=sys.stderr)
    try:
        flags = _merge_flags(root, args.feat, args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return FAIL_FAST
    try:
        decision = compute_next_action(root, args.feat, flags, run_id=args.run_id,
                                       persist=not args.no_record)
    except ConfigError as exc:
        print(f"ERROR: [CONFIG_SECURITY_DOWNGRADE] {exc}", file=sys.stderr)
        return FAIL_FAST
    _emit(json.dumps(decision, indent=2, ensure_ascii=False))
    if decision.get("error") == "[INFRA_BLOCKED]":
        return INFRA_BLOCKED
    return SUCCESS


def _run_record(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    rc = _check_root(root)
    if rc is not None:
        return rc
    if bool(args.phase) == bool(args.step):
        print("ERROR: [INVALID_ARG] exactement un de --phase / --step requis", file=sys.stderr)
        return FAIL_FAST
    if bool(args.status) == bool(args.verdict):
        print("ERROR: [INVALID_ARG] exactement un de --status / --verdict requis", file=sys.stderr)
        return FAIL_FAST
    payload: dict[str, Any] = {}
    if args.payload_json:
        try:
            parsed = json.loads(args.payload_json)
            if isinstance(parsed, dict):
                payload = parsed
        except ValueError as exc:
            print(f"ERROR: [INVALID_ARG] --payload-json invalide : {exc}", file=sys.stderr)
            return FAIL_FAST
    try:
        flags = _merge_flags(root, args.feat, args)
        run_id = resolve_run_id(root, args.feat, args.run_id)
    except StateUnavailable as exc:
        print(f"ERROR: [INFRA_BLOCKED] {exc}", file=sys.stderr)
        return INFRA_BLOCKED
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return FAIL_FAST
    if not run_id:
        print(f"ERROR: [RUN_NOT_FOUND] aucun run `running` pour FEAT {args.feat} — "
              f"lancer `sdd_state.py new-run --feat-number {args.feat} --command /sdd-full` "
              f"(ou exporter SDD_RUN_ID)", file=sys.stderr)
        return FAIL_FAST

    config, _ = _read_config(root)
    cfg = {"QaFailOnSddFull": _as_bool(config.get("QaFailOnSddFull"), True),
           "ReviewFailOnSddFull": _as_bool(config.get("ReviewFailOnSddFull"), True)}

    target = args.phase or args.step
    if args.phase:
        try:
            from sdd_scripts.sdd_state import resolve_phase_name
            canonical, alias_warning = resolve_phase_name(args.phase)
        except ImportError:
            canonical, alias_warning = args.phase, None
        if canonical is None:
            print(f"ERROR: [INVALID_ARG] phase inconnue {args.phase!r} "
                  f"(canoniques : {', '.join(CANONICAL_PHASES + AUX_PHASES)})", file=sys.stderr)
            return FAIL_FAST
        if alias_warning:
            print(f"WARN {alias_warning}", file=sys.stderr)
        target = canonical

    try:
        status = args.status or status_from_verdict(target, args.verdict, cfg)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return FAIL_FAST
    if args.verdict:
        payload.setdefault("decision", args.verdict.upper())
        if status == "warn" and args.verdict.strip().lower() in ("red", "fail"):
            payload.setdefault("bypass", f"{target}FailOnSddFull=false")
            _append_audit_line(root, "sdd-full-bypass.log",
                               f"{iso_now_ms()} /sdd-full {args.feat} phase={target} "
                               f"verdict=RED non bloquant (Project Config)")

    try:
        if args.phase:
            record_phase(root, run_id, target, status, payload or None)
        else:
            record_step(root, run_id, target, status, payload or None)
    except LookupError as exc:
        print(f"ERROR: [RUN_NOT_FOUND] {exc}", file=sys.stderr)
        return FAIL_FAST
    except sqlite3.Error as exc:
        print(f"ERROR: [INFRA_BLOCKED] console.db : {exc}", file=sys.stderr)
        return INFRA_BLOCKED

    # ex-STEP 3.7 — audit log --force (append-only), posé au moment du verdict readiness
    if args.phase and target == "readiness" and flags.get("force"):
        decision = str(payload.get("decision") or status).upper()
        _append_audit_line(
            root, "force-bypass.log",
            f"{iso_now_ms()} /sdd-full {args.feat} --force readiness={decision} "
            f"--no-plan-on-warn={str(bool(flags.get('no_plan_on_warn'))).lower()} run={run_id}",
        )

    _emit(json.dumps({"recorded": target, "kind": "phase" if args.phase else "step",
                      "status": status, "run_id": run_id, "payload": payload},
                     ensure_ascii=False))
    return SUCCESS


def _run_recap(args: argparse.Namespace) -> int:
    root: Path = args.root.resolve()
    recap = build_recap(root, args.run_id, with_drift=not args.no_drift_check)
    if args.json:
        payload = json.dumps(recap, indent=2, ensure_ascii=False)
    else:
        payload = render_recap_markdown(recap)
    try:
        sys.stdout.buffer.write(payload.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()
    except AttributeError:
        print(payload.encode("ascii", errors="replace").decode("ascii"))
    return SUCCESS if "error" not in recap else FAIL_FAST


if __name__ == "__main__":
    sys.exit(main())
