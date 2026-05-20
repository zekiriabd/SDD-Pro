#!/usr/bin/env python3
"""SDD_Pro: déterministe phase planner (méta-orchestrateur conditionnel, v6.4.1).

Détermine quelles phases auditor (v6.3.x + v6.4.0) doivent tourner pour
la FEAT courante, en lisant le Project Config + les stacks actifs +
l'état runtime du workspace.

Phases gérées :
    - threat_model        (security-reviewer mode threat-model, pré-dev)
    - a11y_audit          (accessibility-auditor, post-dev frontend)
    - code_review         (code-reviewer, post-dev)
    - security_scan       (security-reviewer mode scan, post-dev)
    - perf_audit          (performance-auditor, post-qa)

Logique de skip :
    1. Mode global = `off` → phase désactivée
    2. Mode = `manual` → phase désactivée (Tech Lead invoque à la demande)
    3. Stack-conditional :
        - a11y_audit : skip si pas de stack frontend actif
        - threat_model + security_scan : skip A03 SQL si pas de stack backend
          (mais l'agent reste invocable)
        - perf_audit : auto-invoke uniquement si PerfMode=full (opt-in strict)
    4. Stack-content conditional :
        - perf_audit : si une AC d'US mentionne explicitement LCP/p95/etc.,
          force enable même en mode manual

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

from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.project_config import read_project_config  # noqa: E402  (legacy fallback)
from sdd_lib.layered_config import ConfigError, read_layered_config  # noqa: E402  (v6.7.3)


PROJECT_CONFIG_KEYS = (
    # v6.3.x + v6.4.0 auditor modes
    "A11yMode",
    "A11yFailOn",
    "CodeReviewMode",
    "CodeReviewFailOn",
    "SecurityMode",
    "SecurityThreatModelEnabled",
    "SecurityScanEnabled",
    "SecurityFailOn",
    "PerfMode",
    "PerfFailOn",
    # v6.5.2 spec-compliance-reviewer
    "SpecComplianceMode",
    "SpecComplianceFailOn",
    # Stacks
    "AppName",
    "BackendName",
)

# Coûts tokens estimés par phase (cf. agents/*.md "Token footprint cible")
PHASE_COST_ESTIMATE = {
    "threat_model": 7_000,    # security-reviewer mode threat-model
    "a11y_audit": 3_000,      # accessibility-auditor (Haiku)
    "code_review": 12_000,    # code-reviewer
    "security_scan": 15_000,  # security-reviewer mode scan
    "perf_audit": 14_000,     # performance-auditor (avec Lighthouse opt-in)
    "spec_compliance": 12_000,  # spec-compliance-reviewer (v6.5.2)
}

# Modes valides par phase
VALID_MODES = {"off", "full", "manual"}

# Regex pour détecter mentions perf dans ACs
PERF_AC_HINTS = re.compile(
    r"\b(lcp|cls|inp|fid|ttfb|p95|p99|latency|core web vitals|"
    r"bundle\s+size|page\s+load|response\s+time|throughput|qps|rps)\b",
    re.IGNORECASE,
)

# Regex pour détecter mentions security dans ACs (override threat-model si "manual")
SECURITY_AC_HINTS = re.compile(
    r"\b(owasp|xss|sql\s+injection|csrf|jwt|secret|password\s+policy|"
    r"rate\s+limit|brute\s+force|encrypted|hashing|salt|hsts|csp)\b",
    re.IGNORECASE,
)


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


def _active_stacks(root: Path) -> dict[str, str | None]:
    """Détecte les stacks actifs depuis ## Active Tech Specs + UI + Auth de stack.md."""
    stack_md = root / "workspace" / "input" / "stack" / "stack.md"
    if not stack_md.is_file():
        return {"backend": None, "frontend": None, "ui": None, "auth": None, "fullstack": None, "mobiles": None}
    try:
        text = stack_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
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

    a11y_mode = _normalize_mode(config.get("A11yMode"), default="full")
    code_review_mode = _normalize_mode(config.get("CodeReviewMode"), default="manual")
    security_mode = _normalize_mode(config.get("SecurityMode"), default="manual")
    perf_mode = _normalize_mode(config.get("PerfMode"), default="full")
    spec_compliance_mode = _normalize_mode(config.get("SpecComplianceMode"), default="manual")
    security_threat_model_enabled = _bool_flag(config.get("SecurityThreatModelEnabled"), default=True)
    security_scan_enabled = _bool_flag(config.get("SecurityScanEnabled"), default=True)

    app_name = config.get("AppName")
    backend_name = config.get("BackendName")

    # 2. Stacks actifs
    stacks = _active_stacks(root)

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
    has_perf_ac = bool(PERF_AC_HINTS.search(combined_text))
    has_security_ac = bool(SECURITY_AC_HINTS.search(combined_text))

    # 5. Construction des phases
    phases: dict[str, dict[str, object]] = {}

    # --- threat_model (pré-dev) ---
    phases["threat_model"] = _decide_threat_model(
        security_mode=security_mode,
        threat_model_enabled=security_threat_model_enabled,
        has_security_ac=has_security_ac,
        stacks=stacks,
    )

    # --- a11y_audit (post-dev frontend) ---
    # v6.7.5 : fullstack/mobile projects ont aussi une UI a auditer.
    # mobile-maui : UI XAML pas auditable WCAG (pas de markup HTML).
    # mobile-react-native : pas de markup HTML auditable.
    # fullstack (next/nuxt/angular-universal/blazor-server/node-react/kotlin-mustache) : oui, ont du HTML rendu.
    fullstack_has_html_ui = stacks.get("fullstack") is not None
    has_ui_to_audit = (
        stacks.get("frontend") is not None
        or fullstack_has_html_ui
    )
    phases["a11y_audit"] = _decide_a11y(
        a11y_mode=a11y_mode,
        has_frontend_stack=has_ui_to_audit,
        has_frontend_code=has_frontend_code,
    )

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

    # --- perf_audit (post-qa) ---
    phases["perf_audit"] = _decide_perf(
        perf_mode=perf_mode,
        has_perf_ac=has_perf_ac,
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
            "A11yMode": a11y_mode,
            "CodeReviewMode": code_review_mode,
            "SecurityMode": security_mode,
            "SecurityThreatModelEnabled": security_threat_model_enabled,
            "SecurityScanEnabled": security_scan_enabled,
            "PerfMode": perf_mode,
            "SpecComplianceMode": spec_compliance_mode,
        },
        "runtime_state": {
            "has_frontend_code": has_frontend_code,
            "has_backend_code": has_backend_code,
            "us_count": len(us_contents),
            "has_perf_ac": has_perf_ac,
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


def _decide_threat_model(
    *,
    security_mode: str,
    threat_model_enabled: bool,
    has_security_ac: bool,
    stacks: dict[str, str | None],
) -> dict[str, object]:
    if security_mode == "off":
        return _phase("threat_model", enabled=False, reason="SecurityMode=off")
    if security_mode == "manual" and not has_security_ac:
        return _phase(
            "threat_model",
            enabled=False,
            reason="SecurityMode=manual + no AC mentions security (lcp/owasp/jwt/...)",
        )
    if not threat_model_enabled:
        return _phase("threat_model", enabled=False, reason="SecurityThreatModelEnabled=false")
    # v6.7.5 : fullstack et mobile projects ont aussi une surface d'attaque (auth, API distante, etc.)
    if (
        stacks.get("backend") is None
        and stacks.get("frontend") is None
        and stacks.get("fullstack") is None
        and stacks.get("mobiles") is None
    ):
        return _phase("threat_model", enabled=False, reason="no backend/frontend/fullstack/mobiles stack active")
    return _phase("threat_model", enabled=True, reason=None)


def _decide_a11y(
    *,
    a11y_mode: str,
    has_frontend_stack: bool,
    has_frontend_code: bool,
) -> dict[str, object]:
    if a11y_mode == "off":
        return _phase("a11y_audit", enabled=False, reason="A11yMode=off")
    if a11y_mode == "manual":
        return _phase("a11y_audit", enabled=False, reason="A11yMode=manual (Tech Lead invoque à la demande)")
    if not has_frontend_stack:
        return _phase("a11y_audit", enabled=False, reason="no frontend stack active (backend-only project)")
    if not has_frontend_code:
        return _phase("a11y_audit", enabled=False, reason="workspace/output/src/{AppName}/ absent ou vide (markup pas généré)")
    return _phase("a11y_audit", enabled=True, reason=None)


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


def _decide_perf(
    *,
    perf_mode: str,
    has_perf_ac: bool,
    has_backend_code: bool,
    has_frontend_code: bool,
) -> dict[str, object]:
    if perf_mode == "off":
        return _phase("perf_audit", enabled=False, reason="PerfMode=off")
    if perf_mode == "manual" and not has_perf_ac:
        return _phase(
            "perf_audit",
            enabled=False,
            reason="PerfMode=manual + no AC mentions perf metric (lcp/p95/...)",
        )
    if perf_mode == "manual" and has_perf_ac:
        # Override : AC explicite force l'invocation même en manual
        return _phase(
            "perf_audit",
            enabled=True,
            reason="forced by explicit perf metric in AC (PerfMode=manual override)",
        )
    if not has_backend_code and not has_frontend_code:
        return _phase("perf_audit", enabled=False, reason="aucun code production (/dev-run pas exécuté)")
    return _phase("perf_audit", enabled=True, reason=None)


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
        return 1
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"[ERROR] I/O: {exc}\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"[STACK_MALFORMED] {exc}\n")
        return 2

    if "error" in result:
        sys.stderr.write(f"{result['error']}\n")
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        return 2 if "STACK_MALFORMED" in str(result.get("error", "")) else 1

    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
