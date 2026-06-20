"""Stderr helpers — Claude Code displays these messages to the user."""
from __future__ import annotations

import sys


def warn(message: str) -> None:
    """Write a single line to stderr."""
    print(message, file=sys.stderr, flush=True)


def error_block(error_line: str, cause: str, fix: str) -> None:
    """Canonical 3-line ERROR/CAUSE/FIX format."""
    warn(f"ERROR: {error_line}")
    warn(f"CAUSE: {cause}")
    warn(f"FIX: {fix}")
