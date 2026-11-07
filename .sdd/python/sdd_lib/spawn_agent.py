"""spawn_agent — wrapper d'orchestration de sous-agents SDD multi-harnais.

Industrialise le prototype P0.4 (`.sdd/experiments/p04-codex-subagent/`) en un
composant réutilisable : émule un « spawn de sous-agent isolé » sous un harnais
NON-Claude (Codex `codex exec`, Gemini CLI `gemini -p`, ou headless
`claude -p`) via un sous-processus, puis valide que la complétion est un JSON
strict conforme au schéma attendu. C'est le repli du mécanisme `subagent_spawn`
que Claude Code fournit nativement (tool Task/Agent) — cf. capability-matrix.yml
(`subagent_spawn: emulated`) et plan §7.1 (RISQUE #1) / §9 tâche 3.2.

Propriétés :
- **Token-free & testable offline** : le SEUL point de contact avec un binaire
  externe est ``cfg.runner`` (callable injectable). Défaut = vrai subprocess ;
  les tests injectent un runner factice → aucun CLI réel, aucun token requis.
- **Parallélisme borné** : ``spawn_many`` exécute N specs via un pool borné à
  ``max_parallel`` (défaut 3, MaxParallel SDD). Un spec qui échoue -> résultat
  ``ok=False`` (jamais d'exception qui remonte — sémantique ``parallel()``).
- **Retry-on-schema-fail** (§10.2 GO conditionnel) : sur JSON invalide/non
  conforme, 1 re-prompt automatique avec l'erreur de validation (opt-in).
- **Déterministe** : aucune horloge/aléa dans la logique de décision.

Transport du prompt (audit 2026-11-07) : le prompt auto-porteur dépasse
couramment 32 Ko (system prompt d'agent + tâche + schéma). Passé en argv, il
franchit la limite Windows ``CreateProcess`` (``OSError WinError 206``) ou
``E2BIG`` sous POSIX — erreur qui n'était pas capturée. Par défaut le prompt
est donc envoyé sur **stdin** (``prompt_transport="stdin"``) :
- ``codex exec … -`` — ``-`` = « lire les instructions sur stdin » (aide
  ``codex exec --help`` : « If not provided as an argument (or if `-` is
  used), instructions are read from stdin »).
- ``claude -p`` sans argument positionnel — le mode print lit le prompt sur
  stdin quand aucun texte n'est fourni (``cat prompt | claude -p``).
- ``gemini -p "<marqueur court>"`` — Gemini CLI concatène stdin (non-TTY) et
  ``--prompt`` ; le marqueur garde l'invocation explicitement headless.
``prompt_transport="argv"`` conserve l'ancien comportement (prompts courts,
débogage). Tout ``OSError`` résiduel est classé ``[SPAWN_ARGV_TOO_LONG]`` /
``[SPAWN_OS_ERROR]`` (rapport ERROR 3L dans ``error_report``).

Statut : composant prêt ; le VERDICT live (P0.4) et les runs de conformité
(§10) attendent CLI + clés. **Non câblé au pipeline Claude Code** : en
session, le tool Agent est le seul mécanisme de spawn. Ce wrapper est
utilisable par un orchestrateur hors-LLM (CI, script, harnais non-Claude).
"""

from __future__ import annotations

import errno
import inspect
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

__all__ = [
    "HARNESSES",
    "SpawnConfig",
    "AgentSpec",
    "PROMPT_TRANSPORTS",
    "build_prompt",
    "extract_json",
    "validate_schema",
    "spawn_agent",
    "spawn_many",
]

#: Harnais dont le spawn de sous-agent est émulé par ce wrapper.
HARNESSES: tuple[str, ...] = ("codex", "gemini-cli", "antigravity", "claude-code")

DEFAULT_TIMEOUT_S = 180.0
DEFAULT_MAX_PARALLEL = 3

#: Transports du prompt vers le CLI : stdin (défaut, pas de limite argv) | argv.
PROMPT_TRANSPORTS: tuple[str, ...] = ("stdin", "argv")

#: Marqueur court passé en ``-p`` à Gemini CLI quand le prompt complet arrive
#: sur stdin (Gemini concatène stdin + ``--prompt``).
GEMINI_STDIN_MARKER = "Exécute les instructions reçues sur l'entrée standard."

#: Runner : (argv, timeout_s, cwd, stdin_text) -> RunResult. Peut lever
#: FileNotFoundError / TimeoutError / OSError. Un runner à 3 paramètres
#: (argv, timeout_s, cwd) reste accepté (compat tests/callers pré-2026-11).
Runner = Callable[..., "RunResult"]


@dataclass(frozen=True)
class RunResult:
    """Résultat brut d'un sous-processus (avant parsing)."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class SpawnConfig:
    """Paramètres d'un spawn émulé. `runner` injectable = seam de test."""

    harness: str = "codex"
    model: Optional[str] = None
    bin: Optional[str] = None            # override du binaire (défaut = déduit du harnais)
    timeout_s: float = DEFAULT_TIMEOUT_S
    sandbox: str = "read-only"           # codex : le sous-agent émulé n'écrit pas
    extra_args: tuple[str, ...] = ()
    isolate_cwd: bool = True             # cwd temporaire neuf par spawn (isolation)
    max_parallel: int = DEFAULT_MAX_PARALLEL
    schema_retry: bool = True            # 1 re-prompt sur JSON invalide (§10.2)
    runner: Optional[Runner] = None      # None -> subprocess réel ; injecté en test
    prompt_transport: str = "stdin"      # stdin (défaut) | argv (legacy, prompts courts)

    def __post_init__(self) -> None:
        if self.harness not in HARNESSES:
            raise ValueError(
                f"harnais {self.harness!r} non émulé (attendu: {'|'.join(HARNESSES)})"
            )
        if self.max_parallel < 1:
            raise ValueError(f"max_parallel doit être >= 1 (reçu {self.max_parallel})")
        if self.prompt_transport not in PROMPT_TRANSPORTS:
            raise ValueError(
                f"prompt_transport {self.prompt_transport!r} inconnu "
                f"(attendu: {'|'.join(PROMPT_TRANSPORTS)})"
            )

    def binary(self) -> str:
        if self.bin:
            return self.bin
        if self.harness == "codex":
            # Avoid the unsigned npm PowerShell shim on managed Windows hosts.
            return "codex.cmd" if os.name == "nt" else "codex"
        return {"gemini-cli": "gemini", "antigravity": "gemini", "claude-code": "claude"}[self.harness]


@dataclass
class AgentSpec:
    """Un sous-agent à spawner : rôle + tâche + contrat de sortie JSON."""

    system_prompt: str
    task: str
    output_schema: dict
    label: str = ""


# --------------------------------------------------------------------------- #
# Construction d'argv par harnais                                             #
# --------------------------------------------------------------------------- #


def _build_invocation(cfg: SpawnConfig, prompt: str) -> tuple[list[str], Optional[str]]:
    """(argv, stdin_text) du sous-processus selon le harnais et le transport.

    ``stdin_text`` vaut ``None`` en transport ``argv`` (prompt porté par argv,
    comportement historique) et le prompt complet en transport ``stdin``.
    """
    b = cfg.binary()
    via_stdin = cfg.prompt_transport == "stdin"
    stdin_text: Optional[str] = prompt if via_stdin else None
    if cfg.harness == "codex":
        argv = [b, "exec", "--sandbox", cfg.sandbox, "--skip-git-repo-check"]
        if cfg.model:
            argv += ["--model", cfg.model]
        argv += list(cfg.extra_args)
        # `-` : codex exec lit les instructions sur stdin (cf. `codex exec --help`).
        argv.append("-" if via_stdin else prompt)
        return argv, stdin_text
    if cfg.harness in ("gemini-cli", "antigravity"):
        # Gemini CLI concatène stdin (non-TTY) et --prompt : le marqueur court
        # garde l'invocation headless, le prompt complet voyage sur stdin.
        argv = [b, "-p", GEMINI_STDIN_MARKER if via_stdin else prompt]
        if cfg.model:
            argv += ["-m", cfg.model]
        return argv + list(cfg.extra_args), stdin_text
    # claude-code (headless print mode) — le chemin natif reste le tool Agent ;
    # ce mode existe pour l'uniformité des conformance runs. Sans argument
    # positionnel, `claude -p` lit le prompt sur stdin.
    argv = [b, "-p"]
    if not via_stdin:
        argv.append(prompt)
    if cfg.model:
        argv += ["--model", cfg.model]
    return argv + list(cfg.extra_args), stdin_text


def _build_argv(cfg: SpawnConfig, prompt: str) -> list[str]:
    """argv du sous-processus (compat : voir `_build_invocation` pour stdin)."""
    return _build_invocation(cfg, prompt)[0]


def _default_runner(
    argv: list[str], timeout_s: float, cwd: Optional[str], stdin_text: Optional[str] = None
) -> RunResult:
    """Runner réel (subprocess). Seul contact avec un binaire externe."""
    proc = subprocess.run(
        argv,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        cwd=cwd,
    )
    return RunResult(exit_code=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "")


def _call_runner(
    runner: Runner, argv: list[str], timeout_s: float, cwd: Optional[str], stdin_text: Optional[str]
) -> RunResult:
    """Appelle le runner en respectant son arité (3 params legacy ou 4).

    Un runner legacy (``argv, timeout_s, cwd``) ne sait pas transmettre le
    prompt : s'il est utilisé en transport ``stdin``, le prompt serait perdu
    silencieusement — on refuse explicitement plutôt que de spawner à vide.
    """
    try:
        params = inspect.signature(runner).parameters
        accepts_stdin = len(params) >= 4 or any(
            p.kind == inspect.Parameter.VAR_POSITIONAL for p in params.values()
        )
    except (TypeError, ValueError):  # builtins / callables sans signature
        accepts_stdin = True
    if accepts_stdin:
        return runner(argv, timeout_s, cwd, stdin_text)
    if stdin_text is not None:
        raise TypeError(
            "runner à 3 paramètres (argv, timeout_s, cwd) incompatible avec "
            "prompt_transport='stdin' — accepter un 4e paramètre stdin_text "
            "ou passer prompt_transport='argv'"
        )
    return runner(argv, timeout_s, cwd)


# --------------------------------------------------------------------------- #
# Prompt auto-porteur + extraction/validation JSON                           #
# --------------------------------------------------------------------------- #


def build_prompt(system_prompt: str, task: str, output_schema: dict, *, correction: str = "") -> str:
    """Prompt auto-porteur : rôle + tâche + contrat de sortie JSON strict."""
    schema_txt = json.dumps(output_schema, ensure_ascii=False, indent=2)
    corr = f"\n## Correction\n{correction.strip()}\n" if correction.strip() else ""
    return (
        f"{system_prompt.strip()}\n\n"
        f"## Tâche\n{task.strip()}\n{corr}\n"
        "## Contrat de sortie (STRICT)\n"
        "Réponds UNIQUEMENT par un objet JSON valide conforme au schéma "
        "ci-dessous. Aucun texte avant/après, pas de markdown, pas de commentaire.\n"
        f"```json\n{schema_txt}\n```"
    )


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> Optional[Any]:
    """Extrait un objet JSON (strict -> fenced -> premier {…} équilibré)."""
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
                        return json.loads(text[start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break
        start = text.find("{", start + 1)
    return None


_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def validate_schema(obj: Any, schema: dict, path: str = "$") -> list[str]:
    """Valide `obj` contre un sous-ensemble JSONSchema (type/required/props/items/enum)."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        py_type = _TYPE_MAP.get(expected)
        if py_type is not None:
            ok = isinstance(obj, py_type)
            if expected in ("number", "integer") and isinstance(obj, bool):
                ok = False  # bool est un int en Python — refusé
            if not ok:
                errors.append(f"{path}: attendu {expected}, reçu {type(obj).__name__}")
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
            errors.extend(validate_schema(item, schema["items"], f"{path}[{idx}]"))
    return errors


# --------------------------------------------------------------------------- #
# API publique                                                                #
# --------------------------------------------------------------------------- #


def _invoke(prompt: str, cfg: SpawnConfig) -> RunResult:
    """Lance le sous-processus via le runner (réel ou injecté), cwd isolé."""
    runner = cfg.runner or _default_runner
    argv, stdin_text = _build_invocation(cfg, prompt)
    cwd: Optional[str] = None
    tmp = None
    if cfg.isolate_cwd and cfg.runner is None:
        import tempfile

        tmp = tempfile.mkdtemp(prefix="sdd-spawn-")
        cwd = tmp
    try:
        return _call_runner(runner, argv, cfg.timeout_s, cwd, stdin_text)
    finally:
        if tmp is not None:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


#: Windows ERROR_FILENAME_EXCED_RANGE — levé par CreateProcess quand la ligne
#: de commande dépasse ~32 Ko (prompt complet passé en argv).
_WINERROR_ARGV_TOO_LONG = 206


def _classify_os_error(exc: OSError) -> str:
    """Classe un OSError de spawn : ligne de commande trop longue ou autre."""
    if getattr(exc, "winerror", None) == _WINERROR_ARGV_TOO_LONG:
        return "[SPAWN_ARGV_TOO_LONG]"
    if exc.errno == errno.E2BIG:
        return "[SPAWN_ARGV_TOO_LONG]"
    return "[SPAWN_OS_ERROR]"


def _error_report(label: str, cfg: SpawnConfig, klass: str, detail: str, fix: str) -> str:
    """Rapport ERROR 3L (format disque SSoT, output-protocol.md §7.3)."""
    what = label or cfg.harness
    return (
        f"ERROR: spawn_agent {what} ({cfg.harness}) failed\n"
        f"CAUSE: {klass} {detail}\n"
        f"FIX: {fix}"
    )


def _attempt(prompt: str, cfg: SpawnConfig, schema: dict, label: str = "") -> dict:
    """Un essai : invoque, extrait, valide. Retourne un résultat structuré."""
    t0 = time.monotonic()
    try:
        run = _invoke(prompt, cfg)
    except FileNotFoundError:
        return {"ok": False, "parsed": None, "raw": "", "error_class": "[SPAWN_BINARY_NOT_FOUND]"}
    except (subprocess.TimeoutExpired, TimeoutError):
        return {"ok": False, "parsed": None, "raw": "", "error_class": "[TIMEOUT]"}
    except OSError as exc:
        # WinError 206 / E2BIG : prompt (> 32 Ko) passé en argv — non capturé
        # avant l'audit 2026-11-07, le spawn remontait une exception brute.
        klass = _classify_os_error(exc)
        detail = (
            f"{type(exc).__name__}: {str(exc)[:200]} "
            f"(prompt {len(prompt)} chars, transport={cfg.prompt_transport})"
        )
        if klass == "[SPAWN_ARGV_TOO_LONG]":
            fix = ("passer le prompt sur stdin (SpawnConfig(prompt_transport='stdin'), "
                   "défaut) au lieu d'argv")
        else:
            fix = f"vérifier le binaire {cfg.binary()!r}, ses droits d'exécution et le cwd isolé"
        return {
            "ok": False,
            "parsed": None,
            "raw": "",
            "error_class": klass,
            "detail": detail,
            "error_report": _error_report(label, cfg, klass, detail, fix),
        }
    latency_ms = int((time.monotonic() - t0) * 1000)
    raw = run.stdout or ""
    base = {"raw": raw, "latency_ms": latency_ms, "exit_code": run.exit_code}
    if run.exit_code != 0:
        return {**base, "ok": False, "parsed": None, "error_class": "[NONZERO_EXIT]"}
    if not raw.strip():
        return {**base, "ok": False, "parsed": None, "error_class": "[EMPTY_OUTPUT]"}
    parsed = extract_json(raw)
    if parsed is None:
        return {**base, "ok": False, "parsed": None, "error_class": "[JSON_UNPARSEABLE]"}
    schema_errors = validate_schema(parsed, schema)
    if schema_errors:
        return {
            **base,
            "ok": False,
            "parsed": parsed,
            "error_class": "[SCHEMA_MISMATCH]",
            "schema_errors": schema_errors,
        }
    return {**base, "ok": True, "parsed": parsed, "error_class": None}


_RETRYABLE = ("[JSON_UNPARSEABLE]", "[SCHEMA_MISMATCH]")


def spawn_agent(spec: AgentSpec, cfg: Optional[SpawnConfig] = None) -> dict:
    """Spawn d'UN sous-agent émulé. Retry-on-schema-fail (§10.2) si activé.

    Retour : {ok, parsed, raw, latency_ms, error_class, harness, label, attempts}.
    ``ok`` ssi exit 0 + JSON extrait + conforme au schéma.
    """
    cfg = cfg or SpawnConfig()
    prompt = build_prompt(spec.system_prompt, spec.task, spec.output_schema)
    result = _attempt(prompt, cfg, spec.output_schema, spec.label)
    attempts = 1
    if not result["ok"] and cfg.schema_retry and result["error_class"] in _RETRYABLE:
        errs = "; ".join(result.get("schema_errors", []) or ["sortie non-JSON"])
        retry_prompt = build_prompt(
            spec.system_prompt,
            spec.task,
            spec.output_schema,
            correction=f"Ta réponse précédente n'était pas un JSON conforme: {errs}.",
        )
        result = _attempt(retry_prompt, cfg, spec.output_schema, spec.label)
        attempts = 2
    result.update({"harness": cfg.harness, "label": spec.label, "attempts": attempts})
    return result


def spawn_many(specs: Iterable[AgentSpec], cfg: Optional[SpawnConfig] = None) -> list[dict]:
    """Spawn de N sous-agents en parallélisme BORNÉ (max_parallel).

    Sémantique ``parallel()`` : un spec qui échoue -> résultat ``ok=False``
    (jamais d'exception propagée). Résultats dans l'ordre d'entrée.
    """
    cfg = cfg or SpawnConfig()
    spec_list = list(specs)
    if not spec_list:
        return []
    workers = min(cfg.max_parallel, len(spec_list))

    def _one(spec: AgentSpec) -> dict:
        try:
            return spawn_agent(spec, cfg)
        except Exception as exc:  # filet : jamais d'exception qui remonte
            return {
                "ok": False,
                "parsed": None,
                "raw": "",
                "error_class": "[SPAWN_INTERNAL_ERROR]",
                "harness": cfg.harness,
                "label": spec.label,
                "attempts": 0,
                "detail": str(exc),
            }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_one, spec_list))
