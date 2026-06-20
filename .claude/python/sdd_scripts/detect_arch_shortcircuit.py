#!/usr/bin/env python3
"""SDD_Pro: déterministe arch short-circuit detection.

Évalue si l'agent `arch` peut être skippé pour la FEAT courante. Critères
(cf. `commands/dev-run.md §STEP 4.bis`) :

    1. Project Config (stack.md) lisible et fournit BackendName/AppName
    2. CLAUDE.md projet présents pour chaque famille active (back, front,
       lib si LibName)
    3. workspace/output/db/schema.json présent si DatabaseType ≠ none
    4. mtime de stack.md ≤ mtime du plus ancien CLAUDE.md projet
       (= aucun CLAUDE.md plus vieux que stack.md)

Toutes vraies → `required: false`. Au moins une fausse → `required: true`
avec `reason` = première condition non remplie.

Migré depuis logique inline `commands/dev-run.md §STEP 4.bis` (économie
~50 tokens LLM par invocation /dev-run).

Usage:
    python detect_arch_shortcircuit.py [--feat-number N] [--json]

Exit codes:
    0 : OK (lire stdout JSON pour le verdict — required true OR false)
    1 : ERROR I/O (stack.md introuvable, droits insuffisants)
    2 : ERROR malformé (stack.md sans Project Config exploitable)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.project_config import read_project_config  # noqa: E402  (legacy fallback)
from sdd_lib.layered_config import read_layered_config  # noqa: E402  (v6.7.3)
from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402


PROJECT_CONFIG_KEYS = ("AppName", "BackendName", "LibName", "DatabaseType")


def detect(feat_number: int | None = None) -> dict[str, object]:
    root = repo_root()
    stack_md = root / "workspace" / "input" / "stack" / "stack.md"

    if not stack_md.is_file():
        return {
            "required": True,
            "reason": "stack.md absent",
            "checks": {},
        }

    # v6.7.3: layered config with legacy fallback
    try:
        config = read_layered_config(root=root, keys=PROJECT_CONFIG_KEYS)
    except Exception:  # noqa: BLE001
        config = read_project_config(root=root, keys=PROJECT_CONFIG_KEYS)
    if not config.get("BackendName") and not config.get("AppName"):
        return {
            "required": True,
            "reason": "Project Config inexploitable (BackendName/AppName manquants)",
            "checks": {},
        }

    backend_name = config.get("BackendName")
    app_name = config.get("AppName")
    lib_name = config.get("LibName") or None
    if lib_name and lib_name.lower() in {"none", "null", ""}:
        lib_name = None
    db_type = (config.get("DatabaseType") or "none").lower()

    checks: dict[str, object] = {
        "stackMd": normalize(stack_md.relative_to(root)) if stack_md.is_relative_to(root) else str(stack_md),
        "stackMdMtime": stack_md.stat().st_mtime,
    }

    claude_md_paths: list[Path] = []
    if backend_name:
        claude_md_paths.append(root / "workspace" / "output" / "src" / backend_name / "CLAUDE.md")
    if app_name:
        claude_md_paths.append(root / "workspace" / "output" / "src" / app_name / "CLAUDE.md")
    if lib_name:
        claude_md_paths.append(root / "workspace" / "output" / "src" / lib_name / "CLAUDE.md")

    missing_claude = [p for p in claude_md_paths if not p.is_file()]
    if missing_claude:
        first = missing_claude[0]
        rel = normalize(first.relative_to(root)) if first.is_relative_to(root) else str(first)
        return {
            "required": True,
            "reason": f"CLAUDE.md projet manquant : {rel}",
            "checks": checks,
        }

    checks["claudeMdPaths"] = [
        normalize(p.relative_to(root)) if p.is_relative_to(root) else str(p)
        for p in claude_md_paths
    ]

    if db_type != "none":
        schema_json = root / "workspace" / "output" / "db" / "schema.json"
        checks["schemaJsonPresent"] = schema_json.is_file()
        if not schema_json.is_file():
            return {
                "required": True,
                "reason": f"DatabaseType={db_type} mais workspace/output/db/schema.json absent",
                "checks": checks,
            }
        # v7.0.0 audit P0 R2 — schema.json présent mais potentiellement corrompu.
        # Avant : fallback safe arch (qui relisait la corruption et la propageait
        # aux dev-*). Maintenant : émet [CHECKPOINT_STATE_UNREADABLE] qui force
        # un STOP côté caller (dev-run STEP 4.bis) — Tech Lead arbitre.
        # Validation minimale : parsable + clé `tables` (présent dans tous les schemas).
        try:
            data = json.loads(schema_json.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("schema.json top-level n'est pas un objet JSON")
            if "tables" not in data:
                raise KeyError("schema.json: clé 'tables' absente (schema mal formé)")
            checks["schemaJsonValid"] = True
        except (json.JSONDecodeError, OSError, ValueError, KeyError) as e:
            checks["schemaJsonValid"] = False
            checks["schemaJsonError"] = str(e)
            return {
                "required": True,
                "reason": (
                    f"[CHECKPOINT_STATE_UNREADABLE] workspace/output/db/schema.json "
                    f"présent mais corrompu/invalide : {e}"
                ),
                "error_class": "CHECKPOINT_STATE_UNREADABLE",
                "checks": checks,
            }

    stack_mtime = stack_md.stat().st_mtime
    claude_mtimes = [(p, p.stat().st_mtime) for p in claude_md_paths]
    oldest_claude_path, oldest_claude_mtime = min(claude_mtimes, key=lambda x: x[1])
    checks["oldestClaudeMd"] = normalize(oldest_claude_path.relative_to(root)) if oldest_claude_path.is_relative_to(root) else str(oldest_claude_path)
    checks["oldestClaudeMdMtime"] = oldest_claude_mtime

    if stack_mtime > oldest_claude_mtime:
        return {
            "required": True,
            "reason": "stack.md modifié depuis le dernier bootstrap arch",
            "checks": checks,
        }

    bits = ["bootstrap stable"]
    if db_type != "none":
        bits.append("schema DB présent")
    bits.append("CLAUDE.md cohérents")
    return {
        "required": False,
        "reason": ", ".join(bits),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Détection short-circuit arch (cf. dev-run.md §STEP 4.bis)",
    )
    parser.add_argument("--feat-number", type=int, default=None,
                        help="Numéro FEAT (informatif, non utilisé pour la décision)")
    parser.add_argument("--json", action="store_true",
                        help="Sortie JSON sur stdout (toujours actif, ce flag est noop pour compat CLI)")
    args = parser.parse_args()

    try:
        verdict = detect(feat_number=args.feat_number)
    except OSError as e:
        sys.stderr.write(f"ERROR: detect_arch_shortcircuit — I/O failure\n")
        sys.stderr.write(f"CAUSE: [PERMISSION] {e}\n")
        sys.stderr.write(f"FIX: vérifier droits lecture workspace/input/stack/stack.md\n")
        return FAIL_FAST
    except Exception as e:
        sys.stderr.write(f"ERROR: detect_arch_shortcircuit — failure\n")
        sys.stderr.write(f"CAUSE: [UNKNOWN] {e.__class__.__name__}: {e}\n")
        sys.stderr.write(f"FIX: relancer ; si récurrent, ouvrir une issue\n")
        return CORRECTIBLE
    if args.feat_number is not None:
        verdict["featNumber"] = args.feat_number

    sys.stdout.write(json.dumps(verdict, indent=2, ensure_ascii=False) + "\n")
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
