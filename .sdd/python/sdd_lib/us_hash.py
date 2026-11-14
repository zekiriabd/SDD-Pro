"""SDD_Pro: empreinte d'une User Story pour la fraîcheur des plans (`us-hash`).

Défaut constaté le 2026-11-13 (FEAT 43) : `set_us_status.py` réécrit la ligne
`Status:` de l'US (Draft → Ready → InProgress → Review → Done) au fil du
pipeline. Avec une empreinte calculée sur le fichier brut, chaque transition de
statut rendait les plans « périmés » (`[PLAN_STALE]`) alors que le contenu
fonctionnel de l'US n'avait pas changé — `/dev-plan` lui-même passe les US en
InProgress juste après avoir validé ses plans.

`us_content_hash` neutralise la seule valeur du statut ; tout autre changement
de l'US (ACs, Covers, texte) change l'empreinte comme avant. `us_hash_candidates`
renvoie aussi l'empreinte historique du fichier brut, pour que les plans écrits
avant ce correctif restent reconnus frais tant que l'US n'a pas bougé.
"""
from __future__ import annotations

import hashlib
import re

# Même forme de ligne que set_us_status.STATUS_LINE_RE (valeur alphabétique seule).
_STATUS_VALUE_RE = re.compile(r"(?m)^(Status:)[ \t]*[A-Za-z]+[ \t]*(\r?)$")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def legacy_file_hash(text: str) -> str:
    """Empreinte historique : SHA-256 du texte brut de l'US (plans écrits avant 2026-11-13)."""
    return _sha256(text)


def us_content_hash(text: str) -> str:
    """Empreinte insensible au statut : SHA-256 de l'US avec la valeur de `Status:` neutralisée."""
    return _sha256(_STATUS_VALUE_RE.sub(r"\1\2", text))


def us_hash_candidates(text: str) -> tuple[str, str]:
    """Empreintes acceptées pour un plan frais : (insensible au statut, historique brute)."""
    return us_content_hash(text), legacy_file_hash(text)
