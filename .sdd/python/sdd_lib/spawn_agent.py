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

Statut : composant prêt ; le VERDICT live (P0.4) et les runs de conformité
(§10) attendent CLI + clés. Non câblé au pipeline (Phase 3+).
"""

from __future__ import annotations

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
    "build_prompt",
    "extract_json",
    "validate_schema",
    "spawn_agent",
    "spawn_many",
]

#: Harnais dont le spawn de sous-agent est émulé par ce wrapper.
HARNESSES: tuple[str, ...] = ("codex", "gemini-cli", "claude-code")

DEFAULT_TIMEOUT_S = 180.0
DEFAULT_MAX_PARALLEL = 3

#: (exit_code, stdout, stderr). Peut lever FileNotFoundError / TimeoutError.
Runner = Callable[[list[str], float, Optional[str]], "RunResult"]


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

    def __post_init__(self) -> None:
        if self.harness not in HARNESSES:
            raise ValueError(
                f"harnais {self.harness!r} non émulé (attendu: {'|'.join(HARNESSES)})"
            )
        if self.max_parallel < 1:
            raise ValueError(f"max_parallel doit être >= 1 (reçu {self.max_parallel})")

    def binary(self) -> str:
        if self.bin:
            return self.bin
        if self.harness == "codex":
            # Avoid the unsigned npm PowerShell shim on managed Windows hosts.
            return "codex.cmd" if os.name == "nt" else "codex"
        return {"gemini-cli": "gemini", "claude-code": "claude"}[self.harness]


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


def _build_argv(cfg: SpawnConfig, prompt: str) -> list[str]:
    """argv du sous-processus selon le harnais (non-interactif, prompt porteur)."""
    b = cfg.binary()
    if cfg.harness == "codex":
        argv = [b, "exec", "--sandbox", cfg.sandbox, "--skip-git-repo-check"]
        if cfg.model:
            argv += ["--model", cfg.model]
        argv += list(cfg.extra_args)
        argv.append(prompt)
        return argv
    if cfg.harness == "gemini-cli":
        argv = [b, "-p", prompt]
        if cfg.model:
            argv += ["-m", cfg.model]
        return argv + list(cfg.extra_args)
    # claude-code (headless print mode) — le chemin natif reste le tool Task ;
    # ce mode existe pour l'uniformité des conformance runs.
    argv = [b, "-p", prompt]
    if cfg.model:
        argv += ["--model", cfg.model]
    return argv + list(cfg.extra_args)


def _default_runner(argv: list[str], timeout_s: float, cwd: Optional[str]) -> RunResult:
    """Runner réel (subprocess). Seul contact avec un binaire externe."""
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        cwd=cwd,
    )
    return RunResult(exit_code=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "")


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
    argv = _build_argv(cfg, prompt)
    cwd: Optional[str] = None
    tmp = None
    if cfg.isolate_cwd and cfg.runner is None:
        import tempfile

        tmp = tempfile.mkdtemp(prefix="sdd-spawn-")
        cwd = tmp
    try:
        return runner(argv, cfg.timeout_s, cwd)
    finally:
        if tmp is not None:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


def _attempt(prompt: str, cfg: SpawnConfig, schema: dict) -> dict:
    """Un essai : invoque, extrait, valide. Retourne un résultat structuré."""
    t0 = time.monotonic()
    try:
        run = _invoke(prompt, cfg)
    except FileNotFoundError:
        return {"ok": False, "parsed": None, "raw": "", "error_class": "[SPAWN_BINARY_NOT_FOUND]"}
    except (subprocess.TimeoutExpired, TimeoutError):
        return {"ok": False, "parsed": None, "raw": "", "error_class": "[TIMEOUT]"}
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
    result = _attempt(prompt, cfg, spec.output_schema)
    attempts = 1
    if not result["ok"] and cfg.schema_retry and result["error_class"] in _RETRYABLE:
        errs = "; ".join(result.get("schema_errors", []) or ["sortie non-JSON"])
        retry_prompt = build_prompt(
            spec.system_prompt,
            spec.task,
            spec.output_schema,
            correction=f"Ta réponse précédente n'était pas un JSON conforme: {errs}.",
        )
        result = _attempt(retry_prompt, cfg, spec.output_schema)
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
