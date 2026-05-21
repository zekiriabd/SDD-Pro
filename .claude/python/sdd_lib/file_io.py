"""SDD_Pro file IO helpers (safe JSON + text + glob, v7.0.0 M3).

Wraps stdlib `json` / `pathlib` with explicit error classes, atomic
writes (via `sdd_lib.atomic_write`), and UTF-8 default encoding.
Eliminates the scattered `json.load(path.open())` patterns across
~50 scripts in `sdd_scripts/` and `sdd_admin/`.

**Recommended use** — new scripts MUST use these helpers ; existing
scripts can migrate gradually (no breaking change). Audit follows :
    grep -rn 'json\\.load' .claude/python/sdd_scripts/

YAML : SDD_Pro uses `_parse_yaml_minimal` in `layered_config.py` for
flat config files (no nesting, no anchors, no tags). NO `pyyaml`
dependency, NO `yaml.load` unsafe paths anywhere. Do not introduce one.

Public API :
    read_json(path)              -> dict|list|str|int|float|bool|None
    write_json_atomic(path, data, indent=2)
    read_text(path, encoding='utf-8')
    write_text_atomic(path, content, encoding='utf-8')
    glob_us_files(feat_number)   -> list[Path]
    glob_feat_files(feat_number) -> list[Path]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdd_lib.atomic_write import atomic_write_text
from sdd_lib.paths import repo_root


class FileIoError(Exception):
    """Wraps OSError + JSONDecodeError + UnicodeDecodeError with context."""


def read_json(path: Path | str, *, encoding: str = "utf-8") -> Any:
    """Read JSON file with explicit error class.

    Raises FileIoError on:
      - file not found / not readable (OSError)
      - JSON parse error (JSONDecodeError)
      - encoding mismatch (UnicodeDecodeError)

    Returns the parsed Python object (dict|list|str|int|float|bool|None).
    """
    p = Path(path)
    try:
        text = p.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError) as exc:
        raise FileIoError(f"[FILE_IO_READ] {p}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FileIoError(f"[FILE_IO_JSON_PARSE] {p}: {exc}") from exc


def write_json_atomic(path: Path | str, data: Any, *, indent: int = 2) -> None:
    """Write JSON atomically via `.sddtmp` + os.replace.

    Uses `sdd_lib.atomic_write` for crash-safety (no partial writes
    visible to readers). Forces UTF-8, ensure_ascii=False (for accents).
    """
    p = Path(path)
    try:
        text = json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=False)
    except (TypeError, ValueError) as exc:
        raise FileIoError(f"[FILE_IO_JSON_SERIALIZE] {p}: {exc}") from exc
    try:
        atomic_write_text(p, text + ("\n" if not text.endswith("\n") else ""))
    except OSError as exc:
        raise FileIoError(f"[FILE_IO_WRITE] {p}: {exc}") from exc


def read_text(path: Path | str, *, encoding: str = "utf-8") -> str:
    """Read text file with explicit error class (UTF-8 default)."""
    p = Path(path)
    try:
        return p.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError) as exc:
        raise FileIoError(f"[FILE_IO_READ] {p}: {exc}") from exc


def write_text_atomic(path: Path | str, content: str, *, encoding: str = "utf-8") -> None:
    """Write text atomically via `.sddtmp` + os.replace."""
    p = Path(path)
    if encoding != "utf-8":
        raise FileIoError(f"[FILE_IO_ENCODING] only utf-8 supported, got {encoding!r}")
    try:
        atomic_write_text(p, content)
    except OSError as exc:
        raise FileIoError(f"[FILE_IO_WRITE] {p}: {exc}") from exc


def glob_us_files(feat_number: int, *, root: Path | None = None) -> list[Path]:
    """Locate all US files for a FEAT : workspace/output/us/{n}-*-*.md.

    Returns sorted list (deterministic across runs).
    """
    if root is None:
        root = repo_root()
    us_dir = root / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    return sorted(us_dir.glob(f"{feat_number}-*-*.md"))


def glob_feat_files(feat_number: int, *, root: Path | None = None) -> list[Path]:
    """Locate FEAT file : workspace/input/feats/{n}-*.md.

    Returns 0, 1, or N matches (caller handles ambiguity).
    """
    if root is None:
        root = repo_root()
    feat_dir = root / "workspace" / "input" / "feats"
    if not feat_dir.is_dir():
        return []
    return sorted(feat_dir.glob(f"{feat_number}-*.md"))
