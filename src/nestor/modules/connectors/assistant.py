"""The tools of every connected account, as the central agent sees them.

Writing tools (send a mail, create a ticket) are sensitive when the connection says so: the person confirms them
first. Tools of someone's own account (their mailbox) serve that person only. The toolbox applies both.
"""

from collections.abc import Sequence
from dataclasses import replace

from nestor.modules.cognition.tools import Risk, Tool, ToolProvider
from nestor.modules.connectors.service import Connections
from nestor.modules.connectors.types import Connection, Status


class ConnectorTools(ToolProvider):
    name = "connector-tools"

    def __init__(self, connections: Connections) -> None:
        self.connections = connections

    def tools(self) -> Sequence[Tool]:
        found: list[Tool] = []
        for connection in self.connections.connections.values():
            connector = self.connections.connectors.get(connection.kind)
            if connector is None or connection.status is not Status.CONNECTED:
                continue
            for tool in connector.tools(connection, self.connections.access(connection)):
                if tool.name not in connection.disabled_tools:
                    found.append(_as_used(tool, connection))
        return found


def _as_used(tool: Tool, connection: Connection) -> Tool:
    confirmed = tool.risk is Risk.WRITE and connection.confirm_writes
    return replace(tool, risk=Risk.SENSITIVE if confirmed else tool.risk, owner=connection.owner)
