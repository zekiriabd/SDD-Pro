"""HTTP transport for sdd_mcp — opt-in alternative to stdio (Phase 3).

Implements a minimal HTTP transport so non-stdio clients (n8n, Make,
internal dashboards, curl-based smoke tests) can talk to the SDD_Pro MCP
server. Pure stdlib `http.server` — no Flask, no FastAPI, no aiohttp.

Endpoints:
  POST /mcp          — single JSON-RPC request, returns single JSON response
  GET  /healthz      — liveness probe (always 200 OK)
  GET  /tools        — convenience: returns tools/list payload as JSON

Authentication: optional shared-secret bearer token. Set `SDD_MCP_AUTH_TOKEN`
env var; if set, all `/mcp` requests must carry `Authorization: Bearer <token>`.

Run:
    python -m sdd_mcp.server --transport http --port 8765
    python -m sdd_mcp.server --transport http --port 8765 --host 127.0.0.1
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .protocol import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    JsonRpcError,
    encode_message,
    is_notification,
    make_error,
    make_response,
    parse_message,
    validate_request,
)
from .registry import Registry, build_default_registry
from .server import dispatch


AUTH_TOKEN_ENV = "SDD_MCP_AUTH_TOKEN"


class MCPHttpHandler(BaseHTTPRequestHandler):
    """One handler instance per request — relies on `server.registry` for state."""

    # Silence default access log on stderr; the framework expects clean stderr.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    @property
    def registry(self) -> Registry:
        return self.server.registry  # type: ignore[attr-defined]

    def _auth_ok(self) -> bool:
        token = os.environ.get(AUTH_TOKEN_ENV)
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {token}"

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 — http.server casing
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send_json(200, {"status": "ok", "transport": "http"})
            return
        if self.path == "/tools":
            if not self._auth_ok():
                self._send_json(401, {"error": "unauthorized"})
                return
            self._send_json(200, {"tools": self.registry.list_descriptors()})
            return
        self._send_json(404, {"error": "not found", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self._send_json(404, {"error": "not found", "path": self.path})
            return
        if not self._auth_ok():
            self._send_json(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""

        try:
            msg = parse_message(raw)
            request_id, method, params = validate_request(msg)
        except JsonRpcError as e:
            self._send_json(200, make_error(None, e.code, e.message, e.data))
            return

        notification = is_notification(msg)
        try:
            result = dispatch(self.registry, method, params)
        except JsonRpcError as e:
            if notification:
                self.send_response(204)
                self.end_headers()
                return
            self._send_json(200, make_error(request_id, e.code, e.message, e.data))
            return
        except Exception as e:  # pragma: no cover
            if notification:
                self.send_response(204)
                self.end_headers()
                return
            self._send_json(200, make_error(request_id, INTERNAL_ERROR, f"Unhandled: {e}"))
            return

        if notification:
            self.send_response(204)
            self.end_headers()
            return
        self._send_json(200, make_response(request_id, result if result is not None else {}))


def serve_http(host: str = "127.0.0.1", port: int = 8765, registry: Registry | None = None) -> None:
    """Block on the HTTP server. Ctrl-C / SIGTERM cleanly shuts down."""
    httpd = ThreadingHTTPServer((host, port), MCPHttpHandler)
    httpd.registry = registry or build_default_registry()  # type: ignore[attr-defined]
    sys.stderr.write(f"sdd_mcp HTTP transport listening on http://{host}:{port}\n")
    sys.stderr.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        httpd.server_close()
