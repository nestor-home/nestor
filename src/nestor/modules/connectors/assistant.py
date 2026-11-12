"""The tools of every connected account, as the central agent sees them, and the accounts a message can name.

Writing tools (send a mail, create a ticket) are sensitive when the connection says so: the person confirms them
first. Tools of someone's own account (their mailbox) serve that person only. The toolbox applies both.

A message names an account with `@`: by one of the services its connector declares (`@gmail`), or by its kind when
it declares none; with two such accounts, by the service and the start of the address (`@gmail-mathis`). Only the
accounts the person may use are offered: theirs and the household's.
"""

from collections.abc import Iterable, Sequence
from dataclasses import replace

from nestor.modules.cognition.tools import Risk, Tool, ToolProvider
from nestor.modules.connectors.service import Connections
from nestor.modules.connectors.types import Connection, Status
from nestor.modules.conversation import Mentioned, MentionKind, MentionSource
from nestor.modules.household import Person


class ConnectorTools(ToolProvider, MentionSource):
    name = "connector-tools"

    def __init__(self, connections: Connections) -> None:
        self.connections = connections

    def tools(self) -> Sequence[Tool]:
        return [tool for connection in self._connected() for tool in self._tools_of(connection)]

    def mentionable(self, person: Person | None) -> Iterable[Mentioned]:
        usable = [c for c in self._connected() if c.owner is None or (person is not None and c.owner == person.id)]
        named = [(c, name, brand) for c in usable for name, brand, _ in self._services(c)]
        for connection, name, brand in named:
            local = connection.account.partition("@")[0]
            alone = sum(n == name for _, n, _ in named) == 1
            yield Mentioned(
                kind=MentionKind.CONNECTION,
                id=f"{connection.id}:{name}",
                handle=name if alone else f"{name}-{local}",
                label=connection.account,
                aliases=tuple(alias for alias in (connection.kind, brand, local, connection.account) if alias),
                brand=brand,
            )

    def instruction(self, mentioned: Mentioned) -> str:
        connection_id, _, name = mentioned.id.partition(":")
        connection = self.connections.connections.get(connection_id)
        if connection is None:
            return f"the account {mentioned.label}, no longer connected: say so"
        tools = next((tools for n, _, tools in self._services(connection) if n == name), frozenset[str]())
        whose = "the household's" if connection.owner is None else "their own"
        names = ", ".join(t.name for t in self._tools_of(connection) if t.name in tools)
        return f"{whose} {name} on the account {connection.account}: use its tools for that part ({names})"

    def _services(self, connection: Connection) -> list[tuple[str, str | None, frozenset[str]]]:
        """What a message names of the account: each of its services, or the account by its kind."""
        info = self.connections.connectors[connection.kind].info
        if info.services:
            return [(s.name, s.brand or info.brand, s.tools) for s in info.services]
        return [(connection.kind, info.brand, frozenset(t.name for t in self._tools_of(connection)))]

    def _connected(self) -> Iterable[Connection]:
        for connection in self.connections.connections.values():
            if connection.kind in self.connections.connectors and connection.status is Status.CONNECTED:
                yield connection

    def _tools_of(self, connection: Connection) -> list[Tool]:
        connector = self.connections.connectors[connection.kind]
        return [
            _as_used(tool, connection)
            for tool in connector.tools(connection, self.connections.access(connection))
            if tool.name not in connection.disabled_tools
        ]


def _as_used(tool: Tool, connection: Connection) -> Tool:
    confirmed = tool.risk is Risk.WRITE and connection.confirm_writes
    return replace(tool, risk=Risk.SENSITIVE if confirmed else tool.risk, owner=connection.owner)
