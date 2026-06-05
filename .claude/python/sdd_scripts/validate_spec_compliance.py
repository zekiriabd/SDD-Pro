#!/usr/bin/env python3
"""SDD_Pro spec-compliance report validator (déterministe, 0 token LLM).

Validates the JSON output of agent `spec-compliance-reviewer`:
    workspace/output/.sys/.validation/{n}-spec-compliance.json

Checks:
    1. JSON parseable
    2. Required top-level keys present (feat, summary, us)
    3. summary.verdict is one of the 3 valid enums
    4. summary.total_acs == sum(issues) + verified  (arithmetic consistency)
    5. Each AC has required fields (ac_id, ac_text, class, status, severity if not verified)
    6. Each AC with status=verified has non-null evidence.file
    7. Verdict matches SpecComplianceFailOn threshold

Exit codes:
    0 : valid + verdict GREEN
    1 : valid + verdict WARN
    2 : invalid (corrupted JSON, missing fields, inconsistent counts, etc.)

Usage:
    python validate_spec_compliance.py --feat N [--json]
    python validate_spec_compliance.py --report-path PATH [--json]

Companion to `.claude/agents/spec-compliance-reviewer.md` STEP 10.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.project_config import read_project_config  # noqa: E402  (legacy fallback)
from sdd_lib.layered_config import read_layered_config  # noqa: E402  (v6.7.3)
from sdd_lib.exit_codes import CORRECTIBLE  # noqa: E402


VALID_VERDICTS = {"🟢 GREEN", "🟡 WARN", "🔴 RED"}
VALID_AC_CLASSES = {"testable_strict", "testable_soft", "ambiguous", "ui_only"}
VALID_AC_STATUSES = {"verified", "not_verified", "partial", "ambiguous", "ui_present"}
VALID_SEVERITIES = {"critical", "serious", "moderate", "minor"}
VALID_FAIL_ON = {"critical", "serious", "moderate", "minor"}
SEVERITY_ORDER = ("critical", "serious", "moderate", "minor")


class ValidationError(Exception):
    """Carries the canonical 3-line ERROR/CAUSE/FIX format."""

    def __init__(self, error: str, cause: str, fix: str):
        super().__init__(cause)
        self.error = error
        self.cause = cause
        self.fix = fix


def _require_key(d: Any, key: str, context: str) -> Any:
    if not isinstance(d, dict) or key not in d:
        raise ValidationError(
            f"spec-compliance report invalid",
            f"[QA_OUTPUT_INVALID] champ '{key}' manquant dans {context}",
            f"l'agent spec-compliance-reviewer doit émettre {key} (cf. STEP 7.3 schema)",
        )
    return d[key]


def _validate_summary(summary: dict[str, Any], total_in_us: int, issues_in_us: dict[str, int],
                      verified_in_us: int) -> None:
    verdict = _require_key(summary, "verdict", "summary")
    if verdict not in VALID_VERDICTS:
        raise ValidationError(
            "spec-compliance report invalid",
            f"[QA_OUTPUT_INVALID] summary.verdict='{verdict}' invalide "
            f"(attendu un de {sorted(VALID_VERDICTS)})",
            "corriger summary.verdict dans le JSON",
        )

    total = _require_key(summary, "total_acs", "summary")
    verified = _require_key(summary, "verified", "summary")
    issues = _require_key(summary, "issues", "summary")

    if not isinstance(total, int) or not isinstance(verified, int):
        raise ValidationError(
            "spec-compliance report invalid",
            "[QA_OUTPUT_INVALID] summary.total_acs et summary.verified doivent être int",
            "corriger les types dans le JSON",
        )

    sum_issues = sum(int(issues.get(s, 0)) for s in VALID_SEVERITIES)
    if total != sum_issues + verified:
        raise ValidationError(
            "spec-compliance report invalid",
            f"[QA_OUTPUT_INVALID] summary.total_acs={total} ≠ "
            f"sum(issues)={sum_issues} + verified={verified}",
            "corriger le calcul ou les compteurs dans le JSON",
        )

    # Cross-check vs us[].acs[]
    if total_in_us != total:
        raise ValidationError(
            "spec-compliance report invalid",
            f"[QA_OUTPUT_INVALID] summary.total_acs={total} ≠ "
            f"count(us[].acs[])={total_in_us}",
            "corriger les compteurs ou les listes dans le JSON",
        )
    if verified_in_us != verified:
        raise ValidationError(
            "spec-compliance report invalid",
            f"[QA_OUTPUT_INVALID] summary.verified={verified} ≠ "
            f"count(acs with status=verified)={verified_in_us}",
            "corriger les compteurs ou les statuts dans le JSON",
        )
    for sev in VALID_SEVERITIES:
        if issues_in_us.get(sev, 0) != int(issues.get(sev, 0)):
            raise ValidationError(
                "spec-compliance report invalid",
                f"[QA_OUTPUT_INVALID] summary.issues.{sev}={issues.get(sev, 0)} ≠ "
                f"observed={issues_in_us.get(sev, 0)}",
                "corriger les compteurs par sévérité",
            )


def _validate_ac(ac: dict[str, Any], us_id: str) -> tuple[str, str | None]:
    """Validate one AC entry. Returns (status, severity_or_none)."""
    ac_id = _require_key(ac, "ac_id", f"us {us_id}")
    _require_key(ac, "ac_text", f"ac {ac_id}")
    ac_class = _require_key(ac, "class", f"ac {ac_id}")
    status = _require_key(ac, "status", f"ac {ac_id}")

    if ac_class not in VALID_AC_CLASSES:
        raise ValidationError(
            "spec-compliance report invalid",
            f"[QA_OUTPUT_INVALID] ac {ac_id}.class='{ac_class}' invalide "
            f"(attendu un de {sorted(VALID_AC_CLASSES)})",
            "corriger ac.class",
        )
    if status not in VALID_AC_STATUSES:
        raise ValidationError(
            "spec-compliance report invalid",
            f"[QA_OUTPUT_INVALID] ac {ac_id}.status='{status}' invalide "
            f"(attendu un de {sorted(VALID_AC_STATUSES)})",
            "corriger ac.status",
        )

    severity: str | None = None
    if status == "verified":
        evidence = ac.get("evidence")
        if not isinstance(evidence, dict) or not evidence.get("file"):
            raise ValidationError(
                "spec-compliance report invalid",
                f"[QA_OUTPUT_INVALID] ac {ac_id}.status='verified' "
                "mais evidence.file manquant",
                "fournir evidence.file (path) + evidence.lines pour chaque AC verified",
            )
    elif status in ("not_verified", "partial"):
        severity = ac.get("severity")
        if severity not in VALID_SEVERITIES:
            raise ValidationError(
                "spec-compliance report invalid",
                f"[QA_OUTPUT_INVALID] ac {ac_id}.status='{status}' "
                f"requires valid severity, got {severity!r}",
                f"fournir severity dans {sorted(VALID_SEVERITIES)}",
            )

    return status, severity


def _expected_verdict(
    issues: dict[str, int], fail_on: str, has_any_issue: bool
) -> str:
    if fail_on not in VALID_FAIL_ON:
        # No threshold check possible — default to permissive
        return "🟡 WARN" if has_any_issue else "🟢 GREEN"
    fail_idx = SEVERITY_ORDER.index(fail_on)
    for i, sev in enumerate(SEVERITY_ORDER):
        if i > fail_idx:
            break
        if issues.get(sev, 0) > 0:
            return "🔴 RED"
    return "🟡 WARN" if has_any_issue else "🟢 GREEN"


def validate_report(
    report: dict[str, Any], fail_on: str | None = None
) -> tuple[int, dict[str, Any]]:
    """Validate a parsed JSON report. Returns (exit_code, info_dict).

    exit_code:
        0 = valid + verdict GREEN
        1 = valid + verdict WARN
        2 = invalid (caller should print info_dict['error_block'])
    """
    try:
        _require_key(report, "feat", "report root")
        _require_key(report, "summary", "report root")
        us_list = _require_key(report, "us", "report root")
        if not isinstance(us_list, list):
            raise ValidationError(
                "spec-compliance report invalid",
                "[QA_OUTPUT_INVALID] champ 'us' doit être une liste",
                "corriger le type de 'us' dans le JSON",
            )

        total_in_us = 0
        verified_in_us = 0
        issues_in_us = {s: 0 for s in VALID_SEVERITIES}

        for us in us_list:
            us_id = _require_key(us, "us_id", "us entry")
            acs = _require_key(us, "acs", f"us {us_id}")
            if not isinstance(acs, list):
                raise ValidationError(
                    "spec-compliance report invalid",
                    f"[QA_OUTPUT_INVALID] us {us_id}.acs doit être une liste",
                    "corriger le type",
                )
            for ac in acs:
                status, severity = _validate_ac(ac, us_id)
                total_in_us += 1
                if status == "verified":
                    verified_in_us += 1
                elif severity is not None:
                    issues_in_us[severity] += 1
                elif status == "ambiguous":
                    issues_in_us["minor"] += 1
                elif status == "ui_present":
                    issues_in_us["minor"] += 1

        summary = report["summary"]
        _validate_summary(summary, total_in_us, issues_in_us, verified_in_us)

        # Verdict consistency (only if we have a fail_on to compare against)
        if fail_on is None:
            cfg = report.get("config", {})
            fail_on = cfg.get("fail_on")

        if fail_on:
            has_issue = sum(issues_in_us.values()) > 0
            expected = _expected_verdict(summary["issues"], fail_on, has_issue)
            if expected != summary["verdict"]:
                raise ValidationError(
                    "spec-compliance report invalid",
                    f"[QA_OUTPUT_INVALID] verdict='{summary['verdict']}' "
                    f"incohérent avec issues+SpecComplianceFailOn='{fail_on}' "
                    f"(attendu '{expected}')",
                    "régénérer le rapport ou ajuster le seuil SpecComplianceFailOn",
                )

        verdict = summary["verdict"]
        exit_code = 0 if verdict == "🟢 GREEN" else (1 if verdict == "🟡 WARN" else 2)
        return exit_code, {
            "verdict": verdict,
            "total_acs": summary["total_acs"],
            "verified": summary["verified"],
            "issues": summary["issues"],
        }

    except ValidationError as e:
        return 2, {
            "error_block": (
                f"ERROR: {e.error}\n"
                f"CAUSE: {e.cause}\n"
                f"FIX: {e.fix}\n"
            )
        }


def _load_report_for_feat(root: Path, feat: int) -> tuple[Path, dict[str, Any]]:
    path = root / "workspace" / "output" / ".sys" / ".validation" / f"{feat}-spec-compliance.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"[QA_PRECONDITION_FAILED] rapport absent: {path}"
        )
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValidationError(
            "spec-compliance report invalid",
            f"[QA_OUTPUT_INVALID] JSON corrompu dans {path.name}: {e.msg} "
            f"(ligne {e.lineno})",
            "régénérer le rapport via /spec-compliance {feat}",
        ) from e


def _fail_on_from_config(root: Path) -> str | None:
    # v6.7.3: prefer layered config (base + team + project)
    try:
        cfg = read_layered_config(root=root, keys=("SpecComplianceFailOn",))
        if cfg.get("SpecComplianceFailOn"):
            return cfg["SpecComplianceFailOn"]
    except Exception:  # noqa: BLE001
        pass
    # Fallback to legacy project-only read for backward-compat
    try:
        cfg = read_project_config(root=root, keys=("SpecComplianceFailOn",))
        return cfg.get("SpecComplianceFailOn")
    except Exception:  # noqa: BLE001
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_spec_compliance",
        description="Validate spec-compliance-reviewer JSON output",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--feat", type=int, help="FEAT number (derive report path)")
    g.add_argument("--report-path", type=Path, help="Explicit JSON report path")
    parser.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    parser.add_argument(
        "--fail-on",
        choices=sorted(VALID_FAIL_ON),
        default=None,
        help="Override SpecComplianceFailOn from Project Config",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    fail_on = args.fail_on or _fail_on_from_config(root) or "serious"

    try:
        if args.feat is not None:
            path, report = _load_report_for_feat(root, args.feat)
        else:
            path = args.report_path
            if not path.is_file():
                sys.stderr.write(f"[QA_PRECONDITION_FAILED] {path} introuvable\n")
                return CORRECTIBLE
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                sys.stderr.write(
                    f"ERROR: spec-compliance report invalid\n"
                    f"CAUSE: [QA_OUTPUT_INVALID] JSON corrompu: {e.msg} (ligne {e.lineno})\n"
                    f"FIX: régénérer le rapport\n"
                )
                return CORRECTIBLE
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return CORRECTIBLE
    except ValidationError as e:
        sys.stderr.write(f"ERROR: {e.error}\nCAUSE: {e.cause}\nFIX: {e.fix}\n")
        return CORRECTIBLE
    exit_code, info = validate_report(report, fail_on=fail_on)

    if exit_code == 2:
        sys.stderr.write(info.get("error_block", "[QA_OUTPUT_INVALID] unknown\n"))
        if args.json:
            sys.stdout.write(json.dumps(info, ensure_ascii=False) + "\n")
        return CORRECTIBLE
    if args.json:
        sys.stdout.write(
            json.dumps(
                {"path": str(path), "exit_code": exit_code, **info},
                ensure_ascii=False,
                indent=2,
            ) + "\n"
        )
    else:
        verdict = info.get("verdict", "?")
        total = info.get("total_acs", 0)
        verified = info.get("verified", 0)
        sys.stdout.write(
            f"spec-compliance {path.name}: {verdict} "
            f"({verified}/{total} ACs verified)\n"
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
