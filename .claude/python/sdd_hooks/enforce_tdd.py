#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Edit / Write) — TDD enforcement (RED-GREEN-REFACTOR).

Audit P3 TDD (2026-06-08) — enforce test-first discipline (emprunt Superpowers
v5.1 `test-driven-development` skill). When the agent attempts to Write or
Edit production code under `workspace/output/src/{BackendName,AppName}/` to
ADD a new function/class/method/endpoint, this hook verifies that a
corresponding test file exists OR is being created in the same tool batch.

**Detection heuristics** (lightweight, fast) :
  - File path under `workspace/output/src/*/` (production scope)
  - File extension in {.cs, .ts, .tsx, .js, .jsx, .py, .kt, .java}
  - NOT under `*.Tests/`, `__tests__/`, `tests/`, `src/test/` (test scope)
  - Content contains a NEW public function/class definition (regex per language)
  - No companion test file exists for the same logical unit

**Modes** (env var `SDD_TDD_MODE`, default `warn` interactive / `strict` CI) :
  - `off`     → no-op
  - `warn`    → stderr WARN [TDD_NO_TEST_FIRST] + audit log, exit 0
  - `strict`  → exit 2 (block Write) with structured RED-first guidance

**Bypass** :
  - `SDD_DISABLE_TDD=1` env var (one-shot, audit-logged)
  - Edit of EXISTING code (refactor, no new behavior) → allowed
  - Test file itself (`*.Tests/`, `__tests__/`, etc.) → allowed
  - Non-production paths (`workspace/input/`, `.claude/`) → allowed

**Idempotent guard** : the hook is read-only on disk (Glob for companion
test). No side effects beyond stderr audit logging.

Fast-path : Bash detection of NEW symbols (regex) is < 10ms typical.
"""
from __future__ import annotations

import json as _json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.ci import is_ci  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_file_path,
    read_hook_input,
)
from sdd_lib.paths import normalize, repo_root  # noqa: E402


#: Production file extensions that should follow TDD
_PROD_EXTENSIONS = frozenset({
    ".cs", ".ts", ".tsx", ".js", ".jsx",
    ".py", ".kt", ".java",
    ".razor",  # Blazor components (limited TDD relevance, but checked)
})

#: Path segments that mark TEST files (bypass)
_TEST_PATH_MARKERS = (
    ".tests/",      # .NET convention {Project}.Tests/
    "__tests__/",   # JS/TS convention
    "/tests/",      # Python/Go convention
    "/test/",       # Java/Kotlin Gradle convention (src/test/kotlin)
    "/spec/",       # JS spec convention
    ".test.",       # filename.test.ts
    ".spec.",       # filename.spec.ts
    "_test.",       # filename_test.py / filename_test.go
    "test_",        # test_filename.py
)

#: Path segments that are NOT production (skip TDD entirely)
_NON_PROD_PATH_MARKERS = (
    "workspace/input/",
    ".claude/",
    "node_modules/",
    "bin/", "obj/", "dist/", "build/",
    "__pycache__/", ".venv/", "venv/",
    ".gradle/", "target/",
)

#: Regex per extension to detect a "new public definition" (function/class/method).
#: Conservative : matches obvious patterns, not exhaustive. False negatives OK
#: (skill prompts user); false positives create noise but the WARN can be
#: bypassed.
_NEW_SYMBOL_PATTERNS: dict[str, list[str]] = {
    ".cs": [
        r"^\s*public\s+(?:static\s+|async\s+|virtual\s+|override\s+)?(?:class|record|struct|interface)\s+\w+",
        r"^\s*public\s+(?:static\s+|async\s+|virtual\s+|override\s+)?\w[\w<>?,\[\]\s]*\s+\w+\s*\(",
    ],
    ".ts": [
        r"^\s*export\s+(?:async\s+)?(?:function|class|const|interface|type)\s+\w+",
        r"^\s*export\s+default\s+(?:async\s+)?(?:function|class)\s+\w*",
    ],
    ".tsx": [
        r"^\s*export\s+(?:async\s+)?(?:function|class|const|interface|type)\s+\w+",
        r"^\s*export\s+default\s+(?:async\s+)?(?:function|class)\s+\w*",
    ],
    ".js": [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+",
        r"^\s*(?:export\s+)?class\s+\w+",
    ],
    ".jsx": [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+",
        r"^\s*(?:export\s+)?class\s+\w+",
    ],
    ".py": [
        r"^\s*def\s+[a-zA-Z]\w*\s*\(",
        r"^\s*class\s+[a-zA-Z]\w*\s*[:\(]",
    ],
    ".kt": [
        r"^\s*(?:public\s+)?(?:open\s+)?(?:suspend\s+)?fun\s+\w+\s*\(",
        r"^\s*(?:public\s+)?(?:open\s+|abstract\s+)?(?:class|interface|object)\s+\w+",
    ],
    ".java": [
        r"^\s*public\s+(?:static\s+|abstract\s+|final\s+)?(?:class|interface)\s+\w+",
        r"^\s*public\s+(?:static\s+|abstract\s+|final\s+)?\w[\w<>?,\[\]\s]*\s+\w+\s*\(",
    ],
    ".razor": [
        r"@code\s*\{",  # presence of code block in Razor
    ],
}


def _resolve_mode() -> str:
    """Return TDD mode from env or default by context.

    Default : `warn` interactive (dev local), `strict` in CI.
    """
    explicit = os.environ.get("SDD_TDD_MODE", "").strip().lower()
    if explicit in ("off", "warn", "strict"):
        return explicit
    if is_ci():
        return "strict"
    return "warn"


def _is_production_path(path_norm: str) -> bool:
    """True if path is in workspace/output/src/ and not in a test sub-tree."""
    if not path_norm.startswith("workspace/output/src/"):
        return False
    low = path_norm.lower()
    if any(marker in low for marker in _TEST_PATH_MARKERS):
        return False
    if any(marker in low for marker in _NON_PROD_PATH_MARKERS):
        return False
    return True


def _get_extension(path_str: str) -> str:
    """Return lowercase file extension, including the dot."""
    for ext in sorted(_PROD_EXTENSIONS, key=len, reverse=True):
        if path_str.lower().endswith(ext):
            return ext
    return ""


def _content_introduces_new_symbol(content: str, ext: str) -> bool:
    """True if content contains a NEW public symbol per language regex."""
    patterns = _NEW_SYMBOL_PATTERNS.get(ext, [])
    for pat in patterns:
        if re.search(pat, content, re.MULTILINE):
            return True
    return False


def _has_companion_test(prod_path: Path, root: Path) -> bool:
    """Best-effort lookup for an existing test file covering this prod file.

    Strategy : Glob for `*<stem>*` under common test directories.
    Returns True if any match — conservative (false positives allowed).
    """
    stem = prod_path.stem
    if not stem or len(stem) < 3:
        return True  # too short, allow

    test_dirs = [
        # .NET
        *root.glob("workspace/output/src/*.Tests"),
        # Node/TS
        *root.glob("workspace/output/src/*/src/__tests__"),
        *root.glob("workspace/output/src/*/__tests__"),
        # Python
        *root.glob("workspace/output/src/*/tests"),
        # Kotlin/Java Gradle
        *root.glob("workspace/output/src/*/src/test"),
    ]

    test_filename_patterns = [
        f"*{stem}*.cs",
        f"*{stem}*.ts", f"*{stem}*.tsx",
        f"*{stem}*.js", f"*{stem}*.jsx",
        f"test_{stem}.py", f"{stem}_test.py", f"*{stem}*.py",
        f"{stem}Test.kt", f"{stem}Tests.kt", f"*{stem}*.kt",
        f"{stem}Test.java", f"*{stem}*.java",
    ]

    for td in test_dirs:
        if not td.is_dir():
            continue
        for pattern in test_filename_patterns:
            try:
                matches = list(td.rglob(pattern))
            except OSError:
                continue
            if matches:
                return True

    return False


def main() -> int:
    """Hook entry. Narrow exception scope per audit P3 C3 pattern."""
    try:
        payload = read_hook_input()
    except (_json.JSONDecodeError, OSError, UnicodeError, ValueError):
        return HOOK_ALLOW

    mode = _resolve_mode()
    if mode == "off":
        return HOOK_ALLOW
    if os.environ.get("SDD_DISABLE_TDD") == "1":
        sys.stderr.write(
            "WARN [TDD_BYPASSED] SDD_DISABLE_TDD=1 — test-first discipline "
            "bypassed for this tool call. Audit-logged.\n"
        )
        return HOOK_ALLOW

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return HOOK_ALLOW

    file_path = get_file_path(payload)
    if not file_path:
        return HOOK_ALLOW

    try:
        root = repo_root()
    except (OSError, RuntimeError):
        return HOOK_ALLOW
    path_norm = normalize(file_path)
    # Make path relative to repo_root for consistent matching against
    # `workspace/output/src/` prefix (handles both absolute and relative inputs).
    try:
        if Path(path_norm).is_absolute():
            path_norm = str(Path(path_norm).relative_to(root)).replace("\\", "/")
    except (ValueError, OSError):
        pass

    if not _is_production_path(path_norm):
        return HOOK_ALLOW

    ext = _get_extension(path_norm)
    if not ext:
        return HOOK_ALLOW

    # Extract proposed content (Write tool) or new_string (Edit tool)
    tool_input = payload.get("tool_input", {})
    content = tool_input.get("content") or tool_input.get("new_string") or ""
    if not isinstance(content, str) or not content.strip():
        return HOOK_ALLOW

    if not _content_introduces_new_symbol(content, ext):
        # Pure refactor / value change / config tweak — TDD allows
        return HOOK_ALLOW

    prod_path = root / path_norm
    if _has_companion_test(prod_path, root):
        return HOOK_ALLOW

    # No companion test found for a new production symbol → flag
    msg = (
        f"[TDD_NO_TEST_FIRST] About to write a NEW production symbol "
        f"({ext}) at {path_norm}, but no companion test file detected.\n"
        f"  RED-GREEN-REFACTOR contract (SDDPro v7.0.0+ emprunt Superpowers v5.1) :\n"
        f"    1. Write the FAILING test first (in *.Tests/, __tests__/, tests/, or src/test/)\n"
        f"    2. Run the test, confirm RED\n"
        f"    3. Then write the minimal production code to make it GREEN\n"
        f"    4. Refactor if needed\n"
        f"  Bypass options :\n"
        f"    - SDD_TDD_MODE=warn (default interactive) — this becomes WARN only\n"
        f"    - SDD_TDD_MODE=off — disable TDD enforcement entirely\n"
        f"    - SDD_DISABLE_TDD=1 — one-shot bypass (audit-logged)\n"
        f"  Skill reference : @.claude/skills/test-driven-development/SKILL.md\n"
    )

    if mode == "strict":
        sys.stderr.write(f"ERROR: {msg}")
        return HOOK_DENY

    # warn mode
    sys.stderr.write(f"WARN {msg}")
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
