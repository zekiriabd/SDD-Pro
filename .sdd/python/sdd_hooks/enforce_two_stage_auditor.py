#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook for Agent invocations — Two-stage auditor enforcement.

Audit P3 B + B.bis (2026-06-08), durci audit sécurité 2026-11.

Quand un spawn vise `code-reviewer`, `security-reviewer` ou `arch-reviewer`
(Stage B) pour une FEAT, le hook exige que Stage A (`spec-compliance-reviewer`)
ait produit, pour cette FEAT, un verdict non-RED de moins de 24 h.

Source du verdict (audit 2026-11 — le verdict n'est plus LU, il est RECALCULÉ) :

  1. **console.db `qa_spec_compliance`** (autoritaire). Ces lignes par AC sont
     écrites par le script `ingest_agent_report.py` après validation
     déterministe (`validate_spec_compliance.py`). Le hook recalcule le
     verdict à partir des statuts/sévérités des AC et du seuil
     `SpecComplianceFailOn` (défaut `serious`) — il ne fait pas confiance à
     un champ `verdict` écrit par un LLM.
  2. Repli : `workspace/.sys/.validation/{n}-spec-compliance.json` (< 24 h),
     verdict RECALCULÉ depuis `us[].acs[]` ; `summary.verdict` n'est jamais
     lu. Le fichier n'est inscriptible que par `spec-compliance-reviewer`
     (`protect_framework` + `loader.yml writes:`).
  3. Ni l'un ni l'autre → DENY.

Limite assumée : les statuts AC restent le jugement de l'agent Stage A — le
hook garantit l'ordre et la cohérence verdict↔AC, pas la justesse du
jugement (aucun script ne peut re-dériver la conformité AC sans LLM).

Fail-closed (audit 2026-11) :
  - FEAT non extractible du prompt → DENY `[TWO_STAGE_FEAT_UNKNOWN]`
  - console.db absent ET pas de rapport JSON exploitable → DENY `[INFRA_BLOCKED]`
  - payload illisible → DENY `[INFRA_BLOCKED]`

Bypass :
  - `AuditorBatchMode: legacy-parallel` (Project Config) → no-op
  - `SDD_BYPASS_TWO_STAGE=1` (environnement du process Claude Code ; protégé
    par block_env_bypass) → no-op audit-loggué
  - `spec-compliance-reviewer` / `adversarial-reviewer` → toujours autorisés
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_nested,
    get_subagent_type,
    read_hook_input,
)
from sdd_lib.paths import workspace_root, repo_root  # noqa: E402


_STAGE_B_AGENTS = frozenset({"code-reviewer", "security-reviewer", "arch-reviewer"})
_STAGE_A_AGENTS = frozenset({"spec-compliance-reviewer"})
_INFORMATIONAL_AGENTS = frozenset({"adversarial-reviewer"})

_FRESHNESS_SECONDS = 24 * 3600
_SEVERITY_ORDER = ("critical", "serious", "moderate", "minor")
#: Statuts AC qui ne constituent PAS une issue.
_OK_STATUSES = frozenset({"verified", "ui_present", "ui_only"})
_DEFAULT_FAIL_ON = "serious"


def _extract_feat_number_from_prompt(payload: dict) -> int | None:
    """Best-effort extraction of FEAT number from the Agent prompt arg."""
    prompt = get_nested(payload, "tool_input", "prompt")
    if not isinstance(prompt, str):
        return None
    for pattern in (
        r"FEAT\s+(\d+)",
        r"feat[-_](\d+)",
        r"args\s*=\s*[\"'](\d+)",
        r"--feat[-\s]?(?:number)?\s*[=\s]+(\d+)",
        r"\bFEAT[\s:]+(\d+)",
    ):
        m = re.search(pattern, prompt, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _fail_on(root: Path) -> str:
    try:
        from sdd_lib.layered_config import read_layered_config
        v = (read_layered_config(root=root, keys=("SpecComplianceFailOn",))
             .get("SpecComplianceFailOn") or "").strip().lower()
        if v in _SEVERITY_ORDER:
            return v
    except Exception:
        pass
    return _DEFAULT_FAIL_ON


def verdict_from_acs(acs: list[tuple[str | None, str | None]], fail_on: str) -> str:
    """'red' | 'pass' recalculé depuis des `(status, severity)` par AC.

    Même règle que `validate_spec_compliance._expected_verdict` : RED dès
    qu'une AC non vérifiée a une sévérité au moins égale à `fail_on`. Une AC
    non vérifiée SANS sévérité exploitable compte comme `critical`
    (fail-closed : un statut négatif ne peut pas être neutralisé en omettant
    la sévérité).
    """
    if not acs:
        return "red"
    limit = _SEVERITY_ORDER.index(fail_on) if fail_on in _SEVERITY_ORDER else 1
    for status, severity in acs:
        st = (status or "").strip().lower()
        if st in _OK_STATUSES:
            continue
        sev = (severity or "").strip().lower()
        idx = _SEVERITY_ORDER.index(sev) if sev in _SEVERITY_ORDER else 0
        if idx <= limit:
            return "red"
    return "pass"


def _db_path(root: Path) -> Path:
    try:
        from sdd_lib.paths import console_db_path
        return console_db_path(root)
    except Exception:
        return workspace_root(root) / "db" / "console.db"


class _DbUnavailable(Exception):
    """console.db absent, illisible ou sans schéma → [INFRA_BLOCKED]."""


def _acs_from_db(feat_n: int, root: Path) -> list[tuple[str | None, str | None]]:
    """Rows fraîches (≤ 24 h). Lève `_DbUnavailable` si la base est absente,
    illisible ou sans table (`sdd_lib.console_db.ConsoleDbUnavailable` est
    une `sqlite3.OperationalError` : même traitement). Liste vide = base
    saine sans verdict Stage A."""
    db_path = _db_path(root)
    if not db_path.is_file():
        raise _DbUnavailable(f"console.db absent ({db_path})")
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise _DbUnavailable(f"console.db illisible : {exc}") from exc
    try:
        rows = conn.execute(
            "SELECT verdict, severity FROM qa_spec_compliance "
            "WHERE feat_n = ? AND extracted_at > datetime('now', '-24 hours')",
            (feat_n,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise _DbUnavailable(f"console.db illisible : {exc}") from exc
    finally:
        conn.close()
    return [(r[0], r[1]) for r in rows]


def _acs_from_report(feat_n: int, root: Path) -> list[tuple[str | None, str | None]] | None:
    """AC du rapport JSON frais ; None si absent, périmé ou illisible."""
    report = workspace_root(root) / ".sys" / ".validation" / f"{feat_n}-spec-compliance.json"
    if not report.is_file():
        return None
    try:
        if (time.time() - report.stat().st_mtime) > _FRESHNESS_SECONDS:
            return None
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    acs: list[tuple[str | None, str | None]] = []
    for us in data.get("us") or []:
        if not isinstance(us, dict):
            continue
        for ac in us.get("acs") or []:
            if isinstance(ac, dict):
                acs.append((ac.get("status"), ac.get("severity")))
    return acs or None


def _resolve_batch_mode(root: Path) -> str:
    try:
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config(root=root, keys=("AuditorBatchMode",))
        v = (cfg.get("AuditorBatchMode") or "two-stage").strip().lower()
        if v in ("two-stage", "legacy-parallel"):
            return v
    except Exception:
        pass
    return "two-stage"


def _deny(sub_type: str, feat: str, cls: str, cause: str, fix: str) -> int:
    sys.stderr.write(
        f"ERROR: [TWO_STAGE_GATE_VIOLATION] Cannot spawn '{sub_type}' (Stage B) for FEAT {feat}\n"
        f"CAUSE: [{cls}] {cause}\n"
        f"FIX: {fix}\n"
    )
    return HOOK_DENY


def main() -> int:
    try:
        payload = read_hook_input()
    except (json.JSONDecodeError, OSError, UnicodeError, ValueError) as exc:
        sys.stderr.write(
            f"ERROR: two-stage auditor — payload illisible\n"
            f"CAUSE: [INFRA_BLOCKED] {type(exc).__name__}: {exc}\n"
            f"FIX: verifier le format du payload hook (fail-closed)\n"
        )
        return HOOK_DENY

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Agent", "Task"):
        return HOOK_ALLOW

    sub_type = get_subagent_type(payload)
    if not sub_type:
        return HOOK_ALLOW
    sub_type_lower = sub_type.strip().lower()
    if sub_type_lower in _STAGE_A_AGENTS or sub_type_lower in _INFORMATIONAL_AGENTS:
        return HOOK_ALLOW
    if sub_type_lower not in _STAGE_B_AGENTS:
        return HOOK_ALLOW

    if os.environ.get("SDD_BYPASS_TWO_STAGE") == "1":
        sys.stderr.write(
            "WARN [TWO_STAGE_BYPASSED] SDD_BYPASS_TWO_STAGE=1 active — Stage B "
            f"agent '{sub_type}' spawning without Stage A gate verification. "
            "Audit-logged.\n"
        )
        return HOOK_ALLOW

    root = repo_root()
    if _resolve_batch_mode(root) == "legacy-parallel":
        return HOOK_ALLOW

    feat_n = _extract_feat_number_from_prompt(payload)
    if feat_n is None:
        return _deny(
            sub_type, "?", "TWO_STAGE_FEAT_UNKNOWN",
            "numero de FEAT introuvable dans le prompt — le gate ne peut pas verifier Stage A",
            "inclure `FEAT {n}` dans le prompt du spawn (convention /sdd-review, /dev-run) "
            "OU AuditorBatchMode: legacy-parallel / SDD_BYPASS_TWO_STAGE=1 (audit-logged)",
        )

    fail_on = _fail_on(root)
    try:
        acs = _acs_from_db(feat_n, root)
    except _DbUnavailable as exc:
        return _deny(
            sub_type, str(feat_n), "INFRA_BLOCKED",
            f"{exc} — impossible de verifier le gate Stage A (fail-closed)",
            "initialiser/reparer la base (python .sdd/python/sdd_scripts/init_console_db.py) "
            f"puis relancer spec-compliance-reviewer pour FEAT {feat_n}",
        )
    source = "console.db"
    if not acs:
        report_acs = _acs_from_report(feat_n, root)
        if report_acs:
            acs, source = report_acs, "rapport JSON (verdict recalcule)"

    if not acs:
        return _deny(
            sub_type, str(feat_n), "TWO_STAGE_GATE_VIOLATION",
            "Stage A (spec-compliance-reviewer) n'a produit aucun verdict frais (< 24 h) — "
            "AuditorBatchMode=two-stage exige le gate spec avant le batch qualite",
            f"1. Spawn `Agent: spec-compliance-reviewer` avec FEAT {feat_n} (+ ingest "
            "console.db) ; 2. OR AuditorBatchMode: legacy-parallel ; 3. OR "
            "SDD_BYPASS_TWO_STAGE=1 (audit-logged)",
        )

    if verdict_from_acs(acs, fail_on) == "red":
        return _deny(
            sub_type, str(feat_n), "TWO_STAGE_GATE_VIOLATION",
            f"Stage A verdict RED recalcule depuis {source} (SpecComplianceFailOn={fail_on}) "
            "— reviewer du code qui ne respecte pas sa spec = travail jete "
            "(auditor-orchestration.md §3.2)",
            f"lire workspace/.sys/.validation/{feat_n}-spec-compliance.md, corriger le code, "
            "relancer Stage A ; OR AuditorBatchMode: legacy-parallel / "
            "SDD_BYPASS_TWO_STAGE=1 (audit-logged)",
        )
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
