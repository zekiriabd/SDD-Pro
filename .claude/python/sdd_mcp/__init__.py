"""SDD_Pro MCP server module (v6.9 — Sprint MCP-1).

Exposes SDD_Pro commands as Model Context Protocol tools so non-Claude-Code
clients (Cursor, Windsurf, Cline, Claude Desktop, ...) can invoke the
deterministic scripts directly via JSON-RPC over stdio.

Phase 1 scope (this sprint): 7 read-only tools wrapping existing Python
scripts under sdd_scripts/. Zero LLM call, zero Claude Code dependency,
zero modification of the SDD_Pro engine.

Entry point:
    python -m sdd_mcp.server
"""
__version__ = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"
