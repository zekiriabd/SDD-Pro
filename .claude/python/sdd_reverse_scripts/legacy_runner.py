"""SDD_Pro Reverse Engineering Phase 4 — Legacy runner CLI.

Usage:
    python -m sdd_reverse_scripts.legacy_runner --project-path PATH [--port N]
        [--language LANG] [--timeout SEC] [--detach]

    python -m sdd_reverse_scripts.legacy_runner --cleanup PATH

The first form detects the legacy stack from
{PATH}/.sys/inventory-raw.json (or via --language override), launches the
appropriate runtime as a subprocess, waits for HTTP readiness, writes a
pidfile at {PATH}/.sys/.runner.pid, and emits a JSON document on stdout
describing the running process.

The --cleanup form reads the pidfile and terminates the recorded process,
then removes the pidfile.

Exit codes:
  0  success (runtime launched OR fallback-static decision returned)
  1  preconditions failed (project path invalid, inventory missing,
     language undetectable)
  2  runner_signatures.yml malformed or unreadable
  3  cleanup mode succeeded (alternate success code for clarity)

Error format: 3-line ERROR/CAUSE/FIX with [REVERSE_UI_*] prefix per
.claude/rules/reverse-engineering.md.

Output protocol (chat): 1L per major step per
.claude/rules/output-protocol.md. Suppressed when --json passed.

NOTE on launch+detach semantics:
  By default, this CLI blocks until the runtime is ready, then prints JSON
  and EXITS. The runtime subprocess remains running. The orchestrating
  caller (e.g. /sdd-reverse-ui) is responsible for invoking the cleanup
  mode at the end of the capture flow.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Ensure parent directory is on sys.path so we can import sdd_reverse
_THIS_DIR = Path(__file__).resolve().parent
_PYTHON_DIR = _THIS_DIR.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from sdd_reverse import legacy_runner as runner_lib  # noqa: E402


DEFAULT_SIGNATURES_PATH = (
    _PYTHON_DIR / "sdd_reverse" / "runner_signatures.yml"
)


def _print_error_3l(error_msg: str, cause: str, fix: str) -> None:
    """Print 3-line ERROR/CAUSE/FIX to stderr."""
    print(f"ERROR: {error_msg}", file=sys.stderr)
    print(f"CAUSE: {cause}", file=sys.stderr)
    print(f"FIX: {fix}", file=sys.stderr)


_CHAT_QUIET = False


def _chat(message: str, progress: int) -> None:
    if _CHAT_QUIET:
        return
    print(f"[REVERSE-UI] {message} ({progress}%)", flush=True)


def _detect_language_from_inventory(project_path: Path) -> str | None:
    """Read .sys/inventory-raw.json and return languages[0].id (the dominant).

    Returns None if file absent or malformed.
    """
    raw_path = project_path / ".sys" / "inventory-raw.json"
    if not raw_path.is_file():
        return None
    try:
        data = json.loads(raw_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    langs = data.get("languages", [])
    if not langs:
        return None
    # Skip 'unknown' fallback if a real language is also present
    real = [lang for lang in langs if lang.get("id") not in (None, "unknown")]
    if real:
        return real[0].get("id")
    return langs[0].get("id")


def _result_to_json_dict(result: runner_lib.LaunchResult) -> dict[str, Any]:
    """Convert LaunchResult to a JSON-serializable dict (process handle stripped)."""
    return {
        "ok": result.ok,
        "mode": result.mode,
        "language": result.language,
        "runner_id": result.runner_id,
        "base_url": result.base_url,
        "pid": result.pid,
        "pidfile_path": result.pidfile_path,
        "ready_at": result.ready_at,
        "errors": [asdict(err) for err in result.errors],
        "warnings": [asdict(warn) for warn in result.warnings],
    }


def cmd_launch(args: argparse.Namespace) -> int:
    """Handle 'launch' mode (default)."""
    global _CHAT_QUIET
    _CHAT_QUIET = args.json

    project_path = Path(args.project_path).resolve()
    if not project_path.is_dir():
        _print_error_3l(
            f"legacy_runner --project-path invalid",
            f"[REVERSE_PRECONDITION] {project_path} does not exist or is not a directory",
            f"verify the path or run /sdd-reverse-init first",
        )
        return 1

    _chat(f"Charge runner_signatures.yml...", 5)
    try:
        signatures = runner_lib.load_signatures(DEFAULT_SIGNATURES_PATH)
    except (FileNotFoundError, ValueError) as exc:
        _print_error_3l(
            f"legacy_runner --project-path={project_path} (signatures load)",
            f"[REVERSE_UI_CONFIG_INVALID] {exc}",
            f"verify {DEFAULT_SIGNATURES_PATH} exists and schema_version==1",
        )
        return 2

    # Resolve language: explicit --language wins over inventory autodetect
    language: str | None = args.language
    if language is None:
        language = _detect_language_from_inventory(project_path)
    if language is None:
        _print_error_3l(
            f"legacy_runner --project-path={project_path} (language detection)",
            f"[REVERSE_PRECONDITION] no language detected (run /sdd-reverse-inventory first OR pass --language)",
            f"lance /sdd-reverse-inventory {project_path.name} OU --language dotnet-webforms|dotnet-mvc|java-jee|php-procedural",
        )
        return 1

    _chat(f"Detection runner pour langage {language}...", 20)
    result = runner_lib.launch_legacy(
        project_path,
        signatures,
        language,
        port=args.port,
        timeout_s_override=args.timeout,
    )

    if result.ok:
        _chat(f"Runtime {result.runner_id} ready sur {result.base_url} (pid={result.pid}).", 100)
    else:
        first_err = result.errors[0] if result.errors else None
        if first_err is not None:
            _chat(f"Runner indisponible : {first_err.code}. Fallback static disponible.", 100)

    if args.json:
        print(json.dumps(_result_to_json_dict(result), indent=2, ensure_ascii=False))

    # Exit 0 in both runtime AND fallback-static modes : the caller decides
    # whether to proceed with static parse. The CLI itself only returns
    # non-zero for infrastructure errors (signatures missing, precondition fail).
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    """Handle '--cleanup' mode."""
    global _CHAT_QUIET
    _CHAT_QUIET = args.json

    project_path = Path(args.cleanup).resolve()
    if not project_path.is_dir():
        _print_error_3l(
            f"legacy_runner --cleanup invalid path",
            f"[REVERSE_PRECONDITION] {project_path} does not exist",
            f"verify the path passed to --cleanup",
        )
        return 1

    _chat(f"Nettoyage processus runner sous {project_path}...", 50)
    found = runner_lib.cleanup_pidfile_process(project_path)
    if found:
        _chat(f"Pidfile nettoye + process termine.", 100)
        if args.json:
            print(json.dumps({"ok": True, "action": "cleaned"}, ensure_ascii=False))
    else:
        _chat(f"Aucun pidfile trouve (deja propre).", 100)
        if args.json:
            print(json.dumps({"ok": True, "action": "noop"}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="legacy_runner",
        description="Phase 4 — detect+launch legacy runtime OR cleanup pidfile process.",
    )
    parser.add_argument("--project-path", help="Path to workspace/old/{Project}")
    parser.add_argument("--port", type=int, default=None, help="Override default_port from signatures")
    parser.add_argument("--language", default=None, help="Override language autodetect (e.g. dotnet-webforms)")
    parser.add_argument("--timeout", type=int, default=None, help="Override timeout_s from signatures")
    parser.add_argument("--cleanup", help="Cleanup mode : terminate pidfile process under this path")
    parser.add_argument("--json", action="store_true", help="Emit JSON on stdout, suppress chat updates")
    args = parser.parse_args(argv)

    if args.cleanup is not None:
        return cmd_cleanup(args)

    if args.project_path is None:
        parser.error("either --project-path or --cleanup is required")

    return cmd_launch(args)


if __name__ == "__main__":
    sys.exit(main())
