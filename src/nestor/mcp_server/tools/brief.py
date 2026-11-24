"""The task itself: what it is, where it came from and what its turns did (`task_brief`), what the executor is doing
now (`report_progress`), and what it keeps for later (`note`)."""

from zoneinfo import ZoneInfo

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from nestor.core import ContractError, shorten
from nestor.mcp_server.access import TaskAccess
from nestor.modules.cognition.delegation import READ_TURNS, TURN_CHARS
from nestor.modules.memory.episodes.transcript import transcript

BRIEF_LINES = 40  # of the conversation the instruction came from


def register(mcp: MCPServer, access: TaskAccess) -> None:
    nestor = access.nestor

    @mcp.tool(
        description=(
            "What the task is: its title, the instruction of this turn, who it is for, when and where, the "
            "conversation it came from, the turns before this one, the notes kept for it, and every file sent with "
            "it (read_file gives a link to each)."
        )
    )
    async def task_brief(task: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "task_brief")
        persona = nestor.config.persona
        turn = found.turn
        asked_at = turn.started_at.astimezone(ZoneInfo(persona.timezone))
        owner = nestor.household.person(found.owner) if found.owner else None
        conversation = (
            await transcript(
                nestor.journal,
                nestor.household,
                address=turn.origin,
                conversation=turn.exchange.conversation_id,
                since=await access.since(found),
                assistant=persona.name,
                timezone=persona.timezone,
            )
            if turn.exchange is not None
            else []
        )
        earlier = [
            {
                "asked": shorten(t.instruction, TURN_CHARS),
                "status": t.status.value,
                "came_back": shorten(t.came_back, TURN_CHARS),
            }
            for t in found.turns[:-1][-READ_TURNS:]
        ]
        return {
            "title": found.title,
            "instruction": turn.instruction,
            "for": owner.name if owner else None,
            "asked_at": f"{asked_at:%A %d %B %Y %H:%M} ({persona.timezone})",
            "channel": turn.origin.channel,
            "conversation": conversation[-BRIEF_LINES:],
            "earlier_turns": earlier,
            "notes": found.notes,
            "files": [
                {"file": g.blob.digest, "name": g.name, "media_type": g.blob.media_type, "bytes": g.blob.size}
                for g in found.given
            ],
        }

    @mcp.tool(description="Say what you are doing now, in a few words: the person and Nestor see it.")
    async def report_progress(task: str, step: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "report_progress")
        nestor.tasks.report(found, step)
        return {"status": "noted"}

    @mcp.tool(
        description=(
            "Keep a note for this task: what its next turns will need (a choice made, where things are, what is "
            "left to do). Notes stay with the task, never in anyone's memory; task_brief gives them back."
        )
    )
    async def note(task: str, text: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "note")
        try:
            kept = await nestor.tasks.note(found, text)
        except ContractError as error:
            raise ToolError(str(error)) from None
        return {"status": "noted", "note": kept}
