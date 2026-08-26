"""stack_config — parseur pur des 2 axes + sélection de modèle depuis `stack.md`.

Réalise la moitié LOAD-BEARING de la tâche **1.7** du plan
`MIGRATION-PLAN-multi-harness-multi-provider.md` (§8.3 + §8.bis.2) : lire les
sections ``## Active Harness``, ``## Active Model Provider`` (+ ``ModelTierMap``)
et ``## Model Selection`` d'un `stack.md`, avec **défauts rétro-compatibles**
(absence de section = `claude-code` / `anthropic` / `static`).

Ce module est la GLU entre le `stack.md` (choix Tech Lead) et :
- ``model_resolver.resolve_model`` (mode static|dynamic + provider par tier) ;
- ``impact_report.build_impact_report`` (harnais + provider actifs).

Rétro-compatibilité : les 3 sections sont désormais présentes dans
`.sdd/templates/stack.md.template`, mais ce parseur tolère toujours leur
absence totale (stack.md antérieur au multi-provider) sans erreur — les
défauts `claude-code` / `anthropic` / `static` s'appliquent alors.

Pur : aucune I/O réseau, aucun side effect à l'import ; ``load_stack_config``
est le seul point de lecture disque (fail-explicit si fichier absent).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .model_resolver import MODES, TIERS

__all__ = [
    "HARNESSES",
    "DEFAULT_HARNESS",
    "DEFAULT_PROVIDER",
    "DEFAULT_MODE",
    "StackConfigError",
    "StackConfig",
    "parse_stack_config",
    "load_stack_config",
]

#: Harnais valides (axe 1, ADR D1). antigravity accepté même sans adaptateur build.
HARNESSES: tuple[str, ...] = ("claude-code", "codex", "antigravity", "gemini-cli")

DEFAULT_HARNESS = "claude-code"
DEFAULT_PROVIDER = "anthropic"
DEFAULT_ENDPOINT = "default"
DEFAULT_MODE = "static"

# `## Titre` en début de ligne (H2 markdown), capture le titre normalisé.
_H2 = re.compile(r"^##\s+(.+?)\s*$")
# `Clé: valeur` (valeur optionnelle — ModelTierMap: n'a pas de valeur inline).
_KV = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9 _-]*?)\s*:\s*(?P<val>.*?)\s*$")
# Ligne indentée d'un bloc (ex. `  deep: anthropic`).
_INDENTED_KV = re.compile(r"^\s+(?P<key>[A-Za-z0-9_-]+)\s*:\s*(?P<val>.+?)\s*$")


class StackConfigError(ValueError):
    """Section/valeur invalide dans `stack.md` (harnais/mode/tier inconnu…)."""


@dataclass(frozen=True)
class StackConfig:
    """Configuration harnais × provider résolue depuis `stack.md`."""

    harness: str
    provider: str
    endpoint: str
    #: ModelTierMap : tier -> provider (mixage cross-provider). Toujours complet
    #: (les tiers non déclarés retombent sur ``provider``).
    tier_providers: dict[str, str]
    mode: str

    def provider_for_tier(self, tier: str) -> str:
        """Provider actif pour un tier donné (§8.bis.6 — mixage cross-provider).

        >>> StackConfig("claude-code","anthropic","default",
        ...   {"deep":"anthropic","balanced":"moonshot","fast":"moonshot"},
        ...   "dynamic").provider_for_tier("balanced")
        'moonshot'
        """
        if tier not in TIERS:
            raise StackConfigError(f"tier inconnu: {tier!r} (attendu: {'|'.join(TIERS)})")
        return self.tier_providers[tier]

    def is_reference_combo(self) -> bool:
        """True si claude-code × anthropic (combo de référence, non UNTESTED)."""
        return self.harness == DEFAULT_HARNESS and self.provider == DEFAULT_PROVIDER


def _normalize(text: str) -> str:
    """BOM retiré + CRLF/CR -> LF (même contrat que harness_diff)."""
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def _strip_inline_comment(value: str) -> str:
    """Retire un commentaire inline `  # ...` (préfixé d'espace) — jamais un `#` collé."""
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def _split_sections(text: str) -> dict[str, list[str]]:
    """Découpe le markdown en {titre H2 normalisé -> lignes du corps}."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in _normalize(text).split("\n"):
        m = _H2.match(line)
        if m:
            current = m.group(1).strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def _scalar(body: list[str], key: str) -> str | None:
    """Première valeur scalaire `Key: value` (comparaison de clé insensible à la casse)."""
    for line in body:
        m = _KV.match(line)
        if m and m.group("key").strip().lower() == key.lower():
            return _strip_inline_comment(m.group("val"))
    return None


def _tier_map_block(body: list[str]) -> dict[str, str]:
    """Extrait le bloc `ModelTierMap:` (lignes indentées `tier: provider`)."""
    out: dict[str, str] = {}
    in_block = False
    for line in body:
        header = _KV.match(line)
        if header and header.group("key").strip().lower() == "modeltiermap":
            in_block = True
            continue
        if in_block:
            indented = _INDENTED_KV.match(line)
            if indented:
                tier = indented.group("key").strip().lower()
                prov = _strip_inline_comment(indented.group("val"))
                if tier not in TIERS:
                    raise StackConfigError(
                        f"ModelTierMap: tier inconnu {tier!r} (attendu: {'|'.join(TIERS)})"
                    )
                if prov:
                    out[tier] = prov
            elif line.strip() and not line.startswith((" ", "\t")):
                break  # fin du bloc indenté (nouvelle clé non indentée)
    return out


def parse_stack_config(text: str) -> StackConfig:
    """Parse le texte d'un `stack.md` en ``StackConfig`` (défauts rétro-compat).

    Absence totale des sections (stack.md legacy) -> claude-code / anthropic /
    static. Valeurs invalides (harnais/mode/tier inconnu) -> ``StackConfigError``.
    """
    sections = _split_sections(text)

    harness = DEFAULT_HARNESS
    harness_body = sections.get("active harness")
    if harness_body is not None:
        value = _scalar(harness_body, "Harness")
        if value:
            if value not in HARNESSES:
                raise StackConfigError(
                    f"Harness invalide: {value!r} (attendu: {'|'.join(HARNESSES)})"
                )
            harness = value

    provider = DEFAULT_PROVIDER
    endpoint = DEFAULT_ENDPOINT
    tier_overrides: dict[str, str] = {}
    provider_body = sections.get("active model provider")
    if provider_body is not None:
        value = _scalar(provider_body, "Provider")
        if value:
            provider = value  # validité réelle vérifiée au chargement providers/{p}.yaml
        endpoint_value = _scalar(provider_body, "Endpoint")
        if endpoint_value:
            endpoint = endpoint_value
        tier_overrides = _tier_map_block(provider_body)

    mode = DEFAULT_MODE
    selection_body = sections.get("model selection")
    if selection_body is not None:
        value = _scalar(selection_body, "Mode")
        if value:
            if value not in MODES:
                raise StackConfigError(
                    f"Mode invalide: {value!r} (attendu: {'|'.join(MODES)})"
                )
            mode = value

    # ModelTierMap complet : tout tier non surchargé retombe sur le provider actif.
    tier_providers = {tier: tier_overrides.get(tier, provider) for tier in TIERS}

    return StackConfig(
        harness=harness,
        provider=provider,
        endpoint=endpoint,
        tier_providers=tier_providers,
        mode=mode,
    )


def load_stack_config(path: Path) -> StackConfig:
    """Charge et parse un `stack.md` depuis le disque (fail-explicit si absent)."""
    if not path.is_file():
        raise StackConfigError(f"stack.md introuvable: {path}")
    return parse_stack_config(path.read_text(encoding="utf-8-sig"))
