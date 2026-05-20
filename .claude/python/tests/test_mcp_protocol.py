"""Unit tests for sdd_mcp.protocol — JSON-RPC envelope handling.

Pure stdlib, no subprocess. Tests parse/encode round-trip, error envelopes,
notification detection, and request validation.
"""
from __future__ import annotations

import json
import unittest

from sdd_mcp.protocol import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    PARSE_ERROR,
    JsonRpcError,
    encode_message,
    is_notification,
    make_error,
    make_response,
    parse_message,
    validate_request,
)


class TestParseMessage(unittest.TestCase):
    def test_valid_json_returns_dict(self) -> None:
        msg = parse_message('{"jsonrpc":"2.0","id":1,"method":"ping"}')
        self.assertEqual(msg["method"], "ping")
        self.assertEqual(msg["id"], 1)

    def test_malformed_json_raises_parse_error(self) -> None:
        with self.assertRaises(JsonRpcError) as ctx:
            parse_message("not json")
        self.assertEqual(ctx.exception.code, PARSE_ERROR)

    def test_non_object_raises_invalid_request(self) -> None:
        with self.assertRaises(JsonRpcError) as ctx:
            parse_message("[1, 2, 3]")
        self.assertEqual(ctx.exception.code, INVALID_REQUEST)


class TestEncodeMessage(unittest.TestCase):
    def test_encode_ends_with_newline(self) -> None:
        out = encode_message({"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertTrue(out.endswith("\n"))

    def test_encode_round_trip(self) -> None:
        original = {"jsonrpc": "2.0", "id": 42, "result": {"ok": True}}
        decoded = json.loads(encode_message(original).rstrip())
        self.assertEqual(decoded, original)

    def test_encode_preserves_non_ascii(self) -> None:
        out = encode_message({"jsonrpc": "2.0", "id": 1, "result": {"msg": "café"}})
        self.assertIn("café", out)


class TestEnvelopeHelpers(unittest.TestCase):
    def test_make_response_shape(self) -> None:
        r = make_response(7, {"x": 1})
        self.assertEqual(r, {"jsonrpc": "2.0", "id": 7, "result": {"x": 1}})

    def test_make_error_shape_minimal(self) -> None:
        r = make_error(7, -32601, "Not found")
        self.assertEqual(
            r, {"jsonrpc": "2.0", "id": 7, "error": {"code": -32601, "message": "Not found"}}
        )

    def test_make_error_with_data(self) -> None:
        r = make_error(None, -32700, "Parse error", data={"line": 3})
        self.assertEqual(r["error"]["data"], {"line": 3})


class TestValidateRequest(unittest.TestCase):
    def test_valid_request(self) -> None:
        rid, method, params = validate_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        self.assertEqual((rid, method), (1, "tools/list"))
        self.assertEqual(params, {})

    def test_missing_method_invalid_request(self) -> None:
        with self.assertRaises(JsonRpcError) as ctx:
            validate_request({"jsonrpc": "2.0", "id": 1})
        self.assertEqual(ctx.exception.code, INVALID_REQUEST)

    def test_wrong_jsonrpc_version(self) -> None:
        with self.assertRaises(JsonRpcError) as ctx:
            validate_request({"jsonrpc": "1.0", "id": 1, "method": "x"})
        self.assertEqual(ctx.exception.code, INVALID_REQUEST)

    def test_params_must_be_object(self) -> None:
        with self.assertRaises(JsonRpcError) as ctx:
            validate_request(
                {"jsonrpc": "2.0", "id": 1, "method": "x", "params": [1, 2]}
            )
        self.assertEqual(ctx.exception.code, INVALID_PARAMS)

    def test_default_params_empty(self) -> None:
        _, _, params = validate_request({"jsonrpc": "2.0", "id": 1, "method": "x"})
        self.assertEqual(params, {})


class TestNotification(unittest.TestCase):
    def test_no_id_is_notification(self) -> None:
        self.assertTrue(is_notification({"jsonrpc": "2.0", "method": "initialized"}))

    def test_with_id_is_request(self) -> None:
        self.assertFalse(
            is_notification({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        )


if __name__ == "__main__":
    unittest.main()
