"""Parse `workspace/input/stack/stack.md` to extract Project Config + active stacks.

SSOT for all Project Config readers (cf. audit 2026-05-14 — 10 ad-hoc
re-implementations consolidated).
"""
from __future__ import annotations

import re
from pathlib import Path

from sdd_lib.paths import repo_root

_KV_RE = re.compile(r"^[-*]?\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.+?)\s*$")
_ACTIVE_STACK_RE = re.compile(r"^\s*-\s*(\.claude/stacks/[^\s]+\.md)\s*$")
_SECTION_RE_TMPL = r"^##\s+{heading}\s*\n(.*?)(?=^##\s+|\Z)"


def stack_md_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "workspace" / "input" / "stack" / "stack.md"


def section_body(text: str, heading: str) -> str | None:
    """Extract body between `## {heading}` and next H2 (or EOF).

    Heading is regex-escaped; whitespace tolerant.
    """
    pattern = _SECTION_RE_TMPL.format(heading=re.escape(heading).replace(r"\ ", r"\s+"))
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else None


def parse_kv_block(block: str, keys: tuple[str, ...] | None = None) -> dict[str, str]:
    """Parse `Key: value` lines from a markdown block.

    Strips outer quotes. If `keys` is provided, only those keys are returned.
    """
    config: dict[str, str] = {}
    for line in block.splitlines():
        m = _KV_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip().strip('"').strip("'")
        if keys is not None and key not in keys:
            continue
        if value:
            config[key] = value
    return config


def read_project_config(
    root: Path | None = None,
    *,
    keys: tuple[str, ...] | None = None,
) -> dict[str, str]:
    """Parse `## Project Config` section from stack.md (restricted, not whole file).

    v6.10.2+: applies alias normalization (FrontendName → AppName) and
    namespace auto-derive (AppNamespace ← AppName, BackendNamespace ← BackendName)
    before key filtering, so callers can keep using the canonical `{AppName}` /
    `{AppNamespace}` tokens regardless of which key the user wrote in stack.md.
    """
    path = stack_md_path(root)
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    block = section_body(text, "Project Config")
    if block is None:
        return {}
    raw = parse_kv_block(block)
    normalized = normalize_project_aliases(raw)
    if keys is not None:
        return {k: v for k, v in normalized.items() if k in keys}
    return normalized


def normalize_project_aliases(raw: dict[str, str]) -> dict[str, str]:
    """Naming aliases + namespace auto-derive (v6.10.2+).

    Aliases :
        FrontendName → AppName (canonical framework token)
        AppName (legacy) stays as AppName

    Auto-derivations (only if not explicit in stack.md), convention
    "namespace = project name" documented in CLAUDE.md §1 :
        AppNamespace      ← AppName
        BackendNamespace  ← BackendName

    Precedence : explicit AppName beats FrontendName when both present.
    """
    out = dict(raw)
    if "AppName" not in out and "FrontendName" in out:
        out["AppName"] = out["FrontendName"]
    if "AppNamespace" not in out and "AppName" in out:
        out["AppNamespace"] = out["AppName"]
    if "BackendNamespace" not in out and "BackendName" in out:
        out["BackendNamespace"] = out["BackendName"]
    return out


def get_active_stack_paths(root: Path | None = None) -> list[str]:
    """List `.claude/stacks/...` paths referenced under `## Active ...` sections."""
    path = stack_md_path(root)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    paths: list[str] = []
    for line in text.splitlines():
        m = _ACTIVE_STACK_RE.match(line)
        if m:
            paths.append(m.group(1))
    return paths
