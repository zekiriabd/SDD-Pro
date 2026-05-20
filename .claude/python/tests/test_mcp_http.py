"""Integration tests for the HTTP transport — sdd_mcp.http_server.

Spawns the HTTP server on an ephemeral port in a background thread, fires
real http.client requests at it, and asserts JSON-RPC responses are well-
formed. No external dependencies.
"""
from __future__ import annotations

import http.client
import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
_PY_ROOT = REPO_ROOT / ".claude" / "python"
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_mcp.http_server import MCPHttpHandler, AUTH_TOKEN_ENV  # noqa: E402
from sdd_mcp.registry import Registry, Tool  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def _stub_registry() -> Registry:
    """Minimal stub registry so tests don't depend on real sdd_scripts."""
    r = Registry()
    r.register(
        Tool(
            name="echo",
            description="echo",
            input_schema={"type": "object", "additionalProperties": True},
            handler=lambda args: {
                "content": [{"type": "text", "text": json.dumps(args, sort_keys=True)}],
                "isError": False,
                "_meta": {"exitCode": 0},
            },
        )
    )
    return r


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port: int, registry: Registry) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), MCPHttpHandler)
    httpd.registry = registry  # type: ignore[attr-defined]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    # Tiny wait so the listening socket is ready
    time.sleep(0.05)
    return httpd


def _post_json(port: int, path: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any] | None]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        payload = json.dumps(body)
        conn.request(
            "POST",
            path,
            body=payload,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        r = conn.getresponse()
        data = r.read().decode("utf-8")
        parsed = json.loads(data) if data and r.status not in (204,) else None
        return r.status, parsed
    finally:
        conn.close()


def _get(port: int, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any] | None]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path, headers=headers or {})
        r = conn.getresponse()
        data = r.read().decode("utf-8")
        parsed = json.loads(data) if data and r.headers.get("Content-Type", "").startswith("application/json") else None
        return r.status, parsed
    finally:
        conn.close()


class TestHttpTransport(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure no auth token leaks between tests
        os.environ.pop(AUTH_TOKEN_ENV, None)
        self.port = _free_port()
        self.httpd = _start_server(self.port, _stub_registry())

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_healthz(self) -> None:
        status, payload = _get(self.port, "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok", "transport": "http"})

    def test_tools_list_endpoint(self) -> None:
        status, payload = _get(self.port, "/tools")
        self.assertEqual(status, 200)
        assert payload is not None
        self.assertEqual([t["name"] for t in payload["tools"]], ["echo"])

    def test_post_mcp_initialize(self) -> None:
        status, body = _post_json(
            self.port, "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["result"]["protocolVersion"], "2024-11-05")

    def test_post_mcp_tools_list(self) -> None:
        status, body = _post_json(
            self.port, "/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual([t["name"] for t in body["result"]["tools"]], ["echo"])

    def test_post_mcp_tools_call(self) -> None:
        status, body = _post_json(
            self.port, "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"x": 1, "y": 2}},
            },
        )
        self.assertEqual(status, 200)
        assert body is not None
        text = body["result"]["content"][0]["text"]
        self.assertEqual(json.loads(text), {"x": 1, "y": 2})

    def test_post_unknown_method_returns_jsonrpc_error(self) -> None:
        status, body = _post_json(
            self.port, "/mcp",
            {"jsonrpc": "2.0", "id": 99, "method": "no.such"},
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["error"]["code"], -32601)

    def test_post_malformed_json(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("POST", "/mcp", body="not json",
                         headers={"Content-Type": "application/json"})
            r = conn.getresponse()
            data = r.read().decode("utf-8")
            self.assertEqual(r.status, 200)
            body = json.loads(data)
            self.assertEqual(body["error"]["code"], -32700)
        finally:
            conn.close()

    def test_notification_returns_204(self) -> None:
        status, body = _post_json(
            self.port, "/mcp",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        self.assertEqual(status, 204)
        self.assertIsNone(body)

    def test_unknown_path_404(self) -> None:
        status, _ = _get(self.port, "/somewhere")
        self.assertEqual(status, 404)


class TestHttpAuth(unittest.TestCase):
    def setUp(self) -> None:
        os.environ[AUTH_TOKEN_ENV] = "secret-abc"
        self.port = _free_port()
        self.httpd = _start_server(self.port, _stub_registry())

    def tearDown(self) -> None:
        os.environ.pop(AUTH_TOKEN_ENV, None)
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_missing_token_unauthorized(self) -> None:
        status, body = _post_json(
            self.port, "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        self.assertEqual(status, 401)

    def test_wrong_token_unauthorized(self) -> None:
        status, body = _post_json(
            self.port, "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Authorization": "Bearer wrong"},
        )
        self.assertEqual(status, 401)

    def test_correct_token_ok(self) -> None:
        status, body = _post_json(
            self.port, "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Authorization": "Bearer secret-abc"},
        )
        self.assertEqual(status, 200)
        assert body is not None
        self.assertEqual(body["result"], {})

    def test_healthz_no_auth_required(self) -> None:
        status, _ = _get(self.port, "/healthz")
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
