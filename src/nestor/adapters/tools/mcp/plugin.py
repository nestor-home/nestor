"""The `mcp` tool provider plugin, declared under the `nestor.adapters` entry points."""

from nestor.adapters.tools.mcp.settings import McpSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "mcp", McpSettings, build)
