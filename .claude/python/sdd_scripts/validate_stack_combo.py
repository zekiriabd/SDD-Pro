#!/usr/bin/env python3
"""SDD_Pro: validate_stack_combo — déterministe combo validation (v7.0.0+).

Calcule la signature du combo actif depuis stack.md et la compare au
catalogue canonique de combos validés bout-en-bout (cf.
@.claude/docs/validated-combos.md).

Résout la critique M3 de l'audit v7.0.0-alpha (2026-05-20) :
    « 16 stacks → ~120 combinaisons possibles, 2 validées bout-en-bout.
      Le risque que le pipeline casse en runtime sur un combo non-PoC
      est explicitement reconnu. Promesse multi-stacks largement théorique. »

Usage:
    python validate_stack_combo.py [--json] [--quiet]

Exit codes:
    0  validated     — combo matche un PoC (C1 ou C2)
    1  experimental  — au moins un composant 🟡 (stack OK mais combo jamais testé)
    2  untested      — au moins un composant 🔴 (jamais utilisé, risque élevé)
                       Bypass via env var SDD_ALLOW_UNTESTED_COMBO=1
    3  invalid       — combo incohérent ([STACK_COMBO_INVALID])
    4  io_error      — stack.md absent / illisible

Output JSON (stdout si --json) :
    {
      "signature": "kotlin-spring-boot+react+shadcn+kotlin-junit+azure-ad+postgres+ddd",
      "matched_combo": "C2" | null,
      "status": "validated" | "experimental" | "untested" | "invalid",
      "exit_code": 0,
      "components": {
        "backend": {"id": str | null, "level": "validated|experimental|untested|missing"},
        "frontend": {...},
        "ui": {...},
        "qa": [...],
        "auth": {...},
        "db": {...},
        "archi": {...}
      },
      "warnings": [str, ...],
      "bypass_active": bool
    }

Audit trail :
    Exit ≥ 2 sans SDD_ALLOW_UNTESTED_COMBO=1 logue dans
    workspace/output/.sys/.audit/untested-combo.log.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.combos import (  # noqa: E402
    get_component_level,
    get_component_levels,
    get_level_priority,
    get_validated_combos,
)
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.project_config import read_stack_md_text, section_body, stack_md_path  # noqa: E402


# ---------------------------------------------------------------------------
# v7.0.0-alpha (audit CRIT-6, 2026-06-04) — catalogue + levels désormais SSoT
# dans `.claude/templates/combos.json` (cf. sdd_lib/combos.py loader).
# Les helpers ci-dessous reconstruisent les structures attendues par le code
# aval, qui était écrit pour des dicts module-level. Cache mtime-keyed via
# functools.lru_cache dans sdd_lib.combos — re-read automatique sur édition.
# ---------------------------------------------------------------------------


def _validated_combos() -> list[dict[str, object]]:
    """Adapter : combos.json → format attendu par `_match_combo` (qa as set)."""
    out: list[dict[str, object]] = []
    for raw in get_validated_combos():
        combo = dict(raw)
        combo["qa"] = set(raw.get("qa", []))  # JSON arrays → Python set
        # Backward-compat alias for the field renamed in JSON.
        if "validatedAt" in combo and "validated_at" not in combo:
            combo["validated_at"] = combo["validatedAt"]
        out.append(combo)
    return out


def _component_levels_dict() -> dict[str, dict[str, str]]:
    """Adapter : combos.json::componentLevels → 2D dict (per legacy callers)."""
    return get_component_levels()


def _level_priority() -> dict[str, int]:
    return get_level_priority()


# Module-level constants reconstructed on first import — preserves the
# behavioural contract for any external caller doing
# `from validate_stack_combo import VALIDATED_COMBOS, COMPONENT_LEVELS, LEVEL_PRIORITY`.
VALIDATED_COMBOS: list[dict[str, object]] = _validated_combos()
COMPONENT_LEVELS: dict[str, dict[str, str]] = _component_levels_dict()
LEVEL_PRIORITY: dict[str, int] = _level_priority()

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_ACTIVE_STACK_RE = re.compile(r"^\s*-\s*\.claude/stacks/([^/]+)/([^/\s]+)\.md\s*$")
_DB_TYPE_RE = re.compile(r"^\s*-?\s*DatabaseType\s*:\s*([A-Za-z]+)\s*$", re.MULTILINE)


def _parse_active_stacks(block: str | None, category: str) -> list[str]:
    if block is None:
        return []
    ids: list[str] = []
    for line in block.splitlines():
        m = _ACTIVE_STACK_RE.match(line)
        if m and m.group(1) == category:
            ids.append(m.group(2))
    return ids


def _parse_database_type(text: str) -> str:
    block = section_body(text, "Active Database")
    if block is None:
        return "none"
    m = _DB_TYPE_RE.search(block)
    return m.group(1).strip().lower() if m else "none"


def _parse_archi_pattern(text: str) -> str | None:
    block = section_body(text, "Active Architecture Pattern")
    if block is None:
        return None
    ids = _parse_active_stacks(block, "archi")
    return ids[0] if ids else None


def _component_level(category: str, stack_id: str | None) -> str:
    # v7.0.0-alpha (audit CRIT-6) : delegate to combos.json SSoT.
    return get_component_level(category, stack_id)


def _match_combo(components: dict) -> dict | None:
    """Match exact contre les combos validés. Strict (all-or-nothing)."""
    for combo in VALIDATED_COMBOS:
        if components["backend"]["id"] != combo["backend"]:
            continue
        if components["frontend"]["id"] != combo["frontend"]:
            continue
        if components["ui"]["id"] != combo["ui"]:
            continue
        if components["auth"]["id"] != combo["auth"]:
            continue
        if components["db"]["type"] != combo["db"]:
            continue
        # QA : au moins UN des QA validés du combo présent
        qa_ids = {q["id"] for q in components["qa"]}
        if not (qa_ids & combo["qa"]):  # type: ignore[operator]
            continue
        # Archi : si combo précise mvc, il faut mvc explicite OU None (défaut mvc)
        # Si combo précise ddd, il faut ddd explicite (pas de défaut sur ddd)
        archi_id = components["archi"]["id"]
        combo_archi = combo["archi"]
        if combo_archi == "mvc" and archi_id not in (None, "mvc"):
            continue
        if combo_archi == "ddd" and archi_id != "ddd":
            continue
        return combo
    return None


def _build_signature(components: dict) -> str:
    parts = [
        components["backend"]["id"] or "no-backend",
        components["frontend"]["id"] or "no-frontend",
        components["ui"]["id"] or "no-ui",
        "+".join(sorted(q["id"] for q in components["qa"])) or "no-qa",
        components["auth"]["id"] or "no-auth",
        components["db"]["type"],
        components["archi"]["id"] or "mvc-default",
    ]
    return "+".join(parts)


def _audit_log(signature: str, status: str, bypass: bool) -> None:
    """Log untested combo attempts to audit trail."""
    audit_dir = repo_root() / "workspace" / "output" / ".sys" / ".audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / "untested-combo.log"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bypass_marker = " [BYPASS=SDD_ALLOW_UNTESTED_COMBO]" if bypass else ""
    line = f"{ts} status={status} signature={signature}{bypass_marker}\n"
    try:
        audit_file.write_text(
            (audit_file.read_text(encoding="utf-8") if audit_file.is_file() else "") + line,
            encoding="utf-8",
        )
    except OSError:
        pass  # audit log best-effort


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def validate(root: Path | None = None) -> dict:
    root = root or repo_root()
    path = stack_md_path(root)
    if not path.is_file():
        return {
            "signature": None,
            "matched_combo": None,
            "status": "io_error",
            "exit_code": 4,
            "components": {},
            "warnings": [f"stack.md not found at {path}"],
            "bypass_active": False,
        }

    # v7.0.0-alpha (audit CRIT-2) : cached mtime-keyed read.
    text = read_stack_md_text(root)
    if text is None:
        return {
            "signature": None,
            "matched_combo": None,
            "status": "io_error",
            "exit_code": 4,
            "components": {},
            "warnings": [f"stack.md unreadable at {path}"],
            "bypass_active": False,
        }

    # Parse sections
    tech_block = section_body(text, "Active Tech Specs")
    ui_block = section_body(text, "Active UI Specs")
    qa_block = section_body(text, "Active QA Specs")
    auth_block = section_body(text, "Active Auth Specs")

    backends = _parse_active_stacks(tech_block, "backend")
    frontends = _parse_active_stacks(tech_block, "frontend")
    fullstacks = _parse_active_stacks(tech_block, "fullstack")
    mobiles = _parse_active_stacks(tech_block, "mobiles")
    uis = _parse_active_stacks(ui_block, "ui")
    qas = _parse_active_stacks(qa_block, "qa")
    auths = _parse_active_stacks(auth_block, "auth")
    db_type = _parse_database_type(text)
    archi = _parse_archi_pattern(text)

    warnings: list[str] = []

    # Validation grossière de combinaison
    if fullstacks and (backends or frontends):
        return {
            "signature": None,
            "matched_combo": None,
            "status": "invalid",
            "exit_code": 3,
            "components": {},
            "warnings": ["[STACK_COMBO_INVALID] fullstack/* and backend|frontend/* are mutually exclusive"],
            "bypass_active": False,
        }
    if mobiles and frontends:
        return {
            "signature": None,
            "matched_combo": None,
            "status": "invalid",
            "exit_code": 3,
            "components": {},
            "warnings": ["[STACK_COMBO_INVALID] mobiles/* and frontend/* are mutually exclusive"],
            "bypass_active": False,
        }
    if len(backends) > 1 or len(frontends) > 1 or len(uis) > 1 or len(auths) > 1:
        return {
            "signature": None,
            "matched_combo": None,
            "status": "invalid",
            "exit_code": 3,
            "components": {},
            "warnings": ["[STACK_COMBO_INVALID] at most one backend/frontend/ui/auth allowed"],
            "bypass_active": False,
        }
    # Audit 2026-06-06 — fullstack / mobile families are categorically outside
    # the C1/C2 validation envelope. Previously only emitted a warning while
    # leaving status calculation unchanged → callers could see `status: validated`
    # on an unvalidated fullstack combo. Now: force a downgrade to experimental
    # (exit 1) unless explicitly bypassed by SDD_ALLOW_UNTESTED_COMBO=1.
    fullstack_or_mobile_downgrade = False
    if fullstacks or mobiles:
        fullstack_or_mobile_downgrade = True
        warnings.append(
            f"AppType={'fullstack' if fullstacks else 'mobile-*'} — combo families "
            "outside C1/C2 PoC validation (forced to experimental tier)"
        )

    backend_id = backends[0] if backends else None
    frontend_id = frontends[0] if frontends else None
    ui_id = uis[0] if uis else None
    auth_id = auths[0] if auths else None

    components = {
        "backend": {"id": backend_id, "level": _component_level("backend", backend_id)},
        "frontend": {"id": frontend_id, "level": _component_level("frontend", frontend_id)},
        "ui": {"id": ui_id, "level": _component_level("ui", ui_id)},
        "qa": [{"id": q, "level": _component_level("qa", q)} for q in qas],
        "auth": {"id": auth_id, "level": _component_level("auth", auth_id)},
        "db": {"type": db_type, "level": _component_level("db", db_type)},
        "archi": {"id": archi, "level": _component_level("archi", archi) if archi else "validated"},
    }

    # Archi None defaults to mvc per CLAUDE.md §7
    if components["archi"]["id"] is None:
        components["archi"]["level"] = "validated"  # mvc default

    signature = _build_signature(components)
    matched = _match_combo(components)

    # Compute global status from worst component level.
    # Audit 2026-06-06 — safe fallback on unknown levels (e.g. `poc-only`,
    # `scaffold-validated`) so that adding a new tier in combos.json without
    # updating levelPriority no longer crashes with KeyError. Unknown level
    # is treated as the worst known severity (forced to untested-or-worse).
    _max_known_priority = max(LEVEL_PRIORITY.values(), default=0)
    def _priority(lvl: str) -> int:
        if lvl not in LEVEL_PRIORITY:
            warnings.append(
                f"Unknown validation level '{lvl}' not declared in combos.json#levelPriority — treated as worst-known severity"
            )
            return _max_known_priority + 1
        return LEVEL_PRIORITY[lvl]

    levels = [components[c]["level"] for c in ("backend", "frontend", "ui", "auth", "db", "archi")]
    levels.extend(q["level"] for q in components["qa"])
    levels = [lvl for lvl in levels if lvl != "missing"]  # ignore N/A components
    worst = max(levels, key=_priority) if levels else "missing"

    if matched is not None and worst == "validated":
        status, exit_code = "validated", 0
    elif worst == "bench-validated":
        # Sprint 2 closure CRIT-11 (audit consolidé 2026-06-07) : bench-validated
        # devient un statut canonique distinct (priority 0 comme validated).
        # Représente : runtime OK lors du bench 2026-06-05 mais scaffolding
        # /sdd-full partiellement manuel. Pas un risque, juste une promesse
        # plus faible que validated end-to-end.
        status, exit_code = "bench-validated", 0
        if matched is None:
            warnings.append("Combo signature does not match any catalog combo (C1-C13) — components individually bench-validated mais assemblage non listé")
    elif worst in ("experimental", "scaffold-validated"):
        status, exit_code = "experimental", 1
        if matched is None:
            warnings.append("Combo signature does not match any PoC-validated combo (C1, C2)")
    elif worst in ("untested", "poc-only"):
        status, exit_code = "untested", 2
        warnings.append(
            "At least one component (db / archi / stack) has never been used in a real run — pipeline behavior unknown"
        )
    else:
        status, exit_code = "experimental", 1

    # Audit 2026-06-06 (N3) — fullstack/mobile downgrade gate. If we reached
    # `validated` despite being in a non-C1/C2 family, force bench-validated
    # (audit Sprint 2 — was 'experimental' which was too pessimistic now that
    # fullstack components are bench-validated tier per 2026-06-05 evidence).
    if fullstack_or_mobile_downgrade and status == "validated":
        status, exit_code = "bench-validated", 0

    # Archi notes
    if components["archi"]["level"] == "experimental":
        warnings.append(
            f"Archi pattern '{components['archi']['id']}' is experimental "
            "(no formal PoC despite workspace usage)"
        )

    bypass_active = os.environ.get("SDD_ALLOW_UNTESTED_COMBO") == "1"
    if exit_code >= 2 and bypass_active:
        # Bypass downgrades to WARN-equivalent for callers but keeps exit code
        warnings.append("SDD_ALLOW_UNTESTED_COMBO=1 set — running untested combo at your own risk")

    if exit_code >= 1:
        _audit_log(signature, status, bypass_active)

    return {
        "signature": signature,
        "matched_combo": matched["id"] if matched else None,
        "status": status,
        "exit_code": exit_code,
        "components": components,
        "warnings": warnings,
        "bypass_active": bypass_active,
    }


def _emit_human(result: dict) -> None:
    status = result["status"]
    sig = result["signature"] or "<no signature>"
    matched = result["matched_combo"] or "-"
    icon = {
        "validated": "[OK]",
        "bench-validated": "[OK]",  # Sprint 2 CRIT-11 closure : statut canonique distinct
        "experimental": "[WARN]",
        "untested": "[FAIL]",
        "invalid": "[INVALID]",
        "io_error": "[IO_ERR]",
    }.get(status, f"[?{status}]")  # garde-fou : statut inconnu n'engendre plus KeyError crash
    print(f"{icon} Stack combo: {status.upper()}")
    print(f"   signature  : {sig}")
    print(f"   matched    : {matched}")
    if result["bypass_active"]:
        print("   bypass     : SDD_ALLOW_UNTESTED_COMBO=1")
    for w in result["warnings"]:
        print(f"   ! {w}")
    comps = result.get("components") or {}
    if comps:
        print("   components :")
        for cat in ("backend", "frontend", "ui", "auth", "db", "archi"):
            comp = comps.get(cat, {})
            cid = comp.get("id") or comp.get("type") or "—"
            lvl = comp.get("level", "—")
            print(f"     - {cat:9s}: {cid} ({lvl})")
        if comps.get("qa"):
            qa_repr = ", ".join(f"{q['id']} ({q['level']})" for q in comps["qa"])
            print(f"     - qa       : {qa_repr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate active stack combo against PoC catalog")
    parser.add_argument("--json", action="store_true", help="emit JSON on stdout")
    parser.add_argument("--quiet", action="store_true", help="suppress human output")
    args = parser.parse_args()

    result = validate()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif not args.quiet:
        _emit_human(result)

    return int(result["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
