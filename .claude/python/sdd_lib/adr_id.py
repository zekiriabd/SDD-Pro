"""SDD_Pro — Deterministic ADR filename minter (audit 2026-06-06 RUPT-6).

Background
----------
`rules/ownership.md` Partie A §3 + Partie B §4.1 promise that ADR filenames
follow ``ADR-{YYYYMMDDTHHmmss}-{slug}.md`` with a ``-{rand4}`` suffix added
on second-collision within the same UTC second. **No Python implementation
existed** — the slug was generated inside the LLM prompt via
``date -u +%Y%m%dT%H%M%S``, which means two parallel agents (e.g.
`dev-backend` + `dev-frontend` on the same FEAT phase 6.c) finishing within
the same second would emit identical filenames and the second `Write` would
**silently overwrite** the first (Claude Code's `Write` tool overwrites by
default).

Live test (audit) : five calls to ``datetime.now().strftime("%Y%m%dT%H%M%S")``
in the same second return five identical strings. The collision risk is
real on busy `/dev-run` batches.

This module provides a deterministic helper that **always** appends a 4-char
hex random suffix (``secrets.token_hex(2)``), promoting collision avoidance
from "documented intention" to "code invariant". The output matches the existing regex in `sdd_scripts/index_adrs.py`
(``^ADR-(\\d{8}T\\d{6})(?:-[a-z0-9]+)?-(.+)\\.md$``)

The middle segment `(?:-[a-z0-9]+)?` was already optional in v7.0.0 — this
module just stops making it optional and writes the rand4 systematically.

Usage
-----
::

    from sdd_lib.adr_id import mint_adr_filename
    fname = mint_adr_filename("stack-backend-dotnet")
    # -> "ADR-20260606T143022-a1f2-stack-backend-dotnet.md"

Cross-agent safety
------------------
Even if two agents call `mint_adr_filename` within the same UTC second, the
probability of the same `secrets.token_hex(2)` (4 hex chars = 16 bits =
65 536 values) is 1/65 536 ≈ 0.0015 %. For real safety against this
remaining tail risk, callers should use atomic create-then-fail (open with
``O_EXCL``) — see `sdd_lib.atomic_write` patterns. This module guarantees
**uniqueness with very high probability**, not strict atomicity.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

#: Slug constraints — kebab-case ASCII, max 5 words/40 chars per
#: ownership.md §3 ("max 5 mots significatifs"). Enforced lightly here
#: (silent truncation + sanitization) to avoid raising in mid-pipeline.
_SLUG_INVALID_RE = re.compile(r"[^a-z0-9-]+")
_SLUG_MAX_LEN = 40


def _sanitize_slug(slug: str) -> str:
    """Normalize an arbitrary slug to ``[a-z0-9-]{1,40}``.

    - Lowercase
    - Replace any non `[a-z0-9-]` run with `-`
    - Collapse multiple `-`
    - Strip leading/trailing `-`
    - Truncate to 40 chars
    - Fallback to "unnamed" if empty after sanitization
    """
    slug = (slug or "").strip().lower()
    slug = _SLUG_INVALID_RE.sub("-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = "unnamed"
    return slug[:_SLUG_MAX_LEN].rstrip("-") or "unnamed"


def mint_adr_filename(slug: str, *, when: datetime | None = None) -> str:
    """Return a collision-resistant ADR filename matching the v7.0.0 regex.

    Format::

        ADR-{YYYYMMDDTHHmmss}-{rand4}-{sanitized-slug}.md

    Where ``{rand4}`` is a 4-char lowercase hex string. The combination
    ``{timestamp}-{rand4}`` is unique with probability > 99.998 % per UTC
    second, even with multiple agents minting in parallel.

    Parameters
    ----------
    slug:
        Human-readable kebab-case identifier ("stack-backend-dotnet",
        "pagination-cursor-based", etc.). Sanitized via `_sanitize_slug`.
    when:
        Optional UTC datetime override (test injection). Defaults to
        ``datetime.now(timezone.utc)``.

    Returns
    -------
    str
        The filename (no leading directory). Caller writes to
        ``workspace/output/.sys/.context/adrs/{filename}``.
    """
    ts_source = when if when is not None else datetime.now(timezone.utc)
    ts = ts_source.strftime("%Y%m%dT%H%M%S")
    rand4 = secrets.token_hex(2)  # 4 lowercase hex chars (16 bits entropy)
    safe_slug = _sanitize_slug(slug)
    return f"ADR-{ts}-{rand4}-{safe_slug}.md"
