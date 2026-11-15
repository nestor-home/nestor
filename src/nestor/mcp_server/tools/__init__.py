"""The tools of Nestor's MCP server, a module per subject. Each has a `register(mcp, access)` that declares its tools
on the server: every tool takes `task`, the task's capability, and starts with `access.task(ctx, task, "<its name>")`,
which refuses any call that is not for a running task of the calling executor. Its description is what the executor's
model reads: in English, saying what it returns and when to call it."""

from collections.abc import Callable

from mcp.server.mcpserver import MCPServer

from nestor.mcp_server.access import TaskAccess
from nestor.mcp_server.tools import brief, files, home, memory, questions

TOOLS: tuple[Callable[[MCPServer, TaskAccess], None], ...] = (
    brief.register,
    files.register,
    memory.register,
    questions.register,
    home.register,
)

__all__ = ["TOOLS"]
