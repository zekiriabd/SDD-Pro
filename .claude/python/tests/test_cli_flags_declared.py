"""Smoke test : CLI flags declared in `.claude/commands/*.md` must either
be parsed by a real Python `argparse` somewhere in `.claude/python/`, OR
be explicitly marked `@llm-only-flag` in the documentation.

Audit P3 E2 (2026-06-08) — anti-doc-theater enforcement. Without this
check, a `.md` can declare a `--foo` flag that no Python parses, and the
LLM is silently expected to interpret it. When the LLM misses the flag,
the documented bypass doesn't work and the user assumes it failed
randomly. By requiring every flag to be EITHER parsed by Python OR
explicitly annotated as LLM-interpreted, we make the architectural
choice visible.

Annotation syntax (LLM-interpreted flags) :

    - `--my-flag` (optionnel, **@llm-only-flag**) — description …

The `@llm-only-flag` marker tells this smoke test : "yes I know this
flag is not Python-parsed, that's intentional".

Whitelisted patterns (still allowed without annotation) :
- Placeholder `--xxx` inside code fences/quotes (shell examples)
- `--help` / `-h` / `--version` (universal)
- Flags inside YAML/JSON blocks documenting external tools
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


def _repo_root() -> Path:
    cwd = Path(__file__).resolve()
    for p in [cwd, *cwd.parents]:
        if (p / ".claude").is_dir():
            return p
    raise RuntimeError("Cannot locate repo root")


def _extract_command_flags(md_text: str) -> set[str]:
    """Extract `--xxx` flags from command body, excluding code-fence examples.

    Strategy : strip fenced ``` ``` ``` blocks first, then regex remaining
    text. Flags inside code blocks are usually shell/Python invocation
    examples for external tools (npm, dotnet, …), not the command's own
    CLI surface.
    """
    # Strip fenced code blocks
    cleaned = re.sub(r"```[\s\S]*?```", "", md_text)
    # Find flag patterns like `--foo` or `--foo-bar` (not preceded by < to skip type hints)
    flags = set(re.findall(r"(?<!<)`(--[a-z][a-z0-9-]+)`", cleaned))
    return flags


#: File-level annotation : if a command .md declares all its flags as
#: LLM-only (slash command flags interpreted by Claude, not Python-parsed),
#: it can use this single marker at the top of the file instead of
#: annotating every individual flag.
_FILE_LEVEL_LLM_ONLY_MARKER = "@llm-only-flags-file"


def _is_llm_only_annotated(md_text: str, flag: str) -> bool:
    """True if `flag` is annotated with @llm-only-flag in the doc, OR if the
    whole file declares @llm-only-flags-file at the top.

    File-level annotation is preferred for slash command docs where every
    flag is by design LLM-interpreted (the LLM IS the parser of the slash
    command surface). Per-flag annotation is for mixed files where some
    flags ARE parsed by Python and some aren't.
    """
    # File-level marker takes precedence (covers all flags in the file)
    if _FILE_LEVEL_LLM_ONLY_MARKER in md_text:
        return True
    # Per-flag annotation : `--flag` ... @llm-only-flag within next 200 chars
    pattern = re.escape(flag) + r"`[^\n]{0,200}@llm-only-flag"
    return re.search(pattern, md_text) is not None


def _python_parses_flag(flag: str, python_files: list[Path]) -> bool:
    """True if any Python file uses argparse.add_argument with this flag."""
    # Match `add_argument("--foo"` or `add_argument('--foo'` or with comma
    needle1 = f'add_argument("{flag}"'
    needle2 = f"add_argument('{flag}'"
    for p in python_files:
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle1 in content or needle2 in content:
            return True
    return False


# Flags universally accepted (don't require annotation or parsing)
_UNIVERSAL_FLAGS = {"--help", "--version", "--verbose", "--quiet", "--debug"}

# Flags that are documented as belonging to EXTERNAL tools, not SDD_Pro itself.
# These are mentioned in passing within command docs (e.g. "use `--combo c1`"
# when invoking bootstrap.py externally) and need not be parsed by SDD_Pro
# Python.
_EXTERNAL_TOOL_FLAGS = {
    "--combo",         # bootstrap.py
    "--auto-init",     # bootstrap.py
    "--skip-install",  # bootstrap.py
    "--dry-run",       # bootstrap.py + many scripts
    "--no-edit",       # git
}


class TestCliFlagsDeclared(unittest.TestCase):
    """Every `--flag` in commands/*.md is parsed by Python OR @llm-only-flag annotated."""

    def test_command_flags_have_implementation_or_annotation(self):
        commands_dir = _repo_root() / ".claude" / "commands"
        python_dir = _repo_root() / ".claude" / "python"
        python_files = list(python_dir.rglob("*.py"))
        self.assertGreater(len(python_files), 50, "expected many Python files in .claude/python/")

        offenders: list[tuple[str, str]] = []  # (command_name, flag)
        for cmd_md in sorted(commands_dir.glob("*.md")):
            md_text = cmd_md.read_text(encoding="utf-8")
            flags = _extract_command_flags(md_text)
            for flag in sorted(flags):
                if flag in _UNIVERSAL_FLAGS or flag in _EXTERNAL_TOOL_FLAGS:
                    continue
                if _is_llm_only_annotated(md_text, flag):
                    continue
                if _python_parses_flag(flag, python_files):
                    continue
                offenders.append((cmd_md.stem, flag))

        if offenders:
            details = "\n".join(f"  - /{cmd}: {flag}" for cmd, flag in offenders)
            self.fail(
                f"\nDoc-theater detected — CLI flags declared in commands/*.md "
                f"without Python implementation NOR @llm-only-flag annotation :\n"
                f"{details}\n\n"
                f"Fix options :\n"
                f"  1. Add argparse.add_argument({offenders[0][1]!r}, ...) in the relevant Python script\n"
                f"  2. Annotate the flag doc line with `**@llm-only-flag**` if intentionally LLM-interpreted\n"
                f"  3. Add to _EXTERNAL_TOOL_FLAGS whitelist if it's a documented external tool flag\n"
            )


if __name__ == "__main__":
    unittest.main()
