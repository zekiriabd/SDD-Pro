#!/usr/bin/env python3
"""SDD_Pro PostToolUse hook (Edit|Write|MultiEdit).

Verifies that after a code edit under workspace/output/src/, the
`preserves:` and `adds:` contracts declared in the matching plan
file are respected (deterministic substring check, 0 token LLM).

- If edited file is NOT under workspace/output/src/ -> exit 0 (skip)
- If tool_name == 'Write' (file creation) -> exit 0 (contract only on Edit)
- If file is a test file -> exit 0 (QA ownership)
- If no plan matches -> exit 0 (inline mode, can't validate)
- If preserves: violated -> exit 2 + ERROR [PRESERVES_VIOLATED]
- If adds: violated -> exit 2 + ERROR [ADDS_VIOLATED]

Migrated from .claude/scripts/validate-augment-contract.ps1 (2026-05-13).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import get_file_path, get_tool_name, read_hook_input  # noqa: E402
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.stderr import error_block  # noqa: E402


TEST_PATTERNS: tuple[str, ...] = (
    ".Tests/",
    "__tests__/",
    ".FEAT.",
    ".test.",
    "Tests.cs",
    "test_",
    "_test.py",
    "Test.kt",
    "FEAT.kt",
)


# Plan cache (M5 fix v7.0.0-alpha 2026-06-05) — PostToolUse Edit fires very
# often (~30-100×/run). Previously each fire re-read every plan file in
# `workspace/output/plans/*.md` from disk + ran regex finditer. With 5-10
# plans of 30-80 KB, that's ~5-15 MB I/O per Edit on the hot path.
# Cache invalidation = file mtime change (any plan edit busts entry).
_PLAN_CACHE: dict[str, tuple[float, str]] = {}  # path -> (mtime_ns, text)


def _read_plan_cached(plan_path: Path) -> str:
    """Read plan text with mtime-keyed cache. Returns '' on error."""
    try:
        st = plan_path.stat()
    except OSError:
        return ""
    key = str(plan_path)
    cached = _PLAN_CACHE.get(key)
    if cached is not None and cached[0] == st.st_mtime_ns:
        return cached[1]
    try:
        text = plan_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    _PLAN_CACHE[key] = (st.st_mtime_ns, text)
    return text


def _path_in_plan(plan_text: str, file_path: str, file_name: str) -> bool:
    return file_path in plan_text or file_name in plan_text


def _find_block_for_file(plan_text: str, normalized_file: str, file_name: str) -> str | None:
    """Extract the YAML-ish block dedicated to file_path inside the plan.

    Format:
        - path: workspace/output/src/.../File.kt
          operation: augment
          preserves: [ID1, ID2]
          adds: [ID3]
          covers_acs: [AC-3]
        - path: ... (next block)
    """
    block_iter = list(re.finditer(r"(?m)^[-\s]*path:\s*([^\r\n]+?)\s*$", plan_text))
    for i, m in enumerate(block_iter):
        start = m.start()
        end = block_iter[i + 1].start() if i + 1 < len(block_iter) else len(plan_text)
        candidate = normalize(m.group(1)).strip()
        candidate_leaf = candidate.rsplit("/", 1)[-1]
        if (
            candidate == normalized_file
            or normalized_file.endswith(candidate)
            or candidate_leaf == file_name
        ):
            return plan_text[start:end]
    return None


def _parse_id_list(text: str, key: str) -> list[str]:
    """Extract `key: [id1, id2, ...]` list from a YAML-ish block."""
    m = re.search(rf"(?ms){re.escape(key)}:\s*\[([^\]]*)\]", text)
    if not m:
        return []
    raw = m.group(1)
    items: list[str] = []
    for chunk in raw.split(","):
        cleaned = chunk.strip().strip('"').strip("'")
        if cleaned:
            items.append(cleaned)
    return items


def main() -> int:
    payload = read_hook_input()
    file_path = get_file_path(payload)
    if not file_path:
        return HOOK_ALLOW
    norm = normalize(file_path)
    if "workspace/output/src/" not in norm:
        return HOOK_ALLOW
    tool_name = get_tool_name(payload)
    if tool_name == "Write":
        # preserves:/adds: only applies to augmentation Edits, not file creation
        return HOOK_ALLOW
    if any(pat in norm for pat in TEST_PATTERNS):
        return HOOK_ALLOW  # QA ownership, no contract (normalized 2026-06-06)

    root = repo_root()
    target = Path(file_path)
    if not target.is_absolute():
        target = root / target
    if not target.is_file():
        return HOOK_ALLOW
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return HOOK_ALLOW
    if not content.strip():
        return HOOK_ALLOW
    plans_dir = root / "workspace" / "output" / "plans"
    if not plans_dir.is_dir():
        return HOOK_ALLOW
    file_name = target.name
    matching_plan: Path | None = None
    plan_text: str = ""
    for plan in sorted(plans_dir.glob("*.md")):
        text = _read_plan_cached(plan)  # M5 : mtime-keyed cache
        if not text:
            continue
        if _path_in_plan(text, file_path, file_name) or _path_in_plan(text, norm, file_name):
            matching_plan = plan
            plan_text = text
            break

    if matching_plan is None:
        return HOOK_ALLOW  # no plan = inline mode, nothing to enforce (normalized 2026-06-06)

    block_text = _find_block_for_file(plan_text, norm, file_name)
    if block_text is None:
        # File mentioned in plan but not as a primary entry — no contract
        return HOOK_ALLOW
    plan_name = matching_plan.name

    for preserved_id in _parse_id_list(block_text, "preserves"):
        if preserved_id not in content:
            error_block(
                f"PostToolUse hook on {file_path}",
                f"[PRESERVES_VIOLATED] identifiant '{preserved_id}' "
                f"(declare preserves: dans {plan_name}) absent du fichier apres edition",
                f"re-dispatcher l'agent ou restaurer manuellement '{preserved_id}' dans {file_path}",
            )
            return HOOK_DENY

    for added_id in _parse_id_list(block_text, "adds"):
        if added_id not in content:
            error_block(
                f"PostToolUse hook on {file_path}",
                f"[ADDS_VIOLATED] identifiant '{added_id}' "
                f"(declare adds: dans {plan_name}) non present apres ecriture",
                f"re-dispatcher l'agent ou ajouter '{added_id}' manuellement dans {file_path}",
            )
            return HOOK_DENY

    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
