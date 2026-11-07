#!/usr/bin/env python3
"""SDD_Pro telemetry hook — record REAL token usage per agent, from transcripts.

Fires on `SubagentStop` (sous-agents), `Stop` (session principale =
orchestrateur) et `PostToolUse` matcher=Agent (legacy, voir §PostToolUse).

Mode resolved with explicit precedence (highest wins) :
    1. env $SDD_TOKEN_USAGE_MODE (debug override, dev/CI)
    2. effective layered config `TokenUsageMode`
       (base.yml ← team.yml ← project stack.md ## Project Config)
    3. "off" (hard default if config unreadable)

Modes:
    - "off"    : silent skip, exit 0
    - "record" : insert/update rows in workspace/db/console.db (token_usage)
    - "debug"  : record + dump full payload to .audit/token-debug/

Audit tokens 2026-11-07 — pourquoi ce hook enregistrait des zéros
-----------------------------------------------------------------
Le tool `Agent` est asynchrone : son `PostToolUse` se déclenche au LANCEMENT
du sous-agent, sans `usage`. Le payload `SubagentStop` ne porte pas d'usage
non plus. Résultat sur le run réel du 2026-11-06 : 157 lignes, 65 tokens
d'entrée cumulés, pour ≈100 $ facturés. Quand octobre remontait quelque
chose, c'était le seul dernier tour (sous-comptage ×7 à ×126).

La donnée réelle vit dans les transcripts JSONL de Claude Code
(`sdd_lib/transcript_usage.py` sait les lire, dédupliqués par `message.id`) :

  * `SubagentStop` → transcript du sous-agent (`agent_transcript_path`, sinon
    `<dir>/<session>/subagents/agent-<agent_id>.jsonl`, sinon le plus récent
    sous `subagents/`). Somme de TOUS les tours, une ligne par modèle réel,
    `agent` = `agent_type` du payload. Idempotent par `agent_id` (ledger).
  * `Stop` → transcript de la session (`transcript_path`). L'usage de
    l'orchestrateur (`agent='orchestrator'`) est **upserté** par
    (run_id, session_id, modèle) : chaque Stop recalcule le total de la
    session et met à jour la ligne au lieu d'en ajouter une. Si le run_id
    change au sein d'une même session, seule la différence est attribuée au
    nouveau run.
  * `PostToolUse` Agent → plus AUCUNE ligne. Asynchrone : pas d'usage ;
    synchrone : `tool_response.usage` = dernier appel seulement. Le câblage
    peut être retiré de settings.json (no-op conservé pour compatibilité).

Le ledger `workspace/.sys/.state/token-usage-ledger.json` (verrou
`.lock`, écriture atomique) tient l'idempotence sans toucher au schéma de
`console.db` (lot distinct). La provenance (`usage_source=transcript|payload`)
est tracée dans `agent_journal.notes`.

Non-blocking by design — always exit 0. A failure of telemetry must never
break the pipeline, but it must never be silent either : every write failure
lands in `.audit/token-telemetry-failures.log` + a counter read by
`preflight_cost_cap`.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.console_db import connect, ensure_initialized, insert_token_usage  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_nested,
    get_subagent_type,
    read_hook_input,
)
from sdd_lib.paths import audit_dir_path, workspace_root, iso_now_ms, repo_root  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW  # noqa: E402
from sdd_lib.feat_us_ids import FEAT_FILE_RE, US_FILE_RE, US_RE, known_ids  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.transcript_usage import (  # noqa: E402
    TranscriptUsage,
    UsageTotals,
    locate_session_transcript,
    locate_subagent_transcript,
    read_transcript_usage,
)

# Valid modes (lower-cased, env + config normalized to these)
VALID_MODES: frozenset[str] = frozenset({"off", "record", "debug"})

#: Label de la ligne `token_usage` portant l'usage de la session principale.
ORCHESTRATOR_AGENT = "orchestrator"

#: Événements de hook traités comme « session principale ».
_SESSION_EVENTS: frozenset[str] = frozenset({"Stop", "SessionEnd"})

#: Nombre maximal de sous-agents mémorisés dans le ledger (idempotence).
_LEDGER_MAX_SUBAGENTS = 2000

# Module-level memo of the resolved mode. The mode is invariant within a
# pipeline run (config files are not edited mid-run, env vars set at spawn),
# so resolving once per process saves ~50 ms × N hook calls (audit P2 perf
# 2026-06-08 : record_token_usage measured 62 ms cold-start, dominated by
# the layered_config import + read).
_MODE_CACHE: str | None = None


def _resolve_mode() -> str:
    """Resolve effective token-usage mode (memoized).

    Precedence (highest wins):
      1. env $SDD_TOKEN_USAGE_MODE (debug override)
      2. effective layered config `TokenUsageMode`
         (base.yml ← team.yml ← project stack.md)
      3. "off" (hard default)

    Any unknown value normalizes to "off" (defensive — never break the run).
    """
    global _MODE_CACHE
    if _MODE_CACHE is not None:
        return _MODE_CACHE

    # 1. env var override — short-circuit, avoid expensive config import
    env_val = (os.environ.get("SDD_TOKEN_USAGE_MODE") or "").strip().lower()
    if env_val in VALID_MODES:
        _MODE_CACHE = env_val
        return env_val

    # 2. layered config (lazy-import — only paid if env was not set).
    # layered_config is optional; telemetry must never break on import errors.
    try:
        from sdd_lib.layered_config import read_layered_config  # noqa: E402
        cfg = read_layered_config()
        cfg_val = str(cfg.get("TokenUsageMode") or "").strip().lower()
        if cfg_val in VALID_MODES:
            _MODE_CACHE = cfg_val
            return cfg_val
    except Exception:
        # Config layering is opt-in and may fail on partial repos;
        # telemetry MUST NOT raise — fall through to hard default.
        pass

    # 3. hard default
    _MODE_CACHE = "off"
    return "off"


# Candidate paths in the payload where `usage` may live (legacy synchronous
# harnesses). Tried in order; first hit wins. usage_source_path is recorded
# for forensics.
USAGE_CANDIDATE_PATHS: tuple[tuple[str, ...], ...] = (
    ("tool_response", "usage"),
    ("tool_response", "message", "usage"),
    ("response", "usage"),
    ("response", "message", "usage"),
    ("usage",),
    ("message", "usage"),
)

# Field names inside the usage dict (Claude API canonical names).
USAGE_FIELDS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _find_usage(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Walk candidate paths; return (usage_dict, source_path_str) or (None, None)."""
    for path in USAGE_CANDIDATE_PATHS:
        node = get_nested(payload, *path)
        if isinstance(node, dict) and any(k in node for k in USAGE_FIELDS):
            return node, ".".join(path)
    return None, None


#: Env vars a harness may expose to name the model actually driving the agent.
#: Checked in order, first non-empty wins (audit C2, 2026-08-29).
_MODEL_ENV_VARS: tuple[str, ...] = (
    "SDD_AGENT_MODEL",
    "ANTHROPIC_MODEL",
    "CLAUDE_MODEL",
)


def _canonical_model_id(raw: str | None) -> str | None:
    """Normalize a raw model id (strip a runtime ``[1m]`` context suffix)."""
    if not isinstance(raw, str):
        return None
    base = raw.strip().split("[", 1)[0].strip()
    return base or None


def _model_from_agent_tier(subagent: str | None) -> str | None:
    """Resolve the model id from the agent's declared tier (last-resort).

    Audit C2 (2026-08-29) — root cause of `token_usage.model IS NULL` on
    every row of the live console.db : the `PostToolUse.Agent` /
    `SubagentStop` payloads simply do not carry a `model` field (they wrap a
    *tool* response, not a raw API message), so `_find_model` always returned
    None.

    Since the audit tokens 2026-11-07 the transcript carries the REAL model
    per message, so this is only reached when the transcript is unavailable
    (legacy payload path). We reconstruct the id deterministically from what
    SDD_Pro *does* know : the agent's `model_tier` (or `tier_default`)
    frontmatter in `.sdd/agents/{name}.md`, mapped through the active
    provider's `tier_map` (`.sdd/providers/{provider}.yaml`). A correct-tier
    approximation, strictly better than NULL.

    Never raises : telemetry must not break a pipeline.
    """
    if not subagent:
        return None
    try:
        from sdd_lib.paths import sdd_home, repo_root
        sdd_root = sdd_home(repo_root())
        agent_md = sdd_root / "agents" / f"{subagent}.md"
        if not agent_md.is_file():
            return None
        head = agent_md.read_text(encoding="utf-8", errors="replace")[:4096]
        # An explicit `model:` pin always wins over the tier indirection.
        m = re.search(r"^model:\s*([^\s#]+)\s*$", head, re.MULTILINE)
        if m:
            return _canonical_model_id(m.group(1).strip("'\""))
        m = re.search(r"^(?:model_tier|tier_default):\s*([a-z]+)\s*$", head, re.MULTILINE)
        if not m:
            return None
        tier = m.group(1).strip()

        provider = (os.environ.get("SDD_MODEL_PROVIDER") or "").strip() or None
        if not provider:
            try:
                from sdd_lib.stack_config import load_stack_config
                from sdd_lib.paths import workspace_root
                stack_md = workspace_root(repo_root()) / "stack" / "stack.md"
                if stack_md.is_file():
                    provider = load_stack_config(stack_md).provider_for_tier(tier)
            except Exception:
                provider = None
        provider = provider or "anthropic"

        from sdd_lib.config_loader import get_provider_tier_map
        return _canonical_model_id(get_provider_tier_map(provider).get(tier))
    except Exception:
        return None


def _find_model(payload: dict[str, Any], subagent: str | None = None) -> str | None:
    """Best-effort extraction of model id, with deterministic fallbacks.

    Resolution order (audit C2, 2026-08-29) :
      1. the hook payload itself (only source that is factual);
      2. an env var the harness may expose (`SDD_AGENT_MODEL`, ...);
      3. the agent's declared tier mapped through the active provider —
         see :func:`_model_from_agent_tier`.

    Returning None here writes a NULL `token_usage.model`, which the cost cap
    prices at the conservative tariff and reports — a None result is loud,
    not free.
    """
    candidates = (
        ("tool_response", "model"),
        ("tool_response", "message", "model"),
        ("response", "model"),
        ("response", "message", "model"),
        ("message", "model"),
        ("model",),
    )
    for path in candidates:
        node = get_nested(payload, *path)
        if isinstance(node, str) and node.strip():
            # Strip a runtime context-window suffix like "[1m]" so the stored
            # model id stays canonical and prices correctly (audit CR-1).
            return _canonical_model_id(node)

    for var in _MODEL_ENV_VARS:
        resolved = _canonical_model_id(os.environ.get(var))
        if resolved:
            return resolved

    return _model_from_agent_tier(subagent)


# Audit télémétrie 2026-11-07 : défense contre les faux « N-M » (dates,
# plages de lignes) — motif + validation disque factorisés dans
# `sdd_lib/feat_us_ids.py` (partagés avec `enforce_phase_order`).
_US_RE = US_RE
_FEAT_RE = re.compile(
    r"(?i)\b(?:FEAT|feat-?|sdd-full|us-generate|dev-run|dev-plan|qa-generate)"
    r"\s*[-:]?\s*(\d{1,3})(?![\d\-./:]\d|\d)",
)
_US_FILE_RE = US_FILE_RE
_FEAT_FILE_RE = FEAT_FILE_RE


def _known_ids(root: Path | None = None) -> tuple[set[str], set[int]] | None:
    """US ids (`n-m`) and FEAT numbers present on disk, or None if unknowable."""
    return known_ids(root)


def _extract_feat_and_us_from_text(
    haystack: str,
    known: tuple[set[str], set[int]] | None = None,
) -> tuple[int | None, str | None]:
    """First US (`n-m`) or FEAT number found in a free-text haystack.

    `known` = `(us_ids, feat_numbers)` from `_known_ids()` : when given, a
    candidate absent from disk is skipped and the next match is tried.
    """
    text = haystack or ""
    known_us, known_feats = known if known is not None else (None, None)
    for m in _US_RE.finditer(text):
        us_id = f"{int(m.group(1))}-{int(m.group(2))}"
        if known_us is None or us_id in known_us:
            return int(m.group(1)), us_id
    for m in _FEAT_RE.finditer(text):
        n = int(m.group(1))
        if known_feats is None or n in known_feats:
            return n, None
    return None, None


def _extract_feat_and_us(
    payload: dict[str, Any],
    known: tuple[set[str], set[int]] | None = None,
) -> tuple[int | None, str | None]:
    """Same contract as `_extract_feat_and_us_from_text`, on prompt + description."""
    prompt = get_nested(payload, "tool_input", "prompt", default="") or ""
    descr = get_nested(payload, "tool_input", "description", default="") or ""
    return _extract_feat_and_us_from_text(f"{prompt} {descr}", known)


def _hook_event_name(payload: dict[str, Any]) -> str:
    """Identify which hook event fired (PostToolUse.Agent vs SubagentStop).

    Claude Code passes `hook_event_name` at the payload root in newer versions.
    Fallback heuristic: presence of `tool_response` -> PostToolUse, else SubagentStop.
    """
    explicit = payload.get("hook_event_name")
    if isinstance(explicit, str) and explicit.strip():
        # Differentiate Agent vs other tools when PostToolUse fires
        tool_name = payload.get("tool_name")
        if explicit == "PostToolUse" and tool_name:
            return f"PostToolUse.{tool_name}"
        return explicit
    if "tool_response" in payload or "response" in payload:
        return "PostToolUse.Agent"
    return "SubagentStop"


# --------------------------------------------------------------------------- #
# Ledger d'idempotence (sidecar JSON, hors schéma console.db)
# --------------------------------------------------------------------------- #

def _ledger_path(root: Path | None = None) -> Path:
    return workspace_root(root or repo_root()) / ".sys" / ".state" / "token-usage-ledger.json"


def _load_ledger(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    subs = data.get("subagents")
    sess = data.get("sessions")
    data["subagents"] = subs if isinstance(subs, dict) else {}
    data["sessions"] = sess if isinstance(sess, dict) else {}
    return data


def _save_ledger(path: Path, data: dict[str, Any]) -> None:
    subs = data.get("subagents") or {}
    if len(subs) > _LEDGER_MAX_SUBAGENTS:
        # Garder les plus récents (clé de tri : ts ISO, lexicographique).
        keep = sorted(subs.items(), key=lambda kv: str(kv[1].get("ts") or ""))[-_LEDGER_MAX_SUBAGENTS:]
        data["subagents"] = dict(keep)
    from sdd_lib.atomic_write import atomic_write_text
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


class _LedgerLock:
    """Verrou fichier O_EXCL autour du ledger (SubagentStop parallèles)."""

    def __init__(self, ledger: Path) -> None:
        self._lock = ledger.with_name(ledger.name + ".lock")
        self._held = False

    def __enter__(self) -> "_LedgerLock":
        from sdd_lib.file_locks import acquire_with_retry
        self._lock.parent.mkdir(parents=True, exist_ok=True)
        acquire_with_retry(self._lock, payload_prefix="token-usage",
                           ttl_ms=5000, retry_count=20, backoff_ms=50)
        self._held = True
        return self

    def __exit__(self, *_exc: Any) -> bool:
        if self._held:
            from sdd_lib.file_locks import release
            release(self._lock)
        return False


# --------------------------------------------------------------------------- #
# Persistance console.db
# --------------------------------------------------------------------------- #

#: `session_id` du payload courant — transmis à `get_or_create_run_id` pour
#: que le run_id soit scopé à la session Claude Code (sans lui, le run_id
#: retombe en mode legacy partagé 24 h ; API du lot données/états 2026-11-07).
_SESSION_ID: str | None = None


def _resolve_run_id() -> str | None:
    # v7.0.1 : always resolve a stable run_id via sdd_lib/run_id helper
    # (env > workspace marker > generated). Avoids null run_id rows that
    # broke per-run aggregation in preflight_cost_cap.
    try:
        from sdd_lib.run_id import get_or_create_run_id
        if _SESSION_ID:
            return get_or_create_run_id(session_id=_SESSION_ID)
        return get_or_create_run_id()
    except Exception:
        return (os.environ.get("SDD_RUN_ID") or "").strip() or None


def _ensure_run_row(conn, run_id: str | None) -> str | None:
    """Create the parent `runs` row if missing (FK token_usage.run_id → runs.run_id).

    Idempotent and inexpensive. On failure, fall back to a NULL run_id so the
    token row itself is preserved.

    Audit états (2026-11-07) : CREATE-ONLY. L'ancien upsert inconditionnel
    réécrivait `status='running'` et `command='hook'` à CHAQUE enregistrement
    de tokens → un run clos (`completed`/`failed`) était rouvert et un run
    `sdd-full` rebaptisé `hook` (constaté : run FEAT 15 avec `ended_at` posé
    mais `status='running'`). Le cycle de vie d'un run existant appartient à
    son orchestrateur (`run_end` / `run_close.py`), jamais au hook télémétrie.
    """
    if not run_id:
        return None
    try:
        from sdd_lib.console_db import get_run, upsert_run
        if get_run(conn, run_id) is not None:
            return run_id
        upsert_run(conn, run_id=run_id,
                   command=os.environ.get("SDD_RUN_COMMAND") or "hook",
                   status="running")
        return run_id
    except Exception:
        return None


def _insert_row(conn, entry: dict[str, Any], run_id: str | None) -> int:
    insert_token_usage(
        conn,
        agent=entry.get("subagent_type") or "unknown",
        model=entry.get("model"),
        ts=entry.get("ts"),
        run_id=run_id,
        feat_n=entry.get("feat"),
        us_id=entry.get("us_id"),
        input_tokens=int(entry.get("input_tokens") or 0),
        output_tokens=int(entry.get("output_tokens") or 0),
        cache_creation_tokens=int(entry.get("cache_creation_input_tokens") or 0),
        cache_read_tokens=int(entry.get("cache_read_input_tokens") or 0),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0]) if row else 0


def _update_row(conn, row_id: int, entry: dict[str, Any]) -> bool:
    cur = conn.execute(
        "UPDATE token_usage SET ts = ?, model = ?, input_tokens = ?, output_tokens = ?, "
        "cache_creation_tokens = ?, cache_read_tokens = ? WHERE id = ?",
        (
            entry.get("ts"), entry.get("model"),
            int(entry.get("input_tokens") or 0),
            int(entry.get("output_tokens") or 0),
            int(entry.get("cache_creation_input_tokens") or 0),
            int(entry.get("cache_read_input_tokens") or 0),
            int(row_id),
        ),
    )
    return cur.rowcount > 0


def _persist_to_db(entry: dict[str, Any]) -> None:
    """Insert one row into console.db (table token_usage) + journal it.

    Used by the payload path (usage carried by the hook payload itself) and
    by the SubagentStop path (one call per model). Concurrent inserts are
    handled by SQLite WAL + busy_timeout=5s.
    """
    ensure_initialized()
    run_id = _resolve_run_id()
    with connect() as conn:
        run_id = _ensure_run_row(conn, run_id)
        _insert_row(conn, entry, run_id)
        _record_journal_entry(conn, entry, run_id)


def _record_journal_entry(conn, entry: dict[str, Any], run_id: str | None) -> None:
    """Append the same event to `agent_journal` (audit 2026-08-28, correction #5).

    `token_usage` answers « combien ». The journal answers « quoi, pour qui,
    avec quelle fiabilité de prix, et avec quelle issue » — and it is the only
    table that carries `pricing_source`, without which a cost total silently
    mixes real rates with conservative fallback rates.

    Two deliberate limits of what a hook can know, recorded honestly rather
    than guessed :

    - `outcome` is `ok` on SubagentStop (the agent completed) and `unknown` on
      PostToolUse / Stop (the tool returned or the turn ended, which does not
      prove the agent succeeded). Writing `ok` everywhere would make the
      `failed` counter a decoration.
    - `context_hash` stays NULL. The hook does not assemble the agent's
      context, so it cannot hash it.

    Never raises : telemetry must not break a pipeline.
    """
    try:
        from sdd_lib import journal
        hook_event = str(entry.get("hook_event") or "")
        outcome = "ok" if hook_event.startswith("SubagentStop") else "unknown"
        journal.record(
            conn,
            agent=entry.get("subagent_type") or hook_event or "unknown",
            kind="agent",
            ts=entry.get("ts"),
            run_id=run_id,
            feat_n=entry.get("feat"),
            us_id=entry.get("us_id"),
            phase=entry.get("subagent_type"),
            model=entry.get("model"),
            input_tokens=int(entry.get("input_tokens") or 0),
            output_tokens=int(entry.get("output_tokens") or 0),
            cache_read_tokens=int(entry.get("cache_read_input_tokens") or 0),
            cache_creation_tokens=int(entry.get("cache_creation_input_tokens") or 0),
            outcome=outcome,
            decision=hook_event or None,
            notes=(f"usage_source={entry.get('usage_source') or 'none'}"
                   + (f" turns={entry['turns']}" if entry.get("turns") else "")
                   + (f" transcript={entry['transcript']}" if entry.get("transcript") else "")),
        )
    except Exception:
        pass


def _debug_dump_payload(payload: dict[str, Any], audit_dir: Path) -> None:
    """Dump full payload to audit dir for forensic inspection (debug mode only)."""
    dump_dir = audit_dir / "token-debug"
    dump_dir.mkdir(parents=True, exist_ok=True)
    ts = iso_now_ms().replace(":", "-").replace(".", "-")
    target = dump_dir / f"payload-{ts}.json"
    try:
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Construction des entrées depuis un transcript
# --------------------------------------------------------------------------- #

def _entry_from_totals(
    *,
    hook_event: str,
    agent: str,
    model: str | None,
    totals: UsageTotals,
    feat: int | None,
    us_id: str | None,
    transcript: Path | None,
    usage_source: str,
) -> dict[str, Any]:
    return {
        "ts": iso_now_ms(),
        "hook_event": hook_event,
        "subagent_type": agent,
        "feat": feat,
        "us_id": us_id,
        "model": model,
        "input_tokens": totals.input_tokens,
        "output_tokens": totals.output_tokens,
        "cache_creation_input_tokens": totals.cache_creation_input_tokens,
        "cache_read_input_tokens": totals.cache_read_input_tokens,
        "turns": totals.turns,
        "usage_source": usage_source,
        "transcript": transcript.name if transcript else None,
    }


def _entries_from_transcript(
    usage: TranscriptUsage,
    *,
    hook_event: str,
    agent: str,
    feat: int | None,
    us_id: str | None,
    fallback_model: str | None,
) -> list[dict[str, Any]]:
    """Une entrée par modèle réel du transcript (modèle manquant → fallback)."""
    entries: list[dict[str, Any]] = []
    for model, totals in usage.by_model.items():
        if totals.is_empty:
            continue
        real_model = None if model == "<unrecorded>" else model
        entries.append(_entry_from_totals(
            hook_event=hook_event, agent=agent,
            model=real_model or fallback_model, totals=totals,
            feat=feat, us_id=us_id, transcript=usage.path,
            usage_source="transcript",
        ))
    return entries


# --------------------------------------------------------------------------- #
# Branches par événement
# --------------------------------------------------------------------------- #

def _handle_post_tool_use(payload: dict[str, Any], hook_event: str) -> None:
    """PostToolUse Agent : n'écrit PLUS RIEN (audit tokens 2026-11-07).

    Deux raisons, l'une ou l'autre suffit :
      * Agent asynchrone (Claude Code) : le hook part au LANCEMENT du
        sous-agent, sans usage — la ligne « 0/0/0/0 » qu'on insérait ici était
        du bruit pur (157 lignes, 65 tokens sur le run du 2026-11-06).
      * Agent synchrone : `tool_response.usage` ne porte que le DERNIER appel
        API du sous-agent, pas la somme de ses tours (sous-comptage ×7 à ×126
        constaté en octobre). Le compter EN PLUS du SubagentStop serait un
        double comptage partiel.
    La seule source est le transcript, lu au SubagentStop.
    """
    return None


def _subagent_label(payload: dict[str, Any]) -> str:
    """`agent_type` (SubagentStop natif) — PAS `subagent_type` (PostToolUse)."""
    for key in ("agent_type", "agentType"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return get_subagent_type(payload) or "unknown-subagent"


def _handle_subagent_stop(payload: dict[str, Any], hook_event: str) -> None:
    agent = _subagent_label(payload)
    agent_id = payload.get("agent_id") or payload.get("agentId")
    agent_id = agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else None

    transcript, strategy = locate_subagent_transcript(payload)
    entries: list[dict[str, Any]] = []
    if transcript is not None:
        usage = read_transcript_usage(transcript)
        if agent_id is None and usage.agent_id:
            agent_id = usage.agent_id
        known = _known_ids()
        feat, us_id = _extract_feat_and_us_from_text(usage.first_user_text or "", known)
        if feat is None:
            feat, us_id = _extract_feat_and_us(payload, known)
        entries = _entries_from_transcript(
            usage, hook_event=hook_event, agent=agent, feat=feat, us_id=us_id,
            fallback_model=_find_model(payload, agent),
        )
        if not entries:
            warn(f"WARN [token-usage] SubagentStop {agent} : transcript sans "
                 f"usage ({transcript.name}, {usage.lines_total} lignes) — aucune ligne écrite")
            return
    else:
        # Dernier recours : un usage porté par le payload (harnais synchrone).
        usage_dict, usage_path = _find_usage(payload)
        if usage_dict is None:
            warn(f"WARN [token-usage] SubagentStop {agent} : transcript introuvable "
                 f"({strategy}) et payload sans usage — aucune ligne écrite "
                 f"(coût NON compté pour ce sous-agent)")
            return
        totals = UsageTotals()
        totals.add(usage_dict)
        if totals.is_empty:
            return
        feat, us_id = _extract_feat_and_us(payload, _known_ids())
        entries = [_entry_from_totals(
            hook_event=hook_event, agent=agent, model=_find_model(payload, agent),
            totals=totals, feat=feat, us_id=us_id, transcript=None,
            usage_source=f"payload:{usage_path}",
        )]

    ledger_file = _ledger_path()
    ensure_initialized()
    run_id = _resolve_run_id()
    with _LedgerLock(ledger_file):
        ledger = _load_ledger(ledger_file)
        if agent_id and agent_id in ledger["subagents"]:
            return  # déjà enregistré (double déclenchement du hook)
        with connect() as conn:
            run_id = _ensure_run_row(conn, run_id)
            row_ids = []
            for entry in entries:
                row_ids.append(_insert_row(conn, entry, run_id))
                _record_journal_entry(conn, entry, run_id)
        if agent_id:
            ledger["subagents"][agent_id] = {
                "ts": iso_now_ms(), "agent": agent, "run_id": run_id,
                "row_ids": row_ids, "strategy": strategy,
            }
            _save_ledger(ledger_file, ledger)


def _totals_minus(current: UsageTotals, prior: dict[str, int]) -> UsageTotals:
    out = UsageTotals()
    out.turns = max(current.turns - int(prior.get("turns") or 0), 0)
    out.input_tokens = max(current.input_tokens - int(prior.get("input_tokens") or 0), 0)
    out.output_tokens = max(current.output_tokens - int(prior.get("output_tokens") or 0), 0)
    out.cache_creation_input_tokens = max(
        current.cache_creation_input_tokens - int(prior.get("cache_creation_input_tokens") or 0), 0)
    out.cache_read_input_tokens = max(
        current.cache_read_input_tokens - int(prior.get("cache_read_input_tokens") or 0), 0)
    return out


def _handle_session_stop(payload: dict[str, Any], hook_event: str) -> None:
    """Stop : usage de l'orchestrateur, upsert par (run_id, session_id, modèle)."""
    transcript = locate_session_transcript(payload)
    if transcript is None:
        tp = payload.get("transcript_path")
        warn(f"WARN [token-usage] Stop : transcript_path absent ou introuvable "
             f"({tp!r}) — usage orchestrateur NON compté")
        return
    usage = read_transcript_usage(transcript)
    session_id = payload.get("session_id") or usage.session_id or transcript.stem
    if not usage.by_model:
        return  # session sans tour assistant (rien à compter)

    ledger_file = _ledger_path()
    ensure_initialized()
    run_id = _resolve_run_id()
    with _LedgerLock(ledger_file):
        ledger = _load_ledger(ledger_file)
        sess: list[dict[str, Any]] = ledger["sessions"].setdefault(str(session_id), [])
        if not isinstance(sess, list):
            sess = []
            ledger["sessions"][str(session_id)] = sess
        with connect() as conn:
            run_id = _ensure_run_row(conn, run_id)
            for model_key, totals in usage.by_model.items():
                if totals.is_empty:
                    continue
                model = None if model_key == "<unrecorded>" else model_key
                # Ce qui a déjà été attribué à D'AUTRES runs sur cette session.
                prior: dict[str, int] = {}
                current_entry: dict[str, Any] | None = None
                for e in sess:
                    if e.get("model") != model_key:
                        continue
                    if e.get("run_id") == run_id and current_entry is None:
                        current_entry = e
                        continue
                    for k, v in (e.get("totals") or {}).items():
                        prior[k] = prior.get(k, 0) + int(v or 0)
                delta = _totals_minus(totals, prior)
                entry = _entry_from_totals(
                    hook_event=hook_event, agent=ORCHESTRATOR_AGENT, model=model,
                    totals=delta, feat=None, us_id=None, transcript=transcript,
                    usage_source="transcript",
                )
                if current_entry is not None and _update_row(conn, int(current_entry.get("row_id") or 0), entry):
                    current_entry["totals"] = delta.as_dict()
                    current_entry["ts"] = entry["ts"]
                    continue
                if delta.is_empty:
                    continue
                row_id = _insert_row(conn, entry, run_id)
                _record_journal_entry(conn, entry, run_id)
                if current_entry is not None:
                    current_entry.update({"row_id": row_id, "totals": delta.as_dict(), "ts": entry["ts"]})
                else:
                    sess.append({"run_id": run_id, "model": model_key, "row_id": row_id,
                                 "totals": delta.as_dict(), "ts": entry["ts"]})
        _save_ledger(ledger_file, ledger)


def main() -> int:
    mode = _resolve_mode()
    if mode not in {"record", "debug"}:
        return HOOK_ALLOW  # off → silent skip (normalized 2026-06-06)

    try:
        payload = read_hook_input()
    except Exception:
        return HOOK_ALLOW
    if not payload:
        return HOOK_ALLOW
    root = repo_root()
    audit_dir = audit_dir_path(root)

    if mode == "debug":
        try:
            _debug_dump_payload(payload, audit_dir)
        except Exception:
            pass  # never block on debug dump

    global _SESSION_ID
    sid = payload.get("session_id")
    _SESSION_ID = sid.strip() if isinstance(sid, str) and sid.strip() else None

    hook_event = _hook_event_name(payload)
    try:
        if hook_event.startswith("PostToolUse"):
            _handle_post_tool_use(payload, hook_event)
        elif hook_event in _SESSION_EVENTS:
            _handle_session_stop(payload, hook_event)
        else:
            _handle_subagent_stop(payload, hook_event)
        if hook_event == "SessionEnd":
            _close_session_hook_run()
    except Exception as exc:
        # Telemetry must never break the pipeline — but we must NOT swallow
        # silently either, or we regress to pre-fix state (0 rows accumulated).
        # Log failure to a fail counter file ; preflight_cost_cap reads it and
        # emits a visible WARN when telemetry is going dark.
        warn(f"WARN [token-usage] {hook_event} : écriture télémétrie échouée "
             f"({type(exc).__name__}: {str(exc)[:160]})")
        _record_telemetry_failure(audit_dir, exc)
        return HOOK_ALLOW
    return HOOK_ALLOW


def _close_session_hook_run() -> bool:
    """SessionEnd : clôture le run ouvert paresseusement par les hooks de la session.

    Audit états (2026-11-07) : les runs `command='hook'` n'étaient jamais
    clos (13/13 `running`/`stale` dans la base live). Périmètre strict :
      * run_id lu UNIQUEMENT (env `SDD_RUN_ID` ou marker de session) — jamais
        généré ici, pour ne pas créer de marker orphelin en fin de session ;
      * seul un run `command='hook'` encore `running` est clos (`completed`) ;
        un run de pipeline (`sdd-full`, `dev-run`…) garde son cycle de vie
        propre (`run_close.py` / `sdd_state.py end-run`, gate de livraison) ;
      * le marker de session est retiré s'il pointe encore sur ce run.
    Retourne True si un run a été clos.
    """
    from sdd_lib.console_db import connect, ensure_initialized, get_run, run_end
    from sdd_lib.run_id import _marker_path, _read_marker, clear_run_id_marker, resolve_session_id

    run_id = (os.environ.get("SDD_RUN_ID") or "").strip()
    if not run_id:
        sid = resolve_session_id(_SESSION_ID)
        if not sid:
            return False  # marker legacy partagé : jamais clos depuis une session
        run_id = _read_marker(_marker_path(sid), ttl_seconds=None) or ""
    if not run_id:
        return False
    ensure_initialized()
    with connect() as conn:
        row = get_run(conn, run_id)
        if row is None or row["command"] != "hook" or row["status"] != "running":
            return False
        closed = run_end(conn, run_id, "completed", source="SessionEnd")
    clear_run_id_marker(_SESSION_ID, run_id=run_id)
    return bool(closed)


def _record_telemetry_failure(audit_dir: Path, exc: Exception) -> None:
    """Append failure to .audit/token-telemetry-failures.log + maintain counter.

    Schema (one JSON line) :
        {"ts": "...", "error_type": "OperationalError", "message": "..."}

    Counter file `.audit/token-telemetry-failure-count` holds the integer
    count since last successful insert. Read by preflight_cost_cap to emit
    a visible operator alert when telemetry is broken."""
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
        log_path = audit_dir / "token-telemetry-failures.log"
        counter_path = audit_dir / "token-telemetry-failure-count"
        # v7.0.1 audit P1 v2 audit anti-patterns 2026-06-08 (AP-1) — use
        # `with` context manager to guarantee FD closure even on partial
        # write failure (Windows : orphan FD = file lock for that path).
        # Rotation handled by sdd_admin/rotate_audit_logs.py.
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "ts": iso_now_ms(),
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:200],
                }) + "\n"
            )
        # Bump counter — BEST-EFFORT, EVENTUAL CONSISTENCY (audit AP-4
        # 2026-06-08 : the read-modify-write is not atomic ; the counter is a
        # diagnostic, not a billing primitive).
        try:
            cur = int(counter_path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            cur = 0
        counter_path.write_text(str(cur + 1), encoding="utf-8")
    except OSError:
        # Last resort — even the failure log failed. Nothing more we can do
        # without breaking the pipeline contract.
        pass


if __name__ == "__main__":
    sys.exit(main())
