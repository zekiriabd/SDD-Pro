"""context_pack — Context Engineering Layer généralisé (audit 2026-08-28, correction #4).

Le paradoxe relevé par l'audit
------------------------------

Le chemin reverse base de données pratique un Context Engineering de très bon
niveau : budget borné, slicing par objet, packs, échelle de dégradation
DÉCLARÉE (`db_context_slice.TABLE_DETAIL_LADDER`), et un manifeste qui dit à
l'agent ce qui lui a été retiré — pour qu'il baisse sa confiance en
connaissance de cause plutôt que d'affirmer sur du vide.

Le chemin forward ne pratique rien de tout cela. Les agents lisent les stacks
ENTIERS : 40 à 100 KB par fichier, 184 KB pour les 8 stacks actifs d'un projet
type. Conséquence mesurée : l'agent `arch` dépasse son propre budget de
contexte (188 034 o > 180 000) sur un workspace VIDE, et la gate qui mesure ce
budget est bloquante. Le pipeline s'arrête avant d'écrire une ligne de code.

Ce module applique au forward le principe déjà éprouvé côté DB :

    Un agent ne lit jamais tout le contexte disponible. Le framework lui
    construit un pack adapté à son rôle et à son budget, et lui déclare ce
    qui a été retiré.

Chaîne : Source → Pertinence → Priorité → Budget → Slice → Pack → Agent.

Pourquoi par mots-clés et non par numéro de section
--------------------------------------------------

Tentant d'écrire « `arch` lit §1.3, §2.2.1, §2.4, §15 ». Impossible : les
titres des stacks ne sont PAS canoniques d'une dimension à l'autre. Dans
`dotnet-minimalapi.md`, §7 est « CORS » ; dans `kotlin-spring-boot.md`, §6 est
« Interdits projet » ; `shadcn.md` numérote encore autrement. Un profil par
numéro casserait au premier stack ajouté. La pertinence est donc décidée sur le
TITRE de la section, ce qui survit à la renumérotation.

Le biais est volontairement vers la conservation
------------------------------------------------

Retirer une section dont l'agent avait besoin dégrade la génération en
silence — c'est bien pire que le coût en tokens qu'on cherchait à éviter.
D'où trois niveaux et non deux :

    needed    le rôle en a besoin — JAMAIS retiré, même hors budget
    unneeded  le rôle n'en a certainement pas besoin — retiré d'office
    neutral   indécidable — conservé, sauf si le budget l'exige

Et l'échelle de dégradation, quand `unneeded` ne suffit pas à tenir le
budget, retire les sections `neutral` **de la plus grosse à la plus petite** :
maximiser l'économie par section sacrifiée minimise le nombre de sections
sacrifiées.

Stabilité du préfixe = le vrai levier de cache
----------------------------------------------

`cache_control.py` (425 L) cherchait à poser des marqueurs de prompt-caching
Anthropic. Impossible sous Claude Code : le framework ne possède pas la boucle
d'inférence. Ce qu'il contrôle, en revanche, c'est l'ORDRE de ce qu'il fait
lire. `build_pack` émet toujours ses sources du plus stable au plus volatil
(`STABILITY_ORDER`), à contenu égal donc byte-identique d'un spawn à l'autre.
C'est le gain visé par les marqueurs, obtenu sans marqueur.

API publique
------------
    split_sections(text)                        -> list[Section]
    classify(role, title)                       -> "needed"|"unneeded"|"neutral"
    slice_markdown(text, role, ...)             -> (text, manifest)
    build_pack(role, sources, budget_bytes=...) -> (text, manifest)
    ROLES / STABILITY_ORDER / ROLE_PROFILES
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = [
    "ROLES",
    "ROLE_PROFILES",
    "STABILITY_ORDER",
    "RELEVANCE",
    "Section",
    "PackSource",
    "split_sections",
    "classify",
    "slice_markdown",
    "build_pack",
    "role_for_agent",
    "fingerprint_of",
]

#: Niveaux de pertinence, du plus protégé au plus sacrifiable.
RELEVANCE: tuple[str, ...] = ("needed", "neutral", "unneeded")

#: Rôles de consommation. Plusieurs agents partagent un rôle quand leurs
#: besoins de lecture sont identiques — inutile de multiplier les profils.
ROLES: tuple[str, ...] = ("arch", "backend", "frontend", "qa", "review", "spec")

#: agent → rôle. Un agent inconnu tombe sur `spec` (le profil le plus
#: conservateur : il ne retire presque rien). Fail-safe vers la conservation.
_AGENT_ROLE: dict[str, str] = {
    "arch": "arch",
    "constitutioner": "arch",
    "dev-backend": "backend",
    "dev-frontend": "frontend",
    "qa": "qa",
    "code-reviewer": "review",
    "security-reviewer": "review",
    "arch-reviewer": "review",
    "adversarial-reviewer": "review",
    "spec-compliance-reviewer": "spec",
    "po": "spec",
    "elicitor": "spec",
}


def role_for_agent(agent: str) -> str:
    return _AGENT_ROLE.get((agent or "").strip().lower(), "spec")


# --------------------------------------------------------------------------- #
# Profils de pertinence — par mots-clés de titre, insensibles à la casse et
# aux accents. Les listes sont volontairement courtes : chaque entrée doit
# être défendable, une liste fourre-tout ne se maintient pas.
# --------------------------------------------------------------------------- #

ROLE_PROFILES: dict[str, dict[str, tuple[str, ...]]] = {
    # `arch` bootstrappe et configure. Il a besoin du mapping de couches, des
    # commandes d'init, du catalogue de libs, de l'arborescence cible et des
    # variables/ports à propager. Il n'écrit AUCUN code applicatif — donc
    # aucune convention d'usage, aucun composant, aucun style.
    "arch": {
        "needed": (
            "architecture", "couche", "layer", "mapping", "repertoire",
            "structure", "arborescence", "init", "setup", "outil", "tool",
            "librairie", "library", "stack", "identite", "variable", "config",
            "url", "port", "connection", "persistence", "base de donnee",
            "database", "interdit", "hors scope", "principe", "nommage",
            "naming",
        ),
        "unneeded": (
            "convention", "philosophie", "accessibilite", "seo",
            "performance", "navigation", "theming", "interaction", "layout",
            "formulaire", "form", "styling", "multilingue", "state management",
            "symptome", "data handling", "mapping html", "mapping fonctionnel",
            "recommended skills", "logging",
        ),
    },
    # `dev-backend` écrit le code serveur : couches, conventions de lib,
    # persistence, contrats API, erreurs de compilation, CORS, logging.
    # Tout ce qui relève du rendu est hors de son périmètre.
    "backend": {
        "needed": (
            "architecture", "couche", "layer", "mapping", "stack", "librairie",
            "library", "convention", "persistence", "base de donnee", "database",
            "api", "versioning", "cors", "url", "logging", "erreur", "error",
            "security header", "connection", "swagger", "interdit",
            "hors scope", "principe", "multilingue",
        ),
        "unneeded": (
            "layout", "theming", "navigation", "seo", "accessibilite",
            "styling", "formulaire", "design system", "composant",
            "philosophie", "mapping html", "interaction", "data handling",
            "state management", "recommended skills",
        ),
    },
    # `dev-frontend` traduit le mockup vers le design system : conventions,
    # composants, layout, theming, formulaires, state, i18n, a11y.
    # La persistence et les détails serveur ne l'intéressent pas.
    "frontend": {
        "needed": (
            "architecture", "couche", "layer", "stack", "librairie", "library",
            "convention", "composant", "layout", "theming", "navigation",
            "interaction", "state", "formulaire", "form", "styling",
            "accessibilite", "mapping", "design system", "multilingue", "url",
            "interdit", "hors scope", "principe", "data handling", "identite",
            "integration", "seo", "performance", "logging", "erreur", "error",
        ),
        "unneeded": (
            "persistence", "swagger", "connection", "versioning des api",
            "security header", "base de donnee", "database", "cors",
            "recommended skills", "symptome",
        ),
    },
    # `qa` a besoin des commandes de test, du catalogue de libs de test, des
    # contrats d'API et des ports. Ni style ni navigation.
    "qa": {
        "needed": (
            "stack", "outil", "tool", "librairie", "library", "test", "url",
            "port", "commande", "api", "interdit", "hors scope", "erreur",
            "error", "connection", "base de donnee", "database",
        ),
        "unneeded": (
            "theming", "layout", "navigation", "seo", "philosophie",
            "design system", "mapping html", "interaction", "styling",
            "accessibilite", "multilingue", "recommended skills", "symptome",
        ),
    },
    # Les reviewers jugent le code contre les contraintes déclarées : couches,
    # interdits, principes, libs autorisées. Ils n'ont pas besoin des
    # procédures d'installation.
    "review": {
        "needed": (
            "architecture", "couche", "layer", "mapping", "interdit",
            "hors scope", "principe", "librairie", "library", "convention",
        ),
        "unneeded": (
            "init", "setup", "outil", "tool", "commande", "url", "port",
            "swagger", "symptome", "recommended skills", "philosophie",
        ),
    },
    # Profil de repli, le plus conservateur : rien n'est retiré d'office.
    "spec": {"needed": (), "unneeded": ()},
}

#: Marqueurs d'auteur qui protègent une section pour TOUS les rôles.
#:
#: Découvert en auditant les retraits réels du profil `arch` : il écartait
#: « 2.6 Conventions REST API (load-bearing — anti-divergence cross-US) » et
#: « 13.1 Waterfalls réseau (CRITIQUE) ». Ces sections portent, dans leur
#: propre titre, un signal posé par l'auteur du stack. Une décision de PACKING
#: ne doit pas écraser une décision d'AUTEUR : celui qui a écrit le stack en
#: sait plus long sur l'importance de sa section que la table de mots-clés
#: ci-dessus.
#:
#: Le garde-fou coûte du volume (il réduit le gain de `arch` d'environ un
#: tiers) et c'est le bon arbitrage : un retrait erroné dégrade la génération
#: en silence, un octet de trop se voit dans le budget.
AUTHOR_PROTECTED_MARKERS: tuple[str, ...] = (
    "load-bearing", "load bearing", "critique", "critical", "obligatoire",
    "non negociable", "non-negociable", "hard-gate", "hard gate", "interdit",
)

#: Ordre d'émission des sources dans un pack, du plus stable au plus volatil.
#: Load-bearing pour le cache de préfixe (cf. docstring du module) : à contenu
#: égal, un pack doit être byte-identique d'un spawn à l'autre.
STABILITY_ORDER: tuple[str, ...] = (
    "rule",       # règles cross-agent — invariantes inter-projets
    "stack",      # stacks actifs — invariants par projet
    "project",    # CLAUDE.md projet, constitution, schema.json — invariants par FEAT
    "artifact",   # FEAT, US, plan, mockup — volatiles par US
    "runtime",    # erreurs de build, sorties d'agents précédents — volatiles par itération
)


# --------------------------------------------------------------------------- #
# Découpage
# --------------------------------------------------------------------------- #

@dataclass
class Section:
    """Une unité de slicing : un `##`, ou un `###` avec son `##` parent.

    ``parent`` porte le titre du `##` englobant (vide pour un `##` lui-même).
    La pertinence se décide sur ``title`` d'abord, puis sur ``parent`` en
    repli — un `### 3.4 React Hook Form` hérite du contexte de son
    `## 3. Conventions d'usage`.
    """
    title: str
    level: int
    body: str
    start_line: int
    parent: str = ""

    @property
    def size(self) -> int:
        return len(self.title) + len(self.body) + 5

    def render(self) -> str:
        if self.title == "__preamble__":
            return self.body
        return f"{'#' * self.level} {self.title}\n{self.body}"


_HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)$")


def split_sections(text: str) -> list[Section]:
    """Découpe un Markdown en unités de slicing, `###` compris.

    Le découpage descend au niveau `###`, et ce n'est pas un détail : mesuré
    sur les stacks réels du dépôt, `kotlin-spring-boot.md` porte **7** sections
    `##` pour **30** sous-sections `###`, et `react.md` 17 pour 24. Un slicing
    limité au niveau `##` ne retirait que 5 % du volume — la granularité utile
    vit un niveau plus bas, parce que c'est là que les stacks séparent
    réellement les préoccupations (`### 2.2.1 Init Commands` pour `arch`,
    `### 3.4 Formulaires` pour `dev-frontend`).

    Le préambule (avant le premier `##` : frontmatter et titre `#`) forme une
    unité nommée ``__preamble__``, TOUJOURS conservée — elle porte l'identité
    du fichier, et un stack décapité devient anonyme pour l'agent.

    Le texte d'un `##` situé AVANT son premier `###` reste attaché au `##` :
    c'est son chapeau, souvent porteur de la règle générale que les `###`
    déclinent.
    """
    lines = text.splitlines()
    units: list[Section] = []
    cur_title, cur_level, cur_start, cur_parent = "__preamble__", 1, 1, ""
    cur: list[str] = []

    def flush() -> None:
        units.append(Section(cur_title, cur_level, "\n".join(cur).strip("\n"),
                             cur_start, cur_parent))

    last_h2 = ""
    for i, line in enumerate(lines, start=1):
        m = _HEADING_RE.match(line)
        if not m:
            cur.append(line)
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        flush()
        if level == 2:
            last_h2 = title
            cur_parent = ""
        else:
            cur_parent = last_h2
        cur_title, cur_level, cur_start = title, level, i
        cur = []
    flush()
    return [u for u in units if u.title == "__preamble__" or u.body or u.title]


# --------------------------------------------------------------------------- #
# Pertinence
# --------------------------------------------------------------------------- #

def _fold(s: str) -> str:
    """Minuscules sans accents — pour que « accessibilité » matche « accessibilite »."""
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def classify(role: str, title: str, parent: str = "") -> str:
    """Pertinence d'une unité pour un rôle : ``needed`` | ``unneeded`` | ``neutral``.

    Deux règles, dans cet ordre.

    **`needed` l'emporte sur `unneeded` au même niveau.** Exemple réel :
    « 5. URLs / CORS / Multilingue / Logging / OpenAPI » (kotlin-spring-boot)
    matche `url` et `cors` (requis côté backend) ET `multilingue` (inutile côté
    arch). Une section fourre-tout se conserve dès qu'une seule de ses parties
    est requise — la scinder serait modifier le stack, pas décider d'un pack.

    **Le titre décide ; le parent n'est consulté qu'en repli.** Un
    `### 2.2.1 Init Commands` tranche seul (requis pour `arch`) même si son
    parent `## 2. Stack` est neutre. Mais un `### 3.6 Hooks React` que rien
    dans son propre titre ne qualifie hérite de `## 3. Conventions d'usage`,
    et devient donc `unneeded` pour `arch`. Sans cet héritage, les 24 `###` de
    `react.md` resteraient tous neutres et le slicing ne retirerait rien.
    """
    if title == "__preamble__":
        return "needed"
    folded_title = _fold(title)
    if any(mk in folded_title for mk in AUTHOR_PROTECTED_MARKERS):
        return "needed"
    profile = ROLE_PROFILES.get(role) or ROLE_PROFILES["spec"]
    own = _match(profile, title)
    if own != "neutral":
        return own
    return _match(profile, parent) if parent else "neutral"


def _match(profile: dict[str, tuple[str, ...]], title: str) -> str:
    folded = _fold(title)
    if any(k in folded for k in profile["needed"]):
        return "needed"
    if any(k in folded for k in profile["unneeded"]):
        return "unneeded"
    return "neutral"


# --------------------------------------------------------------------------- #
# Slicing d'un fichier
# --------------------------------------------------------------------------- #

def slice_markdown(
    text: str,
    role: str,
    *,
    budget_bytes: int | None = None,
    drop_unneeded: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Réduit un Markdown au périmètre utile à ``role``.

    Retourne ``(texte, manifeste)``. Le manifeste liste chaque section retirée
    avec sa taille et la raison — c'est ce qui permet à l'agent de savoir ce
    qu'il n'a pas vu, au lieu de l'ignorer.

    Échelle de dégradation, dans cet ordre :
      1. sections ``unneeded`` (si ``drop_unneeded``) ;
      2. si ``budget_bytes`` est encore dépassé, sections ``neutral`` de la
         plus grosse à la plus petite, jusqu'à tenir ;
      3. les sections ``needed`` ne sont JAMAIS retirées — un pack hors budget
         est signalé (``over_budget: True``) plutôt que amputé de l'essentiel.
    """
    sections = split_sections(text)
    kept: list[Section] = []
    dropped: list[dict[str, Any]] = []

    for s in sections:
        rel = classify(role, s.title, s.parent)
        if rel == "unneeded" and drop_unneeded:
            dropped.append({"title": s.title, "bytes": s.size,
                            "relevance": rel, "reason": f"hors périmètre du rôle {role}"})
        else:
            kept.append(s)

    if budget_bytes:
        neutrals = sorted(
            [s for s in kept if classify(role, s.title, s.parent) == "neutral"],
            key=lambda s: -s.size,
        )
        for s in neutrals:
            if _render_size(kept) <= budget_bytes:
                break
            kept.remove(s)
            dropped.append({"title": s.title, "bytes": s.size, "relevance": "neutral",
                            "reason": "retirée pour tenir le budget de contexte"})

    rendered = _render(kept)
    return rendered, {
        "role": role,
        "sections_total": len(sections),
        "sections_kept": len(kept),
        "sections_dropped": dropped,
        "bytes_before": len(text),
        "bytes_after": len(rendered),
        "over_budget": bool(budget_bytes and len(rendered) > budget_bytes),
    }


def _render(sections: Sequence[Section]) -> str:
    return "\n\n".join(
        s.render() for s in sections if s.render().strip()
    ).strip() + "\n"


def _render_size(sections: Sequence[Section]) -> int:
    return len(_render(sections))


# --------------------------------------------------------------------------- #
# Assemblage du pack
# --------------------------------------------------------------------------- #

@dataclass
class PackSource:
    """Une source à intégrer au pack.

    ``stability`` pilote l'ordre d'émission (cf. ``STABILITY_ORDER``) ;
    ``sliceable`` dit si le contenu peut être réduit par section — un artefact
    (US, FEAT, plan) ne l'est jamais : il est déjà le sujet de la tâche.
    """
    path: str
    stability: str = "stack"
    sliceable: bool = True
    label: str | None = None
    text: str | None = field(default=None, repr=False)


def fingerprint_of(sources: Iterable[PackSource], root: Path | None = None) -> str:
    """Empreinte attendue d'un jeu de sources, sans assembler le pack.

    Utilisée par la gate de budget pour décider si un pack sur disque est
    encore à jour — recalculer l'empreinte coûte quelques millisecondes, alors
    que reconstruire le pack pour comparer coûterait le slicing complet.
    """
    base = Path(root) if root is not None else Path.cwd()
    resolved: list[tuple[PackSource, str]] = []
    for src in sources:
        if src.text is not None:
            resolved.append((src, src.text))
            continue
        p = Path(src.path)
        if not p.is_absolute():
            p = base / p
        try:
            resolved.append((src, p.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            # Source annoncée mais illisible : elle DOIT peser dans l'empreinte,
            # sinon l'apparition d'un fichier absent au moment du build passerait
            # pour un jeu de sources inchangé.
            resolved.append((src, "<unreadable-source>"))
    return _fingerprint(resolved)


def build_pack(
    role: str,
    sources: Iterable[PackSource],
    *,
    budget_bytes: int | None = None,
    root: Path | None = None,
    agent: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Assemble un pack de contexte borné et auto-descriptif.

    Le pack s'ouvre sur son propre manifeste — même intention que
    ``db_context_slice`` : un agent qui reçoit une vue tronquée doit le SAVOIR
    pour abaisser sa confiance en conséquence, plutôt que d'affirmer avec
    aplomb sur ce qu'il n'a pas lu.

    Le budget est réparti proportionnellement : chaque source sliceable reçoit
    une part du budget au prorata de sa taille d'origine. Une source qui pèse
    la moitié du corpus reçoit la moitié du budget — pas de premier arrivé
    premier servi, qui laisserait la dernière source affamée selon l'ordre
    d'itération.
    """
    base = Path(root) if root is not None else Path.cwd()
    # Materialise : l'empreinte doit porter sur le MEME ensemble que
    # `fingerprint_of`, sources absentes comprises, et un iterable ne se
    # parcourt qu'une fois.
    declared = list(sources)
    resolved: list[tuple[PackSource, str]] = []
    missing: list[str] = []

    for src in declared:
        if src.text is not None:
            resolved.append((src, src.text))
            continue
        p = Path(src.path)
        if not p.is_absolute():
            p = base / p
        if not p.is_file():
            missing.append(src.path)
            continue
        try:
            resolved.append((src, p.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            missing.append(src.path)

    resolved.sort(key=lambda t: (
        STABILITY_ORDER.index(t[0].stability)
        if t[0].stability in STABILITY_ORDER else len(STABILITY_ORDER),
        t[0].path,
    ))

    sliceable_bytes = sum(len(txt) for s, txt in resolved if s.sliceable)
    parts: list[str] = []
    per_source: list[dict[str, Any]] = []

    for src, text in resolved:
        if not src.sliceable:
            parts.append(_wrap(src, text))
            per_source.append({
                "path": src.path, "stability": src.stability, "sliced": False,
                "bytes_before": len(text), "bytes_after": len(text),
                "sections_dropped": [],
            })
            continue
        share = None
        if budget_bytes and sliceable_bytes:
            share = max(2_000, int(budget_bytes * len(text) / sliceable_bytes))
        sliced, man = slice_markdown(text, role, budget_bytes=share)
        parts.append(_wrap(src, sliced))
        per_source.append({
            "path": src.path, "stability": src.stability, "sliced": True,
            "bytes_before": man["bytes_before"], "bytes_after": man["bytes_after"],
            "sections_dropped": man["sections_dropped"],
        })

    body = "\n\n".join(parts)
    total_before = sum(s["bytes_before"] for s in per_source)
    manifest = {
        "agent": agent,
        "role": role,
        "sources": per_source,
        "missing_sources": missing,
        "bytes_before": total_before,
        "budget_bytes": budget_bytes,
        "stability_order": [s["path"] for s in per_source],
    }
    # Le manifeste et les marqueurs de source font PARTIE de ce que l'agent
    # lit : les exclure du total donnerait un gain flatteur et une gate de
    # budget fausse. On mesure donc le texte final, en entier, et on isole
    # l'overhead pour qu'il soit discutable au lieu d'être caché.
    #
    # Le manifeste annonce une taille qui l'inclut lui-même : point fixe. Deux
    # itérations suffisent en pratique (seul le nombre de chiffres du total
    # peut changer, et il change au plus une fois). La borne à 3 garantit la
    # terminaison si un cas pathologique oscillait.
    # Empreinte des sources : sha256 de « chemin:hash-du-contenu » trié.
    #
    # Load-bearing pour la sûreté du dispositif. Dès que le pack REMPLACE les
    # stacks dans `loader.yml`, un pack périmé nourrirait l'agent de contenu
    # obsolète sans que rien ne le signale. L'empreinte permet à la gate de
    # budget de refuser un pack qui ne correspond plus à ses sources — un
    # refus bruyant valant infiniment mieux qu'une génération silencieusement
    # fondée sur un stack d'hier.
    manifest["sourcesFingerprint"] = fingerprint_of(declared, root=base)

    def _set_derived(after: int) -> None:
        manifest["bytes_after"] = after
        # Signé : un pack peut légitimement GROSSIR quand rien n'est retiré
        # (les marqueurs coûtent quelques centaines d'octets). Le dire est
        # plus utile que d'afficher « -0.2 % » d'un gain qui n'existe pas.
        manifest["reduction_pct"] = (
            round(100.0 * (total_before - after) / total_before, 1)
            if total_before else 0.0
        )
        manifest["over_budget"] = bool(budget_bytes and after > budget_bytes)

    _set_derived(len(body))
    header = _header(manifest)
    for _ in range(3):
        total = len(header) + 2 + len(body)
        if total == manifest["bytes_after"]:
            break
        _set_derived(total)
        header = _header(manifest)
    text = header + "\n\n" + body
    _set_derived(len(text))
    manifest["overhead_bytes"] = len(header) + sum(
        len(f"<!-- pack-source: {s.label or s.path} ({s.stability}) -->\n")
        for s, _ in resolved
    )
    return text, manifest


def _fingerprint(resolved) -> str:
    """Empreinte du JEU DE SOURCES d'un pack, insensible à l'ordre.

    Chaque source contribue `chemin:sha256(contenu normalisé)`. La
    normalisation des fins de ligne est celle du journal : sans elle, un clone
    sous Windows produirait une empreinte différente à contenu identique
    et invaliderait tous les packs.
    """
    parts = []
    for src, text in resolved:
        norm = (text or "").replace("\r\n", "\n")\
                            .replace("\r", "\n").rstrip()
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        parts.append(f"{src.path}:{h}")
    joined = "\n".join(sorted(parts))
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _wrap(src: PackSource, text: str) -> str:
    label = src.label or src.path
    return f"<!-- pack-source: {label} ({src.stability}) -->\n{text.strip()}"


def _header(m: dict[str, Any]) -> str:
    """Manifeste en tête de pack, lisible par l'agent."""
    dropped_total = sum(len(s["sections_dropped"]) for s in m["sources"])
    lines = [
        "<!-- SDD_Pro context pack -->",
        f"<!-- sourcesFingerprint: {m.get('sourcesFingerprint', 'n/a')} -->",
        f"# Contexte fourni — rôle `{m['role']}`"
        + (f" (agent `{m['agent']}`)" if m.get("agent") else ""),
        "",
        f"Ce pack a été construit pour ta tâche. Il ne contient PAS tout le "
        f"contexte disponible : {m['bytes_before']:,} o réduits à "
        f"{m['bytes_after']:,} o ({m['reduction_pct']}% de moins), "
        f"{dropped_total} section(s) retirée(s).".replace(",", " "),
        "",
        "**Si une information te manque, dis-le et abaisse ta confiance — "
        "n'invente pas ce qui a été retiré.** Les sections écartées le sont "
        "parce qu'elles sont hors du périmètre de ton rôle ou du budget, pas "
        "parce qu'elles n'existent pas.",
        "",
    ]
    if dropped_total:
        lines.append("## Sections retirées")
        lines.append("")
        for s in m["sources"]:
            if not s["sections_dropped"]:
                continue
            lines.append(f"- `{s['path']}` :")
            for d in s["sections_dropped"]:
                lines.append(f"  - {d['title']} ({d['bytes']} o) — {d['reason']}")
        lines.append("")
    if m["missing_sources"]:
        lines.append("## Sources annoncées mais absentes du disque")
        lines.append("")
        for p in m["missing_sources"]:
            lines.append(f"- `{p}`")
        lines.append("")
    if m["over_budget"]:
        lines.append(
            "> ⚠️ Le pack dépasse encore son budget après dégradation : toutes "
            "les sections restantes sont nécessaires à ton rôle. Signale-le "
            "plutôt que de tronquer ta lecture."
        )
        lines.append("")
    return "\n".join(lines).rstrip()
