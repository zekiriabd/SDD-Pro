"""Tool registry — central catalogue of MCP tools exposed by SDD_Pro.

Each tool is a `Tool` dataclass with a JSON Schema for inputs and a handler
callable. `list_tool_descriptors()` builds the response of `tools/list`,
`call_tool()` dispatches `tools/call`.

Adding a tool: import its handler, append a Tool() to TOOLS in the
appropriate tools/*.py module, and re-register by importing here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .protocol import INVALID_PARAMS, METHOD_NOT_FOUND, JsonRpcError


# Handler signature: (arguments: dict) -> dict with MCP `tools/call` result
# shape: {"content": [{"type": "text", "text": "..."}], "isError": bool}.
ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


class Registry:
    """Append-only registry. One instance is built at server startup."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def register_many(self, tools: list[Tool]) -> None:
        for t in tools:
            self.register(t)

    def list_descriptors(self) -> list[dict[str, Any]]:
        """Build the `tools` array of the MCP tools/list response."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch tools/call by name. Raises JsonRpcError on miss / bad args."""
        if name not in self._tools:
            raise JsonRpcError(METHOD_NOT_FOUND, f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "'arguments' must be an object")
        return self._tools[name].handler(arguments)


def build_default_registry() -> Registry:
    """Eager import of all tool modules + register their tools.

    Phase 1 (read-only): status, us_ops.
    Phase 2 (LLM-driven via claude CLI): pipeline.
    """
    from .tools import pipeline, status, us_ops

    registry = Registry()
    registry.register_many(status.TOOLS)
    registry.register_many(us_ops.TOOLS)
    registry.register_many(pipeline.TOOLS)
    return registry
