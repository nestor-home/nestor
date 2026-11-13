"""The MCP session of one connection: a tool provider reading its address and credentials from the connection."""

from typing import Any

import httpx2

from nestor.adapters.connectors.mcp.auth import ConnectionAuth
from nestor.adapters.tools.mcp import BearerToken, McpToolProvider
from nestor.core import ProviderError
from nestor.modules.connectors import Access, AuthKind, Connection


class ConnectedServer(McpToolProvider):
    """The server of one connection: its address and credentials are read from the connection each time a session
    opens, so a renewed token or a reconnection is used without rebuilding it."""

    def __init__(self, connection: Connection, access: Access, *, label: str, prefix: str, **options: Any) -> None:
        super().__init__("", name=label, prefix=prefix, **options)
        self._connection, self._access = connection, access

    async def endpoint(self) -> tuple[str, httpx2.Auth | None]:
        settings = await self._access.secrets()
        if not (url := settings.get("url")):  # its secrets are already forgotten: it is being unplugged
            raise ProviderError(self.name, "the connection is gone", transient=False)
        if self._connection.auth is AuthKind.OAUTH2:
            return url, ConnectionAuth(self._access)
        token = settings.get("token")
        return url, BearerToken(token) if token else None
