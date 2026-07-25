"""SDD_Pro checkpoint helpers — input-hash validated phase resumption.

Layered on top of `sdd_scripts/sdd_state.py`, which tracks phase status in
**console.db** (tables `runs` + `run_phases`) since v6.10. This module adds
**input-hash validation** so that `--resume` can detect when a phase's inputs
(US, plan, stack, etc.) have been modified post-crash and must therefore be
re-run rather than skipped.

Design rationale:
    - `sdd_state.py` answers "did phase X complete successfully ?"
    - `checkpoint.py` answers "is the phase X result still valid given
      the current inputs ?" (= same hash) → safe to skip on resume

API (4 functions):
    compute_input_hash(paths) -> str
        SHA-256 over concatenated bytes of the listed files (skips
        missing files, stable order). Deterministic.

    record_input_hash(run_id, phase, input_paths) -> str
        Compute hash, merge it into `run_phases.payload_json.input_hash`
        for (run_id, phase). Returns the computed hash.

    is_phase_resumable(feat, phase, input_paths) -> tuple[bool, str]
        Looks up the latest run for FEAT in console.db, checks:
          1. phase.status in {pass, warn} (completed successfully)
          2. payload.input_hash == compute_input_hash(input_paths)
        Returns (resumable, reason).

    get_phase_payload(feat, phase) -> dict | None
        Read-only access to the latest run's phase payload.

Non-regression contract:
    - This module reads/writes **only** via the `sdd_lib.console_db` public
      API (the same SSoT that `sdd_state.py` uses) — never a side file.
    - If console.db is absent/unreadable/locked, the functions return
      False/None (= safe default: re-run the phase). Never raises to the
      pipeline except `record_input_hash` on a genuinely missing run_phase.

Classes d'erreur :
    [CHECKPOINT_HASH_MISMATCH] — input_hash stocké ≠ recalculé → invalidé
    [CHECKPOINT_INPUT_MISSING] — un input_path déclaré n'existe pas
    [CHECKPOINT_STATE_UNREADABLE] — run/phase absent de console.db ou DB illisible

v7.0.1 audit fix (2026-06-12) — REWRITTEN onto console.db. The previous
implementation read/wrote `workspace/.sys/.state/run-{id}.json` files
that `sdd_state.py` stopped producing at the v6.10 migration to console.db
(and looked up `FeatNumber`, a key that never existed — the column is
`feat_n`). Result: `is_phase_resumable()` always returned False and
`record_input_hash()` always raised FileNotFoundError, so `CheckpointMode:
resume` (wired in dev-run.md) was a silent no-op. Now backed by the live SSoT.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from sdd_lib.console_db import (
    connect,
    connect_ro,
    get_run_phases,
    list_runs,
    upsert_run_phase,
)
from sdd_lib.paths import workspace_root, repo_root


def compute_input_hash(paths: list[Path | str], *, root: Path | None = None) -> str:
    """Compute SHA-256 over the concatenated bytes of the listed files.

    Determinism guarantees:
        - Paths are sorted by their normalized string representation
          before hashing (caller order doesn't matter)
        - Missing files contribute a fixed sentinel (`<missing:path>`)
          so a "file added later" creates a different hash
        - Binary-safe: reads as bytes, no encoding assumptions

    Args:
        paths: list of file paths (absolute or relative to root)
        root: repo root, defaults to `repo_root()`

    Returns:
        Hex SHA-256 digest (64 chars).
    """
    if root is None:
        root = repo_root()

    normalized: list[tuple[str, Path]] = []
    for p in paths:
        if isinstance(p, str):
            p = Path(p)
        if not p.is_absolute():
            p = root / p
        rel = str(p.relative_to(root)).replace("\\", "/") if _is_under(p, root) else str(p)
        normalized.append((rel, p))

    normalized.sort(key=lambda t: t[0])

    h = hashlib.sha256()
    for rel, abs_path in normalized:
        h.update(b"---FILE:")
        h.update(rel.encode("utf-8"))
        h.update(b"\n")
        if abs_path.is_file():
            try:
                h.update(abs_path.read_bytes())
            except OSError:
                h.update(f"<unreadable:{rel}>".encode("utf-8"))
        else:
            h.update(f"<missing:{rel}>".encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _is_under(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _db_path(root: Path | None) -> Path:
    """console.db path under the (optional) explicit root, else repo_root()."""
    base = root if root is not None else repo_root()
    return workspace_root(base) / "db" / "console.db"


def _load_payload(row: sqlite3.Row) -> dict[str, Any]:
    """Parse run_phases.payload_json → dict (empty on null/invalid)."""
    raw = row["payload_json"] if "payload_json" in row.keys() else None
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _latest_phase_row(feat: int, phase: str, *, root: Path | None) -> sqlite3.Row | None:
    """Latest run for FEAT → its run_phases row for `phase` (read-only, fail-safe).

    Returns None if console.db is absent/unreadable/locked, no run exists for
    the FEAT, or the phase is absent — all treated as "not resumable".
    """
    try:
        with connect_ro(_db_path(root)) as conn:
            runs = list_runs(conn, feat_n=feat, limit=1)
            if not runs:
                return None
            run_id = runs[0]["run_id"]
            for r in get_run_phases(conn, run_id):
                if r["phase"] == phase:
                    return r
            return None
    except (FileNotFoundError, sqlite3.Error):
        return None


def record_input_hash(
    run_id: str,
    phase: str,
    input_paths: list[Path | str],
    *,
    root: Path | None = None,
) -> str:
    """Compute the input hash and merge it into run_phases.payload_json.input_hash.

    Returns the computed hash. The (run_id, phase) row MUST already exist
    (record is called after the phase ran). If it doesn't, raises
    FileNotFoundError [CHECKPOINT_STATE_UNREADABLE] so the caller can decide.
    Preserves the phase's existing status and payload keys.
    """
    if root is None:
        root = repo_root()
    h = compute_input_hash(input_paths, root=root)

    try:
        with connect(_db_path(root)) as conn:
            existing = {r["phase"]: r for r in get_run_phases(conn, run_id)}
            row = existing.get(phase)
            if row is None:
                raise FileNotFoundError(
                    f"[CHECKPOINT_STATE_UNREADABLE] no run_phase '{phase}' for "
                    f"run '{run_id}' in console.db"
                )
            payload = _load_payload(row)
            payload["input_hash"] = h
            payload["input_paths"] = [str(p) for p in input_paths]
            upsert_run_phase(
                conn,
                run_id=run_id,
                phase=phase,
                status=row["status"] or "pass",
                payload=payload,
            )
    except sqlite3.Error as e:
        raise ValueError(f"[CHECKPOINT_STATE_UNREADABLE] console.db error: {e}") from e
    return h


def is_phase_resumable(
    feat: int,
    phase: str,
    input_paths: list[Path | str],
    *,
    root: Path | None = None,
    accept_warn: bool = True,
) -> tuple[bool, str]:
    """Tell whether a phase can be safely skipped on /sdd-full --resume.

    Conditions (all required for resumable=True):
        1. A run exists in console.db for this FEAT, with a row for `phase`
        2. run_phases.status in {"pass", "warn" (if accept_warn)}
        3. payload.input_hash == compute_input_hash(input_paths)

    Returns:
        (resumable, reason). When resumable=False, `reason` uses a
        `[CHECKPOINT_*]` prefix (error-classification §1.14) for machine
        consumption. Fail-safe: any DB issue → (False, ...) (re-run the phase).
    """
    if root is None:
        root = repo_root()

    row = _latest_phase_row(feat, phase, root=root)
    if row is None:
        return False, (
            f"[CHECKPOINT_STATE_UNREADABLE] no run/phase '{phase}' for FEAT {feat} "
            "in console.db"
        )

    status = row["status"]
    valid_statuses = {"pass"} | ({"warn"} if accept_warn else set())
    if status not in valid_statuses:
        return False, (
            f"[CHECKPOINT_STATE_UNREADABLE] phase '{phase}' status='{status}' "
            f"(must be one of {sorted(valid_statuses)})"
        )

    stored_hash = _load_payload(row).get("input_hash")
    if not stored_hash:
        return False, (
            f"[CHECKPOINT_INPUT_MISSING] phase '{phase}' has no recorded "
            "input_hash (legacy run, can't validate)"
        )

    # Check declared inputs still exist
    missing = []
    for p in input_paths:
        pp = Path(p) if isinstance(p, str) else p
        if not pp.is_absolute():
            pp = root / pp
        if not pp.is_file():
            missing.append(str(p))
    if missing:
        return False, (
            f"[CHECKPOINT_INPUT_MISSING] inputs missing: {', '.join(missing)}"
        )

    current_hash = compute_input_hash(input_paths, root=root)
    if current_hash != stored_hash:
        return False, (
            f"[CHECKPOINT_HASH_MISMATCH] inputs changed since phase '{phase}' "
            f"ran (stored={stored_hash[:12]}..., current={current_hash[:12]}...)"
        )

    return True, "ok"


def get_phase_payload(
    feat: int,
    phase: str,
    *,
    root: Path | None = None,
) -> dict[str, Any] | None:
    """Read-only access to the payload of the latest run's phase entry.

    Useful for commands that want to retrieve cached metadata from a
    previous run (e.g. plan_validate results) without re-computing.
    Returns None if absent/unreadable.
    """
    if root is None:
        root = repo_root()
    row = _latest_phase_row(feat, phase, root=root)
    if row is None:
        return None
    return _load_payload(row)
