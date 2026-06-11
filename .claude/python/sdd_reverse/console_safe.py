"""console_safe.py — Windows cp1252 console crash guard (audit 2026-06-10 M10).

Five reverse scripts crashed with ``UnicodeEncodeError`` on Windows consoles
(cp1252) when printing arrows/emojis (``→``, ``🟢``, ``⚠️``) — including on the
NOMINAL path (preallocate_feats STEP 2.5). One-line fix per script entry point:

    from sdd_reverse.console_safe import ensure_console_safe
    ensure_console_safe()   # first line of main()

Reconfigures stdout/stderr to ``errors="replace"`` when the active encoding
cannot represent the full Unicode range. Payloads (JSON files on disk) are
NEVER altered — only the console rendering degrades (un-encodable chars → ?).
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
