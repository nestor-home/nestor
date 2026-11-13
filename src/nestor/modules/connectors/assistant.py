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
from nestor.modules.connectors.types import Connection, Service, Status
from nestor.modules.conversation import Mentioned, MentionKind, MentionSource
from nestor.modules.household import Person


class ConnectorTools(ToolProvider, MentionSource):
    name = "connector-tools"

    def __init__(self, connections: Connections) -> None:
        self.connections = connections

    async def start(self) -> None:
        """Asks every account for its tools once, so that what a connector opens for them (a remote MCP server's
        session) is ready before the first turn."""
        self.tools()

    def tools(self) -> Sequence[Tool]:
        return [tool for tools in self._offered().values() for _, tool in tools]

    def mentionable(self, person: Person | None) -> Iterable[Mentioned]:
        usable = [c for c in self._connected() if c.owner is None or (person is not None and c.owner == person.id)]
        named = [(c, service) for c in usable for service in self.services(c)]
        for connection, service in named:
            local = connection.account.partition("@")[0]
            alone = sum(s.name == service.name for _, s in named) == 1
            yield Mentioned(
                kind=MentionKind.CONNECTION,
                id=f"{connection.id}:{service.name}",
                handle=service.name if alone else f"{service.name}-{local}",
                label=connection.account,
                aliases=tuple(alias for alias in (connection.kind, service.brand, local, connection.account) if alias),
                brand=service.brand,
            )

    def instruction(self, mentioned: Mentioned) -> str:
        connection_id, _, name = mentioned.id.partition(":")
        connection = self.connections.connections.get(connection_id)
        service = next((s for s in self.services(connection) if s.name == name), None) if connection else None
        if connection is None or service is None:
            return f"the account {mentioned.label}, no longer connected: say so"
        whose = "the household's" if connection.owner is None else "their own"
        offered = self._offered().get(connection.id, [])
        names = ", ".join(tool.name for declared, tool in offered if declared in service.tools)
        return f"{whose} {name} on the account {connection.account}: use its tools for that part ({names})"

    def services(self, connection: Connection) -> list[Service]:
        """What a message names of the account: each service its connector declares, or the account by its kind."""
        connector = self.connections.connectors[connection.kind]
        brand = connector.brand_of(connection)
        if declared := connector.services(connection):
            return [replace(s, brand=s.brand or brand) for s in declared]
        tools = frozenset(t.name for t in self._tools_of(connection))
        return [Service(name=connection.kind, tools=tools, brand=brand)] if tools else []

    def _connected(self) -> Iterable[Connection]:
        for connection in self.connections.connections.values():
            if connection.kind in self.connections.connectors and connection.status is Status.CONNECTED:
                yield connection

    def _offered(self) -> dict[str, list[tuple[str, Tool]]]:
        """Each account's tools as the model sees them, with the name its connector gives each. A second account of a
        service (two people's mailboxes, or two of one person's) gets its tools numbered and its address in their
        description: one name stands for one tool."""
        taken: set[str] = set()
        offered: dict[str, list[tuple[str, Tool]]] = {}
        for connection in self._connected():
            tools = self._tools_of(connection)
            n = 1
            while any(_numbered(t.name, n) in taken for t in tools):
                n += 1
            offered[connection.id] = [(t.name, t if n == 1 else _apart(t, n, connection)) for t in tools]
            taken.update(_numbered(t.name, n) for t in tools)
        return offered

    def _tools_of(self, connection: Connection) -> list[Tool]:
        connector = self.connections.connectors[connection.kind]
        return [
            _as_used(tool, connection)
            for tool in connector.tools(connection, self.connections.access(connection))
            if tool.name not in connection.disabled_tools
        ]


def _numbered(name: str, n: int) -> str:
    return name if n == 1 else f"{name}_{n}"


def _apart(tool: Tool, n: int, connection: Connection) -> Tool:
    spec = replace(
        tool.spec, name=_numbered(tool.name, n), description=f"[{connection.account}] {tool.spec.description}"
    )
    return replace(tool, spec=spec)


def _as_used(tool: Tool, connection: Connection) -> Tool:
    confirmed = tool.risk is Risk.WRITE and connection.confirm_writes
    return replace(
        tool, risk=Risk.SENSITIVE if confirmed else tool.risk, owner=connection.owner, connection=connection.id
    )
