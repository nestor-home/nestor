"""Remote MCP servers connected from the admin: one session per connection, its tools offered as the account's.

A server is asked how it is authorised when its address is typed (`discovery`): OAuth at its own authorization
server, a token typed with the address, or nothing. Its tools keep the server's names after the account's own
(`linear_list_issues`), and its annotations tell reading from writing; whether a write asks the person first is the
connection's setting, like every connected account's.
"""

from collections.abc import Sequence

import httpx2

from nestor import __version__
from nestor.adapters.connectors.mcp import catalogue
from nestor.adapters.connectors.mcp.discovery import discover
from nestor.adapters.connectors.mcp.server import ConnectedServer
from nestor.core import Component, Health, ProviderError
from nestor.core.i18n import Message
from nestor.modules.cognition.tools import Tool
from nestor.modules.connectors import (
    Access,
    AuthKind,
    Connection,
    Connector,
    ConnectorInfo,
    Discovery,
    SecretField,
    Secrets,
    Service,
)


def _field(name: str, *, secret: bool, optional: bool = True) -> SecretField:
    return SecretField(
        name=name, label=Message.of(f"connector-mcp-field-{name}"), secret=secret, default="" if optional else None
    )


INFO = ConnectorInfo(
    kind="mcp",
    brand="mcp",
    title=Message.of("connector-mcp-title"),
    description=Message.of("connector-mcp-description"),
    auth=AuthKind.DISCOVERED,
    fields=(
        _field("url", secret=False, optional=False),
        _field("token", secret=True),
        _field("client_id", secret=False),
        _field("client_secret", secret=True),
    ),
    setup=Message.of("connector-mcp-setup"),
    presets=catalogue.PRESETS,
)


class McpConnector(Connector, Component):
    name = "mcp"
    brand = "mcp"
    info = INFO

    def __init__(self, *, timeout_s: float = 10.0, retry_after_s: float = 30.0) -> None:
        self.timeout_s, self.retry_after_s = timeout_s, retry_after_s
        self._servers: dict[str, ConnectedServer] = {}

    async def close(self) -> None:
        servers, self._servers = list(self._servers.values()), {}
        for server in servers:
            await server.close()

    async def discover(self, settings: Secrets, redirect_uri: str) -> Discovery:
        """A token typed with the address is what the server takes; otherwise the server is asked."""
        url = settings["url"]
        if not catalogue.host(url) or not url.startswith(("https://", "http://")):
            not_one = Message.of("connector-mcp-not-an-address", url=url)
            raise ProviderError(self.name, f"{url!r} is not the address of a server", transient=False, reason=not_one)
        if settings.get("token"):
            return Discovery()
        typed = {k: settings[k] for k in ("client_id", "client_secret") if settings.get(k)}
        headers = {"User-Agent": f"Nestor/{__version__}"}
        async with httpx2.AsyncClient(timeout=self.timeout_s, headers=headers) as http:
            return await discover(url, redirect_uri, typed, http)

    async def identify(self, connection: Connection, access: Access) -> str:
        """Whose account it is and on which server, once a session opens with what was given. Neither MCP nor OAuth
        says who the person is at the service, so two accounts on one server are told apart by their owner."""
        # a broken account being reconnected has no session left: its name goes to the new one
        taken = {s.name for s in self._servers.values() if s.health() is Health.STARTED}
        who = connection.owner or "household"
        label = catalogue.account(who, (await access.secrets())["url"], taken)
        server = self._server(connection, access, label)
        try:
            await server.connect()
        except ProviderError:
            await self.disconnected(connection)
            raise
        return label

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        return self._server(connection, access, connection.account).tools()

    def services(self, connection: Connection) -> Sequence[Service]:
        server = self._servers.get(connection.id)
        names = frozenset(t.name for t in server.tools()) if server else frozenset()
        return [Service(name=catalogue.service_name(connection.account), tools=names)] if names else []

    def brand_of(self, connection: Connection) -> str | None:
        preset = catalogue.known(connection.account)
        return preset.brand if preset else self.info.brand

    async def disconnected(self, connection: Connection) -> None:
        server = self._servers.pop(connection.id, None)
        if server is not None:
            await server.close()

    def _server(self, connection: Connection, access: Access, label: str) -> ConnectedServer:
        if (server := self._servers.get(connection.id)) is None:
            server = ConnectedServer(
                connection,
                access,
                label=label,
                prefix=catalogue.service_name(label).replace("-", "_") + "_",
                timeout_s=self.timeout_s,
                retry_after_s=self.retry_after_s,
            )
            self._servers[connection.id] = server
        return server
