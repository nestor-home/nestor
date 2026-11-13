"""Remote MCP servers (GitHub, Linear, Notion… or any other) connected from the admin by their address, authorised
the way each server says: OAuth with the MCP authorization flow, a token, or nothing.

Configuration (family `connector`, kind `mcp`), every key optional:

    timeout_s: 10        # connecting to a server, and each tool call
    retry_after_s: 30    # least delay between two attempts to reach a server that does not answer

Known servers are offered as presets (`catalogue`). A server is asked how it is authorised (`discovery`): it may
register a client for Nestor, need one typed (GitHub, Asana), take a token, or need nothing. Each connection keeps
one session (`server`), authorised with its OAuth token (`auth`) or its token.

Limits: streamable HTTP only. Neither MCP nor OAuth says who the person is at the service, so an account is named by
its owner and its server (`mathis@mcp.linear.app`). The `iss` of the authorization response (RFC 9207) is not
checked.
"""

from nestor.adapters.connectors.mcp.settings import McpConnectorSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["plugin"]


plugin = Plugin(Family.CONNECTOR, "mcp", McpConnectorSettings, build)
