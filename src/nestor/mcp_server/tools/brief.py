"""The task itself: what it is and where it came from (`task_brief`), and what the executor is doing now
(`report_progress`)."""

from zoneinfo import ZoneInfo

from mcp.server.mcpserver import Context, MCPServer

from nestor.mcp_server.access import TaskAccess
from nestor.modules.memory.episodes.transcript import transcript

BRIEF_LINES = 40  # of the conversation the task came from
STEP_CHARS = 500


def register(mcp: MCPServer, access: TaskAccess) -> None:
    nestor = access.nestor

    @mcp.tool(
        description=(
            "What the task is: its objective, who asked, when and where, the conversation it came from, and the "
            "files they sent (read_file gives a link to each)."
        )
    )
    async def task_brief(task: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "task_brief")
        persona = nestor.config.persona
        asked_at = found.started_at.astimezone(ZoneInfo(persona.timezone))
        requester = nestor.household.person(found.requested_by) if found.requested_by else None
        conversation = (
            await transcript(
                nestor.journal,
                nestor.household,
                address=found.origin,
                conversation=found.exchange.conversation_id,
                since=await access.since(found),
                assistant=persona.name,
                timezone=persona.timezone,
            )
            if found.exchange is not None
            else []
        )
        return {
            "objective": found.objective,
            "requested_by": requester.name if requester else None,
            "asked_at": f"{asked_at:%A %d %B %Y %H:%M} ({persona.timezone})",
            "channel": found.origin.channel,
            "conversation": conversation[-BRIEF_LINES:],
            "files": [
                {"file": g.file.digest, "name": g.name, "media_type": g.file.media_type, "bytes": g.file.size}
                for g in found.given
            ],
        }

    @mcp.tool(description="Say what you are doing now, in a few words: the requester and Nestor see it.")
    async def report_progress(task: str, step: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "report_progress")
        nestor.tasks.report(found, step.strip()[:STEP_CHARS])
        return {"status": "noted"}
