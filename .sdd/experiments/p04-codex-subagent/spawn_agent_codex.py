"""P0.4 — Prototype de dérisquage RISQUE #1 (plan §9 tâche 0.4, §11 R1).

Émule un « spawn de sous-agent SDD-Pro isolé » via `codex exec` en
sous-processus non-interactif, puis vérifie que la complétion est
parseable (JSON strict conforme au schéma attendu).

AUCUN appel n'est déclenché à l'import. Le seul point de contact avec le
binaire `codex` est `_invoke_codex()` — seam unique, mockable dans les
tests (`test_spawn_agent_codex.py` ne lance jamais le vrai codex).

Paramétrage (argv de run_experiment.py ou env) :
  SDD_CODEX_BIN        chemin du binaire codex (défaut : "codex")
  SDD_CODEX_MODEL      modèle (défaut : celui configuré côté codex)
  SDD_CODEX_TIMEOUT_S  timeout par spawn en secondes (défaut : 180)

Classes d'erreur locales (prototype jetable — même discipline [CLASS]
que rules/error-classification.md, taxonomie NON fusionnée) :
  [SPAWN_BINARY_NOT_FOUND]  binaire codex introuvable
  [TIMEOUT]                 spawn tué après timeout
  [NONZERO_EXIT]            codex exit code != 0
  [EMPTY_OUTPUT]            aucune sortie exploitable
  [JSON_UNPARSEABLE]        sortie présente mais aucun JSON extractible
  [SCHEMA_MISMATCH]         JSON parsé mais non conforme au schéma attendu
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Optional

DEFAULT_TIMEOUT_S = 180


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CodexConfig:
    """Paramètres d'invocation du binaire codex (argv > env > défauts)."""
    codex_bin: str = field(
        default_factory=lambda: os.environ.get(
            "SDD_CODEX_BIN", "codex.cmd" if os.name == "nt" else "codex"))
    model: Optional[str] = field(
        default_factory=lambda: os.environ.get("SDD_CODEX_MODEL") or None)
    timeout_s: float = field(
        default_factory=lambda: float(
            os.environ.get("SDD_CODEX_TIMEOUT_S", DEFAULT_TIMEOUT_S)))
    sandbox: str = "read-only"       # le sous-agent émulé ne doit rien écrire
    isolate_cwd: bool = True         # cwd temporaire neuf par spawn (isolation)
    extra_args: tuple = ()           # flags codex additionnels si besoin


# ---------------------------------------------------------------------------
# Seam subprocess — SEUL point d'appel réel, mocké dans les tests
# ---------------------------------------------------------------------------

@dataclass
class CodexInvocation:
    """Résultat brut d'une invocation `codex exec` (avant parsing)."""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    last_message: Optional[str] = None   # contenu de --output-last-message
    timed_out: bool = False
    spawn_error: Optional[str] = None    # ex. binaire introuvable


def _invoke_codex(prompt: str, cfg: CodexConfig) -> CodexInvocation:
    """Lance `codex exec` en sous-processus isolé et capture tout.

    Isolation : cwd temporaire vierge (aucun contexte projet partagé entre
    deux spawns), prompt auto-porteur, sandbox read-only. La complétion
    finale est récupérée via --output-last-message (plus fiable que le
    stdout mêlé aux logs d'exécution codex).
    """
    with tempfile.TemporaryDirectory(prefix="sdd-p04-") as tmp:
        last_msg_path = os.path.join(tmp, "last-message.txt")
        cwd = tmp if cfg.isolate_cwd else None

        argv = [cfg.codex_bin, "exec",
                "--sandbox", cfg.sandbox,
                "--skip-git-repo-check",
                "--output-last-message", last_msg_path]
        if cfg.model:
            argv += ["--model", cfg.model]
        argv += list(cfg.extra_args)
        argv.append(prompt)

        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=cfg.timeout_s, cwd=cwd)
        except FileNotFoundError:
            return CodexInvocation(spawn_error="binary-not-found")
        except subprocess.TimeoutExpired as exc:
            return CodexInvocation(
                timed_out=True,
                stdout=_coerce_text(exc.stdout),
                stderr=_coerce_text(exc.stderr))

        last_message = None
        try:
            with open(last_msg_path, encoding="utf-8", errors="replace") as fh:
                content = fh.read().strip()
                last_message = content or None
        except OSError:
            pass

        return CodexInvocation(
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            last_message=last_message)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


# ---------------------------------------------------------------------------
# Extraction JSON (strict → fence → objet équilibré)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> Optional[Any]:
    """Extrait un objet JSON d'une complétion, du plus strict au plus laxiste.

    1. json.loads direct sur le texte strippé (cas nominal attendu) ;
    2. bloc fenced ```json ... ``` ;
    3. premier objet {...} équilibré (scan conscient des strings/escapes).
    Retourne None si aucun objet extractible.
    """
    if not text:
        return None
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    match = _FENCE_RE.search(stripped)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    return _scan_balanced_object(stripped)


def _scan_balanced_object(text: str) -> Optional[Any]:
    start = text.find("{")
    while start != -1:
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break  # candidat invalide → objet { suivant
        start = text.find("{", start + 1)
    return None


# ---------------------------------------------------------------------------
# Validation de schéma (sous-ensemble minimal, zéro dépendance)
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "object": dict, "array": list, "string": str,
    "number": (int, float), "integer": int, "boolean": bool,
}


def validate_schema(obj: Any, schema: dict, path: str = "$") -> list:
    """Valide `obj` contre un sous-ensemble JSONSchema : type, required,
    properties, items, enum. Retourne la liste des erreurs ([] = conforme)."""
    errors: list = []
    expected = schema.get("type")
    if expected:
        py_type = _TYPE_MAP.get(expected)
        if py_type is not None:
            ok = isinstance(obj, py_type)
            if expected in ("number", "integer") and isinstance(obj, bool):
                ok = False  # bool est un int en Python — refusé
            if not ok:
                errors.append(f"{path}: attendu {expected}, "
                              f"reçu {type(obj).__name__}")
                return errors

    if "enum" in schema and obj not in schema["enum"]:
        errors.append(f"{path}: valeur {obj!r} hors enum {schema['enum']}")

    if isinstance(obj, dict):
        for key in schema.get("required", []):
            if key not in obj:
                errors.append(f"{path}.{key}: clé requise absente")
        for key, sub in schema.get("properties", {}).items():
            if key in obj:
                errors.extend(validate_schema(obj[key], sub, f"{path}.{key}"))

    if isinstance(obj, list) and "items" in schema:
        for idx, item in enumerate(obj):
            errors.extend(
                validate_schema(item, schema["items"], f"{path}[{idx}]"))

    return errors


# ---------------------------------------------------------------------------
# API publique — spawn d'un sous-agent émulé
# ---------------------------------------------------------------------------

def build_prompt(system_prompt: str, task: str, output_schema: dict) -> str:
    """Prompt auto-porteur : rôle d'agent + tâche + contrat de sortie JSON."""
    schema_txt = json.dumps(output_schema, ensure_ascii=False, indent=2)
    return (
        f"{system_prompt.strip()}\n\n"
        f"## Tâche\n{task.strip()}\n\n"
        "## Contrat de sortie (STRICT)\n"
        "Réponds UNIQUEMENT par un objet JSON valide conforme au schéma "
        "ci-dessous. Aucun texte avant ou après l'objet JSON, pas de "
        "markdown, pas de commentaire.\n"
        f"```json\n{schema_txt}\n```"
    )


def spawn_agent(system_prompt: str, task: str, output_schema: dict,
                cfg: Optional[CodexConfig] = None) -> dict:
    """Spawn d'UN sous-agent émulé via `codex exec`.

    Retourne : {ok: bool, parsed: obj|None, raw: str, latency_ms: int,
                error_class: str|None}
    ok=True ssi exit 0 + JSON extrait + conforme au schéma.
    """
    cfg = cfg or CodexConfig()
    prompt = build_prompt(system_prompt, task, output_schema)

    t0 = time.monotonic()
    inv = _invoke_codex(prompt, cfg)
    latency_ms = int((time.monotonic() - t0) * 1000)

    raw = inv.last_message or inv.stdout or ""

    def fail(error_class: str) -> dict:
        return {"ok": False, "parsed": None, "raw": raw,
                "latency_ms": latency_ms, "error_class": error_class}

    if inv.spawn_error == "binary-not-found":
        return fail("[SPAWN_BINARY_NOT_FOUND]")
    if inv.timed_out:
        return fail("[TIMEOUT]")
    if inv.exit_code != 0:
        return fail("[NONZERO_EXIT]")
    if not raw.strip():
        return fail("[EMPTY_OUTPUT]")

    parsed = extract_json(raw)
    if parsed is None:
        return fail("[JSON_UNPARSEABLE]")

    schema_errors = validate_schema(parsed, output_schema)
    if schema_errors:
        result = fail("[SCHEMA_MISMATCH]")
        result["schema_errors"] = schema_errors
        return result

    return {"ok": True, "parsed": parsed, "raw": raw,
            "latency_ms": latency_ms, "error_class": None}
