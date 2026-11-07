#!/usr/bin/env python3
"""SDD_Pro hook — borne `MaxParallel` sur les sous-agents SDD en vol.

Lot « orchestration mécanique » (2026-11-07). `MaxParallel` (Project Config,
`workspace/stack/stack.md`, lu via `sdd_lib.layered_config`) était documenté
dans `/dev-run` et `/sdd-full` mais appliqué par AUCUN mécanisme : un LLM qui
émettait 8 appels `Agent` dans un même message les voyait tous partir.

Un seul module, trois (+1) événements — argument `--event` :

    --event pre    PreToolUse  matcher=Agent   → décide (exit 2 = DENY) ET
                                                 réserve le créneau, sous verrou
    --event post   PostToolUse matcher=Agent   → `mark_started` : confirme le
                                                 créneau ; un agent FOREGROUND
                                                 est déjà terminé à ce stade →
                                                 libéré ; un agent lancé en
                                                 arrière-plan reste en vol
    --event stop   SubagentStop                → `mark_stopped` : libère
    --event sweep  Stop (recommandé)           → fin de tour : purge les
                                                 réservations foreground orphelines

Pourquoi réserver dès PreToolUse (et pas seulement à PostToolUse) : le tool
`Agent` est synchrone pour un appel foreground — PostToolUse ne tombe qu'à la
FIN du sous-agent. Les N appels parallèles d'un même message passent tous leur
PreToolUse avant qu'aucun PostToolUse ne soit émis ; compter à PostToolUse
laisserait passer les N. La réservation atomique (lecture + décision +
écriture sous un seul verrou fichier) est la seule façon de borner un lot
parallèle.

État : `workspace/.sys/.state/inflight.json`, verrou `inflight.json.lock`
(`sdd_lib.file_locks.acquire_with_retry`, O_EXCL + TTL). Une entrée de plus de
2 h est périmée et ignorée (crash, session tuée) — elle ne bloque jamais.
Portée du comptage : la session Claude Code courante (`session_id`).

Seuls les agents du registre SDD (`.sdd/agents/*.md`) sont comptés et bornés ;
`general-purpose`, `Explore`, etc. passent sans être comptés.

Bypass : `SDD_ALLOW_PARALLEL_EXCESS=1` (audit-loggué dans
`workspace/.sys/.audit/bypass.log`). Payload invalide / config illisible :
fail-open sur MaxParallel par défaut (3), jamais fail-open sur le comptage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import get_nested, read_hook_input  # noqa: E402
from sdd_lib.paths import audit_dir_path, iso_now_ms, repo_root, workspace_root  # noqa: E402

#: Au-delà, une entrée en vol est périmée (crash, session tuée).
STALE_AFTER_SECONDS = 2 * 3600
DEFAULT_MAX_PARALLEL = 3
BYPASS_ENV = "SDD_ALLOW_PARALLEL_EXCESS"

#: Repli si `.sdd/agents/` est illisible (registre SDD forward + reverse).
_FALLBACK_SDD_AGENTS = frozenset({
    "po", "arch", "dev-backend", "dev-frontend", "qa", "elicitor",
    "constitutioner", "specbook-writer", "code-reviewer", "security-reviewer",
    "spec-compliance-reviewer", "arch-reviewer", "adversarial-reviewer",
})


# --------------------------------------------------------------------------- #
# Helpers partagés (réutilisés par enforce_phase_order)
# --------------------------------------------------------------------------- #

def sdd_agent_registry(root: Path | None = None) -> frozenset[str]:
    """Noms des agents SDD = stems de `.sdd/agents/*.md` (repli : liste figée)."""
    try:
        from sdd_lib.paths import agents_dir
        d = agents_dir(root or repo_root())
        names = {p.stem for p in d.glob("*.md")} if d.is_dir() else set()
        if names:
            return frozenset(names | _FALLBACK_SDD_AGENTS)
    except Exception:  # noqa: BLE001 — registre best-effort
        pass
    return _FALLBACK_SDD_AGENTS


def agent_type_of(payload: dict[str, Any]) -> str | None:
    """Lit défensivement `tool_input.subagent_type` (Pre/Post) puis `agent_type`
    (SubagentStop) puis `subagent_type` racine."""
    for keys in (("tool_input", "subagent_type"), ("agent_type",), ("subagent_type",)):
        val = get_nested(payload, *keys)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def audit_bypass(root: Path, line: str) -> None:
    """Append-only `workspace/.sys/.audit/bypass.log` (best-effort)."""
    try:
        d = audit_dir_path(root)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "bypass.log", "a", encoding="utf-8") as fh:
            fh.write(f"{iso_now_ms()} {line.rstrip()}\n")
    except OSError:
        pass


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# État inflight.json (sous verrou)
# --------------------------------------------------------------------------- #

def state_path(root: Path) -> Path:
    return workspace_root(root) / ".sys" / ".state" / "inflight.json"


class _Locked:
    """Context manager : verrou O_EXCL + lecture/écriture de inflight.json."""

    def __init__(self, root: Path) -> None:
        self.path = state_path(root)
        self.lock = self.path.with_name(self.path.name + ".lock")
        self.data: dict[str, Any] = {}

    def __enter__(self) -> dict[str, Any]:
        from sdd_lib.file_locks import acquire_with_retry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        acquire_with_retry(self.lock, payload_prefix="inflight", ttl_ms=10000,
                           retry_count=40, backoff_ms=50)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        raw.setdefault("entries", [])
        raw.setdefault("denied", [])
        self.data = raw
        return raw

    def __exit__(self, exc_type, exc, tb) -> None:
        from sdd_lib.atomic_write import atomic_write_text
        from sdd_lib.file_locks import release
        try:
            if exc_type is None:
                atomic_write_text(self.path, json.dumps(self.data, indent=2, ensure_ascii=False))
        finally:
            release(self.lock)


def _prune(data: dict[str, Any], now: float) -> None:
    data["entries"] = [e for e in data.get("entries", [])
                       if now - float(e.get("started_at", 0)) < STALE_AFTER_SECONDS]
    data["denied"] = [d for d in data.get("denied", [])
                      if now - float(d.get("at", 0)) < STALE_AFTER_SECONDS][-200:]


def _active(data: dict[str, Any], session: str | None, now: float) -> list[dict[str, Any]]:
    return [e for e in data.get("entries", [])
            if now - float(e.get("started_at", 0)) < STALE_AFTER_SECONDS
            and (session is None or e.get("session_id") == session)]


def inflight_count(root: Path, session_id: str | None) -> int:
    """Lecture seule (sans verrou) — pour diagnostic / statusline."""
    p = state_path(root)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        data = {}  # état illisible = aucune entrée en vol (compteur, pas un exit code)
    return len(_active(data if isinstance(data, dict) else {}, session_id, time.time()))


def note_denied(root: Path, tool_use_id: str | None) -> None:
    """Appelé par un autre hook PreToolUse qui REFUSE le spawn : libère (ou
    empêche) la réservation de ce `tool_use_id` — sinon le créneau fuirait
    jusqu'à péremption, puisque ni PostToolUse ni SubagentStop ne tomberont."""
    if not tool_use_id:
        return
    try:
        with _Locked(root) as data:
            data["entries"] = [e for e in data["entries"] if e.get("tool_use_id") != tool_use_id]
            data["denied"].append({"tool_use_id": tool_use_id, "at": time.time()})
    except Exception:  # noqa: BLE001 — jamais bloquant
        pass


# --------------------------------------------------------------------------- #
# Événements
# --------------------------------------------------------------------------- #

def resolve_max_parallel(root: Path) -> int:
    try:
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config(root=root, keys=("MaxParallel",), coerce=True)
        val = int(cfg.get("MaxParallel") or DEFAULT_MAX_PARALLEL)
        return val if val >= 1 else DEFAULT_MAX_PARALLEL
    except Exception:  # noqa: BLE001 — config illisible → défaut documenté
        return DEFAULT_MAX_PARALLEL


def on_pre(payload: dict[str, Any], root: Path, *, max_parallel: int | None = None,
           now: float | None = None) -> tuple[int, str]:
    """PreToolUse Agent : DENY si en vol ≥ MaxParallel, sinon réserve."""
    tool = payload.get("tool_name")
    if tool not in ("Agent", "Task"):
        return HOOK_ALLOW, ""
    agent = agent_type_of(payload)
    if not agent or agent not in sdd_agent_registry(root):
        return HOOK_ALLOW, ""
    now = time.time() if now is None else now
    session = payload.get("session_id") or None
    tool_use_id = payload.get("tool_use_id") or None
    limit = max_parallel if max_parallel is not None else resolve_max_parallel(root)
    bypass = _truthy(os.environ.get(BYPASS_ENV))
    with _Locked(root) as data:
        _prune(data, now)
        if tool_use_id and any(d.get("tool_use_id") == tool_use_id for d in data["denied"]):
            return HOOK_ALLOW, ""  # déjà refusé par un autre hook : ne pas réserver
        active = _active(data, session, now)
        if len(active) >= limit and not bypass:
            names = ", ".join(sorted(e.get("agent", "?") for e in active))
            return HOOK_DENY, (
                f"ERROR: [MAX_PARALLEL_EXCEEDED] spawn de '{agent}' refusé — "
                f"{len(active)} sous-agent(s) SDD déjà en vol (MaxParallel={limit}) : {names}\n"
                f"CAUSE: MaxParallel (## Project Config de workspace/stack/stack.md) borne "
                f"les sous-agents SDD simultanés d'une session.\n"
                f"FIX: attendre la fin du lot en cours puis spawner le suivant "
                f"(batches de MaxParallel) ; ou relever MaxParallel ; bypass audit-loggué "
                f"{BYPASS_ENV}=1. Entrées > 2 h ignorées (workspace/.sys/.state/inflight.json).\n"
            )
        if len(active) >= limit and bypass:
            audit_bypass(root, f"{BYPASS_ENV}=1 agent={agent} inflight={len(active)} "
                               f"max={limit} session={session}")
        data["entries"].append({
            "tool_use_id": tool_use_id, "agent": agent, "session_id": session,
            "started_at": now, "state": "reserved",
            "background": bool(get_nested(payload, "tool_input", "run_in_background")),
        })
    return HOOK_ALLOW, ""


def _remove_one(data: dict[str, Any], *, tool_use_id: str | None, agent: str | None,
                session: str | None) -> bool:
    entries = data["entries"]
    if tool_use_id:
        for i, e in enumerate(entries):
            if e.get("tool_use_id") == tool_use_id:
                del entries[i]
                return True
    # Repli : la plus ancienne entrée du même agent (même session si possible)
    for same_session in (True, False):
        cands = [i for i, e in enumerate(entries)
                 if e.get("agent") == agent
                 and (not same_session or session is None or e.get("session_id") == session)]
        if cands:
            oldest = min(cands, key=lambda i: float(entries[i].get("started_at", 0)))
            del entries[oldest]
            return True
    return False


def mark_started(payload: dict[str, Any], root: Path) -> None:
    """PostToolUse Agent. Foreground : l'agent est terminé → libère.
    Arrière-plan : confirme le créneau (libéré au SubagentStop)."""
    agent = agent_type_of(payload)
    if not agent or agent not in sdd_agent_registry(root):
        return
    tool_use_id = payload.get("tool_use_id") or None
    background = bool(get_nested(payload, "tool_input", "run_in_background"))
    with _Locked(root) as data:
        _prune(data, time.time())
        if background:
            for e in data["entries"]:
                if e.get("tool_use_id") == tool_use_id:
                    e["state"] = "running"
                    e["background"] = True
                    return
            data["entries"].append({
                "tool_use_id": tool_use_id, "agent": agent,
                "session_id": payload.get("session_id") or None,
                "started_at": time.time(), "state": "running", "background": True,
            })
        else:
            _remove_one(data, tool_use_id=tool_use_id, agent=agent,
                        session=payload.get("session_id") or None)


def mark_stopped(payload: dict[str, Any], root: Path) -> None:
    """SubagentStop : libère le créneau de l'agent qui s'arrête."""
    agent = agent_type_of(payload)
    if not agent or agent not in sdd_agent_registry(root):
        return
    with _Locked(root) as data:
        _prune(data, time.time())
        _remove_one(data, tool_use_id=payload.get("tool_use_id") or None, agent=agent,
                    session=payload.get("session_id") or None)


def sweep(payload: dict[str, Any], root: Path) -> None:
    """Stop (fin du tour principal) : tout agent foreground est terminé ;
    purge les réservations foreground orphelines (spawn refusé par un autre
    hook, PostToolUse perdu). Les agents d'arrière-plan sont conservés."""
    session = payload.get("session_id") or None
    with _Locked(root) as data:
        _prune(data, time.time())
        data["entries"] = [e for e in data["entries"]
                           if e.get("background")
                           or (session is not None and e.get("session_id") != session)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="enforce_max_parallel")
    ap.add_argument("--event", choices=("pre", "post", "stop", "sweep"), default=None,
                    help="défaut : déduit de hook_event_name")
    args = ap.parse_args(argv)
    try:
        payload = read_hook_input()
    except (OSError, ValueError, UnicodeError):
        payload = {}
    event = args.event
    if event is None:
        name = str(payload.get("hook_event_name") or "")
        event = {"PreToolUse": "pre", "PostToolUse": "post", "SubagentStop": "stop",
                 "Stop": "sweep"}.get(name, "pre")
    root = repo_root()
    if event == "pre":
        try:
            code, msg = on_pre(payload, root)
        except RuntimeError as exc:  # [LOCK_HELD] persistant
            sys.stderr.write(f"ERROR: [INFRA_BLOCKED] inflight.json verrouillé : {exc}\n"
                             f"FIX: supprimer workspace/.sys/.state/inflight.json.lock si périmé\n")
            return HOOK_DENY
        if msg:
            sys.stderr.write(msg)
        return code
    # Événements d'enregistrement : jamais bloquants
    try:
        {"post": mark_started, "stop": mark_stopped, "sweep": sweep}[event](payload, root)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"WARN [MAX_PARALLEL_STATE] {event}: {type(exc).__name__}: {exc}\n")
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
