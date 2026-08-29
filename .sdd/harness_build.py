#!/usr/bin/env python3
"""harness_build — transpileur foyer neutre `.sdd/` -> couche de contrôle harness.

Phase 2, MODE IDENTITÉ (plan MIGRATION-PLAN-multi-harness-multi-provider) :
prouve que le pivot neutre `.sdd/agents/*.agent.yaml` + le corps markdown
d'origine (`body_source`, lecture seule sur `.claude/agents/*.md`) suffisent
à RÉGÉNÉRER fidèlement la couche AGENTS de Claude Code.

Invariants de sécurité (non négociables) :
- N'ÉCRIT JAMAIS sous `.claude/` — sortie confinée à `.sdd/.build/` ;
- lecture seule sur `.claude/**` (le `body_source` n'est jamais modifié) ;
- ne fait RIEN à l'import (aucune I/O, aucun side effect disque) ;
- aucun réseau, aucun binaire externe.

CLI :
    python .sdd/harness_build.py --harness claude-code --agents-only \
        --out .sdd/.build/claude
    python .sdd/harness_build.py --harness claude-code --commands-only \
        --out .sdd/.build/claude
    # les flags sont combinables (agents + commandes + mémoire en un run)
    python .sdd/harness_build.py --harness claude-code --memory-only \
        --out .sdd/.build/claude          # -> CLAUDE.md (round-trip identité)
    python .sdd/harness_build.py --harness codex --memory-only \
        --out .sdd/.build/codex           # -> AGENTS.md (variante neutre)
    python .sdd/harness_build.py --harness gemini-cli --memory-only \
        --out .sdd/.build/gemini          # -> GEMINI.md (variante Gemini CLI)
    # --stack dérive harnais + provider depuis un stack.md (Tech Lead) ;
    # --harness / --provider explicites priment. Rétro-compat : sans --stack,
    # comportement inchangé (--harness requis, provider défaut anthropic).
    python .sdd/harness_build.py --stack workspace/stack/stack.md --memory-only \
        --out .sdd/.build/claude

Sorties : `{out}/agents/{name}.md` (miroir de `.claude/agents/{name}.md`)
et `{out}/commands/{name}.md` (miroir de `.claude/commands/{name}.md`,
pivots `.sdd/commands/*.cmd.yaml`).
La vérification du round-trip sémantique est portée par
`.sdd/python/tests/test_harness_identity.py` (agents) et
`.sdd/python/tests/test_harness_identity_commands.py` (commandes)
via `sdd_lib.harness_diff`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

_SDD_HOME = Path(__file__).resolve().parent          # .sdd/
_REPO_ROOT = _SDD_HOME.parent                        # racine repo
_BUILD_DIRNAME = ".build"

# sdd_lib vit sous .sdd/python/ — insertion de path pure (pas d'I/O).
_PYTHON_DIR = str(_SDD_HOME / "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

from sdd_lib.config_loader import (  # noqa: E402
    ConfigError,
    get_provider_tier_map,
    load_provider,
    load_yaml,
)
from sdd_lib.harness_diff import FrontmatterError, parse_frontmatter  # noqa: E402
from sdd_lib.impact_report import build_impact_report, untested_gate_ok  # noqa: E402
from sdd_lib.stack_config import StackConfigError, load_stack_config  # noqa: E402

__all__ = [
    "Adapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "GeminiAdapter",
    "AntigravityAdapter",
    "EmitResult",
    "BuildSafetyError",
    "main",
]



class BuildSafetyError(RuntimeError):
    """Violation d'un invariant de sécurité (sortie hors `.sdd/.build/`)."""


@dataclass(frozen=True)
class EmitResult:
    """Résultat d'émission pour UN agent (écrit ou skip motivé)."""

    agent: str
    written: Path | None  # None si skip
    skipped_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.written is not None


def _ensure_under_build(out_dir: Path, sdd_home: Path) -> Path:
    """Garde-fou : la sortie DOIT être sous `{sdd_home}/.build/`."""
    resolved = out_dir.resolve()
    build_root = (sdd_home / _BUILD_DIRNAME).resolve()
    try:
        resolved.relative_to(build_root)
    except ValueError:
        raise BuildSafetyError(
            f"sortie interdite: {resolved} — le mode identité n'écrit que sous "
            f"{build_root} (jamais .claude/, jamais hors .sdd/)"
        ) from None
    return resolved


def compose_frontmatter(fields: dict[str, str]) -> str:
    """Recompose le frontmatter Claude Code (ordre canonique name/desc/model/tools)."""
    lines = ["---"]
    for key in ("name", "description", "model", "tools"):
        lines.append(f"{key}: {fields[key]}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def compose_command_frontmatter(fields: dict[str, object]) -> str:
    """Recompose le frontmatter d'une COMMANDE dans l'ordre du pivot.

    Les valeurs sont émises RAW (telles que stockées dans le pivot,
    guillemets inclus — ex. `phase: "0-5"`), ce qui reproduit la forme
    exacte attendue par le parser loose de Claude Code / harness_diff.
    """
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _normalize_body_text(text: str) -> str:
    """BOM retiré + fins de ligne CRLF/CR normalisées en LF (miroir harness_diff)."""
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def _split_optional_frontmatter(text: str) -> tuple[dict | None, str]:
    """Sépare (frontmatter, corps). Frontmatter Claude-spécifique retiré côté
    Codex/Gemini (la description vient du pivot). Corps pur si aucun frontmatter."""
    try:
        fields, body = parse_frontmatter(text)
        return fields, body
    except FrontmatterError:
        return None, text


#: Tools spéciaux natifs Claude Code uniquement — absents des runtimes Codex
#: et Gemini CLI. Un agent qui les référence sous ces harnais lèverait
#: `ToolNotFoundError` au runtime. Le pivot `.sdd/agents/*.md` les liste
#: parce que le harnais historique était Claude ; l'émission MemoryVariant
#: (Codex/Gemini, future Phase 3+) les filtre via `_filter_tools_for_harness`.
#:
#: SSoT décisionnelle : le pivot `.sdd/agents/*.md` reste Claude-annoté ;
#: la traduction se fait à l'émission par harnais. Étendre au besoin
#: (`WebSearch`, `WebFetch`, `NotebookEdit`, `ExitPlanMode`, `TodoWrite`
#: sont aussi Claude-Code-only mais non utilisés par les 29 pivots SDD).
_CLAUDE_ONLY_TOOLS = frozenset({"Skill", "AskUserQuestion"})


class Adapter(ABC):
    """Interface d'un adaptateur harness (cible d'émission du transpileur)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifiant du harness cible (ex. 'claude-code')."""

    def _filter_tools_for_harness(self, tools: list[str]) -> list[str]:
        """Filtre les tools Claude-Code-only pour un harnais non-Claude.

        Défaut (base class) : ne filtre rien — override en sous-classe non-Claude.
        Utilisé par `ClaudeAdapter._emit_one` (no-op, garde tout) et par les
        futurs `_MemoryVariantAdapter.emit_agents` (Phase 3+) qui filtreront.
        Anti-régression : un agent qui référence `Skill` sous Codex/Gemini
        lèverait `ToolNotFoundError` au spawn.
        """
        return list(tools)

    @abstractmethod
    def emit_agents(self, out_dir: Path) -> list[EmitResult]:
        """Régénère la couche agents du harness sous `out_dir`."""

    @abstractmethod
    def emit_commands(self, out_dir: Path) -> list[EmitResult]:
        """Régénère la couche commandes du harness sous `out_dir`."""

    @abstractmethod
    def emit_memory_file(self, out_dir: Path) -> Path:
        """Régénère le fichier mémoire du harness (CLAUDE.md, etc.)."""

    @abstractmethod
    def emit_rules(self, out_dir: Path) -> list[EmitResult]:
        """Régénère la couche rules du harness sous `out_dir`."""


class ClaudeAdapter(Adapter):
    """Adaptateur Claude Code — mode identité (couches AGENTS + COMMANDES).

    Pour chaque pivot `.sdd/agents/{name}.agent.yaml` :
    1. résout `model_tier` -> `model:` concret via la `tier_map` de
       `providers/{provider}.yaml` (deep -> claude-opus-4-8,
       balanced -> claude-sonnet-4-6, fast -> claude-haiku-4-5) ;
    2. recompose le frontmatter Claude Code {name, description, model, tools} ;
    3. RÉATTACHE le corps markdown lu depuis `body_source` (le
       `.claude/agents/{name}.md` d'origine — lecture seule) ;
    4. écrit `{out_dir}/agents/{name}.md` (LF, UTF-8 sans BOM).
    """

    def __init__(self, repo_root: Path | None = None, provider: str = "anthropic") -> None:
        self._repo_root = (repo_root or _REPO_ROOT).resolve()
        self._sdd_home = self._repo_root / ".sdd"
        self._provider = provider

    @property
    def name(self) -> str:
        return "claude-code"

    def _tier_map(self) -> dict[str, str]:
        # env={} force la résolution par base (ignore un SDD_HOME ambiant).
        return get_provider_tier_map(self._provider, env={}, base=self._repo_root)

    def _pivot_paths(self) -> list[Path]:
        # Consolidation 2026-07-25 : un seul fichier .md par agent (frontmatter enrichi
        # + body), remplace le couple .agent.yaml + .body.md.
        return sorted((self._sdd_home / "agents").glob("*.md"))

    def _emit_one(self, pivot_path: Path, agents_out: Path, tier_map: dict[str, str]) -> EmitResult:
        # Format consolidé : pivot ET body dans un seul .md ; parse frontmatter direct.
        agent = pivot_path.stem
        try:
            fields, body = parse_frontmatter(pivot_path.read_text(encoding="utf-8-sig"))
        except FrontmatterError as exc:
            return EmitResult(agent, None, f"frontmatter illisible: {exc}")

        # Convertit dict-of-strings potentiellement RAW en pivot exploitable.
        pivot: dict[str, object] = dict(fields)
        # Normalisation `tools` : accepte liste YAML `[a, b]`, virgules `a, b`.
        tools_raw = pivot.get("tools", "")
        if isinstance(tools_raw, str):
            tools_str = tools_raw.strip().lstrip("[").rstrip("]")
            tools_list = [t.strip() for t in tools_str.split(",") if t.strip()]
        else:
            tools_list = [str(t).strip() for t in (tools_raw or []) if str(t).strip()]

        for key in ("name", "description", "model_tier"):
            if key not in pivot:
                return EmitResult(agent, None, f"pivot incomplet: clé '{key}' absente")

        model = tier_map.get(str(pivot["model_tier"]))
        if model is None:
            return EmitResult(
                agent, None,
                f"model_tier {pivot['model_tier']!r} absent de la tier_map "
                f"du provider {self._provider!r}",
            )

        # Filtre les tools selon les capabilities du harnais (audit R9 2026-07-26).
        # Claude-code garde tout ; Codex/Gemini (Phase 3+) filtrent Skill/AskUserQuestion.
        tools_list = self._filter_tools_for_harness(tools_list)
        tools_line = ", ".join(tools_list) if tools_list else ""
        frontmatter = compose_frontmatter(
            {
                "name": pivot["name"],
                "description": " ".join(str(pivot["description"]).split("\n")),
                "model": model,
                "tools": tools_line,
            }
        )
        target = agents_out / f"{agent}.md"
        target.write_text(frontmatter + body, encoding="utf-8", newline="\n")
        return EmitResult(agent, target)

    def emit_agents(self, out_dir: Path, only: set[str] | None = None) -> list[EmitResult]:
        """Émet les agents (tous, ou restreints à `only`) sous `{out_dir}/agents/`."""
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        agents_out = safe_out / "agents"
        agents_out.mkdir(parents=True, exist_ok=True)
        tier_map = self._tier_map()
        results: list[EmitResult] = []
        for pivot_path in self._pivot_paths():
            agent = pivot_path.stem
            if only is not None and agent not in only:
                continue
            try:
                results.append(self._emit_one(pivot_path, agents_out, tier_map))
            except ConfigError as exc:
                results.append(EmitResult(agent, None, f"pivot illisible: {exc}"))
        return results

    # ------------------------------------------------------------------ #
    # Couche COMMANDES (mode identité — pivots .sdd/commands/*.md consolidés) #
    # ------------------------------------------------------------------ #

    def _command_pivot_paths(self) -> list[Path]:
        return sorted((self._sdd_home / "commands").glob("*.md"))

    def _emit_one_command(self, pivot_path: Path, commands_out: Path) -> EmitResult:
        # Format consolidé 2026-07-25 : un seul fichier .md par commande. Le
        # frontmatter (name, description, spawns, ...) est optionnel ; s'il
        # est présent, il est réémis pour Claude Code. Sinon corps pur.
        name = pivot_path.stem
        source_text = pivot_path.read_text(encoding="utf-8-sig")
        try:
            fields, body = parse_frontmatter(source_text)
        except FrontmatterError:
            fields, body = {}, source_text

        if fields:
            # Émet le frontmatter conservé (name, description, éventuel argument-hint).
            emit_fields: dict[str, str] = {}
            for key in ("name", "description", "argument-hint"):
                if key in fields:
                    emit_fields[key] = str(fields[key])
            content = compose_command_frontmatter(emit_fields) + body if emit_fields else _normalize_body_text(body)
        else:
            content = _normalize_body_text(body)

        target = commands_out / f"{name}.md"
        target.write_text(content, encoding="utf-8", newline="\n")
        return EmitResult(name, target)

    def emit_commands(self, out_dir: Path, only: set[str] | None = None) -> list[EmitResult]:
        """Émet les commandes (toutes, ou restreintes à `only`) sous `{out_dir}/commands/`."""
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        commands_out = safe_out / "commands"
        commands_out.mkdir(parents=True, exist_ok=True)
        results: list[EmitResult] = []
        for pivot_path in self._command_pivot_paths():
            name = pivot_path.stem
            if only is not None and name not in only:
                continue
            try:
                results.append(self._emit_one_command(pivot_path, commands_out))
            except ConfigError as exc:
                results.append(EmitResult(name, None, f"pivot illisible: {exc}"))
        return results

    # ------------------------------------------------------------------ #
    # Couche FICHIERS-MÉMOIRE (pivot .sdd/entrypoint.md)                 #
    # ------------------------------------------------------------------ #

    def emit_memory_file(self, out_dir: Path) -> Path:
        """Régénère `CLAUDE.md` sous `out_dir` (round-trip identité).

        Corps lu VERBATIM depuis le `body_source` du pivot
        `.sdd/entrypoint.md` (le `.claude/CLAUDE.md` vivant — lecture
        seule), seule la normalisation CRLF/BOM est appliquée.
        """
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        body = _read_memory_body(self._repo_root, self._sdd_home)
        safe_out.mkdir(parents=True, exist_ok=True)
        target = safe_out / "CLAUDE.md"
        target.write_text(body, encoding="utf-8", newline="\n")
        return target

    # ------------------------------------------------------------------ #
    # Couche RULES (mode identité — manifest .sdd/rules-manifest.yaml)   #
    # ------------------------------------------------------------------ #

    def _rules_manifest(self) -> list[dict]:
        return _load_rules_manifest(self._sdd_home)

    def emit_rules(self, out_dir: Path, only: set[str] | None = None) -> list[EmitResult]:
        """Régénère les rules (toutes, ou restreintes à `only`) sous `{out_dir}/rules/`.

        Mode IDENTITÉ : chaque rule est du markdown pur ; le corps est lu
        VERBATIM depuis `body_source` (le `.sdd/rules/{name}.md` vivant —
        lecture seule) puis normalisé (BOM retiré, CRLF/CR -> LF). Le golden
        test byte-diffe le résultat contre le vivant (post-normalisation).
        """
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        rules_out = safe_out / "rules"
        rules_out.mkdir(parents=True, exist_ok=True)
        results: list[EmitResult] = []
        for entry in self._rules_manifest():
            name = str(entry.get("name") or "")
            if not name:
                results.append(EmitResult("<sans-nom>", None, "entrée manifest sans 'name'"))
                continue
            if only is not None and name not in only:
                continue
            body_source = entry.get("body_source")
            if not body_source:
                results.append(EmitResult(name, None, "entrée manifest sans 'body_source'"))
                continue
            body_path = (self._repo_root / body_source).resolve()
            if not body_path.is_file():
                results.append(EmitResult(name, None, f"body_source introuvable: {body_path}"))
                continue
            content = _normalize_body_text(body_path.read_text(encoding="utf-8-sig"))
            target = rules_out / f"{name}.md"
            target.write_text(content, encoding="utf-8", newline="\n")
            results.append(EmitResult(name, target))
        return results


def _load_rules_manifest(sdd_home: Path) -> list[dict]:
    """Charge la liste des rules depuis `.sdd/rules-manifest.yaml`."""
    manifest_path = sdd_home / "rules-manifest.yaml"
    if not manifest_path.is_file():
        raise ConfigError(f"manifest rules introuvable: {manifest_path}")
    data = load_yaml(manifest_path)
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ConfigError(f"manifest rules vide ou malformé: {manifest_path}")
    return rules


def _read_memory_body(repo_root: Path, sdd_home: Path) -> str:
    """Lit le corps du fichier-mémoire via le pivot `.sdd/entrypoint.md`.

    Le pivot porte un frontmatter `body_source:` (même patron que les
    pivots agents/commandes) ; le corps N'EST PAS recopié dans le pivot,
    il est lu depuis la source vivante (lecture seule) puis normalisé
    (BOM retiré, CRLF/CR -> LF).
    """
    pivot_path = sdd_home / "entrypoint.md"
    if not pivot_path.is_file():
        raise ConfigError(f"pivot mémoire introuvable: {pivot_path}")
    try:
        fields, _pivot_body = parse_frontmatter(pivot_path.read_text(encoding="utf-8-sig"))
    except FrontmatterError as exc:
        raise ConfigError(f"pivot mémoire sans frontmatter exploitable: {exc}") from exc
    body_source = fields.get("body_source")
    if not body_source:
        raise ConfigError(f"pivot mémoire sans clé 'body_source': {pivot_path}")
    body_path = (repo_root / body_source).resolve()
    if not body_path.is_file():
        raise ConfigError(f"body_source mémoire introuvable: {body_path}")
    return _normalize_body_text(body_path.read_text(encoding="utf-8-sig"))


class _MemoryVariantAdapter(Adapter):
    """Base des adaptateurs non-Claude (Codex, Gemini CLI).

    Émet :
    - le fichier-mémoire (`AGENTS.md` / `GEMINI.md`) — corps métier de
      `.claude/CLAUDE.md`, refs `@.claude/...` réécrites `.sdd/...`,
      en-tête `GENERATED` + note protection (capability-matrix.yml) ;
    - la couche COMMANDES (slash-commands transpilées) — `.codex/prompts/*.md`
      (custom prompts) ou `.gemini/commands/*.toml` (commandes natives), + le
      fichier de config du harnais (config.toml / settings.json) dérivé du
      provider actif (`providers/{provider}.yaml`).

    La couche AGENTS n'a PAS d'équivalent fichier sous ces harnais (les
    sous-agents SDD sont émulés au runtime par le wrapper `spawn_agent.py`,
    Phase 3+) → `emit_agents` reste `NotImplementedError`. La couche RULES
    (path-scoped natif Claude) est repliée par inline universel + pointeurs
    (hors périmètre de ce build) → `emit_rules` reste `NotImplementedError`.

    Honnêteté : les fichiers de config portent des IDs/endpoints « à valider »
    (cf. providers/*.yaml) et sont écrits SOUS `.sdd/.build/` (jamais installés).
    """

    #: clé du harnais dans capability-matrix.yml (à définir en sous-classe)
    matrix_key: str = ""
    #: nom du fichier mémoire émis (à définir en sous-classe)
    memory_filename: str = ""
    #: sous-dossier des commandes transpilées (ex. "prompts" / "commands")
    commands_subdir: str = ""
    #: extension des fichiers commande (ex. ".md" / ".toml")
    command_ext: str = ""

    def __init__(self, repo_root: Path | None = None, provider: str = "anthropic") -> None:
        self._repo_root = (repo_root or _REPO_ROOT).resolve()
        self._sdd_home = self._repo_root / ".sdd"
        # provider conservé pour parité d'interface avec ClaudeAdapter (le
        # fichier mémoire ne dépend pas du provider ; utile au rapport d'impact
        # et à l'émission du fichier de config du harnais).
        self._provider = provider

    @property
    def name(self) -> str:
        return self.matrix_key

    def _filter_tools_for_harness(self, tools: list[str]) -> list[str]:
        """Retire les tools Claude-Code-only (Skill, AskUserQuestion) pour
        les harnais non-Claude (Codex, Gemini CLI). Émission agents Phase 3+."""
        return [t for t in tools if t not in _CLAUDE_ONLY_TOOLS]

    def emit_agents(self, out_dir: Path) -> list[EmitResult]:
        raise NotImplementedError(
            f"emit_agents: pas de couche agents-fichier pour {self.name!r} "
            "(sous-agents émulés au runtime par spawn_agent.py, Phase 3+)"
        )

    def emit_rules(self, out_dir: Path) -> list[EmitResult]:
        raise NotImplementedError(
            f"emit_rules: couche rules non transpilée pour {self.name!r} "
            "(pas de mécanisme path-scoped — inline universelles + pointeurs, "
            "cf. rules-manifest.yaml harness_mapping)"
        )

    # ------------------------------------------------------------------ #
    # Couche COMMANDES (slash-commands transpilées + config harnais)      #
    # ------------------------------------------------------------------ #

    def _command_pivots(self) -> list[Path]:
        # Format consolidé 2026-07-25 : un seul fichier `.md` par commande sous
        # `.sdd/commands/`. Aligné avec `ClaudeAdapter._command_pivot_paths()`.
        return sorted((self._sdd_home / "commands").glob("*.md"))

    def _load_command(self, pivot_path: Path) -> tuple[str, str, str]:
        """(name, description, body) — body normalisé + @-includes réécrits."""
        source_text = pivot_path.read_text(encoding="utf-8-sig")
        fields, body = _split_optional_frontmatter(source_text)
        fields = fields or {}
        name = str(fields.get("name") or pivot_path.stem)
        description = " ".join(str(fields.get("description") or name).split("\n")).strip()
        return name, description, self._rewrite_at_includes(_normalize_body_text(body))

    def _render_command(self, name: str, description: str, body: str) -> str:
        """Rend le contenu du fichier commande pour le harnais (à surcharger)."""
        raise NotImplementedError

    def emit_commands(self, out_dir: Path) -> list[EmitResult]:
        """Émet les 40 commandes transpilées + le fichier de config du harnais."""
        if not self.commands_subdir or not self.command_ext:
            raise NotImplementedError(
                f"couche commandes non configurée pour {self.name!r}"
            )
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        cmd_out = safe_out / self.commands_subdir
        cmd_out.mkdir(parents=True, exist_ok=True)
        results: list[EmitResult] = []
        for pivot_path in self._command_pivots():
            name = pivot_path.stem
            try:
                cmd_name, description, body = self._load_command(pivot_path)
                content = self._render_command(cmd_name, description, body)
                target = cmd_out / f"{cmd_name}{self.command_ext}"
                target.write_text(content, encoding="utf-8", newline="\n")
                results.append(EmitResult(cmd_name, target))
            except ConfigError as exc:
                results.append(EmitResult(name, None, f"commande illisible: {exc}"))
        # Fichier de config du harnais (provider actif) — best-effort motivé.
        try:
            self.emit_config(safe_out)
        except ConfigError as exc:
            results.append(EmitResult(f"<config:{self.name}>", None, str(exc)))
        return results

    def emit_config(self, out_dir: Path) -> Path:
        """Émet le fichier de config du harnais (à surcharger)."""
        raise NotImplementedError

    def _provider_descriptor(self) -> dict:
        """Descripteur providers/{provider}.yaml (fail-explicit)."""
        return load_provider(self._provider, env={}, base=self._repo_root)

    def _capability_note(self) -> str:
        """Note de protection depuis capability-matrix.yml (fail-explicit)."""
        matrix = load_yaml(self._sdd_home / "capability-matrix.yml")
        harness = (matrix.get("harnesses") or {}).get(self.matrix_key)
        if not isinstance(harness, dict):
            raise ConfigError(
                f"harnais {self.matrix_key!r} absent de .sdd/capability-matrix.yml"
            )
        level = harness.get("protection_level", "?")
        at_include = (harness.get("mechanisms") or {}).get("at_include", "?")
        return (
            f"<!-- Harness: {self.matrix_key} — protection_level: {level} "
            f"(.sdd/capability-matrix.yml). at_include: {at_include} — pas de "
            "lazy-load @file en memoire : les refs @-includes du corps sont "
            "reecrites vers .sdd/... ; les charger explicitement (Read) avant usage. -->"
        )

    def _rewrite_at_includes(self, body: str) -> str:
        """Réécrit les refs lazy-load `@.claude/...` et `@.sdd/...` du corps.

        Le `@` est la syntaxe lazy-load de Claude Code, sans sens pour
        Codex/Gemini : on le retire toujours. La cible dépend de ce qui est
        RÉELLEMENT matérialisé sous `.sdd/` :

        - si `.sdd/<path>` existe → `@.claude/<path>` OU `@.sdd/<path>` -> `.sdd/<path>` ;
        - pour les refs brace-expansion (`{a,b}.md`) qui échouent au test
          d'existence, on expanse et on vérifie au moins un membre — si au
          moins un fichier réel matche sous `.sdd/`, cible `.sdd/` ;
        - sinon fallback `.sdd/<path>` (le foyer neutre est la SSoT ; le
          répertoire `.claude/` peut ne pas exister sous Codex/Gemini).

        Les mentions littérales `.claude/...` SANS `@` (chemins descriptifs
        d'invocation Python) sont conservées telles quelles.
        """
        def _any_brace_member_exists(rel: str) -> bool:
            """Vrai si `rel` contient `{a,b}` et qu'au moins une expansion
            matche un fichier réel sous `.sdd/`."""
            if "{" not in rel or "}" not in rel:
                return False
            prefix, rest = rel.split("{", 1)
            group, suffix = rest.split("}", 1)
            for member in group.split(","):
                if (self._sdd_home / f"{prefix}{member.strip()}{suffix}").exists():
                    return True
            return False

        def _repl(m: "re.Match[str]") -> str:
            rel = m.group(1)
            if (self._sdd_home / rel).exists() or _any_brace_member_exists(rel):
                return f".sdd/{rel}"
            # Foyer neutre est SSoT — jamais de fallback `.claude/` (ce
            # répertoire n'existe pas forcément sous Codex/Gemini).
            return f".sdd/{rel}"

        # Token de chemin : caractères usuels de chemin + accolades/virgules
        # pour les refs brace-expansion (`{a,b}.md`).
        rewritten = re.sub(r"@\.claude/([A-Za-z0-9_./{},-]+)", _repl, body)
        # Idem pour `@.sdd/...` (le `@` doit toujours être retiré).
        rewritten = re.sub(r"@\.sdd/([A-Za-z0-9_./{},-]+)", _repl, rewritten)
        # `@.claude` / `@.sdd` nus (sans slash) — dégrade en littéral `.sdd`.
        return rewritten.replace("@.claude", ".sdd").replace("@.sdd", ".sdd")

    def emit_memory_file(self, out_dir: Path) -> Path:
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        body = _read_memory_body(self._repo_root, self._sdd_home)
        content = (
            "# GENERATED FROM .sdd/ — DO NOT EDIT\n\n"
            + self._capability_note()
            + "\n\n"
            + self._rewrite_at_includes(body)
        )
        safe_out.mkdir(parents=True, exist_ok=True)
        target = safe_out / self.memory_filename
        target.write_text(content, encoding="utf-8", newline="\n")
        return target


def _escape_codex_positionals(text: str) -> str:
    """Échappe les ``$1``..``$9`` littéraux du corps pour Codex.

    Codex substitue ``$1``..``$9`` (positionnels) et ``$ARGUMENTS`` dans les
    custom prompts ; littéral ``$`` = ``$$`` (doc OpenAI). Les corps SDD
    contiennent des ``$`` incidents — champs awk (``$2``, ``$5``), caps de coût
    (``$50``, ``$15``) — jamais des positionnels voulus (les args SDD passent
    par le ``$ARGUMENTS`` injecté en tête). Sans échappement, ``awk '{print $2}'``
    devient ``awk '{print }'`` et ``$50`` devient ``0`` à l'exécution Codex.

    On ne touche QUE ``$`` suivi d'un chiffre 1-9 : ``$ARGUMENTS`` (injecté),
    ``$0``, ``${VAR}``, ``$NF``, ``$env:`` et ``$PORT`` ne matchent pas et
    restent intacts. Lookbehind ``(?<!\\$)`` pour ne pas doubler un ``$$``
    préexistant. Spécifique Codex — Gemini utilise ``{{args}}``, ``$N`` y est
    déjà littéral.
    """
    return re.sub(r"(?<!\$)\$(?=[1-9])", "$$", text)


def _toml_basic_string(value: str) -> str:
    """Chaîne TOML basic mono-ligne échappée (`"..."`)."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _toml_multiline_string(value: str) -> str:
    """Chaîne TOML basic multi-ligne (`\"\"\"..."\"\"`), backslash + délimiteur échappés."""
    escaped = value.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return '"""\n' + escaped + '\n"""'


class CodexAdapter(_MemoryVariantAdapter):
    """Adaptateur Codex — `AGENTS.md` + prompts `.codex/prompts/*.md` + config.toml.

    Les slash-commands SDD deviennent des *custom prompts* Codex (markdown,
    invoqués `/{name}`, arguments via `$ARGUMENTS`). Le fichier `config.toml`
    déclare le provider actif (base_url OpenAI-compat, env_key, modèle du tier
    balanced) — IDs/endpoints « à valider » (cf. providers/{provider}.yaml).
    """

    matrix_key = "codex"
    memory_filename = "AGENTS.md"
    commands_subdir = "prompts"
    command_ext = ".md"

    def _render_command(self, name: str, description: str, body: str) -> str:
        # Codex n'a pas d'équivalent natif à `Task(subagent_type=X)` ni à
        # `Agent(X)` de Claude Code. Le corps est copié verbatim ; les
        # instructions de spawn sous-agent qui apparaîtront ci-dessous
        # doivent être interprétées comme de la GUIDANCE textuelle, pas comme
        # des appels de tool réels — le wrapper `spawn_agent.py` (Phase 3+)
        # matérialisera l'invocation quand il sera câblé au pipeline.
        header = (
            f"<!-- GENERATED FROM .sdd/ (commande /{name}) — DO NOT EDIT -->\n"
            f"<!-- {description} -->\n"
            "<!-- ============================================================ -->\n"
            "<!-- IMPORTANT — SPAWN SEMANTICS UNDER CODEX (audit R10 2026-07-26) -->\n"
            "<!-- Toute mention `Task tool (subagent_type=X)`, `Agent(X)`, ou    -->\n"
            "<!-- « spawn agent X » dans le corps ci-dessous est une INSTRUCTION -->\n"
            "<!-- Claude-Code-native. Sous Codex/Gemini, ces spawns ne sont PAS  -->\n"
            "<!-- des tools disponibles ; l'émulation passe par la CLI wrapper : -->\n"
            "<!--                                                                -->\n"
            "<!--   python .sdd/python/sdd_scripts/spawn_agent_cli.py \\         -->\n"
            "<!--       --agent <name>                                           -->\n"
            "<!--       --task-file <path>   (ou --task \"...\")                 -->\n"
            "<!--       [--harness codex|gemini-cli|claude-code]                 -->\n"
            "<!--       [--provider openai|google|anthropic|moonshot]            -->\n"
            "<!--       [--tier deep|balanced|fast]                              -->\n"
            "<!--       [--schema-file <path.json>]                              -->\n"
            "<!--                                                                -->\n"
            "<!-- Le wrapper renvoie du JSON canonique sur stdout : { ok,        -->\n"
            "<!-- parsed, raw, error_class, schema_errors, attempts, ... }.      -->\n"
            "<!-- Voir .sdd/python/sdd_lib/spawn_agent.py (isolation cwd,        -->\n"
            "<!-- parallélisme borné à MaxParallel, retry-on-schema-fail).       -->\n"
            "<!-- Sub-agents intra-session Claude = 0 tokens ; ici = tokens du   -->\n"
            "<!-- LLM cible directement + coût réseau.                           -->\n"
            "<!-- ============================================================ -->\n"
            "<!-- Arguments SDD passés via $ARGUMENTS (ex. numéro de FEAT). -->\n\n"
            "Arguments: $ARGUMENTS\n\n"
        )
        # Échappe les $1..$9 incidents du corps (awk, caps de coût) — le
        # $ARGUMENTS du header, lui, reste une vraie substitution Codex.
        return header + _escape_codex_positionals(body)

    def emit_config(self, out_dir: Path) -> Path:
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        desc = self._provider_descriptor()
        endpoints = desc.get("endpoints") or {}
        base_url = endpoints.get("openai") or "<base_url OpenAI-compat — à renseigner>"
        auth_env = desc.get("auth_env", "OPENAI_API_KEY")
        tier_map = desc.get("tier_map") or {}
        model = tier_map.get("balanced") or tier_map.get("deep") or "<modèle — à valider>"
        # audit 2026-07-26 R5/m2 — restrict `sandbox_workspace_write` writable
        # roots so `workspace/stack/stack.md` (secrets in clear text) is
        # effectively read-only to Codex sub-agents. Without this, the sandbox
        # `workspace-write` mode allowed writes to every path under workspace/
        # including the credentials file.
        content = (
            "# GENERATED FROM .sdd/ — DO NOT EDIT\n"
            f"# Combo harnais=codex x provider={self._provider}. IDs/endpoints "
            "« à valider » (providers/*.yaml) ; conformance run requis avant SLA.\n"
            f"model = {_toml_basic_string(str(model))}\n"
            f"model_provider = {_toml_basic_string(self._provider)}\n"
            'approval_policy = "on-failure"\n'
            'sandbox_mode = "workspace-write"\n'
            "\n"
            "# Restrict writable roots to code + spec output paths only.\n"
            "# `workspace/stack/` (secrets), `.sdd/`, `.claude/`, `.codex/`,\n"
            "# `.gemini/` (framework façades) are intentionally NOT listed →\n"
            "# reads allowed, writes denied by the sandbox. Audit R5/m2 2026-07-26.\n"
            "[sandbox_workspace_write]\n"
            "writable_roots = [\n"
            '  "workspace/src",\n'
            '  "workspace/feats",\n'
            '  "workspace/us",\n'
            '  "workspace/plans",\n'
            '  "workspace/qa",\n'
            '  "workspace/docs",\n'
            '  "workspace/ui",\n'
            '  "workspace/.sys",\n'
            '  "workspace/discovery",\n'
            "]\n"
            "network_access = false\n"
            "\n"
            f"[model_providers.{self._provider}]\n"
            f"name = {_toml_basic_string(self._provider)}\n"
            f"base_url = {_toml_basic_string(str(base_url))}\n"
            f"env_key = {_toml_basic_string(str(auth_env))}\n"
        )
        safe_out.mkdir(parents=True, exist_ok=True)
        target = safe_out / "config.toml"
        target.write_text(content, encoding="utf-8", newline="\n")
        return target


class GeminiAdapter(_MemoryVariantAdapter):
    """Adaptateur Gemini CLI — `GEMINI.md` + commandes `.gemini/commands/*.toml` + settings.json.

    Les slash-commands SDD deviennent des commandes natives Gemini CLI (TOML
    `description` + `prompt`, arguments via `{{args}}`). `settings.json` déclare
    le modèle du tier balanced du provider actif (IDs « à valider »).
    """

    matrix_key = "gemini-cli"
    memory_filename = "GEMINI.md"
    commands_subdir = "commands"
    command_ext = ".toml"

    def _render_command(self, name: str, description: str, body: str) -> str:
        # Gemini CLI n'a pas d'équivalent natif au Task tool Claude Code.
        # Contrat identique à CodexAdapter : les spawns sous-agent apparaissant
        # dans le corps sont de la guidance, non des appels de tool réels
        # (audit R10 2026-07-26 — voir CodexAdapter._render_command).
        prompt = (
            f"<!-- GENERATED FROM .sdd/ (commande /{name}) — DO NOT EDIT. -->\n"
            "<!-- IMPORTANT — Les instructions `Task(subagent_type=X)` / `Agent(X)` -->\n"
            "<!-- du corps sont Claude-Code-native. Sous Gemini CLI, l'émulation   -->\n"
            "<!-- passe par la CLI wrapper (audit R4 2026-07-26) :                 -->\n"
            "<!--                                                                  -->\n"
            "<!--   python .sdd/python/sdd_scripts/spawn_agent_cli.py \\           -->\n"
            "<!--       --agent <name> --task-file <path>                          -->\n"
            "<!--       [--harness gemini-cli] [--provider google]                 -->\n"
            "<!--                                                                  -->\n"
            "<!-- Le wrapper renvoie du JSON canonique sur stdout (ok, parsed,     -->\n"
            "<!-- raw, error_class, attempts, ...). Voir spawn_agent.py pour       -->\n"
            "<!-- isolation cwd, parallélisme borné, retry-on-schema-fail.         -->\n"
            "Arguments: {{args}}\n\n" + body
        )
        return (
            "# GENERATED FROM .sdd/ — DO NOT EDIT\n"
            f"description = {_toml_basic_string(description)}\n"
            f"prompt = {_toml_multiline_string(prompt)}\n"
        )

    def emit_config(self, out_dir: Path) -> Path:
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        desc = self._provider_descriptor()
        tier_map = desc.get("tier_map") or {}
        model = tier_map.get("balanced") or tier_map.get("deep") or "gemini-3-flash"
        auth_env = desc.get("auth_env", "GEMINI_API_KEY")
        # settings.json — JSON déterministe (indent 2, clés stables).
        settings = {
            "_generated": "FROM .sdd/ — DO NOT EDIT — IDs à valider (providers/*.yaml)",
            "harness": "gemini-cli",
            "provider": self._provider,
            "model": {"name": str(model)},
            "security": {"auth": {"env": str(auth_env)}},
        }
        safe_out.mkdir(parents=True, exist_ok=True)
        target = safe_out / "settings.json"
        target.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return target


class AntigravityAdapter(_MemoryVariantAdapter):
    """Adaptateur Antigravity — `GEMINI.md` + commandes `.gemini/commands/*.toml` + settings.json.

    Support du harnais Antigravity IDE (Google Antigravity) avec intégration
    native des commandes TOML et de la configuration de sécurité/modèle.
    """

    matrix_key = "antigravity"
    memory_filename = "GEMINI.md"
    commands_subdir = "commands"
    command_ext = ".toml"

    def _render_command(self, name: str, description: str, body: str) -> str:
        # Antigravity : même contrat que Gemini CLI (audit R10 2026-07-26).
        prompt = (
            f"<!-- GENERATED FROM .sdd/ (commande /{name}) — DO NOT EDIT. -->\n"
            "<!-- IMPORTANT — Les instructions `Task(subagent_type=X)` / `Agent(X)` -->\n"
            "<!-- du corps sont Claude-Code-native. Sous Antigravity, elles seront -->\n"
            "<!-- émulées par `python .sdd/python/sdd_lib/spawn_agent.py --agent X` -->\n"
            "<!-- (Phase 3+ du plan MIGRATION). En attendant : traiter comme un -->\n"
            "<!-- CONTRAT à honorer par le LLM (suivre la logique de l'agent nommé) -->\n"
            "<!-- plutôt que comme un appel de tool mécanique. -->\n"
            "Arguments: {{args}}\n\n" + body
        )
        return (
            "# GENERATED FROM .sdd/ — DO NOT EDIT\n"
            f"description = {_toml_basic_string(description)}\n"
            f"prompt = {_toml_multiline_string(prompt)}\n"
        )

    def emit_config(self, out_dir: Path) -> Path:
        safe_out = _ensure_under_build(Path(out_dir), self._sdd_home)
        desc = self._provider_descriptor()
        tier_map = desc.get("tier_map") or {}
        model = tier_map.get("balanced") or tier_map.get("deep") or "gemini-2.5-flash"
        auth_env = desc.get("auth_env", "GEMINI_API_KEY")
        settings = {
            "_generated": "FROM .sdd/ — DO NOT EDIT — Antigravity IDE config",
            "harness": "antigravity",
            "provider": self._provider,
            "model": {"name": str(model)},
            "security": {"auth": {"env": str(auth_env)}},
        }
        safe_out.mkdir(parents=True, exist_ok=True)
        target = safe_out / "settings.json"
        target.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return target


_ADAPTERS = {
    "claude-code": ClaudeAdapter,
    "codex": CodexAdapter,
    "gemini-cli": GeminiAdapter,
    "antigravity": AntigravityAdapter,
}



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness_build",
        description="Transpileur .sdd/ -> couche de contrôle harness (mode identité).",
    )
    parser.add_argument(
        "--harness",
        required=False,
        default=None,
        choices=sorted(_ADAPTERS),
        help="harnais cible — requis SAUF si dérivé de --stack (le flag prime)",
    )
    parser.add_argument(
        "--stack",
        default=None,
        type=Path,
        help="stack.md dont dériver harnais + provider (## Active Harness / "
        "## Active Model Provider) — les flags --harness/--provider explicites priment",
    )
    parser.add_argument(
        "--agents-only",
        action="store_true",
        help="émet la couche agents (combinable avec --commands-only)",
    )
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="émet la couche commandes (combinable avec --agents-only)",
    )
    parser.add_argument(
        "--memory-only",
        action="store_true",
        help="émet le fichier mémoire (CLAUDE.md / AGENTS.md / GEMINI.md)",
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="émet la couche rules (claude-code — mode identité)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="provider de modèle (anthropic | openai | google | moonshot) — "
        "résout model_tier -> ID modèle et alimente le rapport d'impact. "
        "Défaut : provider de --stack si fourni, sinon anthropic",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="dossier de sortie — DOIT être sous .sdd/.build/",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="après build, INSTALLE la façade en racine (.codex/ ou .gemini/) — "
        "codex/gemini-cli UNIQUEMENT (jamais .claude/, surface servie protégée)",
    )
    args = parser.parse_args(argv)

    if not (args.agents_only or args.commands_only or args.memory_only or args.rules_only):
        print(
            "ERROR: harness_build — mode non supporté\n"
            "CAUSE: [INVALID_MODE] préciser --agents-only, --commands-only, "
            "--rules-only et/ou --memory-only (mode identité Phase 2)\n"
            "FIX: relancer avec --agents-only, --commands-only, --rules-only "
            "et/ou --memory-only",
            file=sys.stderr,
        )
        return 2

    # --- Résolution des 2 axes (flags explicites > --stack > défaut) ------- #
    # Un stack.md fournit harnais + provider (Tech Lead) ; --harness/--provider
    # les surchargent. Rétro-compat totale : sans --stack, comportement inchangé.
    stack_cfg = None
    if args.stack is not None:
        try:
            stack_cfg = load_stack_config(args.stack)
        except StackConfigError as exc:
            print(
                "ERROR: harness_build — stack.md illisible\n"
                f"CAUSE: [INVALID_ARG] {exc}\n"
                "FIX: corriger --stack (## Active Harness / ## Active Model Provider)",
                file=sys.stderr,
            )
            return 1

    harness = args.harness or (stack_cfg.harness if stack_cfg else None)
    if harness is None:
        print(
            "ERROR: harness_build — harnais non déterminé\n"
            "CAUSE: [INVALID_ARG] ni --harness ni --stack ne fournit de harnais\n"
            "FIX: passer --harness <cible> ou --stack <stack.md>",
            file=sys.stderr,
        )
        return 2
    if harness not in _ADAPTERS:
        print(
            "ERROR: harness_build — harnais sans adaptateur build\n"
            f"CAUSE: [INVALID_ARG] harnais {harness!r} (dérivé de --stack) sans "
            f"adaptateur (disponibles: {sorted(_ADAPTERS)})\n"
            "FIX: choisir un harnais transpilable ou étendre _ADAPTERS",
            file=sys.stderr,
        )
        return 2

    # Provider pour l'émission (façade) + rapport : base `Provider:` du stack.
    # Le mixage cross-provider par tier (stack_cfg.provider_for_tier) relève du
    # résolveur runtime dynamique (Phase 3+), pas de l'émission statique ici.
    #
    # Défaut par harnais (audit 2026-07-25) : codex → openai, gemini-cli/
    # antigravity → google, claude-code → anthropic. Un combo cross-harness
    # (ex. codex × anthropic) reste possible via --provider explicite, mais
    # ne doit pas être imposé par défaut — Anthropic n'expose pas d'endpoint
    # OpenAI-compat officiel, Codex sur Anthropic était non-fonctionnel.
    _DEFAULT_PROVIDER_BY_HARNESS = {
        "claude-code": "anthropic",
        "codex": "openai",
        "gemini-cli": "google",
        "antigravity": "google",
    }
    provider = (
        args.provider
        or (stack_cfg.provider if stack_cfg else None)
        or _DEFAULT_PROVIDER_BY_HARNESS.get(harness, "anthropic")
    )

    adapter = _ADAPTERS[harness](provider=provider)
    results: list[EmitResult] = []
    memory_written: Path | None = None
    try:
        if args.agents_only:
            agent_results = adapter.emit_agents(args.out)
            results.extend(agent_results)
            print(
                f"[harness_build] {harness}: "
                f"{sum(1 for r in agent_results if r.ok)} agent(s) régénéré(s) sous {args.out}"
            )
        if args.commands_only:
            command_results = adapter.emit_commands(args.out)
            results.extend(command_results)
            print(
                f"[harness_build] {harness}: "
                f"{sum(1 for r in command_results if r.ok)} commande(s) régénérée(s) sous {args.out}"
            )
        if args.rules_only:
            rule_results = adapter.emit_rules(args.out)
            results.extend(rule_results)
            print(
                f"[harness_build] {harness}: "
                f"{sum(1 for r in rule_results if r.ok)} rule(s) régénérée(s) sous {args.out}"
            )
        if args.memory_only:
            memory_written = adapter.emit_memory_file(args.out)
            print(
                f"[harness_build] {harness}: fichier mémoire régénéré — {memory_written}"
            )
    except NotImplementedError as exc:
        print(
            "ERROR: harness_build — couche non transpilée pour ce harnais\n"
            f"CAUSE: [INVALID_MODE] {exc}\n"
            "FIX: pour codex/gemini-cli : --memory-only + --commands-only supportés "
            "(agents/rules hors périmètre — émulés au runtime / inline)",
            file=sys.stderr,
        )
        return 2
    except (BuildSafetyError, ConfigError) as exc:
        print(
            "ERROR: harness_build — émission échouée\n"
            f"CAUSE: [INVALID_ARG] {exc}\n"
            "FIX: corriger --out (sous .sdd/.build/) ou le foyer .sdd/",
            file=sys.stderr,
        )
        return 1

    # Rapport d'impact — OBLIGATOIRE par build (plan §7.3, ADR D5). Toujours
    # imprimé + persisté, jamais bloquant (le gate SDD_ALLOW_UNTESTED_HARNESS
    # relève du consommateur pipeline, cf. impact_report.untested_gate_ok).
    _emit_impact_report(harness, provider, args.out)

    if args.deploy:
        # Gate UNTESTED — deployer une façade en racine rend le combo « live » :
        # un combo non qualifié (tout sauf claude-code×anthropic, faute de
        # conformance run §10) exige SDD_ALLOW_UNTESTED_HARNESS=1. Symétrique du
        # hook preflight_stack_combo ; le build seul (sans --deploy) reste, lui,
        # informationnel. Fail-open si le rapport est indisponible (ne bloque
        # pas le deploy sur un hoquet de config — #6 ancre déjà le chemin).
        try:
            _gate_report = build_impact_report(harness, provider, env={}, base=_REPO_ROOT)
            if not untested_gate_ok(_gate_report, os.environ):
                print(
                    "ERROR: harness_build — deploy refusé\n"
                    f"CAUSE: [STACK_COMBO_UNTESTED] combo {harness}×{provider} non "
                    "qualifié (conformance run §10 absent)\n"
                    "FIX: exporter SDD_ALLOW_UNTESTED_HARNESS=1 dans le shell parent "
                    "(bypass audit-loggué) pour déployer quand même",
                    file=sys.stderr,
                )
                return 2
        except (ConfigError, BuildSafetyError) as exc:
            print(
                f"[harness_build] WARN gate untested indisponible (deploy autorisé): {exc}",
                file=sys.stderr,
            )
        try:
            dest = _deploy_facade(harness, args.out)
            print(f"[harness_build] {harness}: façade installée -> {dest}")
        except BuildSafetyError as exc:
            print(
                "ERROR: harness_build — deploy refusé\n"
                f"CAUSE: [FRAMEWORK_PROTECTED] {exc}\n"
                "FIX: --deploy valide seulement pour codex/gemini-cli (jamais .claude/)",
                file=sys.stderr,
            )
            return 2

    written = [r for r in results if r.ok]
    skipped = [r for r in results if not r.ok]
    for result in skipped:
        print(f"[harness_build] SKIP {result.agent}: {result.skipped_reason}")
    if skipped:
        return 1
    if written or memory_written is not None:
        return 0
    return 1


#: racine des façades installables (jamais claude-code : .claude est servi/protégé).
_FACADE_ROOT = {"codex": ".codex", "gemini-cli": ".gemini"}


def _deploy_facade(harness: str, out_dir: Path) -> Path:
    """Installe la façade buildée (out_dir) en racine repo (.codex/ ou .gemini/).

    Refuse claude-code (surface servie protégée) et tout harnais sans cible.
    Remplace le contenu existant (façade = produit de build jetable).
    """
    import shutil

    dest_name = _FACADE_ROOT.get(harness)
    if dest_name is None:
        raise BuildSafetyError(
            f"deploy interdit pour {harness!r} — cibles autorisées: {sorted(_FACADE_ROOT)}"
        )
    src = Path(out_dir).resolve()
    dest = (_REPO_ROOT / dest_name).resolve()
    # Garde-fou dur : ne jamais viser .claude/ ni hors du repo.
    if dest == (_REPO_ROOT / ".claude").resolve() or _REPO_ROOT not in dest.parents:
        raise BuildSafetyError(f"cible de deploy interdite: {dest}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def _emit_impact_report(harness: str, provider: str, out_dir: Path) -> None:
    """Imprime (stdout) + persiste le rapport d'impact §7.3 — non bloquant.

    Persistance : `{out}/harness-impact.md` (sous .sdd/.build/, sûr) et,
    best-effort, `workspace/.sys/harness-impact.md` (emplacement canonique
    du plan) SEULEMENT si `workspace/.sys/` existe déjà (jamais de création
    d'arbre workspace). Toute erreur d'écriture est avalée : le rapport ne
    doit jamais faire échouer une transpilation.
    """
    try:
        # Ancrage déterministe au foyer du transpileur (env={} ignore un
        # SDD_HOME ambiant, base=_REPO_ROOT → _REPO_ROOT/.sdd == _SDD_HOME) :
        # sans ça, build_impact_report retombe sur Path.cwd()/.sdd et le
        # rapport « obligatoire par build » (D5) se dégrade en WARN silencieux
        # dès que harness_build est lancé hors de la racine repo.
        report = build_impact_report(harness, provider, env={}, base=_REPO_ROOT)
    except (ConfigError, BuildSafetyError) as exc:
        print(
            f"[harness_build] WARN rapport d'impact indisponible: {exc}",
            file=sys.stderr,
        )
        return
    print(report.render())
    markdown = report.to_markdown()
    try:
        safe_out = _ensure_under_build(Path(out_dir), _SDD_HOME)
        safe_out.mkdir(parents=True, exist_ok=True)
        (safe_out / "harness-impact.md").write_text(markdown, encoding="utf-8", newline="\n")
    except (BuildSafetyError, OSError) as exc:
        print(f"[harness_build] WARN persistance rapport (build) échouée: {exc}", file=sys.stderr)
    workspace_sys = _REPO_ROOT / "workspace" / ".sys"
    if workspace_sys.is_dir():
        try:
            (workspace_sys / "harness-impact.md").write_text(
                markdown, encoding="utf-8", newline="\n"
            )
        except OSError as exc:
            print(
                f"[harness_build] WARN persistance rapport (workspace) échouée: {exc}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    raise SystemExit(main())
