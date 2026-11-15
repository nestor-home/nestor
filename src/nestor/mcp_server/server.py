"""The MCP server and the endpoint the admin serves it at: the tools of `tools`, behind `guard`."""

from contextlib import AbstractAsyncContextManager

from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings

from nestor import __version__
from nestor.mcp_server.access import FILE_BYTES, TaskAccess
from nestor.mcp_server.guard import Guarded
from nestor.mcp_server.tools import TOOLS
from nestor.modules.cognition.delegation import ExecutorKeys
from nestor.runtime import Nestor

BODY_BYTES = FILE_BYTES * 4 // 3 + 1_000_000  # a request carrying the largest file, in base64
INSTRUCTIONS = """Tools for the task Nestor, the household assistant, handed you. Every tool takes `task`, the value \
your brief gives. Start with task_brief."""


class ExecutorServer:
    """The MCP server and the ASGI endpoint the admin serves it at, while `running()`."""

    def __init__(self, nestor: Nestor, keys: ExecutorKeys) -> None:
        self.mcp = MCPServer("nestor", instructions=INSTRUCTIONS, version=__version__)
        access = TaskAccess(nestor)
        for register in TOOLS:
            register(self.mcp, access)
        # makes its session manager: reached at the admin's public address (not only localhost, which the SDK's
        # rebinding guard would require: every call is authenticated by its key), with bodies big enough for a file
        self.mcp.streamable_http_app(
            stateless_http=True,
            json_response=True,
            max_request_body_size=BODY_BYTES,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        self.endpoint = Guarded(StreamableHTTPASGIApp(self.mcp.session_manager), keys.caller)

    def running(self) -> AbstractAsyncContextManager[None]:
        """While it serves: the SDK's session manager, which runs once."""
        return self.mcp.session_manager.run()
