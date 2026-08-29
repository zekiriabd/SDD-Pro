"""journal — journal d'exécution agentique append-only (audit 2026-08-28, correction #5).

Le framework savait ce qu'il avait produit ; il ne savait pas ce qu'il avait
fait. Les 27 tables de `console.db` portaient des verdicts et des compteurs,
aucune trace de la décision, du contexte fourni, ni de la sortie brute. On
pouvait donc constater un résultat, jamais l'expliquer ni le reproduire.

Ce module écrit une ligne par exécution — agent LLM, script déterministe ou
gate — avec ce qu'il faut pour répondre à quatre questions distinctes :

    auditable    qu'a-t-on demandé, à quel modèle, avec quel contexte,
                 pour quel coût, et qu'a-t-il répondu ?
    reproductible même contexte + mêmes entrées ⇒ même sortie attendue.
                 `context_hash` et `inputs_hash` identifient l'entrée.
    rejouable    une étape dont les hashes n'ont pas bougé n'a pas besoin
                 d'être repayée : `replay_plan()` dit lesquelles.
    mesurable    tokens et coût par agent, par phase, par FEAT — avec la
                 fiabilité du prix déclarée, jamais supposée.

Trois partis pris
-----------------

**Append-only.** Aucune fonction d'update n'est exposée. Une correction est
une nouvelle entrée reliée par ``retry_of``. Un journal réinscriptible ne
prouve rien.

**Le coût porte sa provenance.** ``pricing_source`` vaut ``known`` quand le
prix vient de la table canonique ou d'un provider, ``fallback`` quand le
modèle est inconnu et que les tarifs Sonnet ont servi de repli, ``unknown``
quand aucun modèle n'a été rapporté. L'audit a montré que toute la génération
de modèles courante retombe sur le repli — un agrégat qui mélange les deux
sans le dire donne une fausse assurance. ``summarize()`` remonte donc
``unpriced_calls`` à côté du total.

**Les contenus vivent hors base.** Prompts et sorties sont stockés en blobs
adressés par leur hash sous ``workspace/.sys/.journal/blobs/``, dédupliqués :
deux spawns au contexte identique partagent un seul fichier. La base ne porte
que le hash et la référence, pour rester interrogeable.

Déterministe et non bloquant : toute écriture échoue en silence côté appelant
(un hook qui journalise ne doit jamais casser un pipeline). Aucune horloge ni
aléa dans la logique de décision — seul ``ts`` est temporel.

API publique
------------
    content_hash(text)                     -> str        (sha256, normalisé)
    inputs_hash(paths, root=None)          -> str        (hash de contenu d'un jeu de fichiers)
    store_blob(text, kind, root=None)      -> (ref, hash)
    record(conn, ...)                      -> int        (id de l'entrée)
    next_seq(conn, run_id)                 -> int
    entries(conn, ...)                     -> list[dict]
    summarize(conn, ...)                   -> dict
    replay_plan(conn, run_id)              -> dict
    verify_blobs(conn, root=None)          -> dict
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from sdd_lib.atomic_write import atomic_write_text
from sdd_lib.paths import iso_now_ms, normalize, repo_root, workspace_root
from sdd_lib.pricing import base_model_id, get_pricing, has_known_pricing

__all__ = [
    "BLOB_KINDS",
    "OUTCOMES",
    "PRICING_SOURCES",
    "content_hash",
    "inputs_hash",
    "store_blob",
    "blob_path",
    "journal_root",
    "record",
    "next_seq",
    "entries",
    "summarize",
    "replay_plan",
    "verify_blobs",
    "compute_cost",
]

#: Natures d'entrée. `script` et `gate` sont journalisés comme les agents :
#: une décision déterministe est une décision, et son absence de coût est
#: elle-même une information (elle mesure ce qu'on a cessé de payer au LLM).
KINDS: tuple[str, ...] = ("agent", "script", "gate")

#: Issues canoniques. `unknown` est admis — un hook qui ne peut pas conclure
#: doit pouvoir l'écrire plutôt que de deviner `ok`.
OUTCOMES: tuple[str, ...] = ("ok", "fail", "blocked", "skipped", "unknown")

#: Fiabilité du prix appliqué. Cf. docstring du module.
PRICING_SOURCES: tuple[str, ...] = ("known", "fallback", "unknown")

#: Types de blob et leur extension.
BLOB_KINDS: dict[str, str] = {
    "context": "md",     # pack de contexte assemblé, tel que fourni à l'agent
    "prompt": "md",      # consigne de tâche
    "output": "txt",     # sortie brute
    "payload": "json",   # charge structurée (hook, sortie validée)
}


# --------------------------------------------------------------------------- #
# Hashing — normalisation avant hash, sinon un CRLF invalide un replay
# --------------------------------------------------------------------------- #

def content_hash(text: str) -> str:
    """sha256 d'un texte, fins de ligne normalisées et espaces de fin retirés.

    La normalisation est load-bearing sous Windows : sans elle, le même pack
    lu via git avec `core.autocrlf` produirait un hash différent d'un run à
    l'autre et tout replay serait manqué.
    """
    if text is None:
        text = ""
    norm = text.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def inputs_hash(paths: Iterable[str | Path], root: Path | None = None) -> str:
    """Hash de contenu d'un jeu de fichiers d'entrée, ordre-insensible.

    Chaque fichier contribue ``<chemin relatif normalisé>:<hash>``. Un fichier
    absent contribue ``<chemin>:missing`` — c'est un fait d'entrée, pas une
    erreur : « l'agent a tourné SANS le schéma DB » doit se distinguer de
    « l'agent a tourné AVEC un schéma DB différent ».
    """
    base = Path(root) if root is not None else _root()
    parts: list[str] = []
    for p in paths:
        path = Path(p)
        abs_path = path if path.is_absolute() else base / path
        try:
            rel = normalize(str(abs_path.resolve().relative_to(base.resolve())))
        except (ValueError, OSError):
            rel = normalize(str(path))
        if abs_path.is_file():
            try:
                h = content_hash(abs_path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                h = "unreadable"
        else:
            h = "missing"
        parts.append(f"{rel}:{h}")
    joined = "\n".join(sorted(parts))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Blob store — adressé par contenu, donc dédupliqué et immuable
# --------------------------------------------------------------------------- #

def _root() -> Path:
    try:
        return repo_root()
    except Exception:  # noqa: BLE001 — le journal ne doit jamais lever chez l'appelant
        return Path.cwd()


def journal_root(root: Path | None = None) -> Path:
    """Répertoire du journal : ``workspace/.sys/.journal/``."""
    base = Path(root) if root is not None else _root()
    try:
        ws = workspace_root(base)
    except Exception:  # noqa: BLE001
        ws = base / "workspace"
    return ws / ".sys" / ".journal"


def blob_path(hash_hex: str, kind: str, root: Path | None = None) -> Path:
    """Chemin d'un blob. Éclaté sur 2 caractères pour éviter un répertoire à
    plusieurs dizaines de milliers d'entrées."""
    ext = BLOB_KINDS.get(kind, "txt")
    return journal_root(root) / "blobs" / hash_hex[:2] / f"{hash_hex}.{ext}"


def store_blob(
    text: str, kind: str = "output", root: Path | None = None
) -> tuple[str | None, str]:
    """Écrit ``text`` en blob adressé par contenu. Retourne ``(ref, hash)``.

    ``ref`` est le chemin relatif à la racine du dépôt, ou ``None`` si
    l'écriture a échoué — le hash reste valide dans ce cas, donc la ligne de
    journal garde sa valeur d'identification même sans contenu archivé.
    Idempotent : un blob déjà présent n'est pas réécrit.
    """
    h = content_hash(text)
    dest = blob_path(h, kind, root)
    if dest.is_file():
        return _rel(dest, root), h
    try:
        atomic_write_text(dest, text if text is not None else "", newline="\n")
    except OSError:
        return None, h
    return _rel(dest, root), h


def _rel(path: Path, root: Path | None) -> str:
    base = Path(root) if root is not None else _root()
    try:
        return normalize(str(path.resolve().relative_to(base.resolve())))
    except (ValueError, OSError):
        return normalize(str(path))


# --------------------------------------------------------------------------- #
# Coût — et surtout, provenance du prix
# --------------------------------------------------------------------------- #

def compute_cost(
    model: str | None,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> tuple[float | None, str]:
    """Retourne ``(cost_usd, pricing_source)``.

    ``pricing_source`` vaut ``unknown`` (et le coût ``None``) quand aucun
    modèle n'est rapporté : inventer un coût à partir de rien serait pire que
    de ne rien inscrire. Il vaut ``fallback`` quand le modèle est rapporté mais
    absent des tables — le coût est alors calculé aux tarifs de repli et DOIT
    être traité comme une borne inférieure.
    """
    if not model:
        return None, "unknown"
    source = "known" if has_known_pricing(model) else "fallback"
    p = get_pricing(model)
    cost = (
        input_tokens * p["input"]
        + output_tokens * p["output"]
        + cache_read_tokens * p["cache_read"]
        + cache_creation_tokens * p["cache_creation"]
    ) / 1_000_000.0
    return round(cost, 6), source


# --------------------------------------------------------------------------- #
# Écriture
# --------------------------------------------------------------------------- #

def next_seq(conn: sqlite3.Connection, run_id: str | None) -> int:
    """Prochain numéro d'ordre pour un run (1-based). 0 si ``run_id`` est nul."""
    if not run_id:
        return 0
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) FROM agent_journal WHERE run_id = ?", (run_id,)
    ).fetchone()
    return int(row[0] or 0) + 1


def record(
    conn: sqlite3.Connection,
    *,
    agent: str,
    kind: str = "agent",
    ts: str | None = None,
    seq: int | None = None,
    run_id: str | None = None,
    feat_n: int | None = None,
    us_id: str | None = None,
    phase: str | None = None,
    model: str | None = None,
    tier: str | None = None,
    context_hash: str | None = None,
    inputs_hash_: str | None = None,
    output_hash: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cost_usd: float | None = None,
    pricing_source: str | None = None,
    decision: str | None = None,
    gate: str | None = None,
    gate_verdict: str | None = None,
    attempt: int = 1,
    retry_of: int | None = None,
    outcome: str = "unknown",
    error_class: str | None = None,
    blob_ref: str | None = None,
    duration_ms: int | None = None,
    notes: str | None = None,
) -> int:
    """Ajoute une entrée et retourne son ``id``.

    Le coût est calculé ici si ``cost_usd`` n'est pas fourni, pour qu'aucun
    appelant ne puisse inscrire un coût sans sa provenance. ``kind`` et
    ``outcome`` hors vocabulaire sont acceptés (forward-compat) mais normalisés
    vers ``unknown`` côté outcome afin que les agrégats restent lisibles.
    """
    if cost_usd is None or pricing_source is None:
        computed, src = compute_cost(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )
        cost_usd = computed if cost_usd is None else cost_usd
        pricing_source = src if pricing_source is None else pricing_source
    if outcome not in OUTCOMES:
        outcome = "unknown"
    if seq is None:
        seq = next_seq(conn, run_id)
    cur = conn.execute(
        """
        INSERT INTO agent_journal(
            seq, ts, run_id, feat_n, us_id, phase, agent, kind, model, tier,
            context_hash, inputs_hash, output_hash,
            input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
            cost_usd, pricing_source, decision, gate, gate_verdict,
            attempt, retry_of, outcome, error_class, blob_ref, duration_ms, notes)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            seq, ts or iso_now_ms(), run_id, feat_n, us_id, phase, agent,
            kind if kind in KINDS else "agent",
            base_model_id(model) or model, tier,
            context_hash, inputs_hash_, output_hash,
            int(input_tokens or 0), int(output_tokens or 0),
            int(cache_read_tokens or 0), int(cache_creation_tokens or 0),
            cost_usd, pricing_source, decision, gate, gate_verdict,
            int(attempt or 1), retry_of, outcome, error_class, blob_ref,
            duration_ms, notes,
        ),
    )
    return int(cur.lastrowid)


# --------------------------------------------------------------------------- #
# Lecture
# --------------------------------------------------------------------------- #

_COLUMNS = (
    "id", "seq", "ts", "run_id", "feat_n", "us_id", "phase", "agent", "kind",
    "model", "tier", "context_hash", "inputs_hash", "output_hash",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
    "cost_usd", "pricing_source", "decision", "gate", "gate_verdict",
    "attempt", "retry_of", "outcome", "error_class", "blob_ref",
    "duration_ms", "notes",
)


def entries(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    feat_n: int | None = None,
    agent: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Entrées du journal, ordre chronologique stable (``run_id``, ``seq``, ``id``)."""
    where: list[str] = []
    params: list[Any] = []
    if run_id:
        where.append("run_id = ?")
        params.append(run_id)
    if feat_n is not None:
        where.append("feat_n = ?")
        params.append(feat_n)
    if agent:
        where.append("agent = ?")
        params.append(agent)
    sql = f"SELECT {', '.join(_COLUMNS)} FROM agent_journal"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(run_id, ''), COALESCE(seq, 0), id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(zip(_COLUMNS, row)) for row in conn.execute(sql, params)]


def summarize(
    conn: sqlite3.Connection, *, run_id: str | None = None, feat_n: int | None = None
) -> dict[str, Any]:
    """Agrégat tokens / coût / issues, par agent et global.

    ``unpriced_calls`` et ``fallback_priced_calls`` sont remontés au premier
    plan : un total de coût dont on ignore la part estimée aux tarifs de repli
    n'est pas exploitable pour arbitrer un budget.
    """
    rows = entries(conn, run_id=run_id, feat_n=feat_n)
    per_agent: dict[str, dict[str, Any]] = {}
    total = {
        "calls": 0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_creation_tokens": 0,
        "cost_usd": 0.0, "unpriced_calls": 0, "fallback_priced_calls": 0,
        "failed": 0, "blocked": 0, "retries": 0,
    }
    for r in rows:
        a = per_agent.setdefault(r["agent"], {
            "calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
            "kind": r["kind"], "fallback_priced_calls": 0,
        })
        for scope in (a, total):
            scope["calls"] += 1
            scope["input_tokens"] += r["input_tokens"] or 0
            scope["output_tokens"] += r["output_tokens"] or 0
            scope["cost_usd"] = round(scope["cost_usd"] + (r["cost_usd"] or 0.0), 6)
        total["cache_read_tokens"] += r["cache_read_tokens"] or 0
        total["cache_creation_tokens"] += r["cache_creation_tokens"] or 0
        if r["pricing_source"] == "unknown":
            total["unpriced_calls"] += 1
        elif r["pricing_source"] == "fallback":
            total["fallback_priced_calls"] += 1
            a["fallback_priced_calls"] += 1
        if r["outcome"] == "fail":
            total["failed"] += 1
        elif r["outcome"] == "blocked":
            total["blocked"] += 1
        if (r["attempt"] or 1) > 1 or r["retry_of"]:
            total["retries"] += 1
    return {
        "run_id": run_id,
        "feat_n": feat_n,
        "total": total,
        "per_agent": dict(sorted(per_agent.items())),
        "cost_confidence": _cost_confidence(total),
    }


def _cost_confidence(total: dict[str, Any]) -> str:
    """`exact` | `lower-bound` | `none`.

    `lower-bound` dès qu'une seule ligne est tarifée au repli : le total est
    alors un plancher, pas une mesure. C'est l'information qui manquait pour
    juger si un plafond de 50 $ est prudent ou décoratif.
    """
    if not total["calls"]:
        return "none"
    if total["unpriced_calls"] == total["calls"]:
        return "none"
    if total["fallback_priced_calls"] or total["unpriced_calls"]:
        return "lower-bound"
    return "exact"


def replay_plan(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    """Pour chaque entrée d'un run, dit si elle est rejouable depuis le journal.

    Une entrée est ``cacheable`` si une entrée ANTÉRIEURE (tous runs confondus)
    partage le même triplet ``(agent, context_hash, inputs_hash)`` avec une
    issue ``ok`` et un ``output_hash``. C'est la définition minimale et sûre :
    on ne rejoue que ce dont on a déjà observé la sortie sur une entrée
    identique. Une entrée sans hash de contexte n'est jamais rejouable — c'est
    volontaire, l'absence de hash signale un spawn dont on ne maîtrise pas
    l'entrée.
    """
    target = entries(conn, run_id=run_id)
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in entries(conn):
        if r["run_id"] == run_id:
            continue
        if not (r["context_hash"] and r["inputs_hash"] and r["output_hash"]):
            continue
        if r["outcome"] != "ok":
            continue
        seen.setdefault((r["agent"], r["context_hash"], r["inputs_hash"]), r)

    steps: list[dict[str, Any]] = []
    cacheable = 0
    saved = 0.0
    for r in target:
        key = (r["agent"], r["context_hash"] or "", r["inputs_hash"] or "")
        hit = seen.get(key) if (r["context_hash"] and r["inputs_hash"]) else None
        if hit:
            cacheable += 1
            saved = round(saved + (r["cost_usd"] or 0.0), 6)
        steps.append({
            "seq": r["seq"], "agent": r["agent"], "phase": r["phase"],
            "cacheable": bool(hit),
            "source_id": hit["id"] if hit else None,
            "reason": (
                "identique à une exécution ok antérieure" if hit
                else "pas de hash de contexte" if not r["context_hash"]
                else "aucune exécution ok antérieure au même contexte"
            ),
        })
    return {
        "run_id": run_id,
        "steps": steps,
        "total_steps": len(steps),
        "cacheable_steps": cacheable,
        "estimated_saved_usd": saved,
    }


def verify_blobs(conn: sqlite3.Connection, root: Path | None = None) -> dict[str, Any]:
    """Vérifie que chaque ``blob_ref`` référencé existe et porte le bon hash.

    Le journal peut survivre à la purge de ses blobs (rétention, nettoyage
    disque). Cette fonction distingue ``missing`` (blob absent — la ligne reste
    valide mais le contenu est perdu) de ``corrupt`` (blob présent dont le hash
    ne correspond plus — là il y a un vrai problème d'intégrité).
    """
    base = Path(root) if root is not None else _root()
    missing: list[str] = []
    corrupt: list[str] = []
    checked = 0
    for r in entries(conn):
        ref = r["blob_ref"]
        if not ref:
            continue
        checked += 1
        p = base / ref
        if not p.is_file():
            missing.append(ref)
            continue
        expected = r["output_hash"] or r["context_hash"]
        if not expected:
            continue
        try:
            if content_hash(p.read_text(encoding="utf-8", errors="replace")) != expected:
                corrupt.append(ref)
        except OSError:
            missing.append(ref)
    return {
        "checked": checked,
        "missing": sorted(set(missing)),
        "corrupt": sorted(set(corrupt)),
        "ok": not missing and not corrupt,
    }


def record_many(
    conn: sqlite3.Connection, items: Sequence[dict[str, Any]]
) -> list[int]:
    """Confort : plusieurs entrées, ordre préservé. Pas de transaction propre —
    l'appelant maîtrise son `with connect()`."""
    return [record(conn, **it) for it in items]
