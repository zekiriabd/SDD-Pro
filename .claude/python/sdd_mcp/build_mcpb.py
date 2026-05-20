"""Build an MCPB bundle for Claude Desktop one-click install (Phase 3).

MCPB = MCP Bundle, a `.mcpb` file (= ZIP archive) containing the server,
its manifest, and any runtime assets. Claude Desktop discovers MCPBs in
its user data directory and offers them in the tool picker.

Bundle layout (inside the .mcpb):
    manifest.json                    MCPB metadata
    server/                          sdd_mcp/* (recursive copy)
    server/scripts/                  sdd_scripts/*.py (recursive copy)
    server/lib/                      sdd_lib/*.py
    README.md                        short usage note

Usage:
    python -m sdd_mcp.build_mcpb [--output ~/sdd-pro.mcpb] [--clean]

The output defaults to `./dist/sdd-pro-{version}.mcpb` relative to the
SDD_Pro repo root.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_mcp import __version__  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402


MANIFEST_TEMPLATE = {
    "mcpbVersion": "1.0",
    "name": "sdd-pro",
    "displayName": "SDD_Pro MCP",
    "description": (
        "Spec-driven development framework — exposes /sdd-full, /feat-generate, "
        "/us-generate and 11 deterministic tools via MCP. Wraps the user's local "
        "Claude Code CLI for LLM-driven commands; runs Python scripts inline for "
        "the read-only tools. Zero modification of the SDD_Pro engine."
    ),
    "version": __version__,
    "author": "SDD_Pro",
    "license": "see SDD_Pro LICENSE",
    "homepage": "https://github.com/your-org/SDD_Pro",
    "server": {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "sdd_mcp.server"],
        "cwd": "./server",
    },
    "requirements": {
        "python": ">=3.10",
        "external": [
            "Claude Code CLI on PATH (required for /sdd-full, /feat-generate, /us-generate tools)"
        ],
    },
    "tools": [
        # Phase 1
        "sdd_status", "validate_readiness", "feat_validate",
        "set_us_status", "validate_us_deps", "compute_us_complexity",
        "migrate_us_v1_to_v2",
        # Phase 2
        "claude_check", "feat_generate", "us_generate",
        "sdd_full", "get_sdd_full_status", "cancel_sdd_full",
        "list_sdd_full_jobs",
    ],
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .mcpb path (default: ./dist/sdd-pro-{version}.mcpb).",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="Remove the staging directory before building.",
    )
    return p.parse_args(argv)


def _default_output() -> Path:
    return repo_root() / "dist" / f"sdd-pro-{__version__}.mcpb"


def _stage_files(staging: Path, py_root: Path) -> None:
    """Copy sdd_mcp/, sdd_scripts/, sdd_lib/ into a staging tree."""
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    (staging / "server").mkdir()

    for mod in ("sdd_mcp", "sdd_scripts", "sdd_lib"):
        src = py_root / mod
        if not src.is_dir():
            raise FileNotFoundError(f"Required module missing: {src}")
        shutil.copytree(src, staging / "server" / mod, ignore=_ignore_caches)

    (staging / "manifest.json").write_text(
        json.dumps(MANIFEST_TEMPLATE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (staging / "README.md").write_text(
        f"# SDD_Pro MCP bundle v{__version__}\n\n"
        "Distribution of the SDD_Pro Model Context Protocol server for "
        "Claude Desktop and other MCPB-aware clients.\n\n"
        "## Tools exposed\n\n"
        + "\n".join(f"- `{t}`" for t in MANIFEST_TEMPLATE["tools"])
        + "\n\n## Requirements\n\n"
        "- Python ≥ 3.10\n"
        "- `claude` CLI on PATH (only for LLM-driven tools)\n",
        encoding="utf-8",
    )


def _ignore_caches(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in ("__pycache__", ".pytest_cache", ".mypy_cache")}


def _zip_bundle(staging: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in staging.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(staging))


def build(output: Path | None = None, clean: bool = False) -> Path:
    """Produce the .mcpb file. Returns the output path."""
    output = output or _default_output()
    py_root = Path(__file__).resolve().parent.parent
    staging = py_root / ".mcpb-build"
    if clean and staging.exists():
        shutil.rmtree(staging)
    _stage_files(staging, py_root)
    _zip_bundle(staging, output)
    shutil.rmtree(staging)
    return output


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    output = build(output=args.output, clean=args.clean)
    print(f"Built MCPB bundle: {output}")
    print(f"Size: {output.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
