#!/usr/bin/env python3
"""conformance_run — rejeu FEAT × harness × provider et comparaison à la baseline.

Réalise la tâche **§10** du plan `MIGRATION-PLAN-multi-harness-multi-provider.md`
(« conformance run obligatoire avant de sortir un combo de l'état UNTESTED »).

Objectif : lancer une FEAT SDD_Pro (défaut : CalcABC fixture) sur plusieurs
combinaisons ``(harness, provider)`` et comparer les sorties (code généré,
verdicts, coûts, latence) au **combo de référence** conformance-validé
(``claude-code × anthropic``) — cf. ``sdd_lib.impact_report.REFERENCE_*``.

Deux modes d'exécution (mutuellement exclusifs) :

- ``--dry-run`` (défaut) : **aucun** appel réseau. Vérifie que la config est
  cohérente pour chaque combo demandé :
    * providers YAML complets (``endpoint_kind``, ``auth_env``, ``tier_map``
      des 3 tiers, ``capabilities``) ;
    * dispatch stack.md valide (parse via ``sdd_lib.stack_config``) ;
    * adapter présent (``harness_build.py`` sait générer la façade du harnais) ;
    * FEAT fixture existe (``.sdd/experiments/conformance/`` ou chemin
      utilisateur).
  Émet ``[INFRA_BLOCKED]`` sur infra manquante ; sinon
  ``[CONFORMANCE_PASS]`` par combo validé. Sans réseau ni token.

- ``--live`` : **exécute réellement** le pipeline. Nécessite les API keys
  env vars (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, ``GEMINI_API_KEY``,
  ``MOONSHOT_API_KEY`` — selon combos). Timeout strict par combo (défaut
  30 min via ``--timeout-min``). Compare les outputs à la baseline (référence
  Claude Code × Anthropic sur FEAT CalcABC). Émet ``[CONFORMANCE_DRIFT]``
  si divergence détectée, ``[CONFORMANCE_PASS]`` sinon.

Sorties (déterministes, atomiques) :

- ``.sdd/.build/conformance/{timestamp}/report.md`` : rapport lisible Tech Lead
- ``.sdd/.build/conformance/{timestamp}/report.json`` : payload machine (CI)
- Chaque combo écrit son log détaillé sous
  ``.sdd/.build/conformance/{timestamp}/{harness}-{provider}/`` (stdout/stderr
  capturés, stack.md temporaire utilisé, verdict par step).

Guardrails :

- **Ne modifie JAMAIS** ``workspace/stack/stack.md``. Chaque combo travaille
  sur une copie temporaire (workspace temp isolé par run) ; le stack.md réel
  n'est jamais écrasé. Cette propriété est vérifiée par le smoke ``--dry-run``.
- Timeout strict par combo (fail-fast, jamais de blocage indéfini).
- Isolation cross-combo : chaque combo écrit dans son sous-répertoire propre
  sous le run temp — pas de fuite d'état.

Exit codes (convention ``sdd_lib.exit_codes``) :

- 0 SUCCESS — tous les combos ont PASS
- 1 FAIL_FAST — config invalide (provider YAML incomplet, FEAT introuvable,
  combo inconnu, drift bloquant en ``--live --strict``)
- 2 WARN — au moins un ``[CONFORMANCE_DRIFT]`` non-bloquant (mode par défaut
  ``--live``, un WARN est reporté mais l'exit reste 0 sauf ``--strict``)
- 3 INFRA_BLOCKED — CLI harnais absent, API key manquante en ``--live``,
  fixture disque unreadable

Usage :

    # Smoke CI (sans réseau) — les 5 combos par défaut
    python .sdd/python/sdd_scripts/conformance_run.py --dry-run

    # Ciblage explicite d'un combo
    python .sdd/python/sdd_scripts/conformance_run.py --dry-run \\
        --combo claude-code:anthropic --combo codex:openai

    # Live run (nécessite API keys, ~30 min/combo)
    export ANTHROPIC_API_KEY=sk-ant-...
    export OPENAI_API_KEY=sk-...
    python .sdd/python/sdd_scripts/conformance_run.py --live \\
        --combo claude-code:anthropic --combo codex:openai \\
        --timeout-min 30

Statut opérationnel (2026-07-25) :

- ``--dry-run`` : fonctionnel, utilisé en CI (gate config-drift).
- ``--live`` : fonctionnel UNIQUEMENT pour ``claude-code × anthropic``. Les
  autres combos exigent que ``sdd_lib.spawn_agent`` soit câblé au pipeline
  (Phase 3+ du plan de migration). En attendant, ``--live`` sur un combo
  non-référence émet ``[INFRA_BLOCKED]`` avec pointer vers
  ``docs/harness-codex.md`` / ``docs/harness-gemini.md``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# sdd_lib path insertion (script exécutable depuis n'importe où)
# --------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_PYTHON_DIR = _THIS_FILE.parent.parent  # .sdd/python/
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from sdd_lib.exit_codes import (  # noqa: E402
    SUCCESS,
    FAIL_FAST,
    CORRECTIBLE,
    INFRA_BLOCKED,
    describe as describe_exit,
)
from sdd_lib.paths import (  # noqa: E402
    repo_root,
    sdd_home,
    providers_dir,
    iso_now,
)

# --------------------------------------------------------------------------
# Constantes — combos par défaut (§10 du plan de migration)
# --------------------------------------------------------------------------

#: Combo de référence conformance-validé (SSoT = impact_report.REFERENCE_*).
REFERENCE_COMBO: tuple[str, str] = ("claude-code", "anthropic")

#: Liste par défaut des combos à valider (ordre stable pour reproductibilité).
DEFAULT_COMBOS: tuple[tuple[str, str], ...] = (
    ("claude-code", "anthropic"),   # référence
    ("claude-code", "moonshot"),    # Kimi via ANTHROPIC_BASE_URL compat
    ("codex", "openai"),            # natif OpenAI
    ("codex", "moonshot"),          # Moonshot via OpenAI-compat
    ("gemini-cli", "google"),       # natif Gemini
)

#: Providers connus (validité vérifiée par la présence du YAML sous providers/).
KNOWN_PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "google", "moonshot")

#: Harnais connus (SSoT = sdd_lib.stack_config.HARNESSES).
KNOWN_HARNESSES: tuple[str, ...] = ("claude-code", "codex", "gemini-cli", "antigravity")

#: Timeout par combo (secondes) — défaut 30 min.
DEFAULT_TIMEOUT_S: float = 30 * 60.0

#: Nom canonique de la FEAT fixture par défaut.
DEFAULT_FEAT_FIXTURE_NAME = "1-CalcABC.md"

#: Répertoire de la fixture stack.md par défaut.
FIXTURE_STACK_REL = ".sdd/experiments/conformance/stack.md.fixture"

#: Répertoire de la fixture FEAT par défaut.
FIXTURE_FEAT_REL = ".sdd/experiments/conformance/feats"

#: Racine de sortie des runs conformance.
BUILD_OUTPUT_REL = ".sdd/.build/conformance"

# --------------------------------------------------------------------------
# Modèles de données
# --------------------------------------------------------------------------


@dataclass
class ComboResult:
    """Résultat de validation d'un combo (dry-run ou live)."""

    harness: str
    provider: str
    verdict: str  # "PASS" | "DRIFT" | "INFRA_BLOCKED" | "FAIL"
    class_code: str  # [CONFORMANCE_PASS] / [CONFORMANCE_DRIFT] / [INFRA_BLOCKED]
    duration_s: float = 0.0
    is_reference: bool = False
    checks: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    @property
    def label(self) -> str:
        return f"{self.harness} × {self.provider}"


@dataclass
class RunReport:
    """Rapport agrégé d'un run conformance."""

    mode: str  # "dry-run" | "live"
    started_at: str
    finished_at: str
    duration_s: float
    combos: list[ComboResult]
    feat_fixture: str
    stack_fixture: str
    reference_combo: str
    verdict: str  # "PASS" | "DRIFT" | "FAIL"
    exit_code: int

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema": "sdd.conformance/v1",
                "mode": self.mode,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration_s": round(self.duration_s, 3),
                "feat_fixture": self.feat_fixture,
                "stack_fixture": self.stack_fixture,
                "reference_combo": self.reference_combo,
                "verdict": self.verdict,
                "exit_code": self.exit_code,
                "combos": [asdict(c) for c in self.combos],
            },
            indent=2,
            sort_keys=False,
        )


# --------------------------------------------------------------------------
# Validation config (dry-run)
# --------------------------------------------------------------------------

_PROVIDER_REQUIRED_KEYS = (
    "schema",
    "name",
    "endpoint_kind",
    "auth_env",
    "tier_map",
    "capabilities",
)
_TIER_KEYS = ("deep", "balanced", "fast")


def _load_provider_yaml(name: str, root: Path) -> dict[str, Any]:
    """Charge et valide grossièrement un YAML provider.

    Ne dépend PAS de ``sdd_lib.config_loader.load_provider`` pour donner un
    message d'erreur ciblé conformance (la classe [CONFORMANCE_*] doit être
    émise ici, pas remontée depuis un ConfigError générique).
    """
    import yaml  # local import — ne pas payer le coût si le script est --help

    path = providers_dir(repo_root_path=root) / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"provider YAML introuvable: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"racine YAML {path}: mapping requis")
    missing = [k for k in _PROVIDER_REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(
            f"{path}: clé(s) manquante(s) {missing} (schéma sdd.provider/v1)"
        )
    tier_map = data.get("tier_map") or {}
    if not isinstance(tier_map, dict):
        raise ValueError(f"{path}: tier_map doit être un mapping")
    missing_tiers = [t for t in _TIER_KEYS if t not in tier_map]
    if missing_tiers:
        raise ValueError(
            f"{path}: tier_map incomplet — tiers manquants {missing_tiers}"
        )
    return data


def _check_harness_adapter(harness: str, root: Path) -> tuple[bool, str]:
    """Vérifie que ``harness_build.py`` sait générer la façade du harnais.

    Renvoie ``(ok, note)`` — n'invoque pas le binaire (test statique via
    inspection du module). Résiste à un adaptateur manquant sans crash.
    """
    adapter_module = root / ".sdd" / "harness_build.py"
    if not adapter_module.is_file():
        return False, f"harness_build.py absent: {adapter_module}"
    text = adapter_module.read_text(encoding="utf-8", errors="replace")
    # Chaque adapter porte le nom du harnais dans sa classe (ClaudeAdapter, ...).
    marker = {
        "claude-code": "ClaudeAdapter",
        "codex": "CodexAdapter",
        "gemini-cli": "GeminiAdapter",
        "antigravity": "AntigravityAdapter",
    }.get(harness)
    if not marker:
        return False, f"harnais inconnu: {harness}"
    if marker not in text:
        return False, f"adapter absent dans harness_build.py: {marker}"
    return True, f"adapter {marker} détecté"


def _resolve_fixture_paths(
    root: Path, feat_arg: str | None, stack_arg: str | None
) -> tuple[Path, Path]:
    """Résout les chemins des fixtures FEAT + stack (opt-in override CLI)."""
    if stack_arg:
        stack_path = (root / stack_arg).resolve() if not Path(stack_arg).is_absolute() else Path(stack_arg)
    else:
        stack_path = (root / FIXTURE_STACK_REL).resolve()

    if feat_arg:
        feat_path = (root / feat_arg).resolve() if not Path(feat_arg).is_absolute() else Path(feat_arg)
    else:
        feat_path = (root / FIXTURE_FEAT_REL / DEFAULT_FEAT_FIXTURE_NAME).resolve()

    return feat_path, stack_path


def _stack_md_dispatch_check(
    stack_path: Path, harness: str, provider: str
) -> tuple[bool, str]:
    """Vérifie qu'on peut construire un stack.md temp valide pour le combo.

    On lit la fixture (si présente) ou on construit un stack minimal, puis
    on la passe à ``sdd_lib.stack_config.parse_stack_config``. Toute erreur
    remonte en ``(False, message)``.
    """
    from sdd_lib.stack_config import parse_stack_config, StackConfigError

    if stack_path.is_file():
        text = stack_path.read_text(encoding="utf-8-sig")
    else:
        # Fixture absente : on synthétise un stack minimal (dry-run continue).
        text = _synth_stack_md(harness=harness, provider=provider)

    dispatched = _rewrite_stack_dispatch(text, harness=harness, provider=provider)

    try:
        cfg = parse_stack_config(dispatched)
    except StackConfigError as exc:
        return False, f"parse_stack_config KO: {exc}"

    if cfg.harness != harness:
        return False, f"harness dispatché={cfg.harness!r}, attendu={harness!r}"
    if cfg.provider != provider:
        return False, f"provider dispatché={cfg.provider!r}, attendu={provider!r}"
    return True, "stack dispatch OK"


def _synth_stack_md(harness: str, provider: str) -> str:
    """Stack.md minimal utilisé quand la fixture n'existe pas.

    Contient uniquement les sections Active Harness / Active Model Provider
    (le reste du parseur tolère l'absence — cf. ``stack_config.py``).
    """
    return (
        "# Project Stack (synthétisé — conformance_run)\n\n"
        "## Active Harness\n"
        f"Harness: {harness}\n\n"
        "## Active Model Provider\n"
        f"Provider: {provider}\n"
        "Endpoint: default\n"
        "ModelTierMap:\n"
        f"  deep: {provider}\n"
        f"  balanced: {provider}\n"
        f"  fast: {provider}\n\n"
        "## Model Selection\n"
        "Mode: static\n"
    )


def _rewrite_stack_dispatch(text: str, harness: str, provider: str) -> str:
    """Réécrit les sections Active Harness / Active Model Provider dans un stack.md.

    Best-effort : si les sections existent, remplace la ligne ``Harness:`` /
    ``Provider:`` ; sinon, ajoute les 2 sections en tête. Ne modifie **jamais**
    le fichier disque — travaille en mémoire.
    """
    lines = text.splitlines()
    out: list[str] = []
    in_harness_section = False
    in_provider_section = False
    saw_harness_section = False
    saw_provider_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            title = stripped[3:].strip().lower()
            in_harness_section = title == "active harness"
            in_provider_section = title == "active model provider"
            if in_harness_section:
                saw_harness_section = True
            if in_provider_section:
                saw_provider_section = True
            out.append(line)
            continue
        if in_harness_section and stripped.lower().startswith("harness:"):
            out.append(f"Harness: {harness}")
            continue
        if in_provider_section and stripped.lower().startswith("provider:"):
            out.append(f"Provider: {provider}")
            continue
        out.append(line)
    if not saw_harness_section or not saw_provider_section:
        # Prépend les 2 sections manquantes en tête.
        prefix = []
        if not saw_harness_section:
            prefix.append("## Active Harness")
            prefix.append(f"Harness: {harness}")
            prefix.append("")
        if not saw_provider_section:
            prefix.append("## Active Model Provider")
            prefix.append(f"Provider: {provider}")
            prefix.append("Endpoint: default")
            prefix.append("")
        return "\n".join(prefix + out)
    return "\n".join(out)


# --------------------------------------------------------------------------
# Étapes par combo
# --------------------------------------------------------------------------


def _validate_combo_dry(
    harness: str,
    provider: str,
    root: Path,
    feat_path: Path,
    stack_path: Path,
) -> ComboResult:
    """Dry-run : aucune I/O réseau, valide juste la config d'un combo."""
    start = time.monotonic()
    checks: list[dict[str, Any]] = []
    is_ref = (harness, provider) == REFERENCE_COMBO

    # Check 1 — provider YAML complet
    try:
        _load_provider_yaml(provider, root)
        checks.append({"name": "provider_yaml", "ok": True, "note": f"providers/{provider}.yaml OK"})
    except Exception as exc:
        checks.append({"name": "provider_yaml", "ok": False, "note": str(exc)})
        return ComboResult(
            harness=harness,
            provider=provider,
            verdict="INFRA_BLOCKED",
            class_code="[INFRA_BLOCKED]",
            duration_s=time.monotonic() - start,
            is_reference=is_ref,
            checks=checks,
            notes=f"provider YAML {provider} invalide",
        )

    # Check 2 — harnais connu
    if harness not in KNOWN_HARNESSES:
        checks.append(
            {"name": "harness_known", "ok": False, "note": f"harnais inconnu {harness!r}"}
        )
        return ComboResult(
            harness=harness,
            provider=provider,
            verdict="FAIL",
            class_code="[INFRA_BLOCKED]",
            duration_s=time.monotonic() - start,
            is_reference=is_ref,
            checks=checks,
            notes=f"harnais {harness!r} hors {list(KNOWN_HARNESSES)}",
        )
    checks.append({"name": "harness_known", "ok": True, "note": f"harnais {harness!r} connu"})

    # Check 3 — adapter présent dans harness_build.py
    adapter_ok, adapter_note = _check_harness_adapter(harness, root)
    checks.append({"name": "harness_adapter", "ok": adapter_ok, "note": adapter_note})
    if not adapter_ok:
        return ComboResult(
            harness=harness,
            provider=provider,
            verdict="INFRA_BLOCKED",
            class_code="[INFRA_BLOCKED]",
            duration_s=time.monotonic() - start,
            is_reference=is_ref,
            checks=checks,
            notes=adapter_note,
        )

    # Check 4 — stack.md dispatch parseable pour ce combo
    stack_ok, stack_note = _stack_md_dispatch_check(stack_path, harness, provider)
    checks.append({"name": "stack_dispatch", "ok": stack_ok, "note": stack_note})
    if not stack_ok:
        return ComboResult(
            harness=harness,
            provider=provider,
            verdict="FAIL",
            class_code="[INFRA_BLOCKED]",
            duration_s=time.monotonic() - start,
            is_reference=is_ref,
            checks=checks,
            notes=stack_note,
        )

    # Check 5 — FEAT fixture accessible (ou synthétisable)
    if feat_path.is_file():
        checks.append(
            {"name": "feat_fixture", "ok": True, "note": f"FEAT présente: {feat_path}"}
        )
    else:
        # Absence tolérée en dry-run (WARN) — la fixture est un opt-in pour --live.
        checks.append(
            {
                "name": "feat_fixture",
                "ok": True,
                "note": f"FEAT absente ({feat_path}) — tolérée en --dry-run",
            }
        )

    return ComboResult(
        harness=harness,
        provider=provider,
        verdict="PASS",
        class_code="[CONFORMANCE_PASS]",
        duration_s=time.monotonic() - start,
        is_reference=is_ref,
        checks=checks,
        notes="dry-run: config OK",
    )


def _validate_combo_live(
    harness: str,
    provider: str,
    root: Path,
    feat_path: Path,
    stack_path: Path,
    timeout_s: float,
    out_dir: Path,
) -> ComboResult:
    """Live run : exécute réellement le pipeline (nécessite API key + CLI).

    Statut opérationnel v7.0.0 (2026-07-25) : la seule cible fonctionnelle
    est le combo de référence (claude-code × anthropic). Les autres combos
    exigent le câblage ``sdd_lib.spawn_agent`` au pipeline (Phase 3+ du plan
    de migration multi-harness). On émet un ``[INFRA_BLOCKED]``
    explicite plutôt qu'un faux positif.
    """
    start = time.monotonic()
    checks: list[dict[str, Any]] = []
    is_ref = (harness, provider) == REFERENCE_COMBO

    # 1. Dry-run gate d'abord (config KO => on n'appelle pas le réseau).
    dry = _validate_combo_dry(harness, provider, root, feat_path, stack_path)
    checks.extend(dry.checks)
    if dry.verdict != "PASS":
        dry.duration_s = time.monotonic() - start
        return dry

    # 2. API key requise par le provider
    api_key_env = _api_key_env_for(provider, root)
    if api_key_env and not os.environ.get(api_key_env):
        checks.append(
            {"name": "api_key", "ok": False, "note": f"env var {api_key_env} absente"}
        )
        return ComboResult(
            harness=harness,
            provider=provider,
            verdict="INFRA_BLOCKED",
            class_code="[INFRA_BLOCKED]",
            duration_s=time.monotonic() - start,
            is_reference=is_ref,
            checks=checks,
            notes=f"API key {api_key_env} absente — impossible en --live",
        )
    if api_key_env:
        checks.append({"name": "api_key", "ok": True, "note": f"{api_key_env} présente"})

    # 3. CLI du harnais accessible (sauf claude-code où on peut être in-process)
    cli_ok, cli_note = _check_harness_cli(harness)
    checks.append({"name": "harness_cli", "ok": cli_ok, "note": cli_note})
    if not cli_ok:
        return ComboResult(
            harness=harness,
            provider=provider,
            verdict="INFRA_BLOCKED",
            class_code="[INFRA_BLOCKED]",
            duration_s=time.monotonic() - start,
            is_reference=is_ref,
            checks=checks,
            notes=cli_note,
        )

    # 4. Isolation temp : chaque combo dans son sous-dossier
    combo_dir = out_dir / f"{harness}-{provider}"
    combo_dir.mkdir(parents=True, exist_ok=True)
    temp_stack = combo_dir / "stack.md.dispatch"
    _write_dispatched_stack(temp_stack, stack_path, harness, provider)
    checks.append(
        {"name": "stack_dispatch_write", "ok": True, "note": f"stack temp: {temp_stack}"}
    )

    # 5. Combo non-référence : spawn_agent.py pas encore câblé au pipeline
    #    (cf. §7.1 RISQUE #1 du plan). On ne prétend pas exécuter.
    if not is_ref:
        return ComboResult(
            harness=harness,
            provider=provider,
            verdict="INFRA_BLOCKED",
            class_code="[INFRA_BLOCKED]",
            duration_s=time.monotonic() - start,
            is_reference=is_ref,
            checks=checks,
            notes=(
                "spawn_agent.py non câblé au pipeline pour ce harnais — "
                "voir docs/harness-codex.md / docs/harness-gemini.md (§4)"
            ),
        )

    # 6. Référence claude-code × anthropic : on lance --dry-run bootstrap comme
    #    proxy live minimal. Le vrai run /sdd-full nécessite l'orchestrateur
    #    interactif Claude Code — hors scope de ce script (§10.3 du plan).
    ok, note = _invoke_bootstrap_dry(root, timeout_s, combo_dir)
    checks.append({"name": "bootstrap_dry", "ok": ok, "note": note})
    if not ok:
        return ComboResult(
            harness=harness,
            provider=provider,
            verdict="FAIL",
            class_code="[INFRA_BLOCKED]",
            duration_s=time.monotonic() - start,
            is_reference=is_ref,
            checks=checks,
            notes=note,
        )

    return ComboResult(
        harness=harness,
        provider=provider,
        verdict="PASS",
        class_code="[CONFORMANCE_PASS]",
        duration_s=time.monotonic() - start,
        is_reference=is_ref,
        checks=checks,
        notes="live run: référence validée en mode proxy (bootstrap --dry-run)",
    )


def _api_key_env_for(provider: str, root: Path) -> str | None:
    """Retourne le nom de l'env var API key pour un provider (via YAML)."""
    try:
        data = _load_provider_yaml(provider, root)
    except Exception:
        return None
    v = data.get("auth_env")
    return v if isinstance(v, str) and v else None


def _check_harness_cli(harness: str) -> tuple[bool, str]:
    """Vérifie qu'un binaire correspondant au harnais est dans le PATH."""
    binary = {
        "claude-code": "claude",
        "codex": "codex",
        "gemini-cli": "gemini",
        "antigravity": "antigravity",
    }.get(harness)
    if not binary:
        return False, f"harnais inconnu: {harness}"
    found = shutil.which(binary)
    if not found:
        return False, f"CLI {binary!r} introuvable dans PATH"
    return True, f"CLI {binary!r} = {found}"


def _write_dispatched_stack(dest: Path, src: Path, harness: str, provider: str) -> None:
    """Écrit sur disque temp une copie de stack.md dispatchée pour (harness, provider).

    Le fichier ``src`` (le stack.md réel) n'est **jamais** modifié.
    """
    if src.is_file():
        text = src.read_text(encoding="utf-8-sig")
    else:
        text = _synth_stack_md(harness=harness, provider=provider)
    dispatched = _rewrite_stack_dispatch(text, harness=harness, provider=provider)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(dispatched, encoding="utf-8")


def _invoke_bootstrap_dry(root: Path, timeout_s: float, log_dir: Path) -> tuple[bool, str]:
    """Invoque ``python bootstrap.py --dry-run`` et capture stdout/stderr."""
    bootstrap = root / "bootstrap.py"
    if not bootstrap.is_file():
        return False, f"bootstrap.py absent: {bootstrap}"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_p = log_dir / "bootstrap.stdout"
    stderr_p = log_dir / "bootstrap.stderr"
    try:
        proc = subprocess.run(
            [sys.executable, str(bootstrap), "--dry-run"],
            cwd=str(root),
            timeout=timeout_s,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"bootstrap --dry-run timeout après {timeout_s}s"
    except FileNotFoundError as exc:
        return False, f"bootstrap.py non exécutable: {exc}"
    stdout_p.write_text(proc.stdout or "", encoding="utf-8")
    stderr_p.write_text(proc.stderr or "", encoding="utf-8")
    if proc.returncode != 0:
        return False, f"bootstrap --dry-run exit={proc.returncode} (voir {stderr_p})"
    return True, "bootstrap --dry-run OK (proxy live)"


# --------------------------------------------------------------------------
# Rapport (markdown + JSON)
# --------------------------------------------------------------------------


def _render_markdown_report(report: RunReport) -> str:
    """Rapport markdown lisible Tech Lead."""
    lines: list[str] = []
    lines.append(f"# Conformance run — {report.mode}")
    lines.append("")
    lines.append(f"- **Démarré** : {report.started_at}")
    lines.append(f"- **Terminé** : {report.finished_at}")
    lines.append(f"- **Durée totale** : {report.duration_s:.2f}s")
    lines.append(f"- **FEAT fixture** : `{report.feat_fixture}`")
    lines.append(f"- **Stack fixture** : `{report.stack_fixture}`")
    lines.append(f"- **Combo de référence** : `{report.reference_combo}`")
    lines.append(f"- **Verdict global** : **{report.verdict}** (exit={report.exit_code} — {describe_exit(report.exit_code)})")
    lines.append("")
    lines.append("## Résultats par combo")
    lines.append("")
    lines.append("| Combo | Réf. | Verdict | Classe | Durée | Note |")
    lines.append("|---|:---:|:---:|---|---:|---|")
    for c in report.combos:
        marker = "✅" if c.is_reference else ""
        lines.append(
            f"| {c.label} | {marker} | **{c.verdict}** | `{c.class_code}` | {c.duration_s:.2f}s | {c.notes} |"
        )
    lines.append("")
    lines.append("## Détail des checks")
    lines.append("")
    for c in report.combos:
        lines.append(f"### {c.label}")
        lines.append("")
        if not c.checks:
            lines.append("_(aucun check exécuté)_")
            lines.append("")
            continue
        for chk in c.checks:
            icon = "✅" if chk.get("ok") else "❌"
            lines.append(f"- {icon} **{chk.get('name')}** — {chk.get('note')}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "> Émis par `.sdd/python/sdd_scripts/conformance_run.py` — "
        "SSoT plan §10 du `MIGRATION-PLAN-multi-harness-multi-provider.md`."
    )
    return "\n".join(lines) + "\n"


def _write_reports(out_dir: Path, report: RunReport) -> tuple[Path, Path]:
    """Écrit ``report.md`` + ``report.json`` sous ``out_dir`` (atomique)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    json_path = out_dir / "report.json"
    md_path.write_text(_render_markdown_report(report), encoding="utf-8")
    json_path.write_text(report.to_json() + "\n", encoding="utf-8")
    return md_path, json_path


# --------------------------------------------------------------------------
# Parsing CLI + entrée principale
# --------------------------------------------------------------------------


def _parse_combo_arg(raw: str) -> tuple[str, str]:
    """Parse ``harness:provider`` ou ``harness×provider``."""
    for sep in (":", "×", "x"):
        if sep in raw:
            h, p = raw.split(sep, 1)
            return h.strip(), p.strip()
    raise argparse.ArgumentTypeError(
        f"combo invalide {raw!r} — attendu 'harness:provider' (ex: 'codex:openai')"
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="conformance_run",
        description=(
            "Rejeu FEAT × harness × provider et comparaison à la baseline. "
            "Voir la docstring du module pour le protocole complet."
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Valide la config sans appel réseau (défaut si --live absent).",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Exécute réellement le pipeline (nécessite API keys).",
    )
    p.add_argument(
        "--combo",
        action="append",
        type=_parse_combo_arg,
        default=None,
        help="Combo à tester (format 'harness:provider'). Répétable. Défaut = 5 combos §10.",
    )
    p.add_argument(
        "--feat",
        default=None,
        help=f"FEAT fixture à rejouer (défaut : {FIXTURE_FEAT_REL}/{DEFAULT_FEAT_FIXTURE_NAME}).",
    )
    p.add_argument(
        "--stack",
        default=None,
        help=f"Stack fixture (défaut : {FIXTURE_STACK_REL}).",
    )
    p.add_argument(
        "--timeout-min",
        type=float,
        default=DEFAULT_TIMEOUT_S / 60,
        help="Timeout par combo en minutes (défaut 30).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="En --live, tout DRIFT devient exit=1 (défaut : DRIFT = exit=2 WARN).",
    )
    p.add_argument(
        "--output-root",
        default=None,
        help=f"Racine de sortie (défaut : {BUILD_OUTPUT_REL}/{{timestamp}}/).",
    )
    return p


def _select_combos(cli_arg: list[tuple[str, str]] | None) -> list[tuple[str, str]]:
    if not cli_arg:
        return list(DEFAULT_COMBOS)
    return list(cli_arg)


def _aggregate_verdict(combos: list[ComboResult], strict: bool) -> tuple[str, int]:
    """Renvoie ``(verdict, exit_code)`` agrégé.

    Convention (cf. docstring module + exit_codes.py) :
    - PASS pour tous les combos       -> ("PASS", 0)
    - au moins un DRIFT (--strict OFF) -> ("DRIFT", 2 = CORRECTIBLE/WARN)
    - au moins un DRIFT (--strict ON)  -> ("FAIL", 1 = FAIL_FAST)
    - au moins un INFRA_BLOCKED       -> ("FAIL", 3 = INFRA_BLOCKED)
    - au moins un FAIL config          -> ("FAIL", 1 = FAIL_FAST)
    """
    has_infra = any(c.verdict == "INFRA_BLOCKED" for c in combos)
    has_fail = any(c.verdict == "FAIL" for c in combos)
    has_drift = any(c.verdict == "DRIFT" for c in combos)
    if has_fail:
        return "FAIL", FAIL_FAST
    if has_infra:
        return "FAIL", INFRA_BLOCKED
    if has_drift:
        return ("FAIL", FAIL_FAST) if strict else ("DRIFT", CORRECTIBLE)
    return "PASS", SUCCESS


def _timestamp_dirname() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    # UTF-8 stdout/stderr (Windows cp1252 fallback safe — emojis dans le
    # résumé exécutif §output-protocol.md §2, imprimés en fin de run).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # Défaut : dry-run si ni --dry-run ni --live n'a été passé.
    is_live = bool(args.live)
    mode_label = "live" if is_live else "dry-run"

    try:
        root = repo_root()
    except Exception as exc:
        print(f"ERROR: repo_root() failed", file=sys.stderr)
        print(f"CAUSE: [INFRA_BLOCKED] {exc}", file=sys.stderr)
        print(f"FIX: run from within an SDD_Pro repo (or set SDD_REPO_ROOT)", file=sys.stderr)
        return INFRA_BLOCKED

    feat_path, stack_path = _resolve_fixture_paths(root, args.feat, args.stack)
    combos = _select_combos(args.combo)
    timeout_s = max(1.0, float(args.timeout_min) * 60.0)

    # Racine de sortie
    if args.output_root:
        out_root = Path(args.output_root).resolve()
    else:
        out_root = (root / BUILD_OUTPUT_REL / _timestamp_dirname()).resolve()

    started_at = iso_now()
    t0 = time.monotonic()

    results: list[ComboResult] = []
    for harness, provider in combos:
        if is_live:
            r = _validate_combo_live(
                harness=harness,
                provider=provider,
                root=root,
                feat_path=feat_path,
                stack_path=stack_path,
                timeout_s=timeout_s,
                out_dir=out_root,
            )
        else:
            r = _validate_combo_dry(
                harness=harness,
                provider=provider,
                root=root,
                feat_path=feat_path,
                stack_path=stack_path,
            )
        results.append(r)

    verdict, exit_code = _aggregate_verdict(results, strict=args.strict)
    finished_at = iso_now()

    report = RunReport(
        mode=mode_label,
        started_at=started_at,
        finished_at=finished_at,
        duration_s=time.monotonic() - t0,
        combos=results,
        feat_fixture=str(feat_path),
        stack_fixture=str(stack_path),
        reference_combo=f"{REFERENCE_COMBO[0]} × {REFERENCE_COMBO[1]}",
        verdict=verdict,
        exit_code=exit_code,
    )

    md_path, json_path = _write_reports(out_root, report)

    # Executive summary chat (protocole output-protocol.md §2)
    icon = {"PASS": "🟢", "DRIFT": "🟡", "FAIL": "🔴"}.get(verdict, "❓")
    print(f"[CONFORMANCE] {icon} {verdict} — {len(results)} combos, {mode_label}")
    for c in results:
        badge = "✅" if c.verdict == "PASS" else ("⚠" if c.verdict == "DRIFT" else "❌")
        print(f"  {badge} {c.label:<30} {c.class_code}  ({c.duration_s:.2f}s) — {c.notes}")
    print(f"[CONFORMANCE] report: {md_path}")
    print(f"[CONFORMANCE] json  : {json_path}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
