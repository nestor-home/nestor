"""The tools of every connected account, as the central agent sees them.

Writing tools (send a mail, create a ticket) ask the person first when the connection says so: the
model must call them again with `confirmed: true` after the person agreed in the conversation.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.cognition.tools.types import ToolOutput
from nestor.modules.connectors.service import Connections
from nestor.modules.connectors.types import Connection, Status

CONFIRM = {"type": "boolean", "description": "true only once the person explicitly agreed to this exact action"}


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
                if tool.name in connection.disabled_tools:
                    continue
                found.append(self._guarded(tool, connection) if self._needs_consent(tool, connection) else tool)
        return found

    @staticmethod
    def _needs_consent(tool: Tool, connection: Connection) -> bool:
        return tool.risk is Risk.SENSITIVE or (tool.risk is Risk.WRITE and connection.confirm_writes)

    @staticmethod
    def _guarded(tool: Tool, connection: Connection) -> Tool:
        parameters = dict(tool.spec.parameters)
        existing = parameters.get("properties")
        properties = dict(existing) if isinstance(existing, Mapping) else {}
        properties["confirmed"] = CONFIRM
        parameters["properties"] = properties
        run = tool.run

        async def ask_first(arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
            if arguments.get("confirmed") is not True:
                raise ToolFailed(
                    f"{tool.name} acts on {connection.account}: describe exactly what you will do, ask the person to "
                    "confirm, then call it again with confirmed=true"
                )
            return await run({k: v for k, v in arguments.items() if k != "confirmed"}, context)

        description = f"{tool.spec.description} Ask the person before calling it."
        return replace(tool, spec=ToolSpec(tool.spec.name, description, parameters), run=ask_first)
