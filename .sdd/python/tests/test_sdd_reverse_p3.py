"""test_sdd_reverse_p3.py — P3 closure tests.

Covers :
    P3.12  deps_graph_builder._parse_npm_json / _parse_composer_json
           switched to json.loads with regex fallback (handles peer/
           optionalDependencies + nested objects + malformed legacy)
    P3.13  sync_parity_snapshots CLI (regen + dry-run + .prev backup)
    P3.14  structured_log JSON emission, install idempotence, levels
"""
from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest


# ===========================================================================
# P3.12 — deps_graph_builder npm + composer parsing
# ===========================================================================

def test_npm_parses_all_four_sections() -> None:
    from sdd_reverse.deps_graph_builder import _parse_npm_json
    content = json.dumps({
        "dependencies": {"react": "^18.2.0", "lodash": "~4.17.21"},
        "devDependencies": {"vitest": "^1.0.0"},
        "peerDependencies": {"react-dom": "^18.0.0"},
        "optionalDependencies": {"fsevents": "^2.3.0"},
    })
    deps = dict(_parse_npm_json(content))
    assert deps == {
        "react": "18.2.0",
        "lodash": "4.17.21",
        "vitest": "1.0.0",
        "react-dom": "18.0.0",
        "fsevents": "2.3.0",
    }


def test_npm_handles_nested_objects() -> None:
    """A package.json with nested ``resolutions`` / ``scripts`` must not
    leak those nested keys into the deps output."""
    from sdd_reverse.deps_graph_builder import _parse_npm_json
    content = json.dumps({
        "name": "myapp",
        "dependencies": {"react": "^18.0.0"},
        "scripts": {"test": "jest --coverage"},  # nested, not a dep
        "resolutions": {                          # nested object, not a dep
            "ansi-regex": "5.0.1",
            "minimist": "1.2.6",
        },
        "pnpm": {                                  # deeply nested
            "overrides": {
                "lodash": "4.17.21",
            },
        },
    })
    deps = dict(_parse_npm_json(content))
    assert deps == {"react": "18.0.0"}
    # Nested keys MUST NOT leak
    assert "test" not in deps
    assert "ansi-regex" not in deps
    assert "minimist" not in deps


def test_npm_fallback_on_malformed_json() -> None:
    """Legacy package.json with trailing comma → regex fallback still works."""
    from sdd_reverse.deps_graph_builder import _parse_npm_json
    # Trailing comma invalidates JSON but regex catches the basic shape
    content = (
        '{"dependencies": {"react": "^18.0.0", "vue": "^3.0.0",}}'
    )
    deps = dict(_parse_npm_json(content))
    # At minimum react should be captured by the regex fallback
    assert "react" in deps


def test_npm_empty_object_no_deps() -> None:
    from sdd_reverse.deps_graph_builder import _parse_npm_json
    assert _parse_npm_json('{"dependencies": {}}') == []


def test_npm_handles_non_string_values_gracefully() -> None:
    """A weird package.json with non-string version values must not crash."""
    from sdd_reverse.deps_graph_builder import _parse_npm_json
    content = json.dumps({
        "dependencies": {
            "react": "^18.0.0",
            "weird": 42,           # number, not string — skip
            "alsoweird": None,     # null — skip
        },
    })
    deps = dict(_parse_npm_json(content))
    assert deps == {"react": "18.0.0"}


def test_composer_parses_require_and_require_dev() -> None:
    from sdd_reverse.deps_graph_builder import _parse_composer_json
    content = json.dumps({
        "require": {
            "php": ">=7.4",
            "symfony/console": "^5.4",
            "doctrine/orm": "^2.10",
        },
        "require-dev": {
            "phpunit/phpunit": "^9.5",
        },
    })
    deps = dict(_parse_composer_json(content))
    # 'php' must be skipped (runtime pseudo-package)
    assert "php" not in deps
    assert deps["symfony/console"] == "5.4"
    assert deps["doctrine/orm"] == "2.10"
    assert deps["phpunit/phpunit"] == "9.5"


def test_composer_fallback_on_malformed_json() -> None:
    from sdd_reverse.deps_graph_builder import _parse_composer_json
    # Comment in JSON (invalid for json.loads, regex still catches)
    content = (
        '{\n'
        '  // legacy comment\n'
        '  "require": {"symfony/console": "^5.0"}\n'
        '}'
    )
    deps = dict(_parse_composer_json(content))
    assert "symfony/console" in deps


# ===========================================================================
# P3.13 — sync_parity_snapshots CLI
# ===========================================================================

PYTHON_ROOT = Path(__file__).resolve().parent.parent  # .sdd/python/


def _run_sync(args: list[str]) -> tuple[int, str, str]:
    """Invoke sync_parity_snapshots CLI; return (rc, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "-m", "sdd_reverse_scripts.sync_parity_snapshots", *args],
        capture_output=True, text=True, cwd=str(PYTHON_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


def test_sync_parity_snapshots_dry_run_succeeds() -> None:
    """Dry-run reports current state without writing the snapshots file."""
    rc, out, err = _run_sync(["--dry-run", "--json"])
    assert rc == 0, f"unexpected exit: rc={rc} err={err}"
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert isinstance(payload["tracked"], list)
    assert len(payload["tracked"]) >= 2
    assert "sdd_lib/atomic_write.py" in payload["tracked"]
    assert "sdd_lib/file_locks.py" in payload["tracked"]


def test_sync_parity_snapshots_diff_zero_when_in_sync() -> None:
    """When local snapshots already match upstream, diff is empty."""
    rc, out, err = _run_sync(["--dry-run", "--json"])
    assert rc == 0
    payload = json.loads(out)
    # The repo is in a synced state post-P0 — diff should be 0
    assert payload["changed_count"] == 0, payload


# ===========================================================================
# P3.14 — structured_log JSON emission
# ===========================================================================

def _capture_log_event(event: str, **fields) -> dict:
    """Helper : install handler bound to a StringIO buffer and capture one event.

    pytest's `capsys` doesn't capture a logger handler installed at import
    time because it binds to `sys.stderr` BEFORE capsys swaps it. This
    helper builds a fresh handler bound to our own buffer for testing.
    """
    from sdd_reverse.structured_log import (
        _JsonOneLineFormatter, get_logger, log_event,
    )
    buf = io.StringIO()
    handler = logging.StreamHandler(stream=buf)
    handler.setFormatter(_JsonOneLineFormatter())
    root = logging.getLogger("sdd_reverse")
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_propagate = root.propagate
    try:
        root.handlers = [handler]
        root.setLevel("DEBUG")
        root.propagate = False
        log = get_logger("test_capture")
        log_event(log, event, **fields)
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        root.propagate = saved_propagate
    line = buf.getvalue().strip().splitlines()[-1]
    return json.loads(line)


def test_structured_log_event_emits_json_to_stderr() -> None:
    payload = _capture_log_event("test.event", foo="bar", count=3)
    assert payload["event"] == "test.event"
    assert payload["level"] == "INFO"
    assert payload["logger"].startswith("sdd_reverse.")
    assert payload["fields"] == {"foo": "bar", "count": 3}
    assert "ts" in payload


def test_structured_log_install_is_idempotent() -> None:
    """Multiple install_default_handler calls don't multiply handlers."""
    from sdd_reverse.structured_log import install_default_handler
    install_default_handler()
    before = len(logging.getLogger("sdd_reverse").handlers)
    install_default_handler()
    install_default_handler()
    after = len(logging.getLogger("sdd_reverse").handlers)
    assert before == after, "duplicate handlers detected"


def test_structured_log_level_override_via_fields() -> None:
    """The `level=` kwarg in log_event upgrades the emission level.

    WARN alias is normalised to WARNING (standard Python logging name).
    """
    payload = _capture_log_event("test.warn", level="WARN", reason="threshold")
    assert payload["level"] == "WARNING"
    assert payload["fields"] == {"reason": "threshold"}


def test_structured_log_level_aliases() -> None:
    """Common short-form level aliases are normalised."""
    for short, canonical in (("ERR", "ERROR"), ("FATAL", "CRITICAL"), ("TRACE", "DEBUG")):
        payload = _capture_log_event("test.alias", level=short)
        assert payload["level"] == canonical, f"{short} → expected {canonical}"


def test_structured_log_namespace_enforcement() -> None:
    """get_logger always returns a logger under sdd_reverse.* namespace."""
    from sdd_reverse.structured_log import get_logger
    log = get_logger("random_name")
    assert log.name.startswith("sdd_reverse.")
    log2 = get_logger("sdd_reverse.explicit")
    assert log2.name == "sdd_reverse.explicit"


def test_structured_log_no_handler_no_output() -> None:
    """Without any handler, log_event is effectively silent (no exception)."""
    import logging as std_logging
    from sdd_reverse.structured_log import get_logger, log_event
    root = std_logging.getLogger("sdd_reverse")
    saved_handlers = list(root.handlers)
    saved_propagate = root.propagate
    buf = io.StringIO()
    sentinel_handler = std_logging.StreamHandler(stream=buf)
    sentinel_handler.setLevel(std_logging.CRITICAL + 10)  # never accepts
    try:
        root.handlers = [sentinel_handler]
        root.propagate = False
        log = get_logger("silent")
        log_event(log, "should.be.silent", x=1)
        assert buf.getvalue() == ""
    finally:
        root.handlers = saved_handlers
        root.propagate = saved_propagate
