"""Integration tests for sdd_mcp.server — full handshake + dispatch loop.

These tests drive the server through its public `handle_line` entry point
without spawning a subprocess, so we can inspect each response synchronously.
A stub registry is used to avoid invoking real sdd_scripts/* during the
protocol-level checks.
"""
from __future__ import annotations

import io
import json
import unittest
from typing import Any

from sdd_mcp.registry import Registry, Tool
from sdd_mcp.server import dispatch, handle_line, serve


def _stub_handler(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": f"echo:{sorted(args.items())}"}],
        "isError": False,
        "_meta": {"exitCode": 0, "json": args},
    }


def _stub_registry() -> Registry:
    r = Registry()
    r.register(
        Tool(
            name="echo",
            description="Echo back the arguments — test only.",
            input_schema={"type": "object", "additionalProperties": True},
            handler=_stub_handler,
        )
    )
    return r


def _decode(line: str | None) -> dict[str, Any]:
    assert line is not None, "expected a response line"
    return json.loads(line)


class TestInitializeHandshake(unittest.TestCase):
    def test_initialize_returns_protocol_version_and_capabilities(self) -> None:
        reg = _stub_registry()
        resp = _decode(handle_line(
            reg,
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        ))
        self.assertEqual(resp["id"], 1)
        result = resp["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "sdd-pro")

    def test_initialized_notification_produces_no_response(self) -> None:
        reg = _stub_registry()
        reply = handle_line(
            reg,
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        )
        self.assertIsNone(reply)


class TestToolsList(unittest.TestCase):
    def test_tools_list_returns_registered_tools(self) -> None:
        reg = _stub_registry()
        resp = _decode(handle_line(
            reg,
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ))
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(names, ["echo"])
        self.assertIn("inputSchema", resp["result"]["tools"][0])


class TestToolsCall(unittest.TestCase):
    def test_call_dispatches_to_handler(self) -> None:
        reg = _stub_registry()
        resp = _decode(handle_line(
            reg,
            json.dumps({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"x": 1}},
            }),
        ))
        self.assertFalse(resp["result"]["isError"])
        self.assertIn("echo:", resp["result"]["content"][0]["text"])

    def test_unknown_tool_returns_method_not_found(self) -> None:
        reg = _stub_registry()
        resp = _decode(handle_line(
            reg,
            json.dumps({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "does-not-exist", "arguments": {}},
            }),
        ))
        self.assertEqual(resp["error"]["code"], -32601)

    def test_missing_name_returns_invalid_params(self) -> None:
        reg = _stub_registry()
        resp = _decode(handle_line(
            reg,
            json.dumps({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"arguments": {}},
            }),
        ))
        self.assertEqual(resp["error"]["code"], -32602)


class TestPing(unittest.TestCase):
    def test_ping_returns_empty_result(self) -> None:
        reg = _stub_registry()
        resp = _decode(handle_line(
            reg,
            json.dumps({"jsonrpc": "2.0", "id": 6, "method": "ping"}),
        ))
        self.assertEqual(resp["result"], {})


class TestErrors(unittest.TestCase):
    def test_unknown_method_returns_method_not_found(self) -> None:
        reg = _stub_registry()
        resp = _decode(handle_line(
            reg,
            json.dumps({"jsonrpc": "2.0", "id": 7, "method": "nope"}),
        ))
        self.assertEqual(resp["error"]["code"], -32601)

    def test_malformed_json_returns_parse_error_with_null_id(self) -> None:
        reg = _stub_registry()
        resp = _decode(handle_line(reg, "not json"))
        self.assertEqual(resp["error"]["code"], -32700)
        self.assertIsNone(resp["id"])

    def test_empty_line_is_ignored(self) -> None:
        reg = _stub_registry()
        self.assertIsNone(handle_line(reg, ""))
        self.assertIsNone(handle_line(reg, "   \n"))


class TestServeLoop(unittest.TestCase):
    def test_serve_processes_multiple_messages(self) -> None:
        reg = _stub_registry()
        stdin = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n" +
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n"
        )
        stdout = io.StringIO()
        serve(stdin=stdin, stdout=stdout, registry=reg)

        lines = [l for l in stdout.getvalue().split("\n") if l]
        self.assertEqual(len(lines), 2)
        r1, r2 = json.loads(lines[0]), json.loads(lines[1])
        self.assertEqual(r1["id"], 1)
        self.assertEqual(r2["id"], 2)
        self.assertEqual([t["name"] for t in r2["result"]["tools"]], ["echo"])

    def test_serve_skips_notifications(self) -> None:
        reg = _stub_registry()
        stdin = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n" +
            json.dumps({"jsonrpc": "2.0", "id": 99, "method": "ping"}) + "\n"
        )
        stdout = io.StringIO()
        serve(stdin=stdin, stdout=stdout, registry=reg)

        lines = [l for l in stdout.getvalue().split("\n") if l]
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["id"], 99)


class TestDispatchDirect(unittest.TestCase):
    def test_dispatch_initialize(self) -> None:
        reg = _stub_registry()
        result = dispatch(reg, "initialize", {})
        self.assertEqual(result["protocolVersion"], "2024-11-05")

    def test_dispatch_initialized_returns_none(self) -> None:
        reg = _stub_registry()
        self.assertIsNone(dispatch(reg, "notifications/initialized", {}))
        self.assertIsNone(dispatch(reg, "initialized", {}))


if __name__ == "__main__":
    unittest.main()
