"""MCP servers as tool providers: Home Assistant's `/api/mcp`, and any remote MCP server a household connects."""

from nestor.adapters.tools.mcp.settings import McpSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "mcp", McpSettings, build)

__all__ = ["plugin"]
