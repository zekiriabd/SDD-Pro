#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Edit|Write|MultiEdit).

Sprint 1.4 fix (2026-06-06) — H3 forbidden patterns enforced at generation
time, not just audited post-hoc by code-reviewer.

Reads the planned content (Write `content`, Edit `new_string`, MultiEdit
`edits[].new_string`) and the target path. If the file lives under
`workspace/output/src/<project>/` and the project's CLAUDE.md declares
forbidden patterns, scan the new content for matches.

A match returns exit 2 + ERROR `[FORBIDDEN_PATTERN]` 3-line block →
Claude Code blocks the tool call and surfaces the message to the agent
so it can self-correct in the same turn (vs the post-write code-reviewer
flag which costs a full iteration).

Patterns checked (case-sensitive, comment-aware) — derived from the
stack-CLAUDE.md "## Forbidden patterns" sections of v7.0.0 stacks :

Backend Kotlin/Spring (`backend/kotlin-spring-boot`) :
  - `!!` Kotlin force unwrap (unjustified) — except in comments
  - `@Autowired` field injection — constructor only
  - `System.getenv(` for stack-managed env vars (DB_*, AUTH_JWT_*, AZ_*)

Frontend Vue (`frontend/vue`) :
  - Direct `fetch(` in `src/components/` or `src/pages/` (must go via service)
  - `<button>` / `<input>` / `<table>` raw HTML in `.vue` (use Vuetify)
  - `console.log(` in production code
  - Hex color literals `#XXXXXX` in components (use Vuetify tokens)

Universal (every stack) :
  - `TODO` / `FIXME` (signals unfinished work — quality_scan catches too,
    but blocking pre-write avoids the iteration)

Non-blocking by default — set `SDD_PRE_WRITE_LINT_STRICT=1` for strict mode.
Default behavior : log to `workspace/output/.sys/.audit/pre-write-lint.log`
and emit WARN on stderr but allow the write.

Exit 0 (allow) on : non-src paths, test files (QA ownership), no patterns
matching, or hook disabled via `SDD_DISABLE_PRE_WRITE_LINT=1`.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_file_path, get_nested, get_tool_name, read_hook_input,
)
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.stderr import error_block, warn  # noqa: E402


# Test paths — skip (QA ownership, fixtures may use forbidden patterns legitimately)
TEST_PATH_PATTERNS: tuple[str, ...] = (
    ".Tests/", "__tests__/", ".test.", "Tests.cs", "test_", "_test.py",
    "Test.kt", "/tests/", "/spec/", ".spec.",
)


# (pattern_id, regex, description, applies_when_path_matches)
PATTERNS: list[tuple[str, re.Pattern, str, re.Pattern | None]] = [
    # ── Universal ──────────────────────────────────────────
    ("UNIVERSAL_TODO",
     re.compile(r"\b(TODO|FIXME)\b(?![\w-])"),
     "TODO/FIXME unresolved markers — signals unfinished work",
     None),

    # ── Kotlin / Spring backend ────────────────────────────
    ("KOTLIN_FORCE_UNWRAP",
     # `expr!!` not in a // comment and not as part of !!=
     re.compile(r"(?<![\!])!!(?!=)"),
     "Kotlin force unwrap `!!` — use requireNotNull(...) with message or smart-cast (CLAUDE.md forbidden)",
     re.compile(r"\.kt$|\.kts$")),
    ("KOTLIN_FIELD_AUTOWIRED",
     re.compile(r"@Autowired\s+(?:private\s+)?(?:lateinit\s+)?(?:var|val)\b"),
     "@Autowired field injection — use constructor injection (CLAUDE.md forbidden)",
     re.compile(r"\.kt$")),
    ("KOTLIN_ENV_DIRECT_READ",
     re.compile(r"System\.getenv\s*\(\s*\"(DB_|AUTH_JWT_|AZ_|SMTP_)"),
     "System.getenv() for stack-managed vars — use @Value(\"${...}\") (Pattern B SSoT)",
     re.compile(r"\.kt$")),

    # ── Vue frontend ───────────────────────────────────────
    ("VUE_RAW_FETCH_IN_COMPONENT",
     re.compile(r"\bfetch\s*\("),
     "Direct fetch() in component — use a service layer (CLAUDE.md forbidden)",
     re.compile(r"(?:src/components|src/pages)/.*\.(vue|ts|js)$")),
    ("VUE_RAW_HTML_BUTTON",
     re.compile(r"<button\b(?![^>]*v-btn)"),
     "<button> raw HTML — use Vuetify v-btn (CLAUDE.md forbidden)",
     re.compile(r"\.vue$")),
    ("VUE_RAW_HTML_INPUT",
     re.compile(r"<input\b(?![^>]*v-)"),
     "<input> raw HTML — use Vuetify v-text-field (CLAUDE.md forbidden)",
     re.compile(r"\.vue$")),
    ("FRONTEND_CONSOLE_LOG",
     re.compile(r"\bconsole\.log\s*\("),
     "console.log() in prod code — use a proper logger (loglevel)",
     re.compile(r"\.(vue|ts|tsx|js|jsx)$")),
    ("FRONTEND_HEX_HARDCODE",
     # 6-digit hex in template/style, excluding common safe contexts
     re.compile(r"#[0-9a-fA-F]{6}\b"),
     "Hex color hardcoded — use Vuetify tokens (quality.md §B)",
     re.compile(r"(?:src/components|src/pages|src/layouts)/.*\.vue$")),

    # ── React / TSX (universal-ish for SPA) ────────────────
    ("REACT_KEY_INDEX",
     re.compile(r"\bkey\s*=\s*\{\s*(?:index|i|idx)\s*\}"),
     "Array index as React key — unstable on reorder, use stable id",
     re.compile(r"\.(tsx|jsx)$")),
]


# Stacks where each pattern set is "active" — checked against project path heuristics.
# Currently we just match by file extension; CLAUDE.md per-project parsing
# could refine this further (deferred to v7.1).


def _is_test_path(path: str) -> bool:
    norm = path.replace("\\", "/")
    return any(p in norm for p in TEST_PATH_PATTERNS)


def _is_under_output_src(path: str, root: Path) -> bool:
    try:
        rel = Path(path).resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    parts = rel.parts
    return len(parts) >= 4 and parts[0] == "workspace" and parts[1] == "output" and parts[2] == "src"


def _strip_comments(content: str, ext: str) -> str:
    """Best-effort comment stripping to reduce false positives.

    Kotlin/TS/JS/Java/C# line // and block /* */.
    Python # line only (no block comment).
    .vue files have HTML <!-- --> + JS // — handled with both passes.
    """
    if ext in {".py"}:
        # strip # comments
        return re.sub(r"#.*$", "", content, flags=re.MULTILINE)
    out = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    out = re.sub(r"/\*.*?\*/", "", out, flags=re.DOTALL)
    if ext == ".vue":
        out = re.sub(r"<!--.*?-->", "", out, flags=re.DOTALL)
    return out


def _extract_new_content(payload: dict, tool_name: str) -> str:
    """Pull the content/new_string from the tool input.

    Returns empty string if no content extractable (allows the hook to
    silently skip — defensive).
    """
    if tool_name == "Write":
        c = get_nested(payload, "tool_input", "content")
        return c if isinstance(c, str) else ""
    if tool_name == "Edit":
        c = get_nested(payload, "tool_input", "new_string")
        return c if isinstance(c, str) else ""
    if tool_name == "MultiEdit":
        edits = get_nested(payload, "tool_input", "edits")
        if isinstance(edits, list):
            chunks = []
            for e in edits:
                if isinstance(e, dict):
                    ns = e.get("new_string")
                    if isinstance(ns, str):
                        chunks.append(ns)
            return "\n".join(chunks)
    return ""


def _check_patterns(path: str, content: str) -> list[tuple[str, str, int]]:
    """Return list of (pattern_id, description, line_no) violations."""
    ext = Path(path).suffix.lower()
    cleaned = _strip_comments(content, ext)
    violations: list[tuple[str, str, int]] = []
    for pat_id, regex, desc, applies in PATTERNS:
        if applies is not None and not applies.search(path.replace("\\", "/")):
            continue
        m = regex.search(cleaned)
        if m:
            # locate line number from match
            line_no = cleaned[:m.start()].count("\n") + 1
            violations.append((pat_id, desc, line_no))
    return violations


def main() -> int:
    if os.environ.get("SDD_DISABLE_PRE_WRITE_LINT", "").strip() == "1":
        return HOOK_ALLOW

    payload = read_hook_input()
    if not payload:
        return HOOK_ALLOW

    tool_name = get_tool_name(payload)
    if tool_name not in {"Write", "Edit", "MultiEdit"}:
        return HOOK_ALLOW

    file_path = get_file_path(payload)
    if not file_path:
        return HOOK_ALLOW

    if _is_test_path(file_path):
        return HOOK_ALLOW

    root = repo_root()
    if not _is_under_output_src(file_path, root):
        return HOOK_ALLOW

    new_content = _extract_new_content(payload, tool_name)
    if not new_content.strip():
        return HOOK_ALLOW

    violations = _check_patterns(file_path, new_content)
    if not violations:
        return HOOK_ALLOW

    # Log every violation
    log_dir = root / "workspace" / "output" / ".sys" / ".audit"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pre-write-lint.log"
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with log_path.open("a", encoding="utf-8") as f:
            for pat_id, desc, line_no in violations:
                f.write(f"{ts}\t{tool_name}\t{file_path}\t{pat_id}\tline~{line_no}\t{desc}\n")
    except OSError:
        pass

    strict = os.environ.get("SDD_PRE_WRITE_LINT_STRICT", "").strip() == "1"
    primary = violations[0]
    extra_count = len(violations) - 1
    extra_hint = f" (+{extra_count} more — see audit log)" if extra_count > 0 else ""

    if strict:
        error_block(
            f"pre-write-lint — forbidden pattern in {file_path}",
            f"[FORBIDDEN_PATTERN] {primary[0]} at line~{primary[2]}: {primary[1]}{extra_hint}",
            f"fix the pattern in your write payload, or set SDD_DISABLE_PRE_WRITE_LINT=1 to bypass (audit-logged)",
        )
        return HOOK_DENY

    # Default : WARN only, allow the write
    warn(
        f"pre-write-lint: {primary[0]} in {file_path}:~{primary[2]} ({primary[1]}){extra_hint}"
    )
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
