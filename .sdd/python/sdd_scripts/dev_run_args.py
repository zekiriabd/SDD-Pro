#!/usr/bin/env python3
"""SDD_Pro /dev-run args wrapper — parse CLI flags deterministically.

Audit P3 C (2026-06-08) — `/dev-run.md` declares CLI flags (`--unsequenced`,
`--legacy-auditor-parallel`, `--rebuild-arch`, `--resume`, `--force`,
`--max-parallel N`) but the slash command is LLM-interpreted, meaning the
LLM parses these from the user's natural-language invocation. When the LLM
misses a flag (or mis-orders them), the documented bypass doesn't work.

This wrapper script :
  1. Receives the raw user input string (via stdin or `--input`)
  2. Parses CLI flags deterministically via argparse
  3. Writes a structured args file to
     `workspace/.sys/.state/dev-run-{n}.args.json`
  4. Returns the parsed flags as JSON on stdout

Slash command behavior in `.md` :
  STEP 1.bis (new) — invoke this wrapper, read the resulting JSON for
  flag values. The LLM no longer has to parse `--xxx` from raw text.

Lot « orchestration mécanique » (2026-11-07) — le parsing est OBLIGATOIRE
(plus de « fallback interprétation LLM ») et `--preflight` porte les
pré-conditions mécaniques de /dev-run :

  1. run courant : `--run-id` > `$SDD_RUN_ID` > run `/sdd-full` en cours de la
     FEAT (imbrication) > nouveau run `/dev-run` (console.db) ;
  2. readiness : déjà enregistrée dans le run → conservée ; sinon rapport
     `{n}-readiness.md`, à défaut `validate_readiness.py --json` (0 token) ;
     NO-GO sans `--force` → exit 1 `[READINESS_NO_GO]` ; NO-GO + `--force` →
     enregistrée `warn` (forced) + ligne `force-bypass.log` ;
  3. US présentes (sinon `[US_NOT_FOUND]`) ;
  4. `phase_planner.plan()` → `phase-plan-{n}.json` (écriture atomique) +
     phases dev MÉCANIQUES : `dev_backend` / `api_gate` / `dev_frontend`
     désactivées (ex. desktop/wpf sans backend) enregistrées `skip` ;
  5. `dev_run` enregistrée `running` (prérequis du hook enforce_phase_order
     pour l'agent `qa` de l'API gate) ;
  6. `max_parallel` effectif : `--max-parallel` > `MaxParallel` > 3.

`--end {pass,warn,fail}` clôt la phase `dev_run` du run — `pass|warn` soumis au
gate de livraison (preuve build `verify_build.py`) ; refus → `fail` +
`[DELIVERY_GATE_BLOCKED]`, exit 2.

Usage:
    python -m sdd_scripts.dev_run_args --input "1 --unsequenced --max-parallel 4"
    python -m sdd_scripts.dev_run_args --input "1 --legacy-auditor-parallel"

Exit codes :
    0 SUCCESS       : args parsed, JSON file written
    1 FAIL_FAST     : no FEAT number found
    2 CORRECTIBLE   : invalid arg combination (e.g. mutually exclusive flags)
    3 INFRA_BLOCKED : disk write failure
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.console_safe import ensure_console_safe  # noqa: E402
from sdd_lib.paths import audit_dir_path, console_db_path, iso_now_ms, workspace_root  # noqa: E402

INFRA_BLOCKED = 3


def _build_parser() -> argparse.ArgumentParser:
    """The canonical argparse for /dev-run.

    Mirrors the flags documented in `.claude/commands/dev-run.md`. Every
    flag declared in the .md must appear here OR be annotated `@llm-only-flag`
    (smoke test enforces — cf. test_cli_flags_declared.py).
    """
    p = argparse.ArgumentParser(
        prog="/dev-run",
        description="Args parser for /dev-run slash command (v7.0.0+).",
    )
    p.add_argument("feat_number", type=int, nargs="?", default=None,
                   help="FEAT number (positional, required)")
    p.add_argument("--force", action="store_true",
                   help="Bypass readiness NO-GO gate")
    p.add_argument("--max-parallel", type=int, default=None,
                   help="Max US in parallel (1-12, default MaxParallel config)")
    p.add_argument("--rebuild-arch", action="store_true",
                   help="Force arch invocation even if shortcircuit detects stable bootstrap")
    p.add_argument("--resume", action="store_true",
                   help="Resume from last checkpoint (CheckpointMode=resume)")
    p.add_argument("--unsequenced", action="store_true",
                   help="Disable gated API back/front pipeline (legacy v6.x parallel)")
    p.add_argument("--legacy-auditor-parallel", action="store_true",
                   help="Disable two-stage auditor pattern (force 4-reviewer parallel batch)")
    return p


def parse_input_string(input_str: str) -> dict:
    """Parse a /dev-run input string into a structured args dict.

    Input format examples :
        "1"
        "1 --unsequenced"
        "1 --legacy-auditor-parallel --max-parallel 4"
        "--force 1"  (positional order tolerant)

    Returns dict with keys :
        feat_number, force, max_parallel, rebuild_arch, resume,
        unsequenced, legacy_auditor_parallel, _raw, _parsed_at
    """
    # Tokenize honoring quotes
    tokens = shlex.split(input_str)
    parser = _build_parser()
    try:
        args = parser.parse_args(tokens)
    except SystemExit as exc:
        # argparse calls sys.exit on parse error — re-raise as ValueError
        raise ValueError(f"argparse error (code {exc.code}) on input: {input_str!r}") from exc

    # Mutual exclusion check (load-bearing : --unsequenced and
    # --legacy-auditor-parallel are orthogonal, but using both together
    # is suspicious — document but don't block)
    if args.unsequenced and args.legacy_auditor_parallel:
        sys.stderr.write(
            "INFO [DEV_RUN_DUAL_BYPASS] both --unsequenced AND "
            "--legacy-auditor-parallel set. Both apply, but combination is "
            "unusual (full v6.x behavior).\n"
        )

    # Range check max-parallel
    if args.max_parallel is not None and not (1 <= args.max_parallel <= 12):
        raise ValueError(f"--max-parallel must be 1-12, got {args.max_parallel}")

    return {
        "feat_number":             args.feat_number,
        "force":                   args.force,
        "max_parallel":            args.max_parallel,
        "rebuild_arch":            args.rebuild_arch,
        "resume":                  args.resume,
        "unsequenced":             args.unsequenced,
        "legacy_auditor_parallel": args.legacy_auditor_parallel,
        "_raw":                    input_str,
        "_parsed_at":              datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_args_state(parsed: dict, root: Path) -> Path:
    """Persist parsed args to workspace/.sys/.state/dev-run-{n}.args.json."""
    n = parsed["feat_number"]
    if n is None:
        raise ValueError("feat_number is None — cannot write state file")
    state_dir = workspace_root(root) / ".sys" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / f"dev-run-{n}.args.json"
    out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def _repo_root() -> Path:
    from sdd_lib.paths import repo_root
    if os.environ.get("SDD_REPO_ROOT"):
        return repo_root()
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root and Path(env_root).is_dir():
        return Path(env_root)
    return repo_root()


# --------------------------------------------------------------------------- #
# Preflight mécanique (lot orchestration mécanique, 2026-11-07)
# --------------------------------------------------------------------------- #

_READINESS_DONE = {"pass", "warn", "skip"}
_DEV_PHASE_NAMES = ("dev_backend", "api_gate", "dev_frontend")
_DECISION_RE = re.compile(
    r"[Dd][ée]cision[^:\n]*:\s*\**\s*(?:\U0001f7e2|\U0001f7e1|\U0001f534)?\s*(GO|WARN|NO-GO)\b"
)


class PreflightStop(Exception):
    """STOP déterministe : (classe, message, exit code)."""

    def __init__(self, cls: str, message: str, code: int = FAIL_FAST) -> None:
        super().__init__(f"{cls} {message}")
        self.cls, self.message, self.code = cls, message, code


def _resolve_or_create_run(root: Path, feat_n: int, explicit: str | None) -> tuple[str, bool]:
    """(run_id, created). Réutilise un /sdd-full en cours pour l'imbrication."""
    from sdd_lib.console_db import connect, ensure_initialized, insert_event, upsert_run
    db = console_db_path(root)
    ensure_initialized(db)
    with connect(db) as conn:
        for cand in (explicit, (os.environ.get("SDD_RUN_ID") or "").strip() or None):
            if cand:
                row = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (cand,)).fetchone()
                if row:
                    return cand, False
        row = conn.execute(
            "SELECT run_id FROM runs WHERE feat_n = ? AND status = 'running' "
            "AND command = '/sdd-full' ORDER BY started_at DESC LIMIT 1", (feat_n,),
        ).fetchone()
        if row:
            return row["run_id"], False
    from sdd_lib.run_id import get_or_create_run_id
    run_id = explicit or get_or_create_run_id(force_new=True)
    now = iso_now_ms()
    with connect(db) as conn:
        upsert_run(conn, run_id=run_id, command="/dev-run", feat_n=feat_n,
                   started_at=now, status="running", tags=["dev-run"])
        insert_event(conn, event_type="run.start", ts=now, run_id=run_id, feat_n=feat_n,
                     payload={"cmd": "/dev-run", "by": "dev_run_args.preflight"})
    return run_id, True


def _record(root: Path, run_id: str, phase: str, status: str, payload: dict | None = None,
            *, start: bool = False) -> None:
    from sdd_lib.console_db import connect, get_run, insert_event, upsert_run, upsert_run_phase
    now = iso_now_ms()
    with connect(console_db_path(root)) as conn:
        upsert_run_phase(conn, run_id=run_id, phase=phase, status=status,
                         started_at=now, ended_at=None if start else now, payload=payload)
        row = get_run(conn, run_id)
        if row is not None:
            upsert_run(conn, run_id=run_id, command=row["command"],
                       current_phase=phase, status=row["status"])
        insert_event(conn, event_type="phase.start" if start else "phase.end", ts=now,
                     run_id=run_id, feat_n=row["feat_n"] if row else None, phase=phase,
                     payload={"status": status, "by": "dev_run_args", "payload": payload})


def _run_phases(root: Path, run_id: str) -> dict[str, str]:
    from sdd_lib.console_db import connect
    with connect(console_db_path(root)) as conn:
        return {r["phase"]: (r["status"] or "").lower() for r in conn.execute(
            "SELECT phase, status FROM run_phases WHERE run_id = ?", (run_id,))}


def _readiness_decision(root: Path, feat_n: int) -> tuple[str | None, str]:
    """(GO|WARN|NO-GO|None, source). Rapport disque, sinon validate_readiness.py."""
    import subprocess
    report = workspace_root(root) / ".sys" / ".validation" / f"{feat_n}-readiness.md"
    if report.is_file():
        m = _DECISION_RE.search(report.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1).upper(), "report"
    script = Path(__file__).resolve().parent / "validate_readiness.py"
    try:
        proc = subprocess.run([sys.executable, str(script), "--feat-number", str(feat_n), "--json"],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120, cwd=str(root))
        data = json.loads(proc.stdout or "{}")
        d = str(data.get("decision") or "").upper()
        return (d if d in ("GO", "WARN", "NO-GO") else None), "validate_readiness.py"
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, "validate_readiness.py (échec)"


def preflight(parsed: dict, root: Path, *, run_id: str | None = None) -> dict:
    """Pré-conditions mécaniques de /dev-run. Lève PreflightStop sur STOP."""
    n = int(parsed["feat_number"])
    us_dir = workspace_root(root) / "us"
    us = sorted(p.stem for p in us_dir.glob(f"{n}-*.md")) if us_dir.is_dir() else []
    if not us:
        raise PreflightStop("[US_NOT_FOUND]",
                            f"aucun fichier workspace/us/{n}-*.md — lancer /us-generate {n}")

    rid, created = _resolve_or_create_run(root, n, run_id)
    phases = _run_phases(root, rid)

    readiness = phases.get("readiness")
    readiness_info: dict = {"status": readiness, "source": "run_phases"}
    if readiness not in _READINESS_DONE:
        decision, source = _readiness_decision(root, n)
        readiness_info = {"decision": decision, "source": source}
        if decision is None:
            raise PreflightStop("[READINESS_UNKNOWN]",
                                f"décision readiness indéterminable ({source}) — lancer "
                                f"/feat-validate {n}")
        if decision == "NO-GO" and not parsed.get("force"):
            _record(root, rid, "readiness", "fail", {"decision": "NO-GO", "source": source})
            raise PreflightStop("[READINESS_NO_GO]",
                                f"workspace/.sys/.validation/{n}-readiness.md — corriger §3 puis "
                                f"/feat-validate {n} ; bypass : /dev-run {n} --force")
        status = {"GO": "pass", "WARN": "warn", "NO-GO": "warn"}[decision]
        payload = {"decision": decision, "source": source}
        if decision == "NO-GO":
            payload["forced"] = True
            try:
                audit = audit_dir_path(root)
                audit.mkdir(parents=True, exist_ok=True)
                with open(audit / "force-bypass.log", "a", encoding="utf-8") as fh:
                    fh.write(f"{iso_now_ms()} /dev-run {n} --force readiness=NO-GO run={rid}\n")
            except OSError:
                pass
        _record(root, rid, "readiness", status, payload)
        readiness_info["status"] = status

    # Phase plan (SSoT auditors + phases dev mécaniques) — écriture atomique
    from sdd_scripts.phase_planner import plan as _phase_plan
    pp = _phase_plan(feat_number=n, unsequenced=bool(parsed.get("unsequenced")))
    if "error" in pp:
        raise PreflightStop("[PHASE_PLAN_INIT_FAILED]", str(pp["error"]))
    from sdd_lib.atomic_write import atomic_write_text
    pp_path = workspace_root(root) / ".sys" / ".state" / f"phase-plan-{n}.json"
    atomic_write_text(pp_path, json.dumps(pp, indent=2, ensure_ascii=False))

    dev_phases = pp.get("dev_phases", {})
    skipped = []
    for name in _DEV_PHASE_NAMES:
        ph = dev_phases.get(name) or {}
        if not ph.get("enabled", True):
            _record(root, rid, name, "skip", {"reason": ph.get("skip_reason")})
            skipped.append(name)

    _record(root, rid, "dev_run", "running", {"skipped": skipped}, start=True)

    max_parallel = parsed.get("max_parallel")
    if max_parallel is None:
        try:
            from sdd_lib.layered_config import read_layered_config
            cfg = read_layered_config(root=root, keys=("MaxParallel",), coerce=True)
            max_parallel = int(cfg.get("MaxParallel") or 3)
        except Exception:  # noqa: BLE001 — défaut documenté
            max_parallel = 3

    return {
        "feat_number": n, "run_id": rid, "run_created": created,
        "env": {"SDD_RUN_ID": rid}, "readiness": readiness_info,
        "us": us, "max_parallel": max_parallel,
        "dev_phases": dev_phases, "dev_meta": pp.get("dev_meta", {}),
        "skipped_phases": skipped, "phase_plan": str(pp_path),
        "auditors": "hors /dev-run — /sdd-full phase auditor_batch ou /sdd-review",
    }


def end_dev_run(root: Path, feat_n: int, status: str, run_id: str | None) -> str:
    """Clôt `dev_run` du run dont la phase dev_run est `running` (le plus récent)."""
    rid = run_id or (os.environ.get("SDD_RUN_ID") or "").strip() or None
    if not rid:
        from sdd_lib.console_db import connect
        with connect(console_db_path(root)) as conn:
            row = conn.execute(
                "SELECT r.run_id FROM runs r JOIN run_phases p ON p.run_id = r.run_id "
                "WHERE r.feat_n = ? AND p.phase = 'dev_run' AND p.status = 'running' "
                "ORDER BY r.started_at DESC LIMIT 1", (feat_n,),
            ).fetchone()
        rid = row["run_id"] if row else None
    if not rid:
        rid, _ = _resolve_or_create_run(root, feat_n, None)
    _record(root, rid, "dev_run", status)
    return rid


def end_dev_run_gated(root: Path, feat_n: int, status: str,
                      run_id: str | None) -> dict:
    """`--end` soumis au gate de livraison (2026-11-07, docs/delivery-gates.md).

    `pass|warn` déclaré par l'orchestrateur ne vaut rien sans preuve : la phase
    n'est enregistrée telle quelle que si `authorize_delivery(workflow=dev-run)`
    l'autorise (build réellement vérifié par `verify_build.py`, readiness
    enregistrée). Refus → `dev_run` enregistrée `fail` + `[DELIVERY_GATE_BLOCKED]`
    (et le run `/dev-run` autonome est clos `failed`). `--force` n'intervient
    pas ici : il ne porte que sur la readiness du preflight.
    """
    if status == "fail":
        return {"recorded": "dev_run", "status": "fail", "run_id": end_dev_run(root, feat_n, status, run_id)}
    from sdd_lib.delivery_wiring import authorize, blocked_message
    rid = end_dev_run(root, feat_n, "running", run_id)  # résout le run sans clore la phase
    decision = authorize(feat_n=feat_n, workflow="dev-run", run_id=rid, root=root)
    if decision.allowed:
        _record(root, rid, "dev_run", status, {"delivery_gate": decision.to_dict()})
        return {"recorded": "dev_run", "status": status, "run_id": rid,
                "delivery_gate": decision.to_dict()}
    msg = blocked_message(feat_n, "dev-run", decision)
    _record(root, rid, "dev_run", "fail", {"declared": status, "error": msg,
                                           "delivery_gate": decision.to_dict()})
    from sdd_lib.console_db import connect, get_run, run_end
    with connect(console_db_path(root)) as conn:
        row = get_run(conn, rid)
        if row is not None and row["command"] == "/dev-run":
            run_end(conn, rid, "failed", "RED", error_message=msg,
                    source="dev_run_args.end")
    return {"recorded": "dev_run", "status": "fail", "declared": status, "run_id": rid,
            "delivery_blocked": True, "error": msg, "delivery_gate": decision.to_dict()}


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()  # cp1252 guard (audit 2026-06-11 M15)
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    cli = argparse.ArgumentParser(
        prog="dev_run_args",
        description="Deterministic args parser for /dev-run (v7.0.0+ audit P3 C).",
    )
    cli.add_argument("--input", "-i", type=str, default=None,
                     help="Raw /dev-run input string (default: read from stdin)")
    cli.add_argument("--dry-run", action="store_true",
                     help="Parse and print JSON, do not persist state file")
    cli.add_argument("--preflight", action="store_true",
                     help="pré-conditions mécaniques /dev-run (run, readiness, phases dev, MaxParallel)")
    cli.add_argument("--end", choices=("pass", "warn", "fail"), default=None,
                     help="clôt la phase dev_run du run courant")
    cli.add_argument("--run-id", default=None)
    args = cli.parse_args(argv)

    raw = args.input
    if raw is None:
        raw = sys.stdin.read().strip()

    if not raw:
        sys.stderr.write("ERROR: no input provided (use --input or stdin)\n")
        return CORRECTIBLE

    try:
        parsed = parse_input_string(raw)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: [INVALID_ARG] {exc}\n")
        return CORRECTIBLE

    if parsed["feat_number"] is None:
        sys.stderr.write("ERROR: [INVALID_ARG] FEAT number required (positional)\n")
        sys.stderr.write("Example: python -m sdd_scripts.dev_run_args --input '1 --unsequenced'\n")
        return FAIL_FAST

    root = _repo_root()
    if args.end:
        try:
            out = end_dev_run_gated(root, int(parsed["feat_number"]), args.end, args.run_id)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"ERROR: [INFRA_BLOCKED] console.db : {exc}\n")
            return INFRA_BLOCKED
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        if out.get("delivery_blocked"):
            sys.stderr.write(
                f"ERROR: /dev-run {parsed['feat_number']} — dev_run {args.end} refusé\n"
                f"CAUSE: {out['error']}\n"
                f"FIX: python .sdd/python/sdd_scripts/verify_build.py --feat-number "
                f"{parsed['feat_number']} --run-id {out['run_id']} (build réel) puis --end\n")
            return CORRECTIBLE
        return SUCCESS

    if args.preflight and not args.dry_run:
        try:
            parsed["preflight"] = preflight(parsed, root, run_id=args.run_id)
        except PreflightStop as stop:
            sys.stderr.write(f"ERROR: /dev-run {parsed['feat_number']} — preflight\n"
                             f"CAUSE: {stop.cls} {stop.message}\n"
                             f"FIX: cf. CAUSE (STOP avant tout spawn d'agent)\n")
            return stop.code
        except Exception as exc:  # noqa: BLE001 — base/FS
            sys.stderr.write(f"ERROR: [INFRA_BLOCKED] preflight /dev-run : "
                             f"{type(exc).__name__}: {exc}\n")
            return INFRA_BLOCKED

    sys.stdout.write(json.dumps(parsed, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")

    if args.dry_run:
        return SUCCESS

    try:
        out_path = write_args_state(parsed, root)
    except OSError as exc:
        sys.stderr.write(f"ERROR: [INFRA_BLOCKED] cannot write state file: {exc}\n")
        return INFRA_BLOCKED
    try:
        shown = out_path.relative_to(root).as_posix()
    except ValueError:
        shown = out_path.as_posix()
    sys.stderr.write(f"[DEV_RUN_ARGS] state written → {shown}\n")
    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
