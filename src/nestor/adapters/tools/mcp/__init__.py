"""MCP servers as tool providers: any remote MCP server a household connects, and the server of a home's actions."""

from nestor.adapters.tools.mcp.settings import McpSettings, build
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "mcp",
    McpSettings,
    build,
    card=Card(
        summary="Gives the agent the tools of an MCP server the configuration names, with a fixed token, for the "
        "whole household.",
        docs="tools#a-server-in-the-configuration",
        needs=(Need.SERVER,),
    ),
)

__all__ = ["plugin"]
