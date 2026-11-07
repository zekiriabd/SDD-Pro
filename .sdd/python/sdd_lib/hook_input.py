"""Parse JSON stdin payload from Claude Code hooks, with regex fallback.

Payload shapes (Claude Code hook protocol — vérifié doc 2026-11) :

* ``PreToolUse`` / ``PostToolUse`` : ``{"tool_name", "tool_input", ...}``.
  Quand l'appel est émis **depuis un sous-agent**, le payload porte en plus
  ``agent_id`` et ``agent_type`` ; la session principale n'a PAS ces champs.
* ``SubagentStop`` : ``{"agent_type", "agent_id", "agent_transcript_path", ...}``
  — il n'y a **pas** de ``tool_input.subagent_type`` ni de ``usage``.
* ``PreToolUse`` sur le tool ``Agent`` : le type de l'agent à spawner est dans
  ``tool_input.subagent_type``.

Audit sécurité 2026-11 : ``get_subagent_type`` ne lisait QUE
``tool_input.subagent_type`` → sur ``SubagentStop`` il retournait ``None`` et
``audit_file_ownership`` ne scannait jamais rien. Désormais :
``tool_input.subagent_type`` (spawn) puis ``agent_type`` (SubagentStop /
appel depuis un sous-agent) puis ``subagent_type`` racine (compat tests
historiques). ``get_caller_agent_type`` / ``get_spawn_target_type`` lèvent
l'ambiguïté quand les deux coexistent.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any


def read_hook_input() -> dict[str, Any]:
    """Read full stdin and parse as JSON.

    Returns:
        Parsed payload dict, or {} on empty/invalid input.
    """
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return _regex_fallback(raw)


def _regex_fallback(text: str) -> dict[str, Any]:
    """Best-effort field extraction when JSON parsing fails.

    Mimics the PowerShell fallback regex behaviour for `file_path`,
    `tool_name`, `subagent_type`, plus the sub-agent identity fields
    (`agent_id`, `agent_type`) so `is_subagent_call` stays reliable on a
    truncated payload (fail-closed : better to classify as sub-agent).
    """
    out: dict[str, Any] = {}
    tool_input: dict[str, Any] = {}

    fp = re.search(r'"file_path"\s*:\s*"([^"]+)"', text)
    if fp:
        tool_input["file_path"] = fp.group(1)

    tn = re.search(r'"tool_name"\s*:\s*"([^"]+)"', text)
    if tn:
        out["tool_name"] = tn.group(1)

    sa = re.search(r'"subagent_type"\s*:\s*"([^"]+)"', text)
    if sa:
        tool_input["subagent_type"] = sa.group(1)

    for key in ("agent_id", "agent_type", "agent_transcript_path"):
        m = re.search(r'"' + key + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if m:
            out[key] = m.group(1)

    prompt = re.search(r'"prompt"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if prompt:
        tool_input["prompt"] = prompt.group(1)

    descr = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if descr:
        tool_input["description"] = descr.group(1)

    if tool_input:
        out["tool_input"] = tool_input
    return out


def get_nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Walk nested dict keys, return default if any key missing or wrong type."""
    cur: Any = payload
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _non_empty_str(val: Any) -> str | None:
    return val if isinstance(val, str) and val.strip() else None


def get_file_path(payload: dict[str, Any]) -> str | None:
    """Extract the target file of a file-mutating tool.

    Order : ``tool_input.file_path`` (Edit/Write/MultiEdit/Read),
    ``tool_input.notebook_path`` (NotebookEdit — audit 2026-11 : ce tool
    écrit sur disque sans passer par ``file_path``), puis ``file_path`` racine.
    """
    for keys in (("tool_input", "file_path"), ("tool_input", "notebook_path"),
                 ("file_path",), ("notebook_path",)):
        fp = _non_empty_str(get_nested(payload, *keys))
        if fp:
            return fp
    return None


def get_tool_name(payload: dict[str, Any]) -> str | None:
    return _non_empty_str(payload.get("tool_name"))


def get_subagent_type(payload: dict[str, Any]) -> str | None:
    """Return the sub-agent type carried by the payload, whatever the event.

    * ``tool_input.subagent_type`` — ``PreToolUse`` sur le tool ``Agent``
      (identité de l'agent **à spawner**) — lu en premier pour préserver la
      sémantique de tous les hooks de spawn existants (budget, cost cap,
      two-stage, secret scan) même quand l'orchestrateur est lui-même un
      sous-agent (les deux champs coexistent alors) ;
    * ``agent_type`` (racine) — ``SubagentStop`` (il n'y a pas de
      ``tool_input`` sur cet événement), ou tout PreToolUse/PostToolUse émis
      depuis un sous-agent (identité de l'appelant) ;
    * ``subagent_type`` racine — compat payloads historiques / tests.

    Pour lire explicitement l'identité de l'APPELANT, utiliser
    ``get_caller_agent_type``.
    """
    for keys in (("tool_input", "subagent_type"), ("agent_type",), ("subagent_type",)):
        val = _non_empty_str(get_nested(payload, *keys))
        if val:
            return val
    return None


def get_caller_agent_type(payload: dict[str, Any]) -> str | None:
    """``agent_type`` racine : identité du sous-agent qui a émis l'événement
    (``SubagentStop`` → l'agent qui s'arrête ; PreToolUse → l'appelant).
    ``None`` en session principale."""
    return _non_empty_str(payload.get("agent_type"))


def get_spawn_target_type(payload: dict[str, Any]) -> str | None:
    """Type of the agent about to be spawned (``PreToolUse`` tool ``Agent``).

    Reads ``tool_input.subagent_type`` only, then the historical root
    ``subagent_type`` — never ``agent_type`` (that is the CALLER's identity).
    """
    for keys in (("tool_input", "subagent_type"), ("subagent_type",)):
        val = _non_empty_str(get_nested(payload, *keys))
        if val:
            return val
    return None


def is_subagent_call(payload: dict[str, Any]) -> bool:
    """True when the hook event was emitted from inside a sub-agent.

    Doc Claude Code : un PreToolUse/PostToolUse déclenché DANS un sous-agent
    porte ``agent_id`` et ``agent_type`` ; la session principale (Tech Lead
    humain) n'a aucun des deux. Utilisé pour appliquer une politique
    ``strict`` aux agents et ``warn`` au Tech Lead.
    """
    return bool(_non_empty_str(payload.get("agent_id"))
                or _non_empty_str(payload.get("agent_type")))


def get_agent_id(payload: dict[str, Any]) -> str | None:
    return _non_empty_str(payload.get("agent_id"))


def get_agent_transcript_path(payload: dict[str, Any]) -> str | None:
    """``SubagentStop`` only : path of the finished sub-agent's transcript."""
    return _non_empty_str(payload.get("agent_transcript_path"))
