"""impact_report — rapport d'honnêteté des garanties par combo harnais × provider.

Réalise la tâche **2.5** du plan `MIGRATION-PLAN-multi-harness-multi-provider.md`
(§7.3 « rapport d'impact obligatoire ») et concrétise le principe **D5** de
l'ADR `harness-and-provider-abstraction` : chaque build `harness_build.py`
imprime le NIVEAU DE PROTECTION RÉEL du combo cible (mécanismes natifs /
émulés / reportés-CI / absents) et marque `UNTESTED` tout combo qui n'est pas
la référence conformance-validée — jamais de dégradation silencieuse.

SSoT machine : `.sdd/capability-matrix.yml` (harnais × mécanismes) +
`.sdd/providers/{provider}.yaml` (fidélité sorties structurées, pricing).
Ce module est PUR (aucune I/O réseau, aucun binaire externe, aucun side
effect à l'import) et déterministe — testable offline.

Périmètre : le rapport est **informationnel** dans le transpileur (il
n'échoue jamais un build). Le gate bloquant `SDD_ALLOW_UNTESTED_HARNESS`
(``untested_gate_ok``) est exposé pour le futur consommateur pipeline
(symétrique du hook ``preflight_stack_combo``), pas pour le build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config_loader import ConfigError, load_provider, load_yaml
from .paths import capability_matrix_path

__all__ = [
    "REFERENCE_HARNESS",
    "REFERENCE_PROVIDER",
    "MECHANISM_LABELS",
    "VALUE_LABELS",
    "ALLOW_UNTESTED_ENV",
    "ImpactReport",
    "build_impact_report",
    "untested_gate_ok",
]

#: Combo de référence conformance-validé (golden test + baseline CalcABC).
REFERENCE_HARNESS = "claude-code"
REFERENCE_PROVIDER = "anthropic"

#: Env var de bypass du gate UNTESTED (audit-loggué, symétrique preflight_stack_combo).
ALLOW_UNTESTED_ENV = "SDD_ALLOW_UNTESTED_HARNESS"

_HIGH_FIDELITY = "high"

#: Les 7 mécanismes pivot (ordre stable) → libellé humain FR (rapport lisible).
MECHANISM_LABELS: dict[str, str] = {
    "subagent_spawn": "Sous-agents isolés + parallélisme borné",
    "runtime_hooks": "Hooks bloquants intra-session",
    "skills_autotrigger": "Skills auto-trigger",
    "at_include": "Lazy-load @file",
    "slash_commands": "Slash-commands",
    "deterministic_python": "Python déterministe (gates, build_loop)",
    "mcp": "MCP",
}

#: Valeurs de la matrice → libellé humain FR.
VALUE_LABELS: dict[str, str] = {
    "native": "natif",
    "emulated": "émulé (wrapper)",
    "ci_fallback": "reporté CI-time",
    "unsupported": "absent",
}

#: Valeurs considérées comme « pas natif » (déclenchent un ⚠ dans le rapport).
_NON_NATIVE = ("emulated", "ci_fallback", "unsupported")


@dataclass(frozen=True)
class ImpactReport:
    """Rapport d'impact structuré d'un combo harnais × provider (§7.3)."""

    harness: str
    provider: str
    protection_level: str
    #: mécanisme -> valeur brute matrice (native/emulated/ci_fallback/unsupported)
    mechanisms: dict[str, str]
    #: structured_output_fidelity du provider (high/medium/low/unknown/...)
    fidelity: str
    pricing_present: bool
    is_reference: bool
    untested: bool
    warnings: list[str] = field(default_factory=list)

    def mechanism_counts(self) -> dict[str, int]:
        """Nombre de mécanismes par valeur (native/emulated/ci_fallback/unsupported)."""
        counts = {v: 0 for v in VALUE_LABELS}
        for value in self.mechanisms.values():
            counts[value] = counts.get(value, 0) + 1
        return counts

    def render(self) -> str:
        """Rapport texte (stdout du build) — format §7.3 du plan.

        Volontairement ASCII-safe (marqueurs `!`/`[REF]`/`[UNTESTED]` plutôt
        que des glyphes ⚠/✅) : robuste sur console Windows cp1252 et sous la
        capture pytest, sans reconfigurer stdout. Les glyphes riches sont
        réservés à ``to_markdown`` (fichier écrit explicitement en UTF-8).
        """
        counts = self.mechanism_counts()
        lines = [
            f"HARNESS BUILD REPORT — harness={self.harness}, provider={self.provider}",
            "  Protections runtime : "
            f"{counts['native']} natives, {counts['emulated']} emulees, "
            f"{counts['ci_fallback']} reportees CI, {counts['unsupported']} absentes",
        ]
        for warning in self.warnings:
            lines.append(f"  ! {warning}")
        ref_suffix = "" if self.is_reference else " (ref. = A sous claude-code/anthropic)"
        lines.append(f"  Niveau de protection global : {self.protection_level}{ref_suffix}")
        if self.untested:
            lines.append(
                f"  [UNTESTED] le pipeline exige {ALLOW_UNTESTED_ENV}=1 "
                "(audit-loggue) tant qu'aucun conformance run (§10) n'a qualifie ce combo"
            )
        else:
            lines.append("  [REFERENCE] combo valide (golden test + baseline CalcABC)")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Variante Markdown persistée (workspace/.sys/harness-impact.md, {out}/…)."""
        counts = self.mechanism_counts()
        rows = [
            "# Rapport d'impact — build harness",
            "",
            f"- **Harnais** : `{self.harness}`",
            f"- **Provider** : `{self.provider}`",
            f"- **Niveau de protection** : {self.protection_level}"
            + ("" if self.is_reference else " (référence = A sous claude-code/anthropic)"),
            f"- **Combo** : {'RÉFÉRENCE (validé)' if not self.untested else 'UNTESTED'}",
            f"- **Fidélité sorties structurées (provider)** : {self.fidelity}",
            f"- **Pricing renseigné** : {'oui' if self.pricing_present else 'non ([TELEMETRY_UNAVAILABLE])'}",
            "",
            "## Mécanismes",
            "",
            f"native={counts['native']} · émulé={counts['emulated']} · "
            f"reporté-CI={counts['ci_fallback']} · absent={counts['unsupported']}",
            "",
            "| Mécanisme | Statut |",
            "|---|---|",
        ]
        for key, label in MECHANISM_LABELS.items():
            value = self.mechanisms.get(key, "?")
            rows.append(f"| {label} | {VALUE_LABELS.get(value, value)} |")
        if self.warnings:
            rows.extend(["", "## Avertissements", ""])
            rows.extend(f"- ⚠ {w}" for w in self.warnings)
        if self.untested:
            rows.extend(
                [
                    "",
                    f"> ⚠ COMBO UNTESTED — le pipeline exige `{ALLOW_UNTESTED_ENV}=1` "
                    "(audit-loggué) tant qu'aucun conformance run (§10 du plan) n'a "
                    "qualifié ce combo. Le build (transpilation) reste, lui, non bloquant.",
                ]
            )
        return "\n".join(rows) + "\n"


def _mechanism_warnings(harness_key: str, mechanisms: dict[str, str]) -> list[str]:
    """Un ⚠ par mécanisme non natif, libellé humain."""
    warnings: list[str] = []
    for key, label in MECHANISM_LABELS.items():
        value = mechanisms.get(key)
        if value in _NON_NATIVE:
            warnings.append(f"{label} : {VALUE_LABELS[value]}")
    return warnings


def build_impact_report(
    harness: str,
    provider: str,
    *,
    env: dict[str, str] | None = None,
    base: Path | None = None,
) -> ImpactReport:
    """Construit le rapport d'impact d'un combo (harnais × provider).

    Lit `.sdd/capability-matrix.yml` (bloc harnais) + `.sdd/providers/{p}.yaml`
    (fidélité + pricing). Lève ``ConfigError`` si le harnais est absent de la
    matrice ou le provider introuvable (fail-explicit, jamais de repli muet).
    """
    matrix = load_yaml(capability_matrix_path(env=env, base=base))
    harnesses = matrix.get("harnesses")
    if not isinstance(harnesses, dict):
        raise ConfigError("clé 'harnesses' absente ou invalide dans capability-matrix.yml")
    harness_block = harnesses.get(harness)
    if not isinstance(harness_block, dict):
        raise ConfigError(
            f"harnais {harness!r} absent de capability-matrix.yml "
            f"(harnais déclarés: {sorted(harnesses)})"
        )
    protection_level = str(harness_block.get("protection_level", "?"))
    mechanisms_raw = harness_block.get("mechanisms")
    mechanisms: dict[str, str] = (
        {k: str(v) for k, v in mechanisms_raw.items()}
        if isinstance(mechanisms_raw, dict)
        else {}
    )

    provider_data: dict[str, Any] = load_provider(provider, env=env, base=base)
    capabilities = provider_data.get("capabilities")
    fidelity = "unknown"
    if isinstance(capabilities, dict):
        fidelity = str(capabilities.get("structured_output_fidelity", "unknown"))
    pricing = provider_data.get("pricing")
    pricing_present = isinstance(pricing, dict) and bool(pricing)

    is_reference = harness == REFERENCE_HARNESS and provider == REFERENCE_PROVIDER
    # Honnêteté : seule la référence est validée end-to-end (golden test +
    # baseline CalcABC). Tout autre combo attend un conformance run (§10).
    untested = not is_reference

    warnings = _mechanism_warnings(harness, mechanisms)
    if fidelity != _HIGH_FIDELITY:
        if is_reference:
            warnings.append(
                f"Provider {provider} : fidélité sorties structurées « {fidelity} » "
                "(référence de facto — à formaliser au 1er conformance run §10)"
            )
        else:
            warnings.append(
                f"Provider {provider} : fidélité sorties structurées « {fidelity} » "
                "— conformance run (§10) requis avant tout SLA"
            )
    if not pricing_present:
        warnings.append(
            f"Provider {provider} : pricing absent — tout run cost-cappé émettra "
            "[TELEMETRY_UNAVAILABLE] (fail-open loggué)"
        )

    return ImpactReport(
        harness=harness,
        provider=provider,
        protection_level=protection_level,
        mechanisms=mechanisms,
        fidelity=fidelity,
        pricing_present=pricing_present,
        is_reference=is_reference,
        untested=untested,
        warnings=warnings,
    )


def untested_gate_ok(report: ImpactReport, env: dict[str, str] | None = None) -> bool:
    """Gate bloquant pour le CONSOMMATEUR pipeline (pas le build).

    Retourne True si le combo est la référence (validé), ou si
    ``SDD_ALLOW_UNTESTED_HARNESS`` est truthy dans ``env``. Symétrique du
    hook ``preflight_stack_combo`` — le build de façades reste, lui, non
    bloquant (le rapport est informationnel).
    """
    if not report.untested:
        return True
    environ = env if env is not None else {}
    raw = str(environ.get(ALLOW_UNTESTED_ENV, "")).strip().lower()
    return raw in ("1", "true", "yes", "on")
