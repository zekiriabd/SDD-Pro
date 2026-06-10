"""structured_log.py — Lightweight structured JSON logger for reverse scripts.

Phase 1-4 scripts emit one-line JSON events to stderr by default, ingestible
by an observability layer (CI log shipper, console.db tailer, jq pipeline).
No external dependencies — uses only stdlib `logging` + `json`.

Public API:
    get_logger(name) -> logging.Logger
    log_event(logger, event, **fields) -> None
    install_default_handler(level="INFO") -> None

Schema of an emitted event (one JSON object per line):

    {
        "ts":     "2026-06-10T14:33:22.114Z",  # ISO-8601 UTC with millis
        "level":  "INFO" | "WARN" | "ERROR",
        "logger": "sdd_reverse.scan_legacy",
        "event":  "language.detected",         # dotted event name
        "fields": { ...arbitrary structured payload... }
    }

Activation:
    - Off by default — `install_default_handler()` must be called explicitly
      by the CLI entry point (reverse_inventory, reverse_audit, etc.) OR
      via env var `SDD_REVERSE_LOG=json` (auto-installed on import).
    - When inactive, calls are zero-cost no-ops (handler list empty).

Why JSON-on-stderr (not a file under workspace/old/)?
    - Composable with any log pipeline (jq, fluentd, GitHub Actions matrix)
    - Survives across `subprocess.run(capture_output=True)` test harnesses
    - Avoids file ownership ambiguity with workspace/old/.sys/
    - Tech Lead can redirect with `2> reverse.log` if needed
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


_LOGGER_NAMESPACE = "sdd_reverse"
_ENV_ENABLE = "SDD_REVERSE_LOG"
_ENV_LEVEL = "SDD_REVERSE_LOG_LEVEL"


class _JsonOneLineFormatter(logging.Formatter):
    """Format every log record as a single-line JSON object on stderr.

    Records emitted via ``log_event(logger, event, **fields)`` carry the
    structured payload through ``record.event`` and ``record.fields``.
    Other records (plain ``logger.info("text")``) are still rendered as
    JSON with ``event="message"`` and ``fields={"text": ...}`` so the
    schema stays homogeneous.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc)
        # Millisecond precision is sufficient for our cadence.
        iso_ts = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"
        event = getattr(record, "event", None) or "message"
        fields = getattr(record, "fields", None)
        if fields is None:
            # Fallback for plain logger calls
            fields = {"text": record.getMessage()}
        payload = {
            "ts": iso_ts,
            "level": record.levelname,
            "logger": record.name,
            "event": event,
            "fields": fields,
        }
        # Exception info appended as nested field (avoid breaking JSON line)
        if record.exc_info:
            payload["fields"] = {
                **payload["fields"],
                "exception": self.formatException(record.exc_info),
            }
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            # Last-resort serialization
            return json.dumps({
                "ts": iso_ts,
                "level": record.levelname,
                "logger": record.name,
                "event": event,
                "fields": {"_serialization_failed": True},
            })


def install_default_handler(level: str = "INFO") -> None:
    """Install the JSON stderr handler on the `sdd_reverse` namespace.

    Idempotent — if a handler matching our formatter is already installed,
    no duplicate is added (avoids double-logging when CLIs share imports).
    """
    root = logging.getLogger(_LOGGER_NAMESPACE)
    for h in root.handlers:
        if isinstance(getattr(h, "formatter", None), _JsonOneLineFormatter):
            return  # already installed
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(_JsonOneLineFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Don't propagate to root (avoid duplicate plain-text on stderr)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the `sdd_reverse` namespace.

    Example:
        log = get_logger(__name__)
        log_event(log, "scan.start", project=str(root))
    """
    if not name.startswith(_LOGGER_NAMESPACE):
        # Force every reverse log under the namespace for filtering
        name = f"{_LOGGER_NAMESPACE}.{name}"
    return logging.getLogger(name)


#: Common short-form aliases mapped to Python logging level names.
_LEVEL_ALIASES: dict[str, str] = {
    "WARN": "WARNING",
    "ERR": "ERROR",
    "FATAL": "CRITICAL",
    "TRACE": "DEBUG",
}


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a structured event via ``logger`` at INFO level by default.

    ``event`` is a dotted name (e.g. ``inventory.unit.allocated``).
    ``fields`` is a flat dict of JSON-serializable values.

    The level can be overridden through the ``level`` field if needed::

        log_event(log, "lock.contention", level="WARN", agent_id="A")

    Short-form aliases ``WARN``, ``ERR``, ``FATAL``, ``TRACE`` are
    normalised to their Python logging equivalents.
    """
    raw_level = str(fields.pop("level", "INFO")).upper()
    canonical = _LEVEL_ALIASES.get(raw_level, raw_level)
    level = logging.getLevelName(canonical)
    if not isinstance(level, int):
        level = logging.INFO
    logger.log(
        level,
        event,
        extra={"event": event, "fields": fields},
    )


# Auto-install when the env var is set — keeps CLI invocations zero-config
# for CI pipelines that just want to capture structured logs without
# touching every entry point.
if os.environ.get(_ENV_ENABLE, "").lower() in {"1", "json", "true", "on"}:
    install_default_handler(level=os.environ.get(_ENV_LEVEL, "INFO"))
