"""harness_preflight — résolution + gate du combo actif (harnais × provider).

Brique de COMPOSITION qui unifie les 3 briques déjà livrées :

    stack.md ─stack_config─▶ (harnais, provider, mode)
             ─impact_report─▶ niveau protection A/B/C + UNTESTED
             ─untested_gate─▶ autorisé ? (SDD_ALLOW_UNTESTED_HARNESS)

C'est le point d'entrée unique que le CONSOMMATEUR pipeline (et le futur
wrapper `spawn_agent.py`) appellera pour répondre, à partir du `stack.md`
actif : « quel combo je lance, est-il autorisé, et quel est son niveau de
protection honnête ? ». Symétrique du hook `preflight_stack_combo` existant
(combos stacks), transposé à l'axe harnais × provider.

Pur/offline (aucun réseau, aucun binaire) ; ``env`` injectable (zéro
monkeypatch). Ne DÉCIDE rien d'irréversible : renvoie un verdict structuré,
l'appelant choisit de bloquer ou non.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .config_loader import ConfigError
from .impact_report import ImpactReport, build_impact_report, untested_gate_ok
from .stack_config import DEFAULT_HARNESS, DEFAULT_PROVIDER, StackConfig, parse_stack_config

__all__ = [
    "PreflightError",
    "PreflightResult",
    "preflight_combo",
]


class PreflightError(ValueError):
    """Combo irrésolvable (stack.md invalide, provider/harnais inconnu)."""


@dataclass(frozen=True)
class PreflightResult:
    """Verdict de préflight du combo actif — consommable par le pipeline."""

    config: StackConfig
    report: ImpactReport
    #: True si le combo est la référence OU si SDD_ALLOW_UNTESTED_HARNESS est armé.
    allowed: bool

    @property
    def harness(self) -> str:
        return self.config.harness

    @property
    def provider(self) -> str:
        return self.config.provider

    @property
    def blocking_reason(self) -> str | None:
        """Motif de blocage (None si autorisé) — prêt pour un bloc ERROR [CLASS]."""
        if self.allowed:
            return None
        return (
            f"[STACK_COMBO_UNTESTED] combo harnais={self.harness} × "
            f"provider={self.provider} non qualifié (aucun conformance run §10) — "
            "exiger SDD_ALLOW_UNTESTED_HARNESS=1 (audit-loggué) pour passer outre"
        )

    def render(self) -> str:
        """Rapport combo + verdict de gate (ASCII-safe, réutilise report.render)."""
        verdict = "AUTORISÉ" if self.allowed else "BLOQUÉ"
        lines = [self.report.render(), f"  Gate combo : {verdict}"]
        reason = self.blocking_reason
        if reason:
            lines.append(f"  -> {reason}")
        return "\n".join(lines)


def preflight_combo(
    stack_path: Path | None = None,
    *,
    env: dict[str, str] | None = None,
    base: Path | None = None,
) -> PreflightResult:
    """Résout le combo actif depuis un `stack.md` (ou défauts) et applique le gate.

    Args:
        stack_path: chemin du `stack.md`. ``None`` -> défauts rétro-compat
            (claude-code × anthropic × static, combo de référence).
        env: mapping d'environnement (défaut ``os.environ``) — lu pour le gate
            ``SDD_ALLOW_UNTESTED_HARNESS`` et la résolution ``SDD_HOME``.
        base: base de résolution du foyer `.sdd/` (tests).

    Returns:
        PreflightResult(config, report, allowed).

    Raises:
        PreflightError: stack.md illisible/invalide, ou harnais/provider absent
            de la matrice / des descripteurs providers.
    """
    environ = os.environ if env is None else env

    if stack_path is None:
        config = StackConfig(
            harness=DEFAULT_HARNESS,
            provider=DEFAULT_PROVIDER,
            endpoint="default",
            tier_providers={t: DEFAULT_PROVIDER for t in ("deep", "balanced", "fast")},
            mode="static",
        )
    else:
        if not stack_path.is_file():
            raise PreflightError(f"stack.md introuvable: {stack_path}")
        try:
            config = parse_stack_config(stack_path.read_text(encoding="utf-8-sig"))
        except ValueError as exc:  # StackConfigError hérite de ValueError
            raise PreflightError(f"stack.md invalide ({stack_path}): {exc}") from exc

    try:
        report = build_impact_report(config.harness, config.provider, env=environ, base=base)
    except ConfigError as exc:
        raise PreflightError(
            f"combo harnais={config.harness} × provider={config.provider} "
            f"irrésolvable: {exc}"
        ) from exc

    allowed = untested_gate_ok(report, env=environ)
    return PreflightResult(config=config, report=report, allowed=allowed)
