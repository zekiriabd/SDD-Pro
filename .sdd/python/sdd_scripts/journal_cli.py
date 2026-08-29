#!/usr/bin/env python3
"""SDD_Pro: journal_cli — lecture du journal d'exécution agentique (0 token).

Rend le journal `agent_journal` OBSERVABLE — la quatrième propriété du contrat
d'intégration (`.sdd/integration.yml`). Un journal qu'on ne peut pas lire n'est
pas de la traçabilité, c'est du stockage.

Sous-commandes
--------------
    show         une ligne par exécution : agent, modèle, tokens, coût, issue
    summary      agrégat par agent + total, AVEC la fiabilité du coût
    replay-plan  quelles étapes d'un run sont rejouables depuis le journal
    verify       intégrité des blobs référencés (absent vs corrompu)

Usage
-----
    python -m sdd_scripts.journal_cli show --run-id R [--format md|json]
    python -m sdd_scripts.journal_cli summary --feat-number 1
    python -m sdd_scripts.journal_cli replay-plan --run-id R
    python -m sdd_scripts.journal_cli verify

Exit codes (sdd_lib.exit_codes)
    0 SUCCESS
    1 FAIL_FAST      arguments invalides
    3 INFRA_BLOCKED  console.db introuvable / illisible

Note sur `summary` : la ligne « fiabilité » n'est pas cosmétique. L'audit du
2026-08-28 a établi que toute la génération de modèles courante retombe sur
FALLBACK_PRICING (tarifs Sonnet), soit un facteur 5 de sous-estimation sur un
agent Opus. Un total présenté sans cette mention laisserait arbitrer un budget
sur un chiffre faux.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib import journal  # noqa: E402
from sdd_lib.console_safe import ensure_console_safe  # noqa: E402
from sdd_lib.console_db import connect, default_db_path  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402

INFRA_BLOCKED = 3


# --------------------------------------------------------------------------- #
# Rendu
# --------------------------------------------------------------------------- #

def _fmt_usd(v: float | None) -> str:
    return "—" if v is None else f"${v:,.4f}"


def _fmt_int(v: int | None) -> str:
    return "—" if not v else f"{v:,}".replace(",", " ")


_PRICING_MARK = {"known": "", "fallback": " ~", "unknown": " ?"}


def render_show_md(rows: list[dict]) -> str:
    if not rows:
        return "_Journal vide pour ce périmètre._\n"
    out = [
        "| # | agent | kind | modèle | in | out | coût | issue |",
        "|--:|---|---|---|--:|--:|--:|---|",
    ]
    for r in rows:
        mark = _PRICING_MARK.get(r["pricing_source"] or "unknown", " ?")
        out.append(
            f"| {r['seq'] or r['id']} | `{r['agent']}` | {r['kind']} "
            f"| {r['model'] or '—'} | {_fmt_int(r['input_tokens'])} "
            f"| {_fmt_int(r['output_tokens'])} | {_fmt_usd(r['cost_usd'])}{mark} "
            f"| {r['outcome']}{(' ' + r['error_class']) if r['error_class'] else ''} |"
        )
    out.append("")
    out.append("`~` coût estimé aux tarifs de repli (modèle absent des tables de prix) · "
               "`?` aucun modèle rapporté, coût inconnu.")
    return "\n".join(out) + "\n"


_CONFIDENCE_LABEL = {
    "exact": "exact — tous les modèles sont tarifés",
    "lower-bound": "PLANCHER — au moins un appel tarifé au repli, le coût réel est supérieur",
    "none": "indéterminable — aucun modèle tarifé",
}


def render_summary_md(s: dict) -> str:
    t = s["total"]
    scope = f"run `{s['run_id']}`" if s.get("run_id") else (
        f"FEAT {s['feat_n']}" if s.get("feat_n") is not None else "tout le journal")
    out = [f"# Journal — {scope}", ""]
    out.append(f"**{t['calls']} exécutions** · "
               f"{_fmt_int(t['input_tokens'])} tok in · "
               f"{_fmt_int(t['output_tokens'])} tok out · "
               f"**{_fmt_usd(t['cost_usd'])}**")
    out.append("")
    out.append(f"> Fiabilité du coût : **{_CONFIDENCE_LABEL[s['cost_confidence']]}**.")
    if t["fallback_priced_calls"] or t["unpriced_calls"]:
        out.append(f"> {t['fallback_priced_calls']} appel(s) au tarif de repli, "
                   f"{t['unpriced_calls']} sans modèle rapporté.")
    out.append("")
    if t["failed"] or t["blocked"] or t["retries"]:
        out.append(f"Issues : {t['failed']} échec(s), {t['blocked']} bloqué(s), "
                   f"{t['retries']} reprise(s).")
        out.append("")
    if s["per_agent"]:
        out.append("| agent | appels | tok in | tok out | coût | repli |")
        out.append("|---|--:|--:|--:|--:|--:|")
        for name, a in s["per_agent"].items():
            out.append(f"| `{name}` | {a['calls']} | {_fmt_int(a['input_tokens'])} "
                       f"| {_fmt_int(a['output_tokens'])} | {_fmt_usd(a['cost_usd'])} "
                       f"| {a['fallback_priced_calls'] or '—'} |")
        out.append("")
    return "\n".join(out)


def render_replay_md(p: dict) -> str:
    out = [f"# Replay — run `{p['run_id']}`", ""]
    if not p["total_steps"]:
        return "\n".join(out + ["_Aucune étape journalisée pour ce run._", ""])
    out.append(f"**{p['cacheable_steps']}/{p['total_steps']} étapes rejouables** "
               f"depuis le journal · économie estimée {_fmt_usd(p['estimated_saved_usd'])}")
    out.append("")
    out.append("| # | agent | rejouable | raison |")
    out.append("|--:|---|:-:|---|")
    for st in p["steps"]:
        out.append(f"| {st['seq']} | `{st['agent']}` | "
                   f"{'oui' if st['cacheable'] else 'non'} | {st['reason']} |")
    out.append("")
    return "\n".join(out)


def render_verify_md(v: dict) -> str:
    out = ["# Journal — intégrité des blobs", ""]
    out.append(f"{v['checked']} référence(s) vérifiée(s).")
    out.append("")
    if v["ok"]:
        out.append("Aucun blob manquant ni corrompu.")
        out.append("")
        return "\n".join(out)
    if v["missing"]:
        out.append(f"**{len(v['missing'])} blob(s) absent(s)** — contenu perdu, "
                   "les lignes de journal restent valides :")
        out += [f"- `{r}`" for r in v["missing"][:20]]
        out.append("")
    if v["corrupt"]:
        out.append(f"**{len(v['corrupt'])} blob(s) corrompu(s)** — hash divergent, "
                   "problème d'intégrité :")
        out += [f"- `{r}`" for r in v["corrupt"][:20]]
        out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="journal_cli",
        description="Lecture du journal d'exécution agentique (console.db agent_journal)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def _common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--run-id", default=None)
        sp.add_argument("--feat-number", type=int, default=None)
        sp.add_argument("--agent", default=None)
        sp.add_argument("--format", choices=("md", "json"), default="md")
        sp.add_argument("--db-path", default=None, help="override console.db path")

    s = sub.add_parser("show", help="une ligne par exécution")
    _common(s)
    s.add_argument("--limit", type=int, default=200)

    s = sub.add_parser("summary", help="agrégat tokens/coût par agent")
    _common(s)

    s = sub.add_parser("replay-plan", help="étapes rejouables depuis le journal")
    _common(s)

    s = sub.add_parser("verify", help="intégrité des blobs référencés")
    _common(s)
    return p


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()  # cp1252 guard
    args = _build_parser().parse_args(argv)

    db = Path(args.db_path) if args.db_path else default_db_path()
    if not Path(db).is_file():
        print(f"ERROR: journal read failed\n"
              f"CAUSE: [NOT_FOUND] console.db absent ({db})\n"
              f"FIX: lancer un pipeline, ou "
              f"python -m sdd_scripts.init_console_db", file=sys.stderr)
        return INFRA_BLOCKED

    if args.cmd == "replay-plan" and not args.run_id:
        print("ERROR: journal replay-plan failed\n"
              "CAUSE: [INVALID_ARG] --run-id requis pour replay-plan\n"
              "FIX: python -m sdd_scripts.journal_cli summary  # pour lister les runs",
              file=sys.stderr)
        return FAIL_FAST

    try:
        with connect(db) as conn:
            payload, rendered = _dispatch(conn, args)
    except sqlite3.Error as exc:
        print(f"ERROR: journal read failed\n"
              f"CAUSE: [INFRA_BLOCKED] console.db illisible: {exc}\n"
              f"FIX: vérifier workspace/db/console.db (WAL lock ? corruption ?)",
              file=sys.stderr)
        return INFRA_BLOCKED

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(rendered, end="")
    return SUCCESS


def _dispatch(conn, args) -> tuple[object, str]:
    if args.cmd == "show":
        rows = journal.entries(conn, run_id=args.run_id, feat_n=args.feat_number,
                               agent=args.agent, limit=args.limit)
        return rows, render_show_md(rows)
    if args.cmd == "summary":
        s = journal.summarize(conn, run_id=args.run_id, feat_n=args.feat_number)
        return s, render_summary_md(s)
    if args.cmd == "replay-plan":
        p = journal.replay_plan(conn, args.run_id)
        return p, render_replay_md(p)
    v = journal.verify_blobs(conn)
    return v, render_verify_md(v)


if __name__ == "__main__":
    raise SystemExit(main())
