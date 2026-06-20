"""SDD_Pro checkpoint helpers — input-hash validated phase resumption.

Layered on top of `sdd_scripts/sdd_state.py` (which already tracks phase
status in `workspace/output/.sys/.state/run-{runId}.json`). This module
adds **input-hash validation** so that `--resume` can detect when a
phase's inputs (US, plan, stack, etc.) have been modified post-crash
and must therefore be re-run rather than skipped.

Design rationale:
    - `sdd_state.py` answers "did phase X complete successfully ?"
    - `checkpoint.py` answers "is the phase X result still valid given
      the current inputs ?" (= same hash) → safe to skip on resume

API (3 functions):
    compute_input_hash(paths) -> str
        SHA-256 over concatenated bytes of the listed files (skips
        missing files, stable order). Deterministic.

    record_input_hash(run_id, phase, input_paths) -> str
        Compute hash, store under state.json `phases.{phase}.payload.input_hash`.
        Returns the computed hash. Called at phase start.

    is_phase_resumable(feat, phase, input_paths) -> tuple[bool, str]
        Looks up the latest run for FEAT, checks:
          1. phase.status == "pass" (completed successfully)
          2. phase.payload.input_hash == compute_input_hash(input_paths)
             (inputs unchanged)
        Returns (resumable, reason).

Non-regression contract:
    - This module **never** modifies state.json directly except through
      sdd_state.py's public CLI (subprocess call) or by reading/writing
      the same JSON schema atomically.
    - If `sdd_state.py` is unavailable or state.json corrupted, the
      functions return False/missing (= safe default: re-run the phase).
    - Adoption in commands is **optional** — v6.6.2 ships the lib only.
      Commands can integrate gradually.

Classes d'erreur :
    [CHECKPOINT_HASH_MISMATCH] — input_hash stocké ≠ recalculé → invalidé
    [CHECKPOINT_INPUT_MISSING] — un input_path déclaré n'existe pas
    [CHECKPOINT_STATE_UNREADABLE] — state.json absent ou corrompu

v6.6.2 — additive, opt-in. Aucune command n'invoque ce lib en v6.6.2.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sdd_lib.paths import repo_root


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


def _state_dir(root: Path) -> Path:
    return root / "workspace" / "output" / ".sys" / ".state"


def _find_latest_state_for_feat(feat: int, *, root: Path | None = None) -> Path | None:
    """Return path to the latest run-*.json for the given FEAT, or None."""
    if root is None:
        root = repo_root()
    sd = _state_dir(root)
    if not sd.is_dir():
        return None

    candidates: list[tuple[float, Path]] = []
    for f in sd.glob("run-*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if int(data.get("FeatNumber", -1)) == feat:
                mtime = f.stat().st_mtime
                candidates.append((mtime, f))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def record_input_hash(
    run_id: str,
    phase: str,
    input_paths: list[Path | str],
    *,
    root: Path | None = None,
) -> str:
    """Compute input hash and store it under phases.{phase}.payload.input_hash.

    Returns the computed hash. If the state file is missing or unreadable,
    raises FileNotFoundError or ValueError so the caller can decide.

    Modifies state.json directly (atomic write via tempfile + rename).
    The phase entry is created if it doesn't exist.
    """
    if root is None:
        root = repo_root()

    sd = _state_dir(root)
    state_path = sd / f"run-{run_id}.json"
    if not state_path.is_file():
        raise FileNotFoundError(
            f"[CHECKPOINT_STATE_UNREADABLE] state file not found: {state_path}"
        )

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(
            f"[CHECKPOINT_STATE_UNREADABLE] cannot parse state file: {e}"
        ) from e

    h = compute_input_hash(input_paths, root=root)

    phases = state.setdefault("phases", {})
    phase_entry = phases.setdefault(phase, {})
    payload = phase_entry.setdefault("payload", {})
    if not isinstance(payload, dict):
        payload = {}
        phase_entry["payload"] = payload
    payload["input_hash"] = h
    payload["input_paths"] = [str(p) for p in input_paths]

    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(state_path)
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
        1. A run-{id}.json exists for this FEAT
        2. phases.{phase}.status in {"pass", "warn" (if accept_warn)}
        3. phases.{phase}.payload.input_hash == compute_input_hash(input_paths)

    Returns:
        (resumable, reason). When resumable=False, `reason` explains why
        and uses a `[CHECKPOINT_*]` prefix from error-classification §1.16
        for machine consumption.
    """
    if root is None:
        root = repo_root()

    state_path = _find_latest_state_for_feat(feat, root=root)
    if state_path is None:
        return False, "[CHECKPOINT_STATE_UNREADABLE] no run found for this FEAT"

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return False, f"[CHECKPOINT_STATE_UNREADABLE] {e}"

    phases = state.get("phases", {})
    phase_entry = phases.get(phase)
    if not isinstance(phase_entry, dict):
        return False, f"[CHECKPOINT_STATE_UNREADABLE] phase '{phase}' absent from state"

    status = phase_entry.get("status")
    valid_statuses = {"pass"} | ({"warn"} if accept_warn else set())
    if status not in valid_statuses:
        return False, (
            f"[CHECKPOINT_STATE_UNREADABLE] phase '{phase}' status='{status}' "
            f"(must be one of {sorted(valid_statuses)})"
        )

    payload = phase_entry.get("payload", {})
    stored_hash = payload.get("input_hash") if isinstance(payload, dict) else None
    if not stored_hash:
        return False, (
            f"[CHECKPOINT_INPUT_MISSING] phase '{phase}' has no recorded "
            "input_hash (legacy run, can't validate)"
        )

    # Check inputs exist
    missing = []
    for p in input_paths:
        if isinstance(p, str):
            pp = Path(p)
        else:
            pp = p
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
    """
    if root is None:
        root = repo_root()
    state_path = _find_latest_state_for_feat(feat, root=root)
    if state_path is None:
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    phase_entry = state.get("phases", {}).get(phase)
    if not isinstance(phase_entry, dict):
        return None
    payload = phase_entry.get("payload")
    return payload if isinstance(payload, dict) else None
