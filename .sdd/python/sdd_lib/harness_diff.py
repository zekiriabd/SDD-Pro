"""harness_diff — comparaison SÉMANTIQUE d'agents .md régénérés vs vivants.

Phase 2 (mode identité, plan MIGRATION-PLAN-multi-harness-multi-provider) :
vérifie qu'un `.md` d'agent régénéré par `harness_build.py` (ClaudeAdapter)
est sémantiquement équivalent au `.claude/agents/{name}.md` vivant.

Deux niveaux de comparaison :
1. **Frontmatter** — champs {name, description, model, tools} comparés par
   VALEUR (ordre des clés non significatif, `tools` normalisé en liste).
2. **Corps markdown** — égalité STRICTE après normalisation des fins de
   ligne (CRLF/CR -> LF) et retrait d'un BOM éventuel.

Écart connu byte-identité vs sémantique (documenté, accepté au stade PoC) :
- l'ordre des clés du frontmatter peut différer ;
- les commentaires inline du frontmatter vivant (ex. `model: X   # note`)
  sont perdus à la régénération ;
- CRLF vs LF.
La byte-identité stricte est un durcissement Phase 2 ultérieur.

Parser frontmatter TOLÉRANT (line-based, pas yaml.safe_load strict) :
plusieurs agents vivants portent des descriptions contenant `: ` en plein
scalaire (ex. `qa`, `arch`, `security-reviewer`) — valide pour le parser
loose de Claude Code, invalide en YAML strict. Le même parser est appliqué
aux DEUX côtés (régénéré + vivant) pour une comparaison cohérente.

Pur : aucune I/O implicite hors lecture des deux fichiers comparés.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "FRONTMATTER_FIELDS",
    "FrontmatterError",
    "FieldDiff",
    "DiffReport",
    "parse_frontmatter",
    "normalize_tools",
    "diff_agent_texts",
    "diff_agent_files",
]

# Champs du contrat sémantique agent Claude Code (mode identité).
FRONTMATTER_FIELDS: tuple[str, ...] = ("name", "description", "model", "tools")

_FENCE_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
# Commentaire inline YAML : espace(s) + '#' + reste de ligne.
_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


class FrontmatterError(ValueError):
    """Fichier agent sans frontmatter `---` exploitable."""


def _normalize_text(text: str) -> str:
    """BOM éventuel retiré + fins de ligne CRLF/CR normalisées en LF."""
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Découpe un agent .md en (champs frontmatter, corps markdown).

    Parser line-based tolérant : chaque ligne non vide / non commentaire du
    bloc `---` est découpée sur le PREMIER `:` (les `:` suivants restent
    dans la valeur), commentaire inline retiré.

    Returns:
        (fields, body) — body = tout ce qui suit la ligne de fence fermante.

    Raises:
        FrontmatterError: pas de bloc `---` en tête de fichier.
    """
    normalized = _normalize_text(text)
    match = _FENCE_RE.match(normalized)
    if match is None:
        raise FrontmatterError("frontmatter '---' absent ou non fermé en tête de fichier")
    fields: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise FrontmatterError(f"ligne frontmatter sans ':' : {line!r}")
        fields[key.strip()] = _INLINE_COMMENT_RE.sub("", value.strip())
    return fields, normalized[match.end():]


def normalize_tools(value: object) -> list[str]:
    """Normalise `tools` (str CSV Claude Code OU liste) en liste ordonnée."""
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value]
    return [str(value)]


@dataclass(frozen=True)
class FieldDiff:
    """Différence sur UN champ du frontmatter."""

    field: str
    generated: object
    live: object

    def __str__(self) -> str:  # pragma: no cover - cosmétique
        return f"{self.field}: généré={self.generated!r} != vivant={self.live!r}"


@dataclass
class DiffReport:
    """Rapport structuré de comparaison sémantique généré vs vivant."""

    generated_path: str
    live_path: str
    frontmatter_diffs: list[FieldDiff] = field(default_factory=list)
    body_identical: bool = True
    body_first_divergence: str | None = None  # 1ère ligne divergente (contexte)
    extra_live_keys: list[str] = field(default_factory=list)  # informational
    error: str | None = None  # erreur de parse (fichier illisible, etc.)

    @property
    def identical(self) -> bool:
        """Égalité sémantique : frontmatter (4 champs) + corps identique."""
        return self.error is None and not self.frontmatter_diffs and self.body_identical

    def summary(self) -> str:
        """Résumé lisible (utilisé dans les messages d'échec pytest)."""
        if self.identical:
            return "identique (sémantique)"
        parts: list[str] = []
        if self.error:
            parts.append(f"ERREUR: {self.error}")
        for diff in self.frontmatter_diffs:
            parts.append(str(diff))
        if not self.body_identical:
            parts.append(f"corps divergent — 1ère divergence: {self.body_first_divergence!r}")
        return " | ".join(parts)


def _first_body_divergence(generated: str, live: str) -> str | None:
    gen_lines, live_lines = generated.split("\n"), live.split("\n")
    for index, (g_line, l_line) in enumerate(zip(gen_lines, live_lines), start=1):
        if g_line != l_line:
            return f"ligne {index}: généré={g_line!r} vs vivant={l_line!r}"
    if len(gen_lines) != len(live_lines):
        return (
            f"longueurs différentes: {len(gen_lines)} lignes générées "
            f"vs {len(live_lines)} vivantes"
        )
    return None


def diff_agent_texts(
    generated_text: str,
    live_text: str,
    *,
    generated_path: str = "<generated>",
    live_path: str = "<live>",
    fields: tuple[str, ...] = FRONTMATTER_FIELDS,
) -> DiffReport:
    """Compare deux contenus d'agent .md (cœur pur, testable sans disque)."""
    report = DiffReport(generated_path=generated_path, live_path=live_path)
    try:
        gen_fields, gen_body = parse_frontmatter(generated_text)
        live_fields, live_body = parse_frontmatter(live_text)
    except FrontmatterError as exc:
        report.error = str(exc)
        report.body_identical = False
        return report

    for name in fields:
        gen_value: object = gen_fields.get(name)
        live_value: object = live_fields.get(name)
        if name == "tools":
            gen_value = normalize_tools(gen_value)
            live_value = normalize_tools(live_value)
        if gen_value != live_value:
            report.frontmatter_diffs.append(FieldDiff(name, gen_value, live_value))

    report.extra_live_keys = sorted(set(live_fields) - set(fields))

    if gen_body != live_body:
        report.body_identical = False
        report.body_first_divergence = _first_body_divergence(gen_body, live_body)
    return report


def diff_agent_files(generated: Path, live: Path) -> DiffReport:
    """Compare un agent .md régénéré et le .md vivant (lecture seule)."""
    try:
        generated_text = generated.read_text(encoding="utf-8-sig")
        live_text = live.read_text(encoding="utf-8-sig")
    except OSError as exc:
        report = DiffReport(generated_path=str(generated), live_path=str(live))
        report.error = f"lecture impossible: {exc}"
        report.body_identical = False
        return report
    return diff_agent_texts(
        generated_text,
        live_text,
        generated_path=str(generated),
        live_path=str(live),
    )
