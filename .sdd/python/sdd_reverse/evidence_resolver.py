"""evidence_resolver.py — Resolve `<!-- evidence: path:Lx-Ly -->` refs ON DISK.

The reverse module's headline guarantee is that every FEAT / US / task claim
carries a `file:line` citation back into the legacy source. Until the audit of
2026-08-29 that guarantee was checked for **presence** only on the CODE path
(`bool(_EVIDENCE_RE.search(block))`) — a fabricated citation pointing at a file
that does not exist, or at line 400 of a 40-line file, passed every gate. Only
the DB path resolved its snapshot references, and even there only file
existence, never the line range.

This module is the single deterministic resolver (0 token, stdlib only,
D4-isolated) used by:
    - `check_ladder_traceability.py` (FEAT items + 3a tasks, code ladder)
    - `validate_reverse_feat.py`     (per-item evidence of a reverse FEAT)

Contract (`rules/reverse-engineering.md §3`) — an evidence ref is
`path/relative.ext:Lstart-Lend`, `path` relative to `workspace/old/{P}/`,
`L` prefix optional, a single line tolerated (`path:42`). Several refs may be
comma-separated; the FIRST one is the load-bearing citation and is the one
resolved (the others are corroboration).

Tri-state result, because a false accusation is worse than a missed gap
(`bias toward not-verified` applies to CLAIMS, not to the checker itself):

    True  — the file exists AND holds at least `Lend` lines
    False — the ref cannot be honoured (placeholder `unknown`, missing file,
            line range beyond EOF) → emit [REVERSE_EVIDENCE_MISSING]
    None  — undecidable (no project root supplied, file unreadable) → skip

Public API:
    resolve_evidence(project_root, evidence) -> bool | None
    parse_evidence_ref(evidence) -> tuple[str, int | None] | None
"""

from __future__ import annotations

import re
from pathlib import Path

# `path/to/File.cs:L34-L38` | `path:34-38` | `path:34` (single line)
_EV_REF_RE = re.compile(r"^(.*?):[Ll]?(\d+)(?:\s*-\s*[Ll]?(\d+))?$")

#: The assembler's "I have no evidence" placeholder — never resolves, by design.
PLACEHOLDER_PATHS = frozenset({"unknown", "n/a", "none", "-"})


def parse_evidence_ref(evidence: str) -> tuple[str, int | None] | None:
    """Split the FIRST ref of an evidence comment into (path, last_line).

    `last_line` is the highest line number cited (the range end, or the single
    line). None when the ref carries no line number at all. Returns None when
    `evidence` is empty.
    """
    if not evidence:
        return None
    ref = evidence.split(",")[0].strip()
    if not ref:
        return None
    m = _EV_REF_RE.match(ref)
    if not m:
        return (ref, None)
    path = m.group(1).strip()
    last = int(m.group(3) or m.group(2))
    return (path, last)


def _line_count_at_least(path: Path, at_least: int) -> int | None:
    """Count lines in `path`, short-circuiting once `at_least` is reached.

    Bounded on purpose: a multi-hundred-MB legacy dump must not be walked to
    the end just to confirm that line 38 exists. None on any I/O error.
    """
    count = 0
    try:
        with path.open("rb") as fh:
            for _ in fh:
                count += 1
                if count >= at_least:
                    return count
    except OSError:
        return None
    return count


def resolve_evidence(
    project_root: str | Path | None, evidence: str, *, check_lines: bool = True,
) -> bool | None:
    """Does an `path:Lx-Ly` evidence ref point at a real file AND a real range?

    See the module docstring for the tri-state contract. `project_root` is the
    legacy project directory (`workspace/old/{P}/`) the paths are relative to;
    None means "cannot be decided here" (e.g. the checker was invoked with
    `--feat-path` alone, with no inventory to locate the legacy source).

    `check_lines=False` degrades to file-existence only. It exists for the DB
    ladder, whose snapshot citations are emitted by the deterministic assembler
    against a body it has just written — the file identity is the signal there,
    and its established contract predates this resolver. The CODE ladder, where
    the citation is written by an LLM, always resolves the range.
    """
    if project_root is None or not evidence:
        return None
    parsed = parse_evidence_ref(evidence)
    if parsed is None:
        return None
    path, last = parsed
    if not path or path.lower() in PLACEHOLDER_PATHS:
        return False
    target = Path(project_root) / path
    if not target.is_file():
        return False
    if last is None or not check_lines:
        return True  # file-level citation — nothing more to verify
    n_lines = _line_count_at_least(target, last)
    if n_lines is None:
        return None  # unreadable → undecidable, never a fabricated accusation
    return n_lines >= last
