"""SDD_Pro Stop hook — barre de statut IDE (phase courante + coût cumulé).

Lit console.db pour extraire la dernière FEAT en cours, la phase active,
et le coût cumulé du run courant. Écrit une ligne JSON sur stdout que
Claude Code affiche dans la barre d'état VSCode/IDE.

Format sortie (stdout) :
    {"statusline": "SDD F{n}:{PHASE} 💰${cost:.1f} 🔢{tokens}K"}

Fail-open : toute exception → sortie vide, exit 0 (jamais bloquant).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path


_UNKNOWN = "—"


def _find_console_db(root: Path) -> Path | None:
    candidates = [
        root / "workspace" / "db" / "console.db",
        root / "workspace" / "console" / "console.db",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _query_statusline(db_path: Path) -> str:
    """Retourne la chaîne de statut depuis console.db.

    Requêtes légères (index sur feat_number + run_id) :
    - token_usage : dernier run_id, coût cumulé
    - auditor_runs : dernière phase (agent le plus récent)
    """
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Dernier run_id connu
        cur.execute(
            "SELECT run_id, feat_number FROM token_usage "
            "ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            con.close()
            return ""
        run_id: str = row["run_id"] or _UNKNOWN
        feat_n: int = row["feat_number"] or 0

        # Coût et tokens cumulés du run
        cur.execute(
            "SELECT SUM(cost_usd) AS total_cost, SUM(total_tokens) AS total_tok "
            "FROM token_usage WHERE run_id = ?",
            (run_id,),
        )
        agg = cur.fetchone()
        total_cost: float = (agg["total_cost"] or 0.0) if agg else 0.0
        total_tok: int = (agg["total_tok"] or 0) if agg else 0

        # Phase active : dernier agent ayant terminé
        cur.execute(
            "SELECT agent_name FROM auditor_runs "
            "ORDER BY id DESC LIMIT 1"
        )
        phase_row = cur.fetchone()
        phase = phase_row["agent_name"].upper() if phase_row else _UNKNOWN

        con.close()

        feat_label = f"F{feat_n}" if feat_n else "—"
        tok_k = total_tok // 1000
        return f"SDD {feat_label}:{phase} 💰${total_cost:.1f} 🔢{tok_k}K"

    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    root_env = os.environ.get("CLAUDE_PROJECT_DIR")
    root = Path(root_env).resolve() if root_env else Path.cwd().resolve()

    db = _find_console_db(root)
    if not db:
        sys.exit(0)

    status = _query_statusline(db)
    if status:
        print(json.dumps({"statusline": status}))
    sys.exit(0)


if __name__ == "__main__":
    main()
