"""Shared helpers for CI ingest scripts (axe-core + Lighthouse).

Audit S3 (2026-07-26) extracts the 4 helpers duplicated byte-à-byte between
`sdd_scripts/ingest_axe.py` and `sdd_scripts/ingest_lighthouse.py` into a
single SSoT. The 2 scripts also share the CLI pattern (--report + --feat +
--threshold + --no-fail + --json + --delete-json) and the exit-code
convention (0=success, 1=missing, 2=parse, 3=schema, 4=verdict-red) but
those live in each script's `main()` where they're wired to script-specific
arg-parsing — attempting to share the CLI would produce a leaky abstraction.

**Scope** : STRICTLY the ingest_axe + ingest_lighthouse pair (Group B :
"external JSON tool report → qa_{a11y,performance} table via console_db
helpers"). NOT applicable to :
- `ingest_plans.py` / `ingest_feats_us.py` (Group A : workspace markdown
  scan → direct sqlite3 INSERT — different concern entirely) ;
- `ingest_agent_report.py` (Group C : agent report shape parsing, own
  verdict logic — its `_err_block` has different return semantics).

Intentionally NOT abstracted here to avoid forcing a "one-size-fits-all"
API on 3 scripts that don't share this concern. If a future script joins
Group B (e.g. wrk/k6 SLO ingest — roadmap), it imports from this module.
"""

from __future__ import annotations

import sys
from typing import Any

__all__ = [
    "SEVERITY_RANK",
    "DEFAULT_THRESHOLD",
    "emit_error_block",
    "compute_verdict",
]


#: Severity ordinal — sort highest first ; threshold compares `>=`.
#: Aligned with legacy A11yFailOn / PerfFailOn Project Config values.
SEVERITY_RANK: dict[str, int] = {
    "critical": 4,
    "serious": 3,
    "moderate": 2,
    "minor": 1,
}

#: Default threshold for verdict computation. Matches legacy A11yFailOn
#: default (accessibility-auditor v6.3.0-v6.10) and PerfFailOn behaviour.
DEFAULT_THRESHOLD = "serious"


def emit_error_block(error: str, cause: str, fix: str, code: int) -> int:
    """Emit an SDD_Pro 3-line ERROR/CAUSE/FIX block to stderr, return `code`.

    Format canonique par `rules/error-classification.md §2`.
    Callers use `return emit_error_block(...)` as the exit-code source.

    Args:
        error: 1-liner problem summary (script + failure kind).
        cause: `[CLASS_PREFIX]` + short detail (taxonomie
               error-classification.md §1).
        fix:   1-liner remediation.
        code:  int exit code to return (script-specific : 1=missing,
               2=parse, 3=schema, 4=verdict-red per the axe/lighthouse
               contract).

    Returns:
        `code` — for use as `return emit_error_block(...)`.
    """
    sys.stderr.write(f"ERROR: {error}\nCAUSE: {cause}\nFIX: {fix}\n")
    return code


def compute_verdict(issues: list[dict[str, Any]], threshold: str) -> str:
    """Compute 🟢/🟡/🔴 verdict from issue set against severity threshold.

    - No issues → `"green"`
    - At least one issue with severity `>= threshold` → `"red"`
    - Otherwise → `"warn"` (issues present, all below threshold)

    Each issue is expected to have a `severity` key (str, lowercase — one
    of `critical|serious|moderate|minor` per `SEVERITY_RANK`). Missing or
    unknown severity is treated as `"moderate"` (bias to warn, not red).
    Missing/unknown threshold falls back to `DEFAULT_THRESHOLD` ("serious").

    Args:
        issues: list of dicts with at least a `"severity"` key.
        threshold: severity gate (`critical|serious|moderate|minor`).

    Returns:
        `"green"` | `"warn"` | `"red"`.
    """
    if not issues:
        return "green"
    thr_rank = SEVERITY_RANK.get(threshold.lower(), SEVERITY_RANK[DEFAULT_THRESHOLD])
    for it in issues:
        sev = (it.get("severity") or "moderate").lower()
        if SEVERITY_RANK.get(sev, 0) >= thr_rank:
            return "red"
    return "warn"
