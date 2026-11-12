"""The tools of every connected account, as the central agent sees them, and the accounts a message can name.

Writing tools (send a mail, create a ticket) are sensitive when the connection says so: the person confirms them
first. Tools of someone's own account (their mailbox) serve that person only. The toolbox applies both.

A message names an account with `@`: by its service (`@google`, when the person has one such account), or by the
account itself (`@mathis`, the start of the address). Only the accounts the person may use are offered: theirs and the
household's.
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
        for connection in usable:
            info = self.connections.connectors[connection.kind].info
            local = connection.account.partition("@")[0]
            alone = sum(c.kind == connection.kind for c in usable) == 1
            yield Mentioned(
                kind=MentionKind.CONNECTION,
                id=connection.id,
                handle=connection.kind if alone else f"{connection.kind}-{local}",
                label=connection.account,
                aliases=tuple(name for name in (info.brand, local, connection.account) if name),
                brand=info.brand or connection.kind,
            )

    def instruction(self, mentioned: Mentioned) -> str:
        connection = self.connections.connections.get(mentioned.id)
        if connection is None:
            return f"the account {mentioned.label}, no longer connected: say so"
        whose = "the household's" if connection.owner is None else "their own"
        names = ", ".join(t.name for t in self._tools_of(connection))
        return f"{whose} {connection.kind} account {connection.account}: use its tools for that part ({names})"

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
