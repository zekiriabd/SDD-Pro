#!/usr/bin/env python3
"""SDD_Pro: déterministe phase planner (méta-orchestrateur conditionnel).

Détermine quelles phases auditor doivent tourner pour la FEAT courante,
en lisant le Project Config + les stacks actifs + l'état runtime du
workspace.

Phases gérées (v7.0.0+) :
    - code_review         (code-reviewer, post-dev)
    - security_scan       (security-reviewer mode scan, post-dev)
    - spec_compliance     (spec-compliance-reviewer, post-dev)

Phases retirées v7.0.0 (`governance-major-auditors-trim`) :
    - threat_model    → templates/threat-model.template.md (humain)
    - a11y_audit      → axe-core dans CI projet généré
    - perf_audit      → Lighthouse CI + wrk/k6 dans CI projet généré
    Sprint immédiat 2026-06-07 — retirées de l'output JSON pour éliminer
    le code mort déclaratif (~50% de la surface du module).

Logique de skip :
    1. Mode global = `off` → phase désactivée
    2. Mode = `manual` → phase désactivée (Tech Lead invoque à la demande)
    3. Stack-conditional :
        - security_scan : skip si pas de stack backend ni frontend (rien à scanner)
        - code_review + spec_compliance : skip si pas de code production

Usage:
    python phase_planner.py --feat-number N [--json]

Exit codes:
    0 : succès (lire stdout JSON pour le plan)
    1 : ERROR I/O (stack.md ou FEAT introuvable)
    2 : ERROR malformé (Project Config inexploitable)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.project_config import read_project_config, read_stack_md_text  # noqa: E402  (legacy fallback)
from sdd_lib.layered_config import ConfigError, read_layered_config  # noqa: E402  (v6.7.3)


PROJECT_CONFIG_KEYS = (
    # v7.0.0+ auditor modes (3 phases actives — agents threat-model/a11y/perf
    # retirés `governance-major-auditors-trim`, remplacés par CI déterministe)
    "CodeReviewMode",
    "CodeReviewFailOn",
    "SecurityMode",
    "SecurityScanEnabled",
    "SecurityFailOn",
    # v6.5.2 spec-compliance-reviewer
    "SpecComplianceMode",
    "SpecComplianceFailOn",
    # v7.0.0 P2 #12 — Lean reviewers auto-routing (heuristique FEAT S)
    "LeanReviewersPreset",
    # Stacks
    "AppName",
    "BackendName",
)

# Coûts tokens estimés par phase (cf. agents/*.md "Token footprint cible")
PHASE_COST_ESTIMATE = {
    "code_review": 12_000,      # code-reviewer
    "security_scan": 15_000,    # security-reviewer mode scan
    "spec_compliance": 12_000,  # spec-compliance-reviewer (v6.5.2)
}

# Modes valides par phase
VALID_MODES = {"off", "full", "manual"}

# Regex pour détecter mentions security dans ACs (override si SecurityMode=manual)
SECURITY_AC_HINTS = re.compile(
    r"\b(owasp|xss|sql\s+injection|csrf|jwt|secret|password\s+policy|"
    r"rate\s+limit|brute\s+force|encrypted|hashing|salt|hsts|csp)\b",
    re.IGNORECASE,
)

# PERF_AC_HINTS regex retiré v7.0.0 — perf phase removed (Lighthouse CI replace).
# Kept absent rather than aliased to avoid silent re-introduction.


def _read_feat_file(root: Path, feat_number: int) -> tuple[str | None, str | None]:
    """Lit la FEAT N. Retourne (FeatName, content) ou (None, None)."""
    feats_dir = root / "workspace" / "input" / "feats"
    if not feats_dir.is_dir():
        return None, None
    matches = sorted(feats_dir.glob(f"{feat_number}-*.md"))
    if not matches:
        return None, None
    feat_file = matches[0]
    name = feat_file.stem  # ex. "4-Bebes"
    name_parts = name.split("-", 1)
    feat_name = name_parts[1] if len(name_parts) > 1 else name
    try:
        content = feat_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return feat_name, None
    return feat_name, content


def _read_us_files(root: Path, feat_number: int) -> list[str]:
    """Liste les contenus des US de la FEAT N."""
    us_dir = root / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    contents: list[str] = []
    for us_file in sorted(us_dir.glob(f"{feat_number}-*.md")):
        try:
            contents.append(us_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return contents


def _count_us_files(root: Path, feat_number: int) -> int:
    """Count US files for a FEAT (used by LeanReviewersPreset heuristic v7.0.0 P2 #12)."""
    us_dir = root / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return 0
    return len(list(us_dir.glob(f"{feat_number}-*.md")))


def _active_stacks(root: Path) -> dict[str, str | None]:
    """Détecte les stacks actifs depuis ## Active Tech Specs + UI + Auth de stack.md.

    v7.0.0-alpha (audit CRIT-2) : I/O cached on (path, mtime_ns).
    """
    text = read_stack_md_text(root)
    if text is None:
        return {"backend": None, "frontend": None, "ui": None, "auth": None, "fullstack": None, "mobiles": None}

    # v6.7.5 — categories etendues: + fullstack + mobiles
    # v6.7.7 — respect `#` commented lines (skip them)
    stacks: dict[str, str | None] = {
        "backend": None, "frontend": None, "ui": None, "auth": None,
        "fullstack": None, "mobiles": None,
    }
    pattern = re.compile(
        r"\.claude/stacks/(backend|frontend|ui|auth|fullstack|mobiles)/([\w-]+)\.md",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        m = pattern.search(line)
        if not m:
            continue
        category = m.group(1).lower()
        stack_id = m.group(2)
        if stacks.get(category) is None:
            stacks[category] = stack_id
    return stacks


def _project_has_frontend_code(root: Path, app_name: str | None) -> bool:
    """Détecte si workspace/output/src/{AppName}/ existe avec du markup."""
    if not app_name:
        return False
    app_dir = root / "workspace" / "output" / "src" / app_name
    if not app_dir.is_dir():
        return False
    # Heuristique : présence de fichiers markup (.tsx, .vue, .razor, .html)
    extensions = ("*.tsx", "*.jsx", "*.vue", "*.razor", "*.html")
    for ext in extensions:
        if any(app_dir.rglob(ext)):
            return True
    return False


def _project_has_backend_code(root: Path, backend_name: str | None) -> bool:
    """Détecte si workspace/output/src/{BackendName}/ existe avec du code."""
    if not backend_name:
        return False
    backend_dir = root / "workspace" / "output" / "src" / backend_name
    if not backend_dir.is_dir():
        return False
    extensions = ("*.cs", "*.kt", "*.py", "*.ts", "*.js")
    for ext in extensions:
        if any(backend_dir.rglob(ext)):
            return True
    return False


def _normalize_mode(value: str | None, default: str = "manual") -> str:
    if not value:
        return default
    v = value.strip().lower()
    return v if v in VALID_MODES else default


def _bool_flag(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")


def _validate_stack_coherence(stacks: dict[str, str | None]) -> str | None:
    """Validation cohérence stack.md (security audit 2026-06-06, SSoT v2 2026-06-06 R3).

    Délègue à `sdd_lib.stack_validator.validate_active_stacks_coherence` pour
    rester aligné avec sdd_full_planner.py + validate_readiness.py.
    """
    from sdd_lib.stack_validator import validate_active_stacks_coherence
    err = validate_active_stacks_coherence(stacks)
    if err is None:
        return None
    return f"[{err['code']}] {err['message']}"


def plan(feat_number: int) -> dict[str, object]:
    """Construit le plan d'exécution des phases auditor pour la FEAT N."""
    root = repo_root()

    # 1. Lecture Project Config (v6.7.3: layered config base + team + project)
    try:
        config = read_layered_config(root=root, keys=PROJECT_CONFIG_KEYS)
    except ConfigError as exc:
        return {
            "feat_number": feat_number,
            "error": f"{exc.cause}",
            "phases": {},
        }
    except Exception as exc:  # noqa: BLE001
        # Backward-compat fallback to legacy read_project_config()
        try:
            config = read_project_config(root=root, keys=PROJECT_CONFIG_KEYS)
        except Exception as inner:  # noqa: BLE001
            return {
                "feat_number": feat_number,
                "error": f"[STACK_MALFORMED] Project Config illisible: {inner}",
                "phases": {},
            }

    code_review_mode = _normalize_mode(config.get("CodeReviewMode"), default="manual")
    security_mode = _normalize_mode(config.get("SecurityMode"), default="manual")
    spec_compliance_mode = _normalize_mode(config.get("SpecComplianceMode"), default="manual")
    security_scan_enabled = _bool_flag(config.get("SecurityScanEnabled"), default=True)

    # v7.0.0 P2 #12 — Lean reviewers auto-routing (heuristique taille FEAT) :
    # Si LeanReviewersPreset: true ET FEAT S (≤ 2 US) ET pas d'AC sécurité,
    # downgrade security/spec/arch reviewers à "manual" pour économiser
    # ~$1.50-3 par FEAT S. code-reviewer reste toujours `full` (seul reviewer
    # avec preuve empirique de valeur sur petites FEATs).
    lean_preset = _bool_flag(config.get("LeanReviewersPreset"), default=False)
    us_count_for_lean = _count_us_files(root, feat_number)

    app_name = config.get("AppName")
    backend_name = config.get("BackendName")

    # 2. Stacks actifs
    stacks = _active_stacks(root)

    # 2.bis Validation cohérence stack.md (security audit 2026-06-06)
    # Détecte les combinaisons impossibles ou stack.md vide.
    coherence_error = _validate_stack_coherence(stacks)
    if coherence_error:
        return {
            "feat_number": feat_number,
            "error": coherence_error,
            "phases": {},
            "stacks_detected": stacks,
        }

    # 3. État runtime (présence code généré)
    has_frontend_code = _project_has_frontend_code(root, app_name)
    has_backend_code = _project_has_backend_code(root, backend_name)

    # 4. FEAT + US content (pour détecter mentions perf/sec dans ACs)
    feat_name, feat_content = _read_feat_file(root, feat_number)
    us_contents = _read_us_files(root, feat_number)

    if not feat_name or not feat_content:
        return {
            "feat_number": feat_number,
            "error": f"[FEAT_NOT_FOUND] aucun fichier workspace/input/feats/{feat_number}-*.md",
            "phases": {},
        }

    combined_text = feat_content + "\n" + "\n".join(us_contents)
    has_security_ac = bool(SECURITY_AC_HINTS.search(combined_text))

    # v7.0.0 P2 #12 — Apply lean preset BEFORE building phases.
    # Heuristique : FEAT S = ≤ 2 US ET sans AC sécurité.
    # Sous ces conditions, downgrade security/spec/arch à "manual" (le Tech
    # Lead invoque à la demande). code_review reste full (preuve empirique
    # value sur petites FEATs).
    if lean_preset and us_count_for_lean > 0:
        is_feat_s = (us_count_for_lean <= 2 and not has_security_ac)
        if is_feat_s:
            if security_mode == "full":
                security_mode = "manual"
            if spec_compliance_mode == "full":
                spec_compliance_mode = "manual"
            # arch_review_mode lu plus bas — laissé en lecture config (déjà manual default)

    # 5. Construction des phases (3 phases v7.0.0+ — threat_model/a11y/perf retirées)
    phases: dict[str, dict[str, object]] = {}

    # --- code_review (post-dev) ---
    phases["code_review"] = _decide_code_review(
        code_review_mode=code_review_mode,
        has_backend_code=has_backend_code,
        has_frontend_code=has_frontend_code,
    )

    # --- security_scan (post-dev) ---
    phases["security_scan"] = _decide_security_scan(
        security_mode=security_mode,
        scan_enabled=security_scan_enabled,
        has_security_ac=has_security_ac,
        has_backend_code=has_backend_code,
        has_frontend_code=has_frontend_code,
    )

    # --- spec_compliance (post-dev, v6.5.2) ---
    phases["spec_compliance"] = _decide_spec_compliance(
        spec_compliance_mode=spec_compliance_mode,
        has_backend_code=has_backend_code,
        has_frontend_code=has_frontend_code,
    )

    # 6. Summary
    phases_enabled = sum(1 for p in phases.values() if p["enabled"])
    phases_skipped = sum(1 for p in phases.values() if not p["enabled"])
    estimated_total = sum(
        PHASE_COST_ESTIMATE[name]
        for name, ph in phases.items()
        if ph["enabled"]
    )
    estimated_saved = sum(
        PHASE_COST_ESTIMATE[name]
        for name, ph in phases.items()
        if not ph["enabled"]
    )

    return {
        "feat_number": feat_number,
        "feat_name": feat_name,
        "stacks": stacks,
        "config": {
            "CodeReviewMode": code_review_mode,
            "SecurityMode": security_mode,
            "SecurityScanEnabled": security_scan_enabled,
            "SpecComplianceMode": spec_compliance_mode,
        },
        "runtime_state": {
            "has_frontend_code": has_frontend_code,
            "has_backend_code": has_backend_code,
            "us_count": len(us_contents),
            "has_security_ac": has_security_ac,
        },
        "phases": phases,
        "summary": {
            "phases_enabled": phases_enabled,
            "phases_skipped": phases_skipped,
            "estimated_total_tokens": estimated_total,
            "estimated_tokens_saved": estimated_saved,
        },
    }


def _decide_code_review(
    *,
    code_review_mode: str,
    has_backend_code: bool,
    has_frontend_code: bool,
) -> dict[str, object]:
    if code_review_mode == "off":
        return _phase("code_review", enabled=False, reason="CodeReviewMode=off")
    if code_review_mode == "manual":
        return _phase("code_review", enabled=False, reason="CodeReviewMode=manual (Tech Lead invoque à la demande)")
    if not has_backend_code and not has_frontend_code:
        return _phase("code_review", enabled=False, reason="aucun code production (/dev-run pas exécuté)")
    return _phase("code_review", enabled=True, reason=None)


def _decide_security_scan(
    *,
    security_mode: str,
    scan_enabled: bool,
    has_security_ac: bool,
    has_backend_code: bool,
    has_frontend_code: bool,
) -> dict[str, object]:
    if security_mode == "off":
        return _phase("security_scan", enabled=False, reason="SecurityMode=off")
    if security_mode == "manual" and not has_security_ac:
        return _phase(
            "security_scan",
            enabled=False,
            reason="SecurityMode=manual + no security-related AC (Tech Lead invoque à la demande)",
        )
    if not scan_enabled:
        return _phase("security_scan", enabled=False, reason="SecurityScanEnabled=false")
    if not has_backend_code and not has_frontend_code:
        return _phase("security_scan", enabled=False, reason="aucun code production (/dev-run pas exécuté)")
    return _phase("security_scan", enabled=True, reason=None)


def _decide_spec_compliance(
    *,
    spec_compliance_mode: str,
    has_backend_code: bool,
    has_frontend_code: bool,
) -> dict[str, object]:
    """v6.5.2 — spec-compliance-reviewer.

    Verifies that each AC of each US is actually implemented in the
    materialized code. Pattern "Do not trust the report" (superpowers v5.1).

    - Skip if mode = off
    - Skip if mode = manual (Tech Lead invokes explicitly)
    - Skip if no production code present
    - Otherwise enabled
    """
    if spec_compliance_mode == "off":
        return _phase("spec_compliance", enabled=False, reason="SpecComplianceMode=off")
    if spec_compliance_mode == "manual":
        return _phase(
            "spec_compliance",
            enabled=False,
            reason="SpecComplianceMode=manual (Tech Lead invoque à la demande)",
        )
    if not has_backend_code and not has_frontend_code:
        return _phase(
            "spec_compliance",
            enabled=False,
            reason="aucun code production (/dev-run pas exécuté)",
        )
    return _phase("spec_compliance", enabled=True, reason=None)


def _phase(name: str, *, enabled: bool, reason: str | None) -> dict[str, object]:
    return {
        "enabled": enabled,
        "skip_reason": reason,
        "estimated_tokens": PHASE_COST_ESTIMATE[name] if enabled else 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SDD_Pro phase planner (v6.4.1)")
    parser.add_argument("--feat-number", type=int, required=True, help="numéro de FEAT")
    parser.add_argument("--json", action="store_true", help="output JSON (default)")
    args = parser.parse_args(argv)

    try:
        result = plan(feat_number=args.feat_number)
    except FileNotFoundError as exc:
        sys.stderr.write(f"[NOT_FOUND] {exc}\n")
        return FAIL_FAST
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"[ERROR] I/O: {exc}\n")
        return FAIL_FAST
    except ValueError as exc:
        sys.stderr.write(f"[STACK_MALFORMED] {exc}\n")
        return 2  # legacy exit code preserved — STACK_MALFORMED granularity

    if "error" in result:
        sys.stderr.write(f"{result['error']}\n")
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        # legacy exit code preserved — STACK_MALFORMED granularity (exit 2)
        return 2 if "STACK_MALFORMED" in str(result.get("error", "")) else FAIL_FAST

    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
