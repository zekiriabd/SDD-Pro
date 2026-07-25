"""Helpers d'isolation des fixtures legacy (audit 2026-06-11).

Les scripts reverse (`reverse_inventory`, `generate_crosscutting_feats`, ...)
écrivent `.sys/` DANS le projet cible. Les tests ne doivent JAMAIS les
pointer sur `tests/fixtures/` directement : cela mute les baselines,
casse la reproductibilité (l'output d'un run devient l'input du suivant)
et laisse un drift git permanent. Copier d'abord la fixture via
`copy_legacy_fixture(name, tmp_path)` puis cibler la copie.

Les répertoires `.sys/` des fixtures sont gitignorés
(`.sdd/python/tests/fixtures/*/.sys/`) — ils sont régénérés, pas source.
"""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def copy_legacy_fixture(name: str, dst_root: Path) -> Path:
    """Copie `tests/fixtures/{name}` sous `dst_root` et retourne la copie.

    Le `.sys/` éventuel (résidu local d'un run précédent) n'est pas copié :
    chaque test part d'un projet legacy vierge, comme un vrai `workspace/old/`.
    """
    src = FIXTURES_DIR / name
    if not src.is_dir():
        raise FileNotFoundError(f"fixture legacy inconnue: {name} ({src})")
    dst = Path(dst_root) / name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".sys"))
    return dst
