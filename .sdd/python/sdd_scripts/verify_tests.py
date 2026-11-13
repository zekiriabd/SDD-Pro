#!/usr/bin/env python3
"""SDD_Pro — exécution INDÉPENDANTE des tests (+ couverture) pour la gate de livraison.

Usage :
    python verify_tests.py --feat-number N [--run-id R] [--coverage] [--timeout S]

Le script crée lui-même un dossier temporaire de résultats, EXÉCUTE les
tests en y faisant écrire un rapport TRX (.NET) ou JUnit XML, puis lit ce
rapport (jamais un compte rendu d'agent). Preuve ``tests`` passée ⇔ exit 0
ET rapport trouvé ET ``executed > 0`` ET ``failed == 0`` — des tests tous
ignorés (skipped) = 0 exécuté = échec. Le sha256 de chaque rapport est
consigné dans la preuve.

``--coverage`` enregistre aussi ``check='coverage'`` à partir d'un rapport
Cobertura (``coverage.cobertura.xml`` / ``coverage.xml``) produit dans le même
dossier, comparé à ``CoverageMin`` (layered config). Couverture non mesurée
ou ``CoverageMin`` absent → ``passed=False`` — jamais vrai par défaut.

Commande :
  - ``DeliveryGate.TestCommand`` (``## Project Config``) — exécutée (shell)
    depuis ``workspace/src`` ; le jeton ``{results_dir}`` est remplacé par le
    dossier temporaire où le rapport DOIT être écrit ;
  - sinon : ``*.slnx/*.sln`` → ``dotnet test <sln> --logger trx
    --results-directory {results_dir}`` (+ ``--collect "XPlat Code Coverage"``) ;
    Python avec ``tests/`` → ``pytest --junitxml`` (+ ``--cov-report xml``).

Aucun flag force / allow-warn. Exit : 0 vérifié, 2 échec (preuve
d'échec enregistrée), 3 infrastructure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib import delivery_gate as dg  # noqa: E402
from sdd_lib.exit_codes import CORRECTIBLE, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root, workspace_root  # noqa: E402

PRODUCER = "verify_tests.py"
DEFAULT_TIMEOUT = 1800


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tests réels + preuve signée (delivery gate).")
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument("--run-id", default=None)
    p.add_argument("--coverage", action="store_true",
                   help="enregistre aussi la preuve 'coverage' (seuil CoverageMin)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    return p.parse_args(argv)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_trx(path: Path) -> dict[str, int]:
    """Compteurs d'un TRX (ResultSummary/Counters)."""
    root = ET.parse(path).getroot()
    for el in root.iter():
        if _local(el.tag) == "Counters":
            a = {k: int(v) for k, v in el.attrib.items() if v.lstrip("-").isdigit()}
            failed = sum(a.get(k, 0) for k in ("failed", "error", "timeout", "aborted"))
            total = a.get("total", 0)
            not_exec = a.get("notExecuted", 0)
            executed = a.get("executed", max(total - not_exec, 0))
            return {"total": total, "executed": executed, "passed": a.get("passed", 0),
                    "failed": failed, "skipped": not_exec}
    raise ValueError("TRX sans ResultSummary/Counters")


def parse_junit(path: Path) -> dict[str, int]:
    """Compteurs d'un JUnit XML (somme des <testsuite> feuilles)."""
    root = ET.parse(path).getroot()
    suites = [el for el in root.iter() if _local(el.tag) == "testsuite"
              and not any(_local(c.tag) == "testsuite" for c in el)]
    if not suites:
        raise ValueError("JUnit sans <testsuite>")
    tot = {"total": 0, "failed": 0, "skipped": 0}
    for s in suites:
        tot["total"] += int(s.get("tests", 0) or 0)
        tot["failed"] += int(s.get("failures", 0) or 0) + int(s.get("errors", 0) or 0)
        tot["skipped"] += int(s.get("skipped", 0) or s.get("disabled", 0) or 0)
    executed = max(tot["total"] - tot["skipped"], 0)
    return {"total": tot["total"], "executed": executed,
            "passed": max(executed - tot["failed"], 0), "failed": tot["failed"],
            "skipped": tot["skipped"]}


def parse_cobertura(path: Path) -> tuple[int, int] | None:
    """(lignes couvertes, lignes valides) d'un rapport Cobertura, ou None."""
    root = ET.parse(path).getroot()
    if _local(root.tag) != "coverage":
        return None
    covered, valid = root.get("lines-covered"), root.get("lines-valid")
    if covered is not None and valid is not None:
        return int(covered), int(valid)
    rate = root.get("line-rate")
    if rate is None:
        return None
    return int(round(float(rate) * 10000)), 10000


def _classify(path: Path) -> str | None:
    try:
        tag = _local(ET.parse(path).getroot().tag)
    except (ET.ParseError, OSError):
        return None
    if path.suffix.lower() == ".trx" or tag == "TestRun":
        return "trx"
    if tag in ("testsuites", "testsuite"):
        return "junit"
    if tag == "coverage":
        return "cobertura"
    return None


def _default_commands(src: Path, rd: Path, coverage: bool) -> list[tuple[list[str], Path]]:
    cmds: list[tuple[list[str], Path]] = []
    sln = sorted([*src.glob("*.slnx"), *src.glob("*.sln")])
    if sln:
        cmd = ["dotnet", "test", sln[0].name, "--nologo",
               "--logger", "trx;LogFileName=results.trx", "--results-directory", str(rd)]
        if coverage:
            cmd += ["--collect", "XPlat Code Coverage"]
        cmds.append((cmd, src))
    for pdir, ptype in dg.detect_projects(src):
        if ptype == "python" and (pdir / "tests").is_dir():
            cmd = [sys.executable, "-m", "pytest", "-q", f"--junitxml={rd / f'junit-{pdir.name}.xml'}"]
            if coverage:
                cmd += ["--cov=.", f"--cov-report=xml:{rd / f'coverage-{pdir.name}.xml'}"]
            cmds.append((cmd, pdir))
    return cmds


def _err(msg: str) -> None:
    sys.stderr.write(msg.rstrip("\n") + "\n")


def _coverage_threshold(root: Path) -> float | None:
    try:
        from sdd_lib.layered_config import read_layered_config
        raw = read_layered_config(root=root, keys=("CoverageMin",)).get("CoverageMin")
        return float(raw) if raw not in (None, "") else None
    except Exception:  # noqa: BLE001 — config illisible = seuil inconnu (fail-closed)
        return None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = repo_root()
    src = workspace_root(root) / "src"
    ignored = dg.note_ignored_bypass_env(PRODUCER, feat_n=args.feat_number, run_id=args.run_id)
    rd = Path(tempfile.mkdtemp(prefix="sdd-verify-tests-"))
    details: dict = {"ignored_bypass_env": ignored}
    try:
        override = dg.read_gate_command("TestCommand", root)
        exit_code, outputs, duration = 0, [], 0.0
        if not src.is_dir():
            exit_code, command = 1, "<none>"
            details["reason"] = "workspace/src absent — aucun test exécutable"
        elif override:
            command = override.replace("{results_dir}", str(rd))
            details["command_source"] = "DeliveryGate.TestCommand"
            exit_code, out, duration = dg.run_command(command, cwd=src, timeout=args.timeout)
            outputs.append(out)
        else:
            cmds = _default_commands(src, rd, args.coverage)
            details["command_source"] = "auto-detect"
            command = " && ".join(" ".join(c) for c, _ in cmds) or "<none>"
            if not cmds:
                exit_code = 1
                details["reason"] = ("aucune commande de test détectée — poser "
                                     "DeliveryGate.TestCommand (avec {results_dir})")
            for cmd, cwd in cmds:
                rc, out, dur = dg.run_command(cmd, cwd=cwd, timeout=args.timeout)
                duration += dur
                outputs.append(out)
                if rc != 0 and exit_code == 0:
                    exit_code = rc

        counts = {"total": 0, "executed": 0, "passed": 0, "failed": 0, "skipped": 0}
        reports, cov_files, parse_errors = [], [], []
        for f in sorted(p for p in rd.rglob("*") if p.is_file()):
            kind = _classify(f)
            if kind is None:
                continue
            try:
                if kind == "cobertura":
                    cov = parse_cobertura(f)
                    if cov is not None:
                        cov_files.append((f, cov))
                    continue
                c = parse_trx(f) if kind == "trx" else parse_junit(f)
            except (ET.ParseError, ValueError, OSError) as e:
                parse_errors.append(f"{f.name}: {e}")
                continue
            for k in counts:
                counts[k] += c.get(k, 0)
            reports.append({"name": f.relative_to(rd).as_posix(), "kind": kind,
                            "sha256": dg.sha256_file(f)})

        combined = hashlib.sha256("".join(r["sha256"] for r in reports).encode()).hexdigest() \
            if reports else None
        details.update({**counts, "reports": reports, "report_sha256": combined,
                        "parse_errors": parse_errors, "duration_s": round(duration, 3),
                        "output_tail": "\n".join(outputs)[-1500:]})
        passed = (exit_code == 0 and bool(reports) and counts["executed"] > 0
                  and counts["failed"] == 0)
        if not passed and "reason" not in details:
            if not reports:
                details["reason"] = "aucun rapport TRX/JUnit produit dans {results_dir}"
            elif counts["executed"] <= 0:
                details["reason"] = "0 test exécuté (tests absents ou tous ignorés)"
            elif counts["failed"]:
                details["reason"] = f"{counts['failed']} test(s) en échec"
            else:
                details["reason"] = f"exit {exit_code}"

        tree_hash = dg.compute_tree_hash([src])
        results = []
        try:
            ev = dg._record_evidence(  # noqa: SLF001 — producteur légitime
                feat_n=args.feat_number, check="tests", run_id=args.run_id, passed=passed,
                exit_code=exit_code, command=command, details=details, tree_hash=tree_hash,
                producer=PRODUCER)
            results.append(("tests", passed, ev, details.get("reason")))
            if args.coverage:
                threshold = _coverage_threshold(root)
                cov_d: dict = {"threshold": threshold, "files": [
                    {"name": f.relative_to(rd).as_posix(), "sha256": dg.sha256_file(f)}
                    for f, _ in cov_files]}
                # Périmètre FEAT (audit 2026-11-07) : même règle que
                # parse_coverage.py — code créé + méthodes `adds:` des plans.
                from sdd_scripts.parse_coverage import plan_scoped_code_files, scope_cobertura
                scope = plan_scoped_code_files(root / "workspace", args.feat_number)
                if scope:
                    # Plusieurs rapports (un par projet de tests) : fusion ligne à ligne
                    # (max des hits) au lieu d'une somme qui recompterait à 0 une ligne
                    # couverte par un autre rapport (2026-11-12).
                    merged = scope_cobertura([f for f, _ in cov_files], scope)
                    if merged:
                        cov_files = [(cov_files[0][0], (merged["covered"], merged["total"]))]
                        cov_d["scope"] = f"plans FEAT {args.feat_number} ({len(scope)} fichiers)"
                covered = sum(c for _, (c, _v) in cov_files)
                valid = sum(v for _, (_c, v) in cov_files)
                pct = round(100.0 * covered / valid, 2) if valid > 0 else None
                cov_d["coverage_pct"] = pct
                if pct is None:
                    cov_d["reason"] = "couverture non mesurable (aucun rapport Cobertura exploitable)"
                elif threshold is None:
                    cov_d["reason"] = "CoverageMin non configuré — seuil inconnu"
                elif pct < threshold:
                    cov_d["reason"] = f"couverture {pct}% < seuil {threshold}%"
                cov_passed = (pct is not None and threshold is not None and pct >= threshold
                              and exit_code == 0)
                if cov_passed is False and "reason" not in cov_d:
                    cov_d["reason"] = f"tests exit {exit_code}"
                ev2 = dg._record_evidence(  # noqa: SLF001
                    feat_n=args.feat_number, check="coverage", run_id=args.run_id,
                    passed=cov_passed, exit_code=exit_code, command=command, details=cov_d,
                    tree_hash=tree_hash, producer=PRODUCER)
                results.append(("coverage", cov_passed, ev2, cov_d.get("reason")))
        except Exception as e:  # noqa: BLE001
            _err(f"ERROR: verify_tests feat {args.feat_number} failed\n"
                 f"CAUSE: [INFRA_BLOCKED] preuve non enregistrée : {type(e).__name__}: {e}\n"
                 f"FIX: vérifier console.db et la clé ~/.sdd/{dg.KEY_FILENAME}")
            return INFRA_BLOCKED
    finally:
        shutil.rmtree(rd, ignore_errors=True)

    print(json.dumps({"results": [{"check": c, "passed": p, "evidence_id": i}
                                  for c, p, i, _ in results],
                      "executed": counts["executed"], "failed": counts["failed"],
                      "skipped": counts["skipped"]}, ensure_ascii=False))
    for check, ok, ev_id, reason in results:
        if not ok:
            cls = "QA_COVERAGE_GAP" if check == "coverage" else "QA_TEST_FAILED"
            _err(f"ERROR: verify_tests feat {args.feat_number} {check} failed\n"
                 f"CAUSE: [{cls}] {reason}\n"
                 f"FIX: corriger puis relancer verify_tests.py (preuve d'échec #{ev_id} conservée)")
    return SUCCESS if all(ok for _, ok, _, _ in results) else CORRECTIBLE


if __name__ == "__main__":
    sys.exit(main())
