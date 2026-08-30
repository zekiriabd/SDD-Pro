"""validate_reverse_feat.py — Validate a reverse-generated FEAT (ADV-5).

Distinct from /feat-validate (validate_readiness.py) standard SDD_Pro which
checks stack/hash/mockups — absent at Phase 3 of reverse pipeline.

Invocation:
    python -m sdd_reverse_scripts.validate_reverse_feat \
        --feat-path workspace/feats/{n}-{Name}.md \
        [--legacy-root workspace/old/{P}] [--json]
    python -m sdd_reverse_scripts.validate_reverse_feat \
        --reconcile [--project workspace/old/{P}/] [--json]

--reconcile mode (ADV-21 V2 closure):
    Scans inventory.json._allocatedNames + _featAllocations for entries
    whose corresponding FEAT file has been manually deleted from disk.
    Removes the stale entries (idempotent), so the next /sdd-reverse {U-N}
    doesn't incorrectly suffix "-Legacy" on a name that's actually free.

Checks (deterministic, 0 token):
    1. Frontmatter YAML parsable + REQUIRED_FRONTMATTER_KEYS_REVERSE present
    2. confidence ∈ {high, medium, low}
    3. Required sections in fixed order (REQUIRED_SECTIONS)
    4. Stable IDs (SFD-N, FD-N, BR-N, AC-N) non-reordered
    5. AC in Given/When/Then format
    6. Each SFD/FD/BR/AC has <!-- evidence: ... --> and <!-- confidence: ... -->
    6.bis (audit C1, 2026-08-29) when --legacy-root is supplied, each evidence
       citation is RESOLVED on disk: the cited file must exist and hold at
       least `Lend` lines. Presence of the comment was the only thing ever
       checked before, so a fabricated `Foo.cs:34-38` validated GREEN. Without
       --legacy-root the check degrades to presence-only (backward compatible),
       never to a guess.
    7. REVERSE-GATE comment present + sync with frontmatter.confidence (ADV-22)
    8. Banner present if confidence=low

Exit:
    0  GREEN
    1  RED (structural errors)
    2  I/O error (file unreadable)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.evidence_resolver import resolve_evidence
from sdd_reverse.feat_structure_spec import (
    AC_GIVEN_WHEN_THEN_RE,
    CONFIDENCE_COMMENT_RE,
    CONFIDENCE_ENUM,
    EVIDENCE_COMMENT_RE,
    REQUIRED_FRONTMATTER_KEYS_REVERSE,
    REQUIRED_SECTIONS,
    REVERSE_GATE_RE,
    ID_PATTERNS,
    ids_are_stable,
    parse_frontmatter,
    section_order_violations,
)


# Same comment as EVIDENCE_COMMENT_RE but capturing the citation body, so it
# can be handed to the resolver (audit C1, 2026-08-29).
_EVIDENCE_REF_RE = re.compile(r"<!--\s*evidence:\s*([^>]+?)\s*-->")


def _check_items_have_evidence_and_confidence(
    content: str, section: str, legacy_root: Path | None = None,
) -> list[str]:
    """For each ID-line in section, verify the following lines/inline have evidence + confidence.

    When `legacy_root` is given (the `workspace/old/{P}/` the citations are
    relative to), each evidence ref is additionally RESOLVED on disk — file must
    exist and hold the cited line range (audit C1, 2026-08-29). Without it the
    check stays presence-only, as it has always been.
    """
    errors: list[str] = []
    pat = ID_PATTERNS.get(section)
    if not pat:
        return errors
    section_start = content.find(section)
    if section_start == -1:
        return errors
    next_section_start = -1
    for other in REQUIRED_SECTIONS:
        if other == section:
            continue
        idx = content.find(f"\n{other}", section_start + 1)
        if idx != -1 and (next_section_start == -1 or idx < next_section_start):
            next_section_start = idx
    section_body = content[section_start:next_section_start] if next_section_start != -1 else content[section_start:]

    # Audit 2026-06-11 (B2) : découpage par BLOC D'ITEM (début de l'item N →
    # début de la ligne de l'item N+1, ou fin de section) au lieu d'une fenêtre
    # fixe de 600 chars. L'ancienne fenêtre produisait (a) des faux négatifs —
    # un item sans evidence « couvert » par les commentaires de l'item suivant
    # quand les lignes étaient courtes — et (b) des faux
    # [REVERSE_EVIDENCE_MISSING] sur les items légitimes > 600 chars.
    matches = list(pat.finditer(section_body))
    for i, m in enumerate(matches):
        item_id = m.group(0).strip("-*: ")
        line_start = section_body.rfind("\n", 0, m.start()) + 1
        if i + 1 < len(matches):
            nxt_start = matches[i + 1].start()
            block_end = section_body.rfind("\n", 0, nxt_start) + 1
            if block_end <= line_start:
                block_end = nxt_start
        else:
            block_end = len(section_body)
        lookahead = section_body[line_start:block_end]
        ev_match = EVIDENCE_COMMENT_RE.search(lookahead)
        has_confidence = bool(CONFIDENCE_COMMENT_RE.search(lookahead))
        if not ev_match:
            errors.append(f"[REVERSE_EVIDENCE_MISSING] {item_id} in {section}: missing <!-- evidence: ... -->")
        elif legacy_root is not None:
            # EVIDENCE_COMMENT_RE (feat_structure_spec, shared with the DB path)
            # carries no capture group — re-read the ref itself, locally.
            ref_m = _EVIDENCE_REF_RE.search(lookahead)
            citation = ref_m.group(1).strip() if ref_m else ""
            if resolve_evidence(legacy_root, citation) is False:
                errors.append(
                    f"[REVERSE_EVIDENCE_MISSING] {item_id} in {section}: evidence "
                    f"'{citation}' does not resolve — no such file, or fewer lines "
                    f"than the cited range, under {legacy_root}")
        if not has_confidence:
            errors.append(f"{item_id} in {section}: missing <!-- confidence: ... -->")
    return errors


def validate_feat(
    feat_path: Path, legacy_root: Path | None = None,
) -> tuple[bool, list[str], list[str]]:
    """Validate a reverse FEAT.

    `legacy_root` (optional, `workspace/old/{P}/`) turns the per-item evidence
    check from "the comment is present" into "the citation resolves to a real
    file:line-range" (audit C1, 2026-08-29). Omitted → presence-only, as before.

    Returns (ok, errors, warnings).
    """
    if not feat_path.is_file():
        return False, [f"File not found: {feat_path}"], []

    try:
        content = feat_path.read_text(encoding="utf-8")
    except OSError as e:
        return False, [f"I/O error: {e}"], []

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Frontmatter
    fm, body = parse_frontmatter(content)
    if not fm:
        return False, ["Frontmatter YAML absent or malformed"], []
    missing_keys = REQUIRED_FRONTMATTER_KEYS_REVERSE - set(fm.keys())
    if missing_keys:
        errors.append(f"Frontmatter missing keys: {sorted(missing_keys)}")

    # 2. confidence enum
    fm_confidence = fm.get("confidence", "")
    if fm_confidence not in CONFIDENCE_ENUM:
        errors.append(
            f"confidence='{fm_confidence}' not in {sorted(CONFIDENCE_ENUM)} (strict enum)"
        )

    # 3. Required sections
    errors.extend(section_order_violations(body))

    # 4. Stable IDs
    for section in REQUIRED_SECTIONS:
        ok, msg = ids_are_stable(body, section)
        if not ok:
            errors.append(msg)

    # 5. AC Given/When/Then
    ac_section_start = body.find("## Acceptance Criteria")
    if ac_section_start != -1:
        next_idx = body.find("\n## ", ac_section_start + 1)
        ac_body = body[ac_section_start:next_idx] if next_idx != -1 else body[ac_section_start:]
        # Check each AC-N has a Given/When/Then nearby
        ac_pat = ID_PATTERNS["## Acceptance Criteria"]
        for m in ac_pat.finditer(ac_body):
            item_id = m.group(0).strip("-*: ")
            line_start = ac_body.rfind("\n", 0, m.start()) + 1
            lookahead = ac_body[line_start: line_start + 800]
            if not AC_GIVEN_WHEN_THEN_RE.search(lookahead):
                errors.append(f"AC-{m.group(1)} not in Given/When/Then format")

    # 6. Evidence + confidence per item
    for section in REQUIRED_SECTIONS:
        if section == "## Actors" or section == "## Project Config":
            continue  # no per-ID evidence required
        errors.extend(
            _check_items_have_evidence_and_confidence(body, section, legacy_root))

    # 7. REVERSE-GATE comment + sync (ADV-22)
    gate_match = REVERSE_GATE_RE.search(body)
    if not gate_match:
        errors.append("[REVERSE_GATE_DRIFT] <!-- REVERSE-GATE: ... --> comment missing (ADV-15)")
    else:
        gate_confidence = gate_match.group(1)
        if fm_confidence in CONFIDENCE_ENUM and gate_confidence != fm_confidence:
            errors.append(
                f"[REVERSE_GATE_DRIFT] frontmatter.confidence='{fm_confidence}' "
                f"!= comment.confidence='{gate_confidence}'"
            )
        gate_allow = gate_match.group(2)
        expected_allow = "true" if fm_confidence == "high" else "false"
        if gate_allow != expected_allow:
            errors.append(
                f"[REVERSE_GATE_DRIFT] allow-sdd-full='{gate_allow}' "
                f"inconsistent with confidence='{fm_confidence}' (expected '{expected_allow}')"
            )

    # 8. Low-confidence banner
    if fm_confidence == "low":
        # Banner: "> ⚠️" line within first 30 lines of body
        first_30 = "\n".join(body.splitlines()[:30])
        if "⚠️" not in first_30 and "WARNING" not in first_30.upper():
            warnings.append("confidence=low but no warning banner detected in first 30 lines")

    return not errors, errors, warnings


def reconcile_inventories(project_filter: str | None = None) -> dict:
    """ADV-21 : remove orphan entries from _allocatedNames + _featAllocations.

    Scans workspace/old/*/.sys/inventory.json, checks if each entry's FEAT
    file still exists on disk, removes stale ones.

    Audit 2026-06-10 M14 closure :
        - `--project` accepts a name OR a path (`workspace/old/P`) — it was
          compared raw against the directory name, making the filter inert ;
        - candidate stems are built from the SANITIZED name (same
          `_sanitize_name` as preallocate_feats) — raw suggestedName drift
          risked purging live allocations ;
        - workspace paths anchor on the repo root, never on the CWD.
    """
    import os

    from sdd_reverse.atomic_write_local import atomic_write_text
    from sdd_reverse.paths import workspace_root, repo_root
    from sdd_reverse_scripts.preallocate_feats import _sanitize_name

    override = os.environ.get("SDD_REVERSE_WORKSPACE_ROOT")
    root = Path(override).resolve() if override and Path(override).is_dir() else repo_root()
    workspace_old = workspace_root(root) / "old"
    workspace_feats = workspace_root(root) / "feats"
    if not workspace_old.is_dir():
        return {"ok": False, "error": "workspace/old/ not found", "reconciled": []}

    # Normalize the filter to a bare project name (tolerates path form).
    filter_name = Path(project_filter).name if project_filter else None

    feat_files_on_disk = set()
    if workspace_feats.is_dir():
        for f in workspace_feats.glob("*.md"):
            feat_files_on_disk.add(f.stem)  # e.g. "1-Login"

    reconciled: list[dict] = []
    for inv_path in workspace_old.rglob(".sys/inventory.json"):
        project_name = inv_path.parent.parent.name
        if filter_name and project_name != filter_name:
            continue
        try:
            inv = json.loads(inv_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        feat_allocs = inv.get("_featAllocations") or {}
        alloc_names = inv.get("_allocatedNames") or {}
        # Reverse-map U-N → expected file stem
        unit_by_id = {u["id"]: u for u in (inv.get("units") or [])}

        def _stems_for(unit_id: str, n: int) -> list[str]:
            unit = unit_by_id.get(unit_id)
            base = _sanitize_name(
                (unit or {}).get("suggestedName") or unit_id
            )
            return [
                f"{n}-{base}",
                f"{n}-{base}-Legacy",
                f"{n}-{base}-Legacy-{unit_id}",
            ]

        removed_allocs: list[str] = []
        removed_names: list[str] = []
        for unit_id, n in list(feat_allocs.items()):
            if unit_id not in unit_by_id:
                # Unknown unit (e.g. crosscut XC-* or stale id) — leave intact,
                # conservative : never purge what we cannot verify.
                continue
            # Allocated names registered for this unit take precedence over the
            # re-derived sanitized base (exact stem knowledge).
            allocated_for_unit = [nm for nm, uid in alloc_names.items() if uid == unit_id]
            possible_stems = [f"{n}-{nm}" for nm in allocated_for_unit] + _stems_for(unit_id, n)
            if not any(s in feat_files_on_disk for s in possible_stems):
                removed_allocs.append(unit_id)
                del feat_allocs[unit_id]
        import re as _re
        for name, uid in list(alloc_names.items()):
            if uid not in unit_by_id and uid not in feat_allocs:
                continue  # conservative — unknown owner, keep
            # Orphan iff NO feat file stem matches `{digits}-{name}` exactly.
            stem_re = _re.compile(rf"^\d+-{_re.escape(name)}$")
            if not any(stem_re.match(s) for s in feat_files_on_disk):
                removed_names.append(name)
                del alloc_names[name]

        if removed_allocs or removed_names:
            inv["_featAllocations"] = feat_allocs
            inv["_allocatedNames"] = alloc_names
            atomic_write_text(inv_path,
                               json.dumps(inv, indent=2, ensure_ascii=False) + "\n")
            reconciled.append({
                "project": project_name,
                "removed_featAllocations": removed_allocs,
                "removed_allocatedNames": removed_names,
            })

    return {"ok": True, "reconciled": reconciled}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_reverse_feat",
        description="Validate a reverse-generated FEAT (ADV-5 — distinct from /feat-validate).",
    )
    parser.add_argument("--feat-path", help="Path to {n}-{Name}.md (validation mode)")
    parser.add_argument("--reconcile", action="store_true",
        help="Reconcile mode (ADV-21): remove orphan _allocatedNames / _featAllocations entries")
    parser.add_argument("--project", default=None,
        help="In --reconcile mode: limit to one project under workspace/old/")
    parser.add_argument("--legacy-root", default=None,
        help="Legacy project root (workspace/old/{P}) the evidence citations are "
             "relative to. Supplied → each <!-- evidence: path:Lx-Ly --> is "
             "RESOLVED on disk (file exists + holds the cited range). Omitted → "
             "presence-only check (audit C1, 2026-08-29).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    ensure_console_safe()

    # --reconcile mode (ADV-21)
    if args.reconcile:
        report = reconcile_inventories(args.project)
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            if not report["reconciled"]:
                print("[VALIDATE_REVERSE] --reconcile : aucune entrée orpheline détectée.")
            else:
                for r in report["reconciled"]:
                    n_alloc = len(r["removed_featAllocations"])
                    n_names = len(r["removed_allocatedNames"])
                    print(f"[VALIDATE_REVERSE/RECONCILE] {r['project']} : "
                          f"-{n_alloc} _featAllocations, -{n_names} _allocatedNames orphans removed.")
        return 0

    if not args.feat_path:
        parser.error("--feat-path required (unless --reconcile)")
    feat_path = Path(args.feat_path)
    legacy_root = Path(args.legacy_root) if args.legacy_root else None
    if legacy_root is not None and not legacy_root.is_dir():
        print(f"[WARN] --legacy-root {legacy_root} is not a directory — evidence "
              f"resolution disabled (presence-only check).", file=sys.stderr)
        legacy_root = None
    ok, errors, warnings = validate_feat(feat_path, legacy_root)

    if args.json:
        print(json.dumps({
            "ok": ok,
            "feat_path": str(feat_path),
            "legacy_root": str(legacy_root) if legacy_root else None,
            "evidence_resolved": legacy_root is not None,
            "errors": errors,
            "warnings": warnings,
        }, ensure_ascii=False))
    else:
        # ASCII markers (M10 — Windows cp1252 console compat)
        if ok:
            print(f"[GREEN] [VALIDATE_REVERSE] {feat_path.name} - structure valide ({len(warnings)} warning).")
        else:
            print(f"[RED] [VALIDATE_REVERSE] {feat_path.name} - {len(errors)} erreur(s) :")
            for e in errors:
                print(f"  - {e}")
            for w in warnings:
                print(f"  [WARN] {w}")
    return 0 if ok else (2 if not feat_path.is_file() else 1)


if __name__ == "__main__":
    sys.exit(main())
