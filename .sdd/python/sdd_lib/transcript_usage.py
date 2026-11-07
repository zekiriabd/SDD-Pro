"""SDD_Pro — lecteur partagé des transcripts JSONL de Claude Code.

Pourquoi ce module existe (audit tokens 2026-11-07)
---------------------------------------------------
Le hook ``record_token_usage`` enregistrait des zéros : le tool ``Agent`` est
asynchrone, son ``PostToolUse`` se déclenche au lancement sans ``usage``, et
le payload ``SubagentStop`` n'en porte pas non plus. La donnée réelle vit dans
les transcripts que Claude Code écrit sur disque :

    ~/.claude/projects/<cwd-encodé>/<session>.jsonl                  (orchestrateur)
    ~/.claude/projects/<cwd-encodé>/<session>/subagents/agent-<id>.jsonl (sous-agents)

Format observé (vérifié sur des fichiers réels) : chaque tour assistant est un
enregistrement ``{"type": "assistant", "uuid": ..., "message": {"id": "msg_…",
"model": "claude-…", "usage": {"input_tokens", "output_tokens",
"cache_creation_input_tokens", "cache_read_input_tokens", "cache_creation":
{"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"}, …}}}``.

Piège central : **un même message apparaît plusieurs fois** (un enregistrement
par bloc de contenu streamé — texte, thinking, tool_use), chacun portant le
même ``message.id`` et le même ``usage``. Sommer naïvement multiplie le coût
par 2 à 4. On déduplique donc par ``message.id`` (sinon ``uuid``, sinon le
numéro de ligne) en gardant la **dernière** occurrence, qui porte l'usage final.

Consommateurs : ``sdd_hooks/record_token_usage.py`` (SubagentStop + Stop),
``sdd_hooks/statusline.py`` (indirect via console.db),
``sdd_admin/measure_cache_hit_rate.py`` (taux de cache).

Zéro dépendance hors stdlib. Ne lève jamais sur un fichier malformé : les
lignes illisibles sont ignorées, un fichier absent produit un résultat vide
(``TranscriptUsage.found == False``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

#: Champs d'usage canoniques de l'API (noms du transcript).
USAGE_FIELDS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


@dataclass
class UsageTotals:
    """Somme d'usage sur un ensemble de tours (dédupliqués)."""

    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    ephemeral_5m_input_tokens: int = 0
    ephemeral_1h_input_tokens: int = 0

    def add(self, usage: dict[str, Any]) -> None:
        self.turns += 1
        self.input_tokens += _int(usage.get("input_tokens"))
        self.output_tokens += _int(usage.get("output_tokens"))
        self.cache_creation_input_tokens += _int(usage.get("cache_creation_input_tokens"))
        self.cache_read_input_tokens += _int(usage.get("cache_read_input_tokens"))
        cc = usage.get("cache_creation")
        if isinstance(cc, dict):
            self.ephemeral_5m_input_tokens += _int(cc.get("ephemeral_5m_input_tokens"))
            self.ephemeral_1h_input_tokens += _int(cc.get("ephemeral_1h_input_tokens"))

    def merge(self, other: "UsageTotals") -> None:
        self.turns += other.turns
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens
        self.ephemeral_5m_input_tokens += other.ephemeral_5m_input_tokens
        self.ephemeral_1h_input_tokens += other.ephemeral_1h_input_tokens

    @property
    def total_input(self) -> int:
        return (self.input_tokens + self.cache_creation_input_tokens
                + self.cache_read_input_tokens)

    @property
    def is_empty(self) -> bool:
        return (self.input_tokens == 0 and self.output_tokens == 0
                and self.cache_creation_input_tokens == 0
                and self.cache_read_input_tokens == 0)

    def as_dict(self) -> dict[str, int]:
        return {
            "turns": self.turns,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "ephemeral_5m_input_tokens": self.ephemeral_5m_input_tokens,
            "ephemeral_1h_input_tokens": self.ephemeral_1h_input_tokens,
        }


@dataclass
class TranscriptUsage:
    """Usage d'un transcript entier, ventilé par modèle réel."""

    path: Path
    found: bool = False
    session_id: str | None = None
    agent_id: str | None = None
    by_model: dict[str, UsageTotals] = field(default_factory=dict)
    first_user_text: str | None = None
    last_uuid: str | None = None
    last_timestamp: str | None = None
    lines_total: int = 0
    lines_skipped: int = 0

    @property
    def total(self) -> UsageTotals:
        t = UsageTotals()
        for v in self.by_model.values():
            t.merge(v)
        return t

    @property
    def turns(self) -> int:
        return sum(v.turns for v in self.by_model.values())

    @property
    def primary_model(self) -> str | None:
        """Modèle portant le plus de tours (``None`` si aucun tour)."""
        if not self.by_model:
            return None
        return max(self.by_model.items(), key=lambda kv: kv[1].turns)[0]


# --------------------------------------------------------------------------- #
# Lecture bas niveau
# --------------------------------------------------------------------------- #

def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def iter_records(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Itère ``(numéro_de_ligne, enregistrement)`` d'un JSONL, tolérant.

    Lignes vides ou non-JSON ignorées. Un fichier absent ou illisible produit
    une itération vide (l'appelant distingue via ``path.is_file()``).
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield n, obj
    except OSError:
        return


def canonical_model_id(raw: Any) -> str | None:
    """``claude-opus-5[1m]`` → ``claude-opus-5`` ; non-chaîne → ``None``."""
    if not isinstance(raw, str):
        return None
    base = raw.strip().split("[", 1)[0].strip()
    return base or None


def _text_of(content: Any) -> str:
    """Texte brut d'un ``message.content`` (str ou liste de blocs)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def read_transcript_usage(path: Path | str) -> TranscriptUsage:
    """Lit un transcript et somme l'usage de TOUS ses tours assistant.

    Déduplication : clé = ``message.id`` si présent, sinon ``uuid``, sinon le
    numéro de ligne. La **dernière** occurrence gagne (usage final du message).
    Le modèle est celui porté par chaque message (``message.model``), ce qui
    rend la ventilation exacte même si la session change de modèle.
    """
    p = Path(path)
    result = TranscriptUsage(path=p)
    if not p.is_file():
        return result
    result.found = True

    # key -> (model, usage) — l'insertion dans un dict conserve l'ordre de
    # première apparition mais la VALEUR est celle de la dernière occurrence.
    seen: dict[str, tuple[str, dict[str, Any]]] = {}
    for n, rec in iter_records(p):
        result.lines_total += 1
        if result.session_id is None:
            sid = rec.get("sessionId") or rec.get("session_id")
            if isinstance(sid, str) and sid:
                result.session_id = sid
        if result.agent_id is None:
            aid = rec.get("agentId") or rec.get("agent_id")
            if isinstance(aid, str) and aid:
                result.agent_id = aid
        msg = rec.get("message")
        rtype = rec.get("type")
        if rtype == "user" and result.first_user_text is None and isinstance(msg, dict):
            text = _text_of(msg.get("content")).strip()
            if text:
                result.first_user_text = text[:4000]
            continue
        if not isinstance(msg, dict):
            result.lines_skipped += 1
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict) or not any(k in usage for k in USAGE_FIELDS):
            result.lines_skipped += 1
            continue
        model = canonical_model_id(msg.get("model")) or "<unrecorded>"
        key = msg.get("id") if isinstance(msg.get("id"), str) and msg.get("id") else None
        if key is None:
            uid = rec.get("uuid")
            key = uid if isinstance(uid, str) and uid else f"line:{n}"
        seen[key] = (model, usage)
        uid = rec.get("uuid")
        if isinstance(uid, str) and uid:
            result.last_uuid = uid
        ts = rec.get("timestamp")
        if isinstance(ts, str) and ts:
            result.last_timestamp = ts

    for model, usage in seen.values():
        result.by_model.setdefault(model, UsageTotals()).add(usage)
    return result


# --------------------------------------------------------------------------- #
# Localisation des transcripts à partir d'un payload de hook
# --------------------------------------------------------------------------- #

def session_dir_for(transcript_path: Path | str) -> Path:
    """``<dir>/<session>.jsonl`` → ``<dir>/<session>/`` (dossier de session)."""
    p = Path(transcript_path)
    return p.with_suffix("") if p.suffix == ".jsonl" else p


def subagents_dir_for(transcript_path: Path | str) -> Path:
    return session_dir_for(transcript_path) / "subagents"


def latest_subagent_transcript(transcript_path: Path | str) -> Path | None:
    """Le ``agent-*.jsonl`` le plus récemment modifié sous ``subagents/``."""
    d = subagents_dir_for(transcript_path)
    if not d.is_dir():
        return None
    candidates = [p for p in d.glob("agent-*.jsonl") if p.is_file()]
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None


def locate_subagent_transcript(payload: dict[str, Any]) -> tuple[Path | None, str]:
    """Résout le transcript d'un sous-agent depuis un payload ``SubagentStop``.

    Ordre (du plus factuel au plus heuristique) :
      1. ``agent_transcript_path`` (champ natif des versions récentes) ;
      2. ``transcript_path`` + ``agent_id`` →
         ``<dir>/<session>/subagents/agent-<agent_id>.jsonl`` ;
      3. le fichier le plus récent sous ``subagents/`` (dernier recours —
         ambigu si plusieurs sous-agents s'arrêtent en même temps).

    Retourne ``(chemin | None, stratégie)`` ; la stratégie est journalisée
    pour qu'un sous-comptage soit traçable à sa cause.
    """
    atp = payload.get("agent_transcript_path")
    if isinstance(atp, str) and atp.strip():
        p = Path(atp.strip())
        if p.is_file():
            return p, "agent_transcript_path"
    tp = payload.get("transcript_path")
    agent_id = payload.get("agent_id")
    if isinstance(tp, str) and tp.strip():
        if isinstance(agent_id, str) and agent_id.strip():
            p = subagents_dir_for(tp.strip()) / f"agent-{agent_id.strip()}.jsonl"
            if p.is_file():
                return p, "transcript_path+agent_id"
        latest = latest_subagent_transcript(tp.strip())
        if latest is not None:
            return latest, "latest-under-subagents"
    return None, "not-found"


def locate_session_transcript(payload: dict[str, Any]) -> Path | None:
    """Transcript de la session principale (payload ``Stop``)."""
    tp = payload.get("transcript_path")
    if isinstance(tp, str) and tp.strip():
        p = Path(tp.strip())
        if p.is_file():
            return p
    return None
