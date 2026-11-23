"""The requester's memory, through the agent's own memory tools: what is theirs, never another person's nor the
household's (`recall`), and a fact learned about them while working (`remember`)."""

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from nestor.mcp_server.access import TaskAccess
from nestor.modules.cognition.tools import ToolFailed
from nestor.modules.usage import CallPurpose, attributed


def register(mcp: MCPServer, access: TaskAccess) -> None:
    memory = access.nestor.memory_tools

    @mcp.tool(
        description=(
            "What Nestor knows of the requester: their memories matching `query`, and their past conversations "
            "(dated: since and until as 2026-11-01)."
        )
    )
    async def recall(task: str, query: str, ctx: Context, since: str = "", until: str = "") -> dict[str, object]:
        asked = await access.task(ctx, task, "recall")
        requester = access.requester(asked)
        try:
            with attributed(purpose=CallPurpose.TASK, person=requester, origin=f"task:{asked.id}"):
                found = await memory.search(
                    query,
                    person=requester,
                    about=requester,
                    since=memory.bound(since, end=False),
                    until=memory.bound(until, end=True),
                )
        except ToolFailed as failed:
            raise ToolError(str(failed)) from None
        return dict(found)

    @mcp.tool(description="Keep a lasting fact about the requester, learned while working on the task.")
    async def remember(task: str, fact: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "remember")
        kept = await memory.keep(fact, about=access.requester(found), source=found.origin, exchange=found.exchange)
        return dict(kept)
