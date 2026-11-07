#!/usr/bin/env python3
"""SDD_Pro: manual gates (afterUS / afterReadiness / afterPlan / afterCode).

SOURCE DE VÉRITÉ (audit « fiabilité des données et des états », 2026-11-07)
---------------------------------------------------------------------------
**console.db (table `gates`) est la source de vérité unique.** L'état courant
d'un gate = sa ligne `gates` la plus récente pour `(feat_n, gate_name)`
(`sdd_lib.console_db.get_latest_gate`). `workspace/console/status.json` n'est
plus qu'un **export dérivé**, régénéré depuis la base par `export_status_json()`
après chaque écriture — il n'est JAMAIS lu comme source.

Avant ce lot, l'inverse était déclaré (status.json « source », console.db
« miroir » best-effort) alors que status.json n'existait même pas sur disque
quand `gates` comptait 56 lignes : la seule trace réelle était la base.

Compat console Node (Fastify) : la console écrit encore `status.json`
directement puis appelle `record_gate_decision.py` (best-effort) pour la base.
Pour qu'une décision humaine ne soit jamais perdue si cet appel échoue,
`read` / `is-resolved` / l'export **réconcilient** : une décision
`validated|skipped` présente dans status.json, différente de la dernière ligne
`gates` et pas plus ancienne qu'elle, est importée en base
(`payload.source = "status.json-import"`, WARN stderr). Import
unidirectionnel ; la base reste l'autorité.

Erreurs : base indisponible → exit 3 (`INFRA_BLOCKED`) + ERROR 3L
`[INFRA_BLOCKED]` — une écriture de gate n'est plus jamais « avalée ».

Clôture de run : `set --decision validated|skipped` sur le gate final
`afterCode` n'implique PAS la fin du run (les reviews suivent) — la clôture
est faite par `sdd_state.py set-phase --phase sdd_review` (terminal) ou
`end-run`, ou `run_close.py`.

CROSS-LANGUAGE SYMMETRY (load-bearing): the status.json export keeps the same
lock protocol as workspace/console/lib/atomic-write.js:
  - same lock path: <dirname(filePath)>/.status.lock
  - same stale TTL: 10000 ms (10_000 on Node side)
  - same retry count: 5
  - same atomicity: O_EXCL create
Any change must be replicated on both sides. Verified by
framework_smoke.py check `console-lock-symmetry`.

Usage:
    python gate_decide.py read         --feat-num 1 --phase afterUS
        -> stdout: pending|validated|skipped|none

    python gate_decide.py pose-pending --feat-num 1 --phase afterUS
        -> inserts decision=pending (askedAt=now), re-exports status.json

    python gate_decide.py set --feat-num 1 --phase afterUS \\
                             --decision skipped --answered-by "user@x.fr"
        -> inserts decision=skipped|validated (answeredAt=now), re-exports

    python gate_decide.py is-resolved --feat-num 1 --phase afterUS
        -> exit 0 if validated|skipped, exit 1 otherwise (3 = DB unavailable)

    python gate_decide.py export --status-file workspace/console/status.json
        -> regenerates status.json from console.db (all FEATs)

Migrated from .claude/scripts/gate-decide.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# sdd_lib is sibling package — add parent dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.atomic_write import atomic_write_text  # noqa: E402
from sdd_lib.console_db import (  # noqa: E402
    connect,
    ensure_initialized,
    get_latest_gate,
    insert_gate,
    list_latest_gates,
)
from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.file_locks import acquire_with_retry, release  # noqa: E402
from sdd_lib.paths import iso_now  # noqa: E402
from sdd_lib.stderr import error_block, warn  # noqa: E402


VALID_PHASES = ("afterUS", "afterReadiness", "afterPlan", "afterCode")
VALID_DECISIONS = ("pending", "validated", "skipped", "none")
_RESOLVED = ("validated", "skipped")
_IMPORT_SOURCE = "status.json-import"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)

    for name in ("read", "pose-pending", "set", "is-resolved"):
        s = sub.add_parser(name)
        s.add_argument("--feat-num", type=int, required=True)
        s.add_argument("--phase", required=True, choices=VALID_PHASES)
        s.add_argument("--status-file", default="workspace/console/status.json")
        s.add_argument("--json", action="store_true")
        if name == "set":
            s.add_argument("--decision", required=True,
                           choices=[d for d in VALID_DECISIONS if d != "none"])
            s.add_argument(
                "--answered-by",
                default=f"{os.environ.get('USERNAME') or getpass.getuser()}@local",
            )
    s_exp = sub.add_parser("export", help="Regenerate status.json from console.db")
    s_exp.add_argument("--status-file", default="workspace/console/status.json")
    return p.parse_args(argv)


def acquire_lock(lock_path: Path) -> None:
    """Acquire the status.json lock — identical protocol as Fastify console
    (`workspace/console/lib/atomic-write.js`). 10s TTL, 5 retries, 50ms backoff."""
    acquire_with_retry(lock_path, payload_prefix="py", ttl_ms=10000, retry_count=5, backoff_ms=50)


def release_lock(lock_path: Path) -> None:
    release(lock_path)


# ---------------------------------------------------------------------------
# status.json helpers (export target + legacy import source ONLY)
# ---------------------------------------------------------------------------

def read_status(path: Path) -> dict[str, Any]:
    """Parse a status.json tolerantly (skeleton on absence/corruption).

    Used only (a) to preserve non-gate keys written by the Node console when
    re-exporting and (b) to import legacy decisions — never as gate source.
    """
    if not path.is_file():
        return {
            "version":   1,
            "updatedAt": iso_now(),
            "FEATs":     {},
            "gates":     {},
        }
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw = ""
    if not raw.strip():
        return {"version": 1, "FEATs": {}, "gates": {}}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = {"version": 1, "FEATs": {}, "gates": {}}
    if not isinstance(obj, dict):
        obj = {"version": 1, "FEATs": {}, "gates": {}}
    obj.setdefault("FEATs", {})
    obj.setdefault("gates", {})
    return obj


def write_status(path: Path, status: dict[str, Any]) -> None:
    status["updatedAt"] = iso_now()
    atomic_write_text(
        path,
        json.dumps(status, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )


def ensure_gate(status: dict[str, Any], feat_key: str, phase: str) -> dict[str, Any]:
    gates = status.setdefault("gates", {})
    feat_gates = gates.setdefault(feat_key, {})
    return feat_gates.setdefault(phase, {})


def get_gate(status: dict[str, Any], feat_key: str, phase: str) -> dict[str, Any] | None:
    gates = status.get("gates", {})
    if not isinstance(gates, dict):
        return None
    feat_gates = gates.get(feat_key)
    if not isinstance(feat_gates, dict):
        return None
    g = feat_gates.get(phase)
    return g if isinstance(g, dict) else None


# ---------------------------------------------------------------------------
# console.db = source of truth
# ---------------------------------------------------------------------------

def _public_gate(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """status.json gate shape (drop DB-only keys)."""
    if state is None:
        return None
    return {k: v for k, v in state.items() if k != "decidedAt"}


def _import_legacy_decisions(conn: sqlite3.Connection, status_file: Path,
                             only: tuple[int, str] | None = None) -> int:
    """Import validated|skipped decisions found ONLY in status.json (Node writer).

    A decision is imported when it is resolved, differs from the latest DB
    row, and its `answeredAt` is not older than that row. Returns the count.
    """
    imported = 0  # compteur de décisions importées (pas un code de sortie)
    if not status_file.is_file():
        return imported
    status = read_status(status_file)
    gates = status.get("gates")
    if not isinstance(gates, dict):
        return imported
    for feat_key, feat_gates in gates.items():
        if not isinstance(feat_gates, dict):
            continue
        try:
            feat_n = int(feat_key)
        except (TypeError, ValueError):
            continue
        for phase, g in feat_gates.items():
            if only is not None and (feat_n, phase) != only:
                continue
            if phase not in VALID_PHASES or not isinstance(g, dict):
                continue
            decision = g.get("decision")
            if decision not in _RESOLVED:
                continue
            answered_at = str(g.get("answeredAt") or "")
            current = get_latest_gate(conn, feat_n=feat_n, gate_name=phase)
            if current is not None:
                if current.get("decision") == decision:
                    continue
                if answered_at and answered_at[:19] < str(current.get("decidedAt") or "")[:19]:
                    continue
            insert_gate(
                conn, gate_name=phase, decision=decision, feat_n=feat_n,
                by_user=g.get("answeredBy"),
                decided_at=answered_at or None,
                payload={"answeredAt": answered_at or None,
                         "answeredBy": g.get("answeredBy"),
                         "source": _IMPORT_SOURCE},
            )
            warn(f"WARN gate_decide — décision {decision!r} gate={phase} "
                 f"feat={feat_n} trouvée uniquement dans {status_file} : "
                 "importée dans console.db (source de vérité).")
            imported += 1
    return imported


def export_status_json(status_file: Path, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Regenerate `status.json` from console.db (derived export, never a source).

    Non-gate keys already present (``FEATs`` etc., written by the Node
    console) are preserved ; the ``gates`` block is replaced by the DB
    projection (latest row per FEAT × gate). Written atomically under the
    shared `.status.lock`. Returns the exported document.
    """
    def _build(c: sqlite3.Connection) -> dict[str, Any]:
        _import_legacy_decisions(c, status_file)
        projection = list_latest_gates(c)
        return {fk: {ph: _public_gate(st) for ph, st in gates.items()}
                for fk, gates in projection.items()}

    status_file = Path(status_file)
    lock_path = status_file.parent / ".status.lock"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    acquire_lock(lock_path)
    try:
        if conn is not None:
            gates = _build(conn)
        else:
            ensure_initialized()
            with connect() as c:
                gates = _build(c)
        status = read_status(status_file)
        status["version"] = status.get("version", 1)
        status["gates"] = gates
        status["source"] = "console.db"  # documents the derivation
        write_status(status_file, status)
        return status
    finally:
        release_lock(lock_path)


def _infra_error(step: str, exc: BaseException) -> int:
    error_block(
        f"gate_decide {step} failed",
        f"[INFRA_BLOCKED] console.db indisponible ({type(exc).__name__}: {exc})",
        "vérifier workspace/db/console.db (verrou, droits, $SDD_CONSOLE_DB_PATH) puis relancer",
    )
    return INFRA_BLOCKED


def _current_gate(feat_n: int, phase: str, status_file: Path) -> dict[str, Any] | None:
    ensure_initialized()
    with connect() as conn:
        _import_legacy_decisions(conn, status_file, only=(feat_n, phase))
        return get_latest_gate(conn, feat_n=feat_n, gate_name=phase)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    status_file = Path(args.status_file)

    if args.action == "export":
        try:
            export_status_json(status_file)
        except (sqlite3.Error, OSError) as exc:
            return _infra_error("export", exc)
        print(str(status_file))
        return SUCCESS

    if args.action in ("read", "is-resolved"):
        try:
            gate = _public_gate(_current_gate(args.feat_num, args.phase, status_file))
        except (sqlite3.Error, OSError) as exc:
            return _infra_error(args.action, exc)
        if args.action == "is-resolved":
            # predicate: 0/1 as boolean answer (not error code)
            if not gate:
                return FAIL_FAST
            return SUCCESS if gate.get("decision") in _RESOLVED else FAIL_FAST
        if args.json:
            print(json.dumps(gate if gate else {"decision": "none"}, separators=(",", ":")))
        else:
            print(gate.get("decision", "none") if gate else "none")
        return SUCCESS

    if args.action in ("pose-pending", "set"):
        now = iso_now()
        if args.action == "pose-pending":
            decision = "pending"
            by_user = None
            payload: dict[str, Any] = {"askedAt": now}
        else:
            decision = args.decision
            by_user = args.answered_by
            payload = {"answeredAt": now, "answeredBy": args.answered_by}
        try:
            ensure_initialized()
            with connect() as conn:
                if args.action == "set":
                    previous = get_latest_gate(conn, feat_n=args.feat_num, gate_name=args.phase)
                    if previous and previous.get("askedAt"):
                        payload["askedAt"] = previous["askedAt"]
                insert_gate(
                    conn, gate_name=args.phase, decision=decision,
                    feat_n=args.feat_num, by_user=by_user, payload=payload,
                )
                gate = _public_gate(get_latest_gate(conn, feat_n=args.feat_num, gate_name=args.phase))
        except Exception as exc:  # noqa: BLE001 — any write failure is INFRA, never silent
            return _infra_error(
                f"{args.action} gate={args.phase} feat={args.feat_num} decision={decision}", exc)
        # Derived export — a failure here is visible but does not undo the
        # decision already committed to the source of truth.
        try:
            export_status_json(status_file)
        except Exception as exc:  # noqa: BLE001
            warn(f"WARN gate_decide — export status.json échoué ({type(exc).__name__}: "
                 f"{exc}) : la décision est en base (source de vérité) ; relancer "
                 "`gate_decide.py export`.")
        if args.json:
            print(json.dumps(gate, separators=(",", ":")))
        else:
            print(decision)
        return SUCCESS

    warn(f"Unknown action: {args.action}")
    return FAIL_FAST


if __name__ == "__main__":
    sys.exit(main())
