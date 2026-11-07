"""Extraction défensive des identifiants FEAT / US depuis du texte libre.

Factorisé 2026-11-07 depuis `sdd_hooks/record_token_usage.py` (audit
télémétrie) pour être partagé avec `sdd_hooks/enforce_phase_order.py`.

L'ancien motif `\\b(\\d{1,3})-(\\d{1,3})` prenait n'importe quel « N-M » d'un
prompt libre pour une US — dates (`2026-10-10` → US `10-10`), plages de lignes
(`84-92`, `201-215`). Deux défenses :
  1. `US_RE` refuse un N-M précédé d'un mot / `-` / `.` / `:` ou suivi d'un
     séparateur + chiffre (dates, versions, heures) — un chemin
     `workspace/us/15-1-Name.md` ou une fin de phrase `US 15-2.` restent lus ;
  2. `known_ids()` confronte chaque candidat aux US/FEAT réellement présentes
     sur disque (`workspace/us/{n}-{m}-*.md`, `workspace/feats/{n}-*.md`) —
     seule parade contre une plage `84-92`, syntaxiquement identique à une US.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Set, Tuple

from sdd_lib.paths import repo_root, workspace_root

US_RE = re.compile(
    r"(?<![\w\-.:])(\d{1,3})-(\d{1,3})(?:-[A-Za-z][A-Za-z0-9\-]*)?(?!\w|[\-.:/]\d)"
)
US_FILE_RE = re.compile(r"^(\d{1,3})-(\d{1,3})-")
FEAT_FILE_RE = re.compile(r"^(\d{1,3})-[A-Za-z]")

KnownIds = Tuple[Set[str], Set[int]]


def known_ids(root: Path | None = None) -> KnownIds | None:
    """US ids (`n-m`) and FEAT numbers present on disk, or None if unknowable.

    None (workspace introuvable ou sans aucune US/FEAT) → pas de validation :
    l'extraction retombe sur le seul contrat syntaxique.
    """
    try:
        ws = workspace_root(root or repo_root())
        us = {f"{int(m.group(1))}-{int(m.group(2))}"
              for f in (ws / "us").glob("*.md") if (m := US_FILE_RE.match(f.name))}
        feats = {int(m.group(1))
                 for f in (ws / "feats").glob("*.md") if (m := FEAT_FILE_RE.match(f.name))}
    except OSError:
        return None
    if not us and not feats:
        return None
    return us, feats


def iter_us_candidates(text: str, known: KnownIds | None = None) -> Iterator[tuple[int, str]]:
    """`(feat_n, "n-m")` des US plausibles de `text`, dans l'ordre d'apparition.

    `known` fourni : une US absente du disque est ignorée. Si aucune US n'est
    encore sur disque (FEAT pas encore découpée) mais que des FEAT existent, le
    numéro de FEAT du candidat doit au moins exister.
    """
    known_us, known_feats = known if known is not None else (set(), set())
    for m in US_RE.finditer(text or ""):
        n, us_id = int(m.group(1)), f"{int(m.group(1))}-{int(m.group(2))}"
        if known is not None:
            if known_us and us_id not in known_us:
                continue
            if not known_us and known_feats and n not in known_feats:
                continue
        yield n, us_id
