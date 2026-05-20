"""Minimal MCP / JSON-RPC 2.0 protocol implementation (stdlib-only).

Implements the subset of Model Context Protocol used by Phase 1:
- initialize / initialized
- tools/list
- tools/call
- ping

Wire format (stdio transport): newline-delimited JSON, one message per line,
UTF-8 encoded. See https://spec.modelcontextprotocol.io/.

Why hand-rolled instead of using the `mcp` SDK: the framework invariant is
stdlib-pure (cf. CLAUDE.md). The protocol is small enough that a 150-line
implementation is cheaper than a new external dependency.
"""
from __future__ import annotations

import json
from typing import Any


# JSON-RPC 2.0 standard error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    """Raised to short-circuit handler -> JSON-RPC error response."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        return payload


def make_response(request_id: Any, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response envelope."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response envelope."""
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": err}


def parse_message(raw: str) -> dict[str, Any]:
    """Parse one incoming line as a JSON-RPC message.

    Raises JsonRpcError(PARSE_ERROR) on malformed JSON. Returns the parsed
    dict otherwise (caller validates `jsonrpc`/`method` fields).
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise JsonRpcError(PARSE_ERROR, f"Parse error: {e}") from e
    if not isinstance(msg, dict):
        raise JsonRpcError(INVALID_REQUEST, "Message must be a JSON object")
    return msg


def encode_message(msg: dict[str, Any]) -> str:
    """Encode an outgoing JSON-RPC message as a single line (with trailing \\n).

    Uses compact separators to keep stdio chatter low, ensure_ascii=False so
    non-ASCII (accents, emoji in error messages) survives the round-trip.
    """
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n"


def is_notification(msg: dict[str, Any]) -> bool:
    """A JSON-RPC notification has no `id` field -> no response expected."""
    return "id" not in msg


def validate_request(msg: dict[str, Any]) -> tuple[Any, str, dict[str, Any]]:
    """Validate envelope, return (id, method, params).

    Raises JsonRpcError(INVALID_REQUEST) if mandatory fields are missing.
    """
    if msg.get("jsonrpc") != "2.0":
        raise JsonRpcError(INVALID_REQUEST, "Expected jsonrpc='2.0'")
    method = msg.get("method")
    if not isinstance(method, str) or not method:
        raise JsonRpcError(INVALID_REQUEST, "Missing or invalid 'method'")
    params = msg.get("params", {}) or {}
    if not isinstance(params, dict):
        raise JsonRpcError(INVALID_PARAMS, "'params' must be an object")
    return msg.get("id"), method, params
