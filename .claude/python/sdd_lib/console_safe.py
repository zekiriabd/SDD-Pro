"""console_safe.py — Windows cp1252 console crash guard (audit 2026-06-11 M15).

Port forward du guard reverse ``sdd_reverse/console_safe.py`` (audit M10) :
14 sites ``print()`` de sdd_scripts/sdd_admin émettent des flèches/emojis
(``→``, ``🟢``, ``🟡``) qui crashent en ``UnicodeEncodeError`` sur console
Windows cp1252 — y compris sur le chemin NOMINAL de ``/dev-run``
(``dev_run_args.py``). Le guard n'existait que côté reverse (D4) ; ce module
le porte dans sdd_lib pour les scripts forward. Une ligne par entry point :

    from sdd_lib.console_safe import ensure_console_safe
    ensure_console_safe()   # première ligne de main()

Reconfigure stdout/stderr en ``errors="replace"`` quand l'encodage actif ne
couvre pas tout Unicode. Les payloads (JSON disque) ne sont JAMAIS altérés —
seul le rendu console dégrade (caractères non encodables → ?).

NOTE D4 : sdd_reverse/console_safe.py reste la copie isolée du module reverse
(jamais d'import sdd_lib depuis sdd_reverse). Toute évolution doit être portée
dans les DEUX fichiers.
"""

from __future__ import annotations

import sys


def ensure_console_safe() -> None:
    """Make stdout/stderr non-crashing on narrow console encodings."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if enc in ("utf8", ""):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
