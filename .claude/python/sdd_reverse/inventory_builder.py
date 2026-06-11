"""inventory_builder.py — Build inventory.json from a scan result.

Produces the canonical inventory.json per design doc §5.1.

Key responsibilities:
    - Allocate stable U-N IDs via dual fingerprint (full + core)        # ADV-1 + ADV-11
    - Initialize _allocatedNames + _featAllocations to {} explicitly    # ADV-23
    - Track legacyMtimeMax (max mtime of scanned files)                 # ADV-1
    - Preserve U-N mapping across re-runs (load existing inventory)

Public API:
    build_inventory(project_root, scan_result, pages, units, existing_inventory=None) -> dict
    compute_unit_fingerprint_full(evidence_paths, label) -> str
    compute_unit_fingerprint_core(top3_paths, label) -> str
    select_top3_distinctive(evidence_files, file_bytes_map, signatures, language_id) -> list[Path]

ADV-23: schemaVersion is hardcoded to 1. Consumers MUST check it.
ADV-20: normalize_bytes is reused for size measurement (BOM + EOL stripped).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import ScanResult, normalize_bytes

INVENTORY_SCHEMA_VERSION = 1


def _normalize_label(label: str) -> str:
    return label.strip().lower()


def compute_unit_fingerprint_full(evidence_paths: list[str], label: str) -> str:
    """sha256 over sorted paths + normalized label (ADV-1 strict variant)."""
    sorted_paths = sorted(evidence_paths)
    blob = ("\n".join(sorted_paths) + "\n" + _normalize_label(label)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def compute_unit_fingerprint_core(top3_paths: list[str], label: str) -> str:
    """sha256 over top-3 distinctive paths + normalized label (ADV-1 resilient variant)."""
    sorted_paths = sorted(top3_paths)
    blob = ("\n".join(sorted_paths) + "\n" + _normalize_label(label)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def select_top3_distinctive(
    evidence_files: list[Path],
    project_root: Path,
    signatures: dict[str, Any],
    language_id: str,
) -> list[str]:
    """Pick top-3 distinctive evidence files per ADV-11 criteria.

    Scoring (deterministic, cross-OS stable):
        1. Primary: cumulative evidence_pattern.weight matched in the file
        2. Tie-break 1: len(normalize_bytes(file_bytes)) — BOM + EOL stripped
        3. Tie-break 2: path lexicographic
    """
    import re as _re

    lang = next((l for l in signatures["languages"] if l["id"] == language_id), None)
    if not lang:
        return [str(p.relative_to(project_root).as_posix()) for p in evidence_files[:3]]

    patterns = lang.get("evidence_patterns") or []
    scored: list[tuple[float, int, str, Path]] = []
    for p in evidence_files:
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        norm = normalize_bytes(raw)
        try:
            text = norm.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        weight = 0.0
        for ep in patterns:
            pat = ep.get("pattern")
            w = float(ep.get("weight", 0.0))
            if not pat:
                continue
            try:
                if _re.search(pat, text):
                    weight += w
            except _re.error:
                continue
        rel = p.relative_to(project_root).as_posix()
        scored.append((weight, len(norm), rel, p))

    # Sort: weight desc, size desc, path asc.
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return [t[2] for t in scored[:3]]


def _compute_legacy_mtime_max(project_root: Path, scanned_files: list[Path]) -> int:
    """Return max mtime UNIX seconds across scanned files."""
    if not scanned_files:
        try:
            return int(project_root.stat().st_mtime)
        except OSError:
            return 0
    max_mtime = 0
    for f in scanned_files:
        try:
            mt = int(f.stat().st_mtime)
            if mt > max_mtime:
                max_mtime = mt
        except OSError:
            continue
    return max_mtime


def build_inventory(
    project_name: str,
    project_root: str | Path,
    scan_result: ScanResult,
    pages: list[dict[str, Any]],
    units_candidates: list[dict[str, Any]],
    signatures: dict[str, Any],
    existing_inventory: dict[str, Any] | None = None,
    entry_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble inventory.json from scan + page/unit candidates.

    Args:
        project_name: project label
        project_root: workspace/old/{P}/
        scan_result: output of scan_legacy.scan_project()
        pages: list of {id, path, codeBehindPath, locTotal, linkedUnits}
        units_candidates: list of {label, suggestedName, language, kind,
                                    evidenceFiles, entities, confidenceEstimate, rationale}
        signatures: language_signatures.yml loaded dict
        existing_inventory: previous inventory.json content (for U-N stability)
    """
    root = Path(project_root).resolve()
    existing_fp_map: dict[str, dict[str, Any]] = {}
    existing_feat_allocations: dict[str, int] = {}
    existing_allocated_names: dict[str, str] = {}
    next_id = 1
    if existing_inventory and existing_inventory.get("schemaVersion") == INVENTORY_SCHEMA_VERSION:
        existing_fp_map = dict(existing_inventory.get("_fingerprintMap") or {})
        existing_feat_allocations = dict(existing_inventory.get("_featAllocations") or {})
        existing_allocated_names = dict(existing_inventory.get("_allocatedNames") or {})
        # Compute next free U-N (max existing + 1)
        used_ids: list[int] = []
        for v in existing_fp_map.values():
            uid = v.get("unitId", "")
            if uid.startswith("U-"):
                try:
                    used_ids.append(int(uid[2:]))
                except ValueError:
                    continue
        if used_ids:
            next_id = max(used_ids) + 1

    # Mark all existing as potentially stale; we'll un-stale matched ones.
    new_fp_map: dict[str, dict[str, Any]] = {
        k: {**v, "status": "stale"} for k, v in existing_fp_map.items()
    }

    def _to_rel(paths: list[str]) -> list[str]:
        return [
            str(Path(p).relative_to(root).as_posix()) if Path(p).is_absolute()
            else str(Path(p).as_posix())
            for p in paths
        ]

    finalized_units: list[dict[str, Any]] = []
    for cand in units_candidates:
        # Full (possibly transitively-enriched) evidence — what the agent reads.
        evidence_paths_rel = _to_rel(cand["evidenceFiles"])
        # Seed evidence (page + code-behind) — drives the U-N fingerprint so that
        # L0 graph-walk enrichment never destabilises U-N IDs across re-runs.
        seed_rel = _to_rel(cand.get("fingerprintSeed") or cand.get("seedEvidenceFiles")
                           or cand["evidenceFiles"])
        seed_abs = [
            Path(p) if Path(p).is_absolute() else (root / p)
            for p in (cand.get("fingerprintSeed") or cand.get("seedEvidenceFiles")
                      or cand["evidenceFiles"])
        ]
        label = cand["label"]
        fp_full = compute_unit_fingerprint_full(seed_rel, label)
        top3 = select_top3_distinctive(
            seed_abs, root, signatures, cand.get("language", "unknown")
        )
        fp_core = compute_unit_fingerprint_core(top3, label)

        # Resolve U-N: full match > core match > new
        unit_id: str | None = None
        for fp_key in (fp_full, fp_core):
            entry = existing_fp_map.get(fp_key)
            if entry and entry.get("unitId"):
                unit_id = entry["unitId"]
                break

        if unit_id is None:
            unit_id = f"U-{next_id}"
            next_id += 1

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for fp_key in (fp_full, fp_core):
            new_fp_map[fp_key] = {
                "unitId": unit_id,
                "status": "active",
                "firstSeen": (
                    existing_fp_map.get(fp_key, {}).get("firstSeen") or now_iso
                ),
            }

        finalized_unit_extra: dict[str, Any] = {}
        if cand.get("cliCommands"):
            # C2 : CLI/batch command tokens detected on kind=job units —
            # consumed by the Phase 3 extractor (1 FD per commande visible).
            finalized_unit_extra["cliCommands"] = cand["cliCommands"]
        finalized_units.append({
            "id": unit_id,
            "label": label,
            "suggestedName": cand["suggestedName"],
            "language": cand.get("language", "unknown"),
            "kind": cand.get("kind", "unknown"),
            **finalized_unit_extra,
            "evidenceFiles": evidence_paths_rel,
            # L0: provenance of the seed (page + code-behind) before graph-walk.
            "seedEvidenceFiles": seed_rel,
            # L0: role-classified classes reached transitively from the seed.
            "classes": cand.get("classes", []),
            # L1: SQL queries + stored-proc calls owned by this unit's files.
            "dataAccess": cand.get("dataAccess", {}),
            "entities": sorted(set(cand.get("entities", []))),
            "confidenceEstimate": cand.get("confidenceEstimate", "low"),
            "rationale": cand.get("rationale", ""),
        })

    # Collect actual scanned file paths from the scan result for mtime computation.
    scanned_files: list[Path] = []
    for lm in scan_result.languages:
        scanned_files.extend(lm.files)
    legacy_mtime_max = _compute_legacy_mtime_max(root, scanned_files)

    inventory: dict[str, Any] = {
        "schemaVersion": INVENTORY_SCHEMA_VERSION,
        "project": project_name,
        "scanDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scanDurationMs": scan_result.duration_ms,
        "languagesDetected": scan_result.to_dict()["languagesDetected"],
        "primaryLanguage": scan_result.primary_language,
        "frameworksDetected": scan_result.frameworks,
        "entryPoints": entry_points or [],
        "exclusions": sorted({"bin/", "obj/", "node_modules/", ".git/", "packages/"}),
        "pages": pages,
        "units": finalized_units,
        "legacyMtimeMax": legacy_mtime_max,
        "_fingerprintMap": new_fp_map,
        "_featAllocations": existing_feat_allocations,   # ADV-23: always {} or preserved dict
        "_allocatedNames": existing_allocated_names,      # ADV-23: always {} or preserved dict
    }
    return inventory


def validate_inventory_schema(inventory: dict[str, Any]) -> tuple[bool, str]:
    """Validate inventory shape per ADV-23 strict checks.

    Returns (ok, reason_if_not_ok).
    """
    if inventory.get("schemaVersion") != INVENTORY_SCHEMA_VERSION:
        return False, f"schemaVersion != {INVENTORY_SCHEMA_VERSION}"
    if "_allocatedNames" not in inventory:
        return False, "_allocatedNames missing (ADV-23 schema gate)"
    if "_featAllocations" not in inventory:
        return False, "_featAllocations missing (ADV-23 schema gate)"
    if not isinstance(inventory["_allocatedNames"], dict):
        return False, "_allocatedNames not a dict"
    if not isinstance(inventory["_featAllocations"], dict):
        return False, "_featAllocations not a dict"
    return True, ""
