#!/usr/bin/env python3
"""SDD_Pro — Acceptance Gate runner (script, invoked by agent qa).

Hoisted out of `sdd_hooks/validate_acceptance_gate.py` (audit P0-security 2026-06-05).

Previously the entire AcceptanceGate logic (npm test / dotnet build / pytest / gradle test)
ran INSIDE the SubagentStop hook matcher=qa. That violated Claude Code hook semantics:
hooks must be < 5s, this could take 10+ minutes blocking the pipeline.

New design:
  1. Agent qa invokes this script as a SHELL command during its STEP X (acceptance check).
  2. Script walks workspace/output/src/*, runs the checks, writes a verdict report
     to workspace/output/.sys/.acceptance/acceptance.json.
  3. The remaining SubagentStop hook only READS the verdict JSON (fast, < 100ms)
     and decides BLOCK or ALLOW.

Exit codes:
  0 = all checks passed (or AcceptanceGate=off / warn mode tolerant)
  2 = at least one fail in strict mode (BLOCK)
  3 = infra failure (cannot run checks: cwd missing, etc.)

Bypass: SDD_ALLOW_ACCEPTANCE_BYPASS=1
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

# Make sdd_lib importable when invoked directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.atomic_write import atomic_write_text  # noqa: E402
from sdd_lib.exit_codes import SUCCESS, INFRA_BLOCKED  # noqa: E402
from sdd_lib.paths import project_root_for_hook as _resolve_project_root

PROJECT_TYPE_MARKERS = {
    "node": ["package.json"],
    "dotnet": ["*.csproj"],
    "kotlin": ["build.gradle.kts", "build.gradle"],
    "python": ["pyproject.toml", "requirements.txt"],
}

DEFAULT_TIMEOUT = 120  # seconds per check (security audit 2026-06-06 — was 300s, trop long pour CI)
DEFAULT_MAX_PROJECTS = 8  # safety cap : scan > 8 projets = symptôme de mauvais scoping


def _read_acceptance_config(root: Path) -> dict[str, str]:
    stack_md = root / "workspace" / "input" / "stack" / "stack.md"
    if not stack_md.is_file():
        return {"mode": "off", "require_e2e": "false"}
    try:
        content = stack_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"mode": "off", "require_e2e": "false"}

    mode = "strict"
    require_e2e = True
    m = re.search(r"^AcceptanceGate:\s*(\w+)", content, re.MULTILINE)
    if m:
        mode = m.group(1).lower()
    m = re.search(r"^AcceptanceGate\.RequireE2E:\s*(\w+)", content, re.MULTILINE)
    if m:
        require_e2e = m.group(1).lower() in ("true", "yes", "1")

    return {"mode": mode, "require_e2e": str(require_e2e).lower()}


def _detect_project_type(project_dir: Path) -> str | None:
    for ptype, markers in PROJECT_TYPE_MARKERS.items():
        for marker in markers:
            if "*" in marker:
                if any(project_dir.glob(marker)):
                    return ptype
            elif (project_dir / marker).is_file():
                return ptype
    return None


# Audit 2026-06-06 MA-9 — whitelist project directory name to neutralize
# the case where `workspace/output/src/` contains a directory whose name
# starts with `-` (interpreted as a flag by npm/dotnet/etc). Defensive
# even though we trust internal globs — paths from arch scaffolding could
# theoretically inherit a malformed name from a malicious FEAT.
_SAFE_PROJECT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")


def _is_safe_project_dir(project_dir: Path) -> bool:
    return bool(_SAFE_PROJECT_NAME.match(project_dir.name))


def _run_check(project_dir: Path, cmd: list[str]) -> tuple[bool, str]:
    if not _is_safe_project_dir(project_dir):
        return False, f"unsafe project dir name: {project_dir.name!r} (must match ^[A-Za-z][A-Za-z0-9._-]*$)"
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
        tail = (result.stdout or result.stderr or "")[-500:]
        return result.returncode == 0, tail
    except subprocess.TimeoutExpired:
        return False, f"timeout {DEFAULT_TIMEOUT}s"
    except FileNotFoundError as e:
        return False, f"command not found: {e}"
    except OSError as e:
        return False, f"OS error: {e}"


def _check_node(project_dir: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    pkg_path = project_dir / "package.json"
    if not pkg_path.is_file():
        return [("node-detection", False, "package.json missing")]
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [("node-detection", False, "package.json invalid")]
    scripts = pkg.get("scripts", {})

    if "test" in scripts:
        ok, out = _run_check(project_dir, ["npm", "test", "--silent"])
        results.append(("test", ok, out if not ok else "OK"))
    else:
        results.append(("test", False, "script 'test' absent (cf. quality.md §C.6)"))

    if "lint" in scripts:
        ok, out = _run_check(project_dir, ["npm", "run", "lint", "--silent"])
        results.append(("lint", ok, out if not ok else "OK"))
    else:
        results.append(("lint", False, "script 'lint' absent (cf. quality.md §C.6)"))

    return results


def _check_dotnet(project_dir: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    csproj = next(project_dir.glob("*.csproj"), None)
    if not csproj:
        return [("dotnet-detection", False, "*.csproj missing")]
    is_test = "test" in csproj.stem.lower()
    if is_test:
        ok, out = _run_check(project_dir, ["dotnet", "test", "--nologo", "--verbosity", "quiet"])
        results.append(("test", ok, out if not ok else "OK"))
    ok, out = _run_check(project_dir, ["dotnet", "build", "--nologo", "--verbosity", "quiet"])
    results.append(("build", ok, out if not ok else "OK"))
    return results


def _check_kotlin(project_dir: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    is_windows = os.name == "nt"
    wrapper = "gradlew.bat" if is_windows else "gradlew"
    if not (project_dir / wrapper).is_file():
        return [("kotlin-detection", False, f"{wrapper} wrapper missing")]
    gradlew_cmd = str(project_dir / wrapper) if is_windows else f"./{wrapper}"
    ok, out = _run_check(project_dir, [gradlew_cmd, "test", "--quiet"])
    results.append(("test", ok, out if not ok else "OK"))
    return results


def _check_python(project_dir: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    venv_py = project_dir / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    py_cmd = str(venv_py) if venv_py.is_file() else sys.executable

    tests_dir = project_dir / "tests"
    if tests_dir.is_dir():
        ok, out = _run_check(project_dir, [py_cmd, "-m", "pytest", "tests/", "-q"])
        results.append(("test", ok, out if not ok else "OK"))
    return results


def _write_report(report_path: Path, payload: dict) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(report_path, json.dumps(payload, indent=2, ensure_ascii=False))


def _parse_args(argv: list[str] | None = None):
    """CLI : --projects pour scoper (security audit 2026-06-06)."""
    import argparse
    p = argparse.ArgumentParser(description="SDD_Pro AcceptanceGate validator")
    p.add_argument(
        "--projects",
        default=None,
        help="Comma-separated list of project names to scope the gate to "
             "(default: tous les projets sous workspace/output/src/, capped at "
             f"{DEFAULT_MAX_PROJECTS}). Recommandé en CI pour éviter de scanner "
             "des projets non modifiés.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout per check in seconds (default: {DEFAULT_TIMEOUT}s).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    # Propage le timeout choisi globalement (consommé par _run_check via DEFAULT_TIMEOUT
    # — on évite la réécriture globale en exposant une closure simple).
    global DEFAULT_TIMEOUT
    if args.timeout != DEFAULT_TIMEOUT:
        DEFAULT_TIMEOUT = args.timeout

    scope_projects: set[str] | None = None
    if args.projects:
        scope_projects = {p.strip() for p in args.projects.split(",") if p.strip()}

    root = _resolve_project_root()
    report_path = root / "workspace" / "output" / ".sys" / ".acceptance" / "acceptance.json"

    if os.environ.get("SDD_ALLOW_ACCEPTANCE_BYPASS", "").lower() in ("1", "true", "yes"):
        sys.stderr.write("[acceptance] SDD_ALLOW_ACCEPTANCE_BYPASS=1 — bypass\n")
        _write_report(report_path, {
            "verdict": "bypass",
            "mode": "bypass",
            "extractedAt": datetime.now(timezone.utc).isoformat(),
            "projects": {},
            "failures": [],
        })
        return SUCCESS

    config = _read_acceptance_config(root)
    mode = config["mode"]

    if mode == "off":
        _write_report(report_path, {
            "verdict": "skipped",
            "mode": "off",
            "extractedAt": datetime.now(timezone.utc).isoformat(),
            "projects": {},
            "failures": [],
        })
        return SUCCESS

    src_dir = root / "workspace" / "output" / "src"
    if not src_dir.is_dir():
        _write_report(report_path, {
            "verdict": "skipped",
            "mode": mode,
            "reason": "no workspace/output/src/ yet",
            "extractedAt": datetime.now(timezone.utc).isoformat(),
            "projects": {},
            "failures": [],
        })
        return SUCCESS

    projects = [p for p in src_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if scope_projects is not None:
        projects = [p for p in projects if p.name in scope_projects]
    elif len(projects) > DEFAULT_MAX_PROJECTS:
        sys.stderr.write(
            f"[acceptance] WARN: {len(projects)} projets détectés > cap "
            f"{DEFAULT_MAX_PROJECTS}. Limite par défaut appliquée (ordre d'iterdir). "
            f"Use `--projects A,B,C` pour scoper explicitement.\n"
        )
        projects = projects[:DEFAULT_MAX_PROJECTS]
    if not projects:
        _write_report(report_path, {
            "verdict": "skipped",
            "mode": mode,
            "reason": "no projects under workspace/output/src/",
            "extractedAt": datetime.now(timezone.utc).isoformat(),
            "projects": {},
            "failures": [],
        })
        return SUCCESS

    all_results: dict[str, list[tuple[str, bool, str]]] = {}
    for project_dir in projects:
        ptype = _detect_project_type(project_dir)
        if not ptype:
            continue
        if ptype == "node":
            all_results[project_dir.name] = _check_node(project_dir)
        elif ptype == "dotnet":
            all_results[project_dir.name] = _check_dotnet(project_dir)
        elif ptype == "kotlin":
            all_results[project_dir.name] = _check_kotlin(project_dir)
        elif ptype == "python":
            all_results[project_dir.name] = _check_python(project_dir)

    failures = []
    for proj, results in all_results.items():
        for check, ok, msg in results:
            if not ok:
                failures.append({"project": proj, "check": check, "message": (msg or "").strip()[-300:]})

    verdict = "pass" if not failures else ("warn" if mode == "warn" else "fail")
    payload = {
        "verdict": verdict,
        "mode": mode,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "projects": {
            p: [{"check": c, "ok": ok, "message": (m or "").strip()[-300:]} for c, ok, m in r]
            for p, r in all_results.items()
        },
        "failures": failures,
    }
    _write_report(report_path, payload)

    if not failures:
        sys.stderr.write(f"[acceptance] {len(all_results)} projets, tous OK\n")
        return SUCCESS

    sys.stderr.write(f"ERROR: AcceptanceGate ({mode}) {len(failures)} échec(s) sur {len(all_results)} projets\n")
    sys.stderr.write("CAUSE: [ACCEPTANCE_GATE_FAILED]\n")
    for f in failures[:20]:
        msg_tail = (f["message"] or "").splitlines()[-1] if f["message"] else ""
        sys.stderr.write(f"  - {f['project']} / {f['check']} : {msg_tail[:120]}\n")
    sys.stderr.write("FIX: corriger les checks fail OU set AcceptanceGate=warn dans Project Config (decision tracee)\n")

    if mode == "warn":
        return SUCCESS
    return 2  # strict: BLOCK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — script entry-point, must not crash silently
        sys.stderr.write(f"ERROR: validate_acceptance script crashed\nCAUSE: [INFRA_BLOCKED] {type(e).__name__}: {e}\nFIX: report bug\n")
        sys.exit(INFRA_BLOCKED)
