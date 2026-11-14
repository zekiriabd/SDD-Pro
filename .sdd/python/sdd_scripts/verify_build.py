#!/usr/bin/env python3
"""SDD_Pro — vérification INDÉPENDANTE du build (gate de livraison, audit 2026-11-07).

Usage :
    python verify_build.py --feat-number N [--run-id R] [--timeout S]

Ce script ne croit personne : il EXÉCUTE lui-même la commande de build sur
``workspace/src``, capture l'exit code, relève APRÈS le build les artefacts
produits (chemin + sha256) et enregistre une preuve signée
``delivery_evidence(check='build')`` (cf. ``sdd_lib.delivery_gate``).

Commande :
  - ``DeliveryGate.BuildCommand`` (``## Project Config`` de stack.md) si
    posée — exécutée telle quelle (shell) depuis ``workspace/src`` ;
    ex. ``"C:\\…\\MSBuild.exe" DesktopApp.slnx -restore -m -nologo -v:minimal``
    quand ``dotnet.exe`` est inaccessible ;
  - sinon détection (même logique que ``validate_acceptance.py``) :
    ``*.slnx/*.sln`` à la racine → ``dotnet build <sln>`` ; ``*.csproj`` →
    ``dotnet build`` ; ``package.json`` (script build) → ``npm run build`` ;
    ``build.gradle(.kts)`` → ``gradlew assemble`` ; Python → ``compileall``.

Preuve ``passed`` ⇔ exit 0 ET au moins un artefact relevé. Aucun flag
force / allow-warn ; les variables ``SDD_ALLOW_*`` / ``SDD_BYPASS_*`` /
``SDD_FORCE*`` sont ignorées (présence consignée dans l'audit).

Exit : 0 build vérifié, 2 build en échec (preuve d'échec enregistrée),
3 infrastructure (console.db / clé HMAC).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib import delivery_gate as dg  # noqa: E402
from sdd_lib.exit_codes import CORRECTIBLE, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root, workspace_root  # noqa: E402

PRODUCER = "verify_build.py"
DEFAULT_TIMEOUT = 1800
_MAX_ARTIFACTS = 200


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build réel + preuve signée (delivery gate).")
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument("--run-id", default=None)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    return p.parse_args(argv)


def _default_commands(src: Path, projects: list[tuple[Path, str]]) -> list[tuple[list[str], Path]]:
    """Commandes de build par défaut (liste d'arguments, cwd)."""
    sln = sorted([*src.glob("*.slnx"), *src.glob("*.sln")])
    cmds: list[tuple[list[str], Path]] = []
    if sln:
        cmds.append((["dotnet", "build", sln[0].name, "--nologo", "-v:minimal"], src))
    for pdir, ptype in projects:
        if ptype == "dotnet" and not sln:
            cmds.append((["dotnet", "build", "--nologo", "-v:minimal"], pdir))
        elif ptype == "node":
            try:
                scripts = json.loads((pdir / "package.json").read_text(encoding="utf-8")).get("scripts", {})
            except (OSError, ValueError):
                scripts = {}
            if "build" in scripts:
                cmds.append((["npm", "run", "build"], pdir))
        elif ptype == "kotlin":
            wrapper = "gradlew.bat" if os.name == "nt" else "gradlew"
            if (pdir / wrapper).is_file():
                cmds.append(([str(pdir / wrapper), "assemble", "--quiet"], pdir))
        elif ptype == "python":
            cmds.append(([sys.executable, "-m", "compileall", "-q", "."], pdir))
    return cmds


def _collect_artifacts(src: Path, projects: list[tuple[Path, str]]) -> list[dict]:
    """Artefacts relevés APRÈS le build (chemin absolu + sha256 + taille)."""
    found: list[Path] = []
    for pdir, ptype in projects:
        if ptype == "dotnet":
            for csproj in pdir.glob("*.csproj"):
                for ext in (".dll", ".exe"):
                    found.extend(pdir.glob(f"bin/**/{csproj.stem}{ext}"))
        elif ptype == "node":
            for out in ("dist", "build"):
                found.extend(f for f in (pdir / out).rglob("*") if f.is_file())
        elif ptype == "kotlin":
            found.extend((pdir / "build" / "libs").glob("*.jar"))
        elif ptype == "python":
            found.extend(pdir.rglob("__pycache__/*.pyc"))
    uniq = sorted({f.resolve() for f in found if f.is_file()}, key=str)[:_MAX_ARTIFACTS]
    out: list[dict] = []
    for f in uniq:
        try:
            out.append({"path": str(f), "sha256": dg.sha256_file(f), "size": f.stat().st_size})
        except OSError:
            continue
    return out


def _err(msg: str) -> None:
    sys.stderr.write(msg.rstrip("\n") + "\n")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = repo_root()
    src = workspace_root(root) / "src"
    ignored = dg.note_ignored_bypass_env(PRODUCER, feat_n=args.feat_number, run_id=args.run_id)

    projects = dg.detect_projects(src)
    override = dg.read_gate_command("BuildCommand", root)
    details: dict = {"projects": [{"name": p.name, "type": t} for p, t in projects],
                     "ignored_bypass_env": ignored}

    exit_code, outputs, duration = 0, [], 0.0
    if not src.is_dir():
        exit_code, command = 1, "<none>"
        details["reason"] = "workspace/src absent — rien à construire"
    elif override:
        command = override
        details["command_source"] = "DeliveryGate.BuildCommand"
        exit_code, out, duration = dg.run_command(override, cwd=src, timeout=args.timeout)
        outputs.append(out)
    else:
        cmds = _default_commands(src, projects)
        details["command_source"] = "auto-detect"
        command = " && ".join(" ".join(c) for c, _ in cmds) or "<none>"
        if not cmds:
            exit_code = 1
            details["reason"] = ("aucune commande de build détectée — poser "
                                 "DeliveryGate.BuildCommand dans ## Project Config")
        for cmd, cwd in cmds:
            rc, out, dur = dg.run_command(cmd, cwd=cwd, timeout=args.timeout)
            duration += dur
            outputs.append(out)
            if rc != 0:
                exit_code = rc
                break

    artifacts = _collect_artifacts(src, projects) if src.is_dir() else []
    details.update({"duration_s": round(duration, 3), "artifacts": artifacts,
                    "output_tail": ("\n".join(outputs))[-1500:]})
    passed = exit_code == 0 and bool(artifacts)
    if exit_code == 0 and not artifacts:
        details["reason"] = "build exit 0 mais aucun artefact relevé (dll/exe/jar/dist/pyc)"

    tree_hash = dg.compute_tree_hash([src])
    try:
        ev_id = dg._record_evidence(  # noqa: SLF001 — producteur légitime
            feat_n=args.feat_number, check="build", run_id=args.run_id, passed=passed,
            exit_code=exit_code, command=command, details=details, tree_hash=tree_hash,
            producer=PRODUCER)
    except Exception as e:  # noqa: BLE001
        _err(f"ERROR: verify_build feat {args.feat_number} failed\n"
             f"CAUSE: [INFRA_BLOCKED] preuve non enregistrée : {type(e).__name__}: {e}\n"
             f"FIX: vérifier console.db et la clé ~/.sdd/{dg.KEY_FILENAME}")
        return INFRA_BLOCKED

    print(json.dumps({"check": "build", "passed": passed, "exit_code": exit_code,
                      "evidence_id": ev_id, "artifacts": len(artifacts),
                      "duration_s": details["duration_s"]}, ensure_ascii=False))
    if passed:
        return SUCCESS
    _err(f"ERROR: verify_build feat {args.feat_number} failed\n"
         f"CAUSE: [BUILD_BLOCKING] {details.get('reason') or f'exit {exit_code}'}\n"
         f"FIX: corriger le build puis relancer verify_build.py (preuve d'échec #{ev_id} conservée)")
    return CORRECTIBLE


if __name__ == "__main__":
    sys.exit(main())
