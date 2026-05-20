"""SDD_Pro MCP server — entry point (stdio default, HTTP opt-in).

Exposes 14 MCP tools to non-Claude-Code clients (Cursor, Windsurf, Cline,
Claude Desktop, n8n, ...). Default transport is stdio (newline-delimited
JSON-RPC); `--transport http` enables a JSON-over-HTTP endpoint for
orchestrators that can't drive a stdio child process.

Run:
    python -m sdd_mcp.server                          # stdio (default)
    python -m sdd_mcp.server --transport http         # HTTP on 127.0.0.1:8765
    python -m sdd_mcp.server --transport http --port 9000 --host 0.0.0.0

stdio mode reads one JSON-RPC request per line from stdin and writes the
response to stdout. Logs go to stderr so they never pollute the protocol
stream. HTTP mode listens on /mcp for POST requests, /healthz for liveness,
/tools for discovery.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, TextIO

from . import PROTOCOL_VERSION, __version__
from .protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    JsonRpcError,
    encode_message,
    is_notification,
    make_error,
    make_response,
    parse_message,
    validate_request,
)
from .registry import Registry, build_default_registry


SERVER_INFO = {"name": "sdd-pro", "version": __version__}


def _handle_initialize(_params: dict[str, Any]) -> dict[str, Any]:
    """Reply to the `initialize` handshake. We only advertise tools."""
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
    }


def _handle_tools_list(registry: Registry, _params: dict[str, Any]) -> dict[str, Any]:
    return {"tools": registry.list_descriptors()}


def _handle_tools_call(registry: Registry, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise JsonRpcError(INVALID_PARAMS, "Missing 'name' in tools/call params")
    arguments = params.get("arguments", {}) or {}
    return registry.call(name, arguments)


def dispatch(
    registry: Registry,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Route one validated request to the right handler.

    Returns the result payload for the JSON-RPC envelope, or None for
    notifications that don't need a result.
    """
    if method == "initialize":
        return _handle_initialize(params)
    if method == "initialized" or method == "notifications/initialized":
        return None  # client confirms handshake — no response expected
    if method == "ping":
        return {}
    if method == "tools/list":
        return _handle_tools_list(registry, params)
    if method == "tools/call":
        return _handle_tools_call(registry, params)
    raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {method}")


def handle_line(registry: Registry, raw_line: str) -> str | None:
    """Process one input line; return the response line (with \\n) or None.

    None is returned for notifications (no `id` field) — the caller writes
    nothing back, matching the JSON-RPC 2.0 spec.
    """
    raw = raw_line.strip()
    if not raw:
        return None
    try:
        msg = parse_message(raw)
        request_id, method, params = validate_request(msg)
    except JsonRpcError as e:
        # If we can't even parse, we have no id — respond with null id (spec-allowed).
        return encode_message(make_error(None, e.code, e.message, e.data))

    notification = is_notification(msg)
    try:
        result = dispatch(registry, method, params)
    except JsonRpcError as e:
        if notification:
            return None
        return encode_message(make_error(request_id, e.code, e.message, e.data))
    except Exception as e:  # pragma: no cover — last-resort safety net
        if notification:
            return None
        return encode_message(
            make_error(request_id, INTERNAL_ERROR, f"Unhandled exception: {e}")
        )

    if notification:
        return None
    return encode_message(make_response(request_id, result if result is not None else {}))


def serve(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    registry: Registry | None = None,
) -> None:
    """Main loop — read one JSON message per line, dispatch, write reply.

    Returns when stdin is closed (EOF). Pure stdio, no signals, no threading.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    registry = registry or build_default_registry()

    for line in stdin:
        reply = handle_line(registry, line)
        if reply is not None:
            stdout.write(reply)
            stdout.flush()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sdd_mcp.server",
        description="SDD_Pro MCP server (stdio default, HTTP opt-in).",
    )
    p.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport layer (default: stdio).",
    )
    p.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host (HTTP transport only, default: 127.0.0.1).",
    )
    p.add_argument(
        "--port",
        type=int,
        default=8765,
        help="HTTP bind port (HTTP transport only, default: 8765).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Default transport: stdio. Opt-in: --transport http."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.transport == "stdio":
            serve()
        else:
            from .http_server import serve_http  # local import keeps stdio fast

            serve_http(host=args.host, port=args.port)
    except KeyboardInterrupt:  # pragma: no cover
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
