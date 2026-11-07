#!/usr/bin/env python3
"""SDD_Pro — CLI de la gate de livraison fondée sur des preuves (audit 2026-11-07).

Sous-commandes :
    authorize --feat-number N --workflow W [--run-id R] [--json]
        exit 0 autorisé ; exit 2 bloqué (ERROR 3L ``[DELIVERY_GATE_BLOCKED]``).
    requirements --workflow W [--json]
        liste les checks obligatoires du workflow (SSoT
        ``sdd_lib.delivery_gate.WORKFLOW_REQUIREMENTS``).
    record-spec --feat-number N [--report PATH] [--run-id R]
        LIT le rapport du reviewer spec-compliance
        (``workspace/.sys/.validation/{n}-spec-compliance.json``) et enregistre
        ``check='spec_compliance'`` — passé seulement si verdict GREEN, ou
        YELLOW sans finding au niveau ``fail_on`` ou au-dessus, et ≥ 1 AC.
    record-readiness --feat-number N [--run-id R]
        EXÉCUTE ``validate_readiness.py --json`` et enregistre
        ``check='readiness'`` sur l'empreinte des entrées (FEAT, US, mockups,
        stack.md, constitution). Un NO-GO ne se lève que par un changement des
        entrées (même règle d'instabilité que build/tests).

Volontairement ABSENT : toute sous-commande acceptant ``passed`` /
``exit_code`` en argument, et tout flag force / allow-warn. Les variables
``SDD_ALLOW_*`` / ``SDD_BYPASS_*`` / ``SDD_FORCE*`` sont ignorées ; leur
présence est consignée (raison + ``delivery-gate.jsonl``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib import delivery_gate as dg  # noqa: E402
from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root, workspace_root  # noqa: E402

#: Exit « bloqué » du contrat (= CORRECTIBLE : corriger puis re-vérifier).
EXIT_BLOCKED = CORRECTIBLE

_SEVERITIES = ("minor", "moderate", "serious", "critical")


def _err(msg: str) -> None:
    sys.stderr.write(msg.rstrip("\n") + "\n")


# ---------------------------------------------------------------------------
# authorize / requirements
# ---------------------------------------------------------------------------

def cmd_authorize(args: argparse.Namespace) -> int:
    dec = dg.authorize_delivery(feat_n=args.feat_number, workflow=args.workflow,
                                run_id=args.run_id, project_roots=dg.default_project_roots())
    if args.json:
        print(json.dumps(dec.to_dict(), ensure_ascii=False, indent=2))
    if dec.allowed:
        if not args.json:
            print(f"delivery-gate feat {args.feat_number} workflow {args.workflow} : autorisé "
                  f"({', '.join(dec.required)})")
        for r in dec.reasons:
            _err(f"WARN: {r}")
        return SUCCESS
    _err(dg.format_error_3l(dec, args.feat_number))
    return EXIT_BLOCKED


def cmd_requirements(args: argparse.Namespace) -> int:
    req = dg.WORKFLOW_REQUIREMENTS.get(args.workflow)
    if req is None:
        _err(f"ERROR: delivery-gate requirements failed\n"
             f"CAUSE: [{dg.ERROR_CLASS}] workflow inconnu {args.workflow!r}\n"
             f"FIX: utiliser l'un de {', '.join(sorted(dg.WORKFLOW_REQUIREMENTS))}")
        return EXIT_BLOCKED
    if args.json:
        print(json.dumps({"workflow": args.workflow, "required": list(req)}))
    else:
        print("\n".join(req))
    return SUCCESS


# ---------------------------------------------------------------------------
# record-spec
# ---------------------------------------------------------------------------

def _normalize_verdict(raw: object) -> str:
    m = re.search(r"GREEN|YELLOW|RED", str(raw or "").upper())
    return m.group(0) if m else "UNKNOWN"


def evaluate_spec_report(payload: dict, feat_n: int) -> tuple[bool, dict]:
    """Évalue un rapport spec-compliance (format réel : summary.verdict / issues)."""
    summary = payload.get("summary") or {}
    config = payload.get("config") or {}
    verdict = _normalize_verdict(summary.get("verdict"))
    fail_on = str(config.get("fail_on") or "serious").lower()
    if fail_on not in _SEVERITIES:
        fail_on = "serious"
    issues = summary.get("issues") or {}
    blocking = sum(int(issues.get(s, 0) or 0) for s in _SEVERITIES[_SEVERITIES.index(fail_on):])
    total_acs = int(summary.get("total_acs", 0) or 0)
    details = {"verdict": verdict, "fail_on": fail_on, "issues": issues,
               "blocking_findings": blocking, "total_acs": total_acs,
               "verified": summary.get("verified"), "report_feat": payload.get("feat")}
    reason = None
    try:
        report_feat = int(payload.get("feat"))
    except (TypeError, ValueError):
        report_feat = None
    if report_feat != feat_n:
        reason = f"rapport de la FEAT {payload.get('feat')!r}, attendu {feat_n}"
    elif verdict not in ("GREEN", "YELLOW"):
        reason = f"verdict {verdict}"
    elif blocking:
        reason = f"{blocking} finding(s) ≥ {fail_on}"
    elif total_acs <= 0:
        reason = "0 AC vérifiée — conformité vide"
    if reason:
        details["reason"] = reason
    return reason is None, details


def cmd_record_spec(args: argparse.Namespace) -> int:
    root = repo_root()
    ws = workspace_root(root)
    report = Path(args.report) if args.report else (
        ws / ".sys" / ".validation" / f"{args.feat_number}-spec-compliance.json")
    if not report.is_absolute():
        report = (root / report).resolve()
    ignored = dg.note_ignored_bypass_env("delivery_gate.py:record-spec", feat_n=args.feat_number)
    exit_code = 0
    try:
        raw = report.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("JSON racine non objet")
        passed, details = evaluate_spec_report(payload, args.feat_number)
        details["report_sha256"] = hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError) as e:
        passed, exit_code = False, 1
        details = {"reason": f"rapport illisible : {type(e).__name__}: {e}"}
    details.update({"report": str(report), "ignored_bypass_env": ignored})
    try:
        ev = dg._record_evidence(  # noqa: SLF001 — producteur légitime
            feat_n=args.feat_number, check="spec_compliance", run_id=args.run_id,
            passed=passed, exit_code=exit_code, command=f"read {report.name}", details=details,
            tree_hash=dg.compute_tree_hash(dg.default_project_roots(root)),
            producer="delivery_gate.py:record-spec")
    except Exception as e:  # noqa: BLE001
        _err(f"ERROR: delivery-gate record-spec feat {args.feat_number} failed\n"
             f"CAUSE: [INFRA_BLOCKED] {type(e).__name__}: {e}\n"
             f"FIX: vérifier console.db et la clé ~/.sdd/{dg.KEY_FILENAME}")
        return INFRA_BLOCKED
    print(json.dumps({"check": "spec_compliance", "passed": passed, "evidence_id": ev,
                      "verdict": details.get("verdict")}, ensure_ascii=False))
    if passed:
        return SUCCESS
    _err(f"ERROR: delivery-gate record-spec feat {args.feat_number} failed\n"
         f"CAUSE: [SPEC_COMPLIANCE_RED] {details.get('reason')}\n"
         f"FIX: corriger les AC non conformes puis relancer le reviewer spec-compliance")
    return EXIT_BLOCKED


# ---------------------------------------------------------------------------
# record-readiness
# ---------------------------------------------------------------------------

def _run_readiness(feat_n: int) -> tuple[int, dict, str]:
    """EXÉCUTE validate_readiness.py --json ; retourne (exit, payload, commande)."""
    script = Path(__file__).resolve().parent / "validate_readiness.py"
    cmd = [sys.executable, str(script), "--feat-number", str(feat_n), "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    try:
        payload = json.loads(proc.stdout or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except ValueError:
        payload = {}
    if not payload:
        payload = {"decision": "UNKNOWN", "stderr_tail": (proc.stderr or "")[-800:]}
    return proc.returncode, payload, f"validate_readiness.py --feat-number {feat_n} --json"


def cmd_record_readiness(args: argparse.Namespace) -> int:
    ignored = dg.note_ignored_bypass_env("delivery_gate.py:record-readiness",
                                         feat_n=args.feat_number)
    before = dg.compute_readiness_hash(args.feat_number)
    try:
        exit_code, payload, command = _run_readiness(args.feat_number)
    except (OSError, subprocess.SubprocessError) as e:
        exit_code, payload, command = 126, {"decision": "UNKNOWN", "error": str(e)}, \
            "validate_readiness.py"
    after = dg.compute_readiness_hash(args.feat_number)
    decision = str(payload.get("decision", "UNKNOWN")).upper()
    details = {"decision": decision, "errors": payload.get("errors", []),
               "warnings": len(payload.get("warnings", []) or []),
               "inputs": [p.name for p in dg.readiness_inputs(args.feat_number)],
               "ignored_bypass_env": ignored}
    passed = exit_code == 0 and decision in ("GO", "WARN")
    if before != after:
        passed = False
        details["reason"] = "entrées FEAT/US modifiées pendant la validation"
    elif not passed:
        details["reason"] = f"readiness {decision} (exit {exit_code})"
    try:
        ev = dg._record_evidence(  # noqa: SLF001 — producteur légitime
            feat_n=args.feat_number, check="readiness", run_id=args.run_id, passed=passed,
            exit_code=exit_code, command=command, details=details, tree_hash=after,
            producer="delivery_gate.py:record-readiness")
    except Exception as e:  # noqa: BLE001
        _err(f"ERROR: delivery-gate record-readiness feat {args.feat_number} failed\n"
             f"CAUSE: [INFRA_BLOCKED] {type(e).__name__}: {e}\n"
             f"FIX: vérifier console.db et la clé ~/.sdd/{dg.KEY_FILENAME}")
        return INFRA_BLOCKED
    print(json.dumps({"check": "readiness", "passed": passed, "decision": decision,
                      "evidence_id": ev}, ensure_ascii=False))
    if passed:
        return SUCCESS
    _err(f"ERROR: delivery-gate record-readiness feat {args.feat_number} failed\n"
         f"CAUSE: [READINESS_NO_GO] {details.get('reason')}\n"
         f"FIX: corriger la FEAT / les US (seul un changement des entrées lève un NO-GO)")
    return EXIT_BLOCKED


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Gate de livraison fondée sur des preuves.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("authorize", help="décision de livraison (0 autorisé, 2 bloqué)")
    a.add_argument("--feat-number", type=int, required=True)
    a.add_argument("--workflow", required=True)
    a.add_argument("--run-id", default=None)
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_authorize)

    r = sub.add_parser("requirements", help="checks obligatoires d'un workflow")
    r.add_argument("--workflow", required=True)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_requirements)

    s = sub.add_parser("record-spec", help="lit le rapport spec-compliance du reviewer")
    s.add_argument("--feat-number", type=int, required=True)
    s.add_argument("--report", default=None)
    s.add_argument("--run-id", default=None)
    s.set_defaults(func=cmd_record_spec)

    d = sub.add_parser("record-readiness", help="exécute validate_readiness.py")
    d.add_argument("--feat-number", type=int, required=True)
    d.add_argument("--run-id", default=None)
    d.set_defaults(func=cmd_record_readiness)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.func(args))
    except dg.DeliveryGateError as e:
        _err(f"ERROR: delivery-gate {args.cmd} failed\n"
             f"CAUSE: [INFRA_BLOCKED] {e}\nFIX: vérifier ~/.sdd/{dg.KEY_FILENAME}")
        return INFRA_BLOCKED if args.cmd != "authorize" else EXIT_BLOCKED
    except KeyboardInterrupt:
        return FAIL_FAST


if __name__ == "__main__":
    sys.exit(main())
