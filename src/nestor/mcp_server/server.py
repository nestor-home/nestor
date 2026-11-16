"""The MCP server and the endpoints the admin serves: the tools of `tools`, behind `guard`, and the links to the
tasks' files (`files`)."""

from contextlib import AbstractAsyncContextManager

from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings

from nestor import __version__
from nestor.mcp_server.access import TaskAccess
from nestor.mcp_server.files import FileLinks
from nestor.mcp_server.guard import Guarded
from nestor.mcp_server.links import Links
from nestor.mcp_server.tools import TOOLS
from nestor.modules.cognition.delegation import ExecutorKeys
from nestor.runtime import Nestor

FILES = "/files"  # under the server's path: the links to the tasks' files
INSTRUCTIONS = """Tools for the task Nestor, the household assistant, handed you. Every tool takes `task`, the value \
your brief gives. Start with task_brief."""


class ExecutorServer:
    """The MCP server, the ASGI endpoint the admin serves it at (`endpoint`) while `running()`, and the endpoint of
    the links to the tasks' files (`files`, at the server's path + `FILES` + `/{token}`)."""

    def __init__(self, nestor: Nestor, keys: ExecutorKeys) -> None:
        self.mcp = MCPServer("nestor", instructions=INSTRUCTIONS, version=__version__)
        links = Links(keys.url + FILES)
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
        self.endpoint = Guarded(StreamableHTTPASGIApp(self.mcp.session_manager), keys.caller)
        self.files = FileLinks(nestor, links).endpoint

    def running(self) -> AbstractAsyncContextManager[None]:
        """While it serves: the SDK's session manager, which runs once."""
        return self.mcp.session_manager.run()
