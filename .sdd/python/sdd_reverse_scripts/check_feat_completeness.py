"""check_feat_completeness.py — Deterministic back-side completeness review (L5).

The reverse pipeline's worst failure mode was a FEAT that "looks fine" but
silently omitted the deep business layer (the user's complaint: "il n'est pas
rentré dans chaque classe"). The structural validator (`validate_reverse_feat`)
cannot catch this — a 1-AC FEAT passes it.

This checker confronts a reverse FEAT against its unit's L0/L1 evidence
(inventory `units[U-N].classes` + `dataAccess`) and flags what the extraction
did NOT mention:

    - behavioural classes (repository / service / controller / complex) whose
      name appears NOWHERE in the FEAT  → likely un-extracted logic
    - SQL tables touched by the unit but not referenced in the FEAT  → likely
      un-documented data behaviour
    - stored-procedure calls not mentioned

Verdict is INFORMATIONAL (never blocks `/sdd-full`) — it is a richness signal
for the Tech Lead and the orchestrator, mirroring the forward pipeline's
spec-compliance reviewer but on the reverse "did we capture enough?" axis.

Invocation:
    python -m sdd_reverse_scripts.check_feat_completeness --project workspace/old/{P} --unit U-3 [--json]
    python -m sdd_reverse_scripts.check_feat_completeness --feat-path workspace/feats/3-X.md --project workspace/old/{P} [--json]

Exit: 0 (always — informational) ; 1 bad args ; 2 unit/feat not found
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.console_safe import ensure_console_safe

# `viewmodel` added 2026-06-10 (audit C1) — MVVM business layer is behavioural.
_BEHAVIOURAL = {"repository", "service", "controller", "complex", "viewmodel"}


def _load_json(p: Path) -> dict[str, Any] | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolve_unit(inventory: dict[str, Any], *, unit_id: str | None,
                  feat_source_unit: str | None) -> dict[str, Any] | None:
    target = unit_id or feat_source_unit
    if not target:
        return None
    for u in inventory.get("units", []):
        if u["id"] == target:
            return u
    return None


def _mentioned(name: str, low_feat: str) -> bool:
    """True if `name` appears in the FEAT, qualified or by its leaf.

    Object names are schema-qualified since finding D1 (`dbo.Orders`), while a
    FEAT may legitimately cite either form — comparing only the full string would
    manufacture phantom gaps.
    """
    n = (name or "").strip().lower()
    if not n:
        return True
    return n in low_feat or n.rsplit(".", 1)[-1] in low_feat


def assess_db_module(unit: dict[str, Any], feat_text: str) -> dict[str, Any]:
    """Completeness of a DB-reverse module FEAT vs its SQL objects.

    Audit finding M3 (2026-08-25): this checker only understood the CODE-reverse
    unit shape (`units[].classes` + `dataAccess`). A DB-reverse unit
    (`kind: db-module`) carries `units[].procedures` instead, so the checker
    found nothing to compare and returned a vacuous "complete" — worse than no
    check at all, because it looked like a green verdict.

    What matters for a SQL module, in order of severity:
      - a SQL object of the module not named in the FEAT: the object IS the
        capability, so an omission means a lost capability;
      - a raised precondition (`RAISERROR`/`THROW`/`RAISE`/`SIGNAL`) with no trace
        in the FEAT: that is a business RULE silently dropped;
      - a written table not mentioned: undocumented data effect;
      - an encrypted object: an inherent, irreducible gap — reported so it is
        visible, never counted as an extraction failure.
    """
    gaps: list[dict[str, str]] = []
    low = feat_text.lower()
    procs = unit.get("procedures", []) or []

    for p in procs:
        fq = p.get("fqName", "")
        if not _mentioned(fq, low):
            gaps.append({
                "type": "sql_object_not_mentioned",
                "item": fq,
                "role": str(p.get("routineType") or "routine"),
                "severity": "serious",
                "evidence": p.get("evidence", "?"),
            })
            # An object absent from the FEAT makes its own rules moot — do not
            # pile up derived gaps that all say the same thing.
            continue

        if p.get("raises") and not any(
            r.lower() in low for r in ("précondition", "precondition", "erreur",
                                       "refus", "rejet", *[
                                           str(x).lower() for x in p.get("raises", [])])
        ):
            gaps.append({
                "type": "raised_rule_not_mentioned",
                "item": f"{fq} ({', '.join(p.get('raises', []))})",
                "severity": "serious",
                "evidence": p.get("evidence", "?"),
            })

        for table in p.get("tablesWritten", []) or []:
            if not _mentioned(table, low):
                gaps.append({
                    "type": "written_table_not_mentioned",
                    "item": table,
                    "severity": "moderate",
                    "evidence": p.get("evidence", "?"),
                })

        if p.get("encrypted"):
            gaps.append({
                "type": "encrypted_object",
                "item": fq,
                "severity": "info",
                "evidence": p.get("evidence", "?"),
            })

    serious = sum(1 for g in gaps if g["severity"] == "serious")
    actionable = [g for g in gaps if g["severity"] != "info"]
    if serious:
        verdict = "incomplete"
    elif actionable:
        verdict = "partial"
    else:
        verdict = "complete"
    return {
        "unit": unit["id"],
        "kind": "db-module",
        "verdict": verdict,
        "gaps": gaps,
        "summary": {
            "sqlObjects": len(procs),
            "encrypted": sum(1 for p in procs if p.get("encrypted")),
            "gapsTotal": len(actionable),
            "serious": serious,
        },
    }


def assess(unit: dict[str, Any], feat_text: str) -> dict[str, Any]:
    """Compute completeness gaps for a unit vs its FEAT text. Pure."""
    # M3 — dispatch on the unit shape. A DB-reverse unit has `procedures`, never
    # `classes`; running the code-reverse rubric on it yields a vacuous pass.
    if unit.get("kind") == "db-module" or (
        unit.get("procedures") and not unit.get("classes")
    ):
        return assess_db_module(unit, feat_text)

    gaps: list[dict[str, str]] = []
    low = feat_text.lower()

    for c in unit.get("classes", []):
        if c.get("role") in _BEHAVIOURAL:
            if c["name"].lower() not in low:
                gaps.append({
                    "type": "class_not_mentioned",
                    "item": c["name"],
                    "role": c["role"],
                    "severity": "serious" if c["role"] in ("repository", "service", "viewmodel") else "moderate",
                    "evidence": f"{c.get('file', '?')}:{c.get('lines', '?')}",
                })

    da = unit.get("dataAccess", {}) or {}
    tables: set[str] = set()
    for q in da.get("queries", []):
        tables.update(q.get("tables", []))
    for t in sorted(tables):
        if t.lower() not in low:
            gaps.append({
                "type": "table_not_mentioned",
                "item": t,
                "severity": "moderate",
                "evidence": "dataAccess.queries",
            })
    for call in da.get("storedProcedureCalls", []):
        nm = call.get("name", "")
        if nm and nm.lower() not in low:
            gaps.append({
                "type": "stored_proc_not_mentioned",
                "item": nm,
                "severity": "serious",
                "evidence": f"{call.get('file', '?')}:{call.get('line', '?')}",
            })

    serious = sum(1 for g in gaps if g["severity"] == "serious")
    # ASCII verdict values (M10 — emojis in this JSON field crashed the
    # human-output path on cp1252 consoles). Consumers match on the bare word.
    if serious:
        verdict = "incomplete"
    elif gaps:
        verdict = "partial"
    else:
        verdict = "complete"
    return {
        "unit": unit["id"],
        "verdict": verdict,
        "gaps": gaps,
        "summary": {
            "behaviouralClasses": sum(1 for c in unit.get("classes", []) if c.get("role") in _BEHAVIOURAL),
            "gapsTotal": len(gaps),
            "serious": serious,
        },
    }


def _find_feat_for_unit(feats_dir: Path, n: int | None, unit_id: str) -> Path | None:
    if not feats_dir.is_dir():
        return None
    if n is not None:
        hits = list(feats_dir.glob(f"{n}-*.md"))
        if hits:
            return hits[0]
    # fallback: scan for source-unit frontmatter
    for f in feats_dir.glob("*.md"):
        txt = f.read_text(encoding="utf-8", errors="replace")
        if re.search(rf"source-unit:\s*{re.escape(unit_id)}\b", txt):
            return f
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_feat_completeness")
    parser.add_argument("--project", required=True)
    parser.add_argument("--unit", default=None, help="U-N")
    parser.add_argument("--feat-path", default=None)
    parser.add_argument("--feats-dir", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    ensure_console_safe()

    project_root = Path(args.project).resolve()
    inventory = _load_json(project_root / ".sys" / "inventory.json")
    if not inventory:
        print("ERROR: [REVERSE_NO_SOURCE] inventory.json missing.", file=sys.stderr)
        return 2

    feat_text = ""
    feat_source_unit = None
    if args.feat_path:
        fp = Path(args.feat_path)
        if not fp.is_file():
            print(f"ERROR: feat not found: {fp}", file=sys.stderr)
            return 2
        feat_text = fp.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"source-unit:\s*(\S+)", feat_text)
        feat_source_unit = m.group(1) if m else None

    unit = _resolve_unit(inventory, unit_id=args.unit, feat_source_unit=feat_source_unit)
    if unit is None:
        print(f"ERROR: [REVERSE_UNIT_NOT_FOUND] unit {args.unit or feat_source_unit} absent.",
              file=sys.stderr)
        return 2

    if not feat_text:
        feats_dir = Path(args.feats_dir).resolve() if args.feats_dir else (
            project_root.parent.parent / "feats"
        )
        n = (inventory.get("_featAllocations") or {}).get(unit["id"])
        fp = _find_feat_for_unit(feats_dir, n, unit["id"])
        if fp is None:
            print(f"ERROR: [REVERSE_UNIT_NOT_FOUND] no FEAT for {unit['id']}.", file=sys.stderr)
            return 2
        feat_text = fp.read_text(encoding="utf-8", errors="replace")

    report = assess(unit, feat_text)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"[REVERSE] Complétude {report['unit']} : {report['verdict']} "
              f"({report['summary']['gapsTotal']} gap(s), "
              f"{report['summary']['serious']} sérieux). (100%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
