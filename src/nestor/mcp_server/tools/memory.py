"""What Nestor knows of the task's owner, through the agent's own memory tools: what is theirs, never another person's
nor the household's (`recall`). What the executor learns stays with the task (`note`), never in anyone's memory."""

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from nestor.mcp_server.access import TaskAccess
from nestor.modules.cognition.tools import ToolFailed


def register(mcp: MCPServer, access: TaskAccess) -> None:
    memory = access.nestor.memory_tools

    @mcp.tool(
        description=(
            "What Nestor knows of the person the task is for: their memories matching `query`, and their past "
            "conversations (dated: since and until as 2026-11-01)."
        )
    )
    async def recall(task: str, query: str, ctx: Context, since: str = "", until: str = "") -> dict[str, object]:
        owner = access.owner(await access.task(ctx, task, "recall"))
        try:
            found = await memory.search(
                query,
                person=owner,
                about=owner,
                since=memory.bound(since, end=False),
                until=memory.bound(until, end=True),
            )
        except ToolFailed as failed:
            raise ToolError(str(failed)) from None
        return dict(found)
