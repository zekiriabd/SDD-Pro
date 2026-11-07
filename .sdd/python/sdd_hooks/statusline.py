"""SDD_Pro Stop hook — barre de statut IDE (phase courante + coût du run).

Lit `workspace/db/console.db` et émet UNE ligne JSON sur stdout que Claude
Code affiche dans la barre d'état VSCode/IDE :

    {"statusline": "SDD F{n}:{PHASE} 💰$12.4 🔢1 234K (run 20261106)"}

Audit tokens 2026-11-07 — réécriture complète. La version précédente était
du code mort : elle interrogeait `cost_usd`, `total_tokens` et `feat_number`,
trois colonnes qui n'existent pas dans `token_usage` (schéma réel : `feat_n`,
`input_tokens`, `output_tokens`, `cache_creation_tokens`, `cache_read_tokens`,
`model`), puis avalait l'`OperationalError` dans un `except Exception:
return ""`. La barre affichait donc… rien, en silence, depuis sa création.

Désormais :
  * le coût est CALCULÉ (`sdd_lib.pricing.estimate_cost`, tarif par modèle,
    conservateur si inconnu) à partir des tokens réels du run courant ;
  * le run courant est celui de `sdd_lib.run_id` (env `SDD_RUN_ID` > marker)
    — le même périmètre que `preflight_cost_cap`, donc le même chiffre ;
  * toute erreur est ÉCRITE sur stderr avec sa classe (`[INFRA_BLOCKED]`,
    `[TELEMETRY_UNAVAILABLE]`) — jamais avalée. L'exit reste 0 : un hook
    `Stop` qui sort en 2 empêcherait Claude de rendre la main, et une barre
    de statut n'a pas ce pouvoir.

Phase affichée : dernière `run_phases.phase` du run (sinon `runs.current_phase`),
sinon le dernier agent de `token_usage` du run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW  # noqa: E402
from sdd_lib.pricing import estimate_cost, has_known_pricing  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402

_UNKNOWN = "—"


def _current_run_id() -> str | None:
    """Run courant, sans effet de bord (ne génère PAS de marker)."""
    import os
    env_id = (os.environ.get("SDD_RUN_ID") or "").strip()
    if env_id:
        return env_id
    try:
        from sdd_lib.run_id import _marker_path, _RUN_ID_TTL_SECONDS
        import time
        marker = _marker_path()
        if marker.is_file() and (time.time() - marker.stat().st_mtime) < _RUN_ID_TTL_SECONDS:
            cached = marker.read_text(encoding="utf-8").strip()
            if cached:
                return cached
    except Exception:  # noqa: BLE001 — fallback DB plus bas
        pass
    return None


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n // 1_000}K"
    return str(n)


def compute_status(conn, run_id: str | None) -> dict:
    """Agrège le run : coût calculé, tokens, phase, FEAT. Pur (testable)."""
    cur = conn.cursor()
    if not run_id:
        row = cur.execute(
            "SELECT run_id FROM token_usage WHERE run_id IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        run_id = row[0] if row else None
    if not run_id:
        return {"run_id": None, "rows": 0, "cost_usd": 0.0, "tokens": 0,
                "phase": _UNKNOWN, "feat_n": None, "unpriced": [], "agents": {}}

    rows = cur.execute(
        "SELECT agent, model, feat_n, input_tokens, output_tokens, "
        "       cache_creation_tokens, cache_read_tokens "
        "FROM token_usage WHERE run_id = ? ORDER BY id",
        (run_id,),
    ).fetchall()

    cost = 0.0
    tokens = 0
    feat_n = None
    unpriced: list[str] = []
    agents: dict[str, float] = {}
    last_agent = None
    for agent, model, f_n, inp, outp, cc, cr in rows:
        c = estimate_cost(model, input_tokens=inp or 0, output_tokens=outp or 0,
                          cache_creation_tokens=cc or 0, cache_read_tokens=cr or 0,
                          warn_unknown=False)
        cost += c
        tokens += (inp or 0) + (outp or 0) + (cc or 0) + (cr or 0)
        agents[agent or "?"] = agents.get(agent or "?", 0.0) + c
        last_agent = agent or last_agent
        if f_n is not None:
            feat_n = f_n
        label = (model or "").strip() or "<unrecorded>"
        if not has_known_pricing(model) and label not in unpriced:
            unpriced.append(label)

    phase = None
    try:
        row = cur.execute(
            "SELECT phase FROM run_phases WHERE run_id = ? ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        phase = row[0] if row else None
        if not phase:
            row = cur.execute(
                "SELECT current_phase, feat_n FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row:
                phase = row[0]
                if feat_n is None and row[1] is not None:
                    feat_n = row[1]
    except Exception as exc:  # noqa: BLE001 — tables optionnelles (migration)
        warn(f"WARN [statusline] phase illisible ({type(exc).__name__}: {exc})")
    if not phase:
        phase = (last_agent or _UNKNOWN).upper()

    return {"run_id": run_id, "rows": len(rows), "cost_usd": round(cost, 4),
            "tokens": tokens, "phase": str(phase).upper(), "feat_n": feat_n,
            "unpriced": unpriced, "agents": agents}


def format_status(st: dict) -> str:
    if not st.get("run_id"):
        return ""
    feat_label = f"F{st['feat_n']}" if st.get("feat_n") else _UNKNOWN
    run_short = str(st["run_id"])[:8]
    flag = " ⚠tarif" if st.get("unpriced") else ""
    return (f"SDD {feat_label}:{st['phase']} 💰${st['cost_usd']:.2f}{flag} "
            f"🔢{_fmt_tokens(st['tokens'])} ({st['rows']} appels, run {run_short})")


def main() -> int:
    # Le payload Stop (stdin) n'est pas nécessaire ; on le vide pour ne pas
    # laisser le harnais sur un pipe plein.
    try:
        sys.stdin.read()
    except (OSError, ValueError):
        pass

    try:
        from sdd_lib.console_db import connect_ro, default_db_path
        db_path = default_db_path()
    except Exception as exc:  # noqa: BLE001
        warn(f"WARN [statusline] [INFRA_BLOCKED] console_db indisponible "
             f"({type(exc).__name__}: {exc})")
        return HOOK_ALLOW
    if not Path(db_path).is_file():
        return HOOK_ALLOW  # fresh checkout / pré-bootstrap : rien à afficher

    try:
        with connect_ro(db_path) as conn:
            st = compute_status(conn, _current_run_id())
    except Exception as exc:  # noqa: BLE001
        warn(f"WARN [statusline] [TELEMETRY_UNAVAILABLE] console.db illisible "
             f"({type(exc).__name__}: {str(exc)[:160]}) — statut non affiché. "
             f"FIX : python .sdd/python/sdd_admin/verify_telemetry_health.py")
        return HOOK_ALLOW

    status = format_status(st)
    if status:
        print(json.dumps({"statusline": status}, ensure_ascii=False))
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
