"""The MCP server and the routes the admin serves: the tools of `tools`, behind `guard`, and the links to the tasks'
files (`files`) beside them."""

from contextlib import AbstractAsyncContextManager

from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from nestor import __version__
from nestor.mcp_server.access import TaskAccess
from nestor.mcp_server.files import FileLinks
from nestor.mcp_server.guard import Guarded
from nestor.mcp_server.links import Links
from nestor.mcp_server.tools import TOOLS
from nestor.modules.cognition.delegation import ExecutorKeys
from nestor.runtime import Nestor

INSTRUCTIONS = """Tools for the task Nestor, the household assistant, handed you. Every tool takes `task`, the value \
your brief gives. Start with task_brief."""


class ExecutorServer:
    """The MCP server and the links to the tasks' files, served at the routes of `routes` while `running()`."""

    def __init__(self, nestor: Nestor, keys: ExecutorKeys) -> None:
        self.mcp = MCPServer("nestor", instructions=INSTRUCTIONS, version=__version__)
        links = Links(keys.url + "/files")
        access = TaskAccess(nestor, links)
        for register in TOOLS:
            register(self.mcp, access)
        # makes its session manager: reached at the admin's public address (not only localhost, which the SDK's
        # rebinding guard would require: every call is authenticated by its key)
        self.mcp.streamable_http_app(
            stateless_http=True,
            json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        self._endpoint = Guarded(StreamableHTTPASGIApp(self.mcp.session_manager), keys.caller)
        self._files = FileLinks(nestor, links).endpoint

    def routes(self, path: str) -> list[Route]:
        """The server at `path` (where `keys.url` says executors reach it), and the links to the tasks' files below."""
        return [
            Route(path, endpoint=self._endpoint, methods=["GET", "POST", "DELETE"]),
            Route(f"{path}/files/{{token}}", endpoint=self._files, methods=["GET", "PUT"]),
        ]

    def running(self) -> AbstractAsyncContextManager[None]:
        """While it serves: the SDK's session manager, which runs once."""
        return self.mcp.session_manager.run()
