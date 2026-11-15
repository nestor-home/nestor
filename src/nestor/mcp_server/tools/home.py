"""The home as its system sees it (`home_state`): offered only when Nestor has a home."""

from mcp.server.mcpserver import Context, MCPServer

from nestor.mcp_server.access import TaskAccess


def register(mcp: MCPServer, access: TaskAccess) -> None:
    nestor = access.nestor
    if (source := nestor.presence) is None:
        return

    @mcp.tool(description="Who is home now, and the occupied rooms, as the home system sees it.")
    async def home_state(task: str, ctx: Context) -> dict[str, object]:
        await access.task(ctx, task, "home_state")
        presence = source.presence()
        people = {
            nestor.household.person(person).name: (
                "unknown" if where.home is None else (where.room or "home") if where.home else "away"
            )
            for person, where in presence.people.items()
        }
        return {"people": people, "occupied_rooms": sorted(presence.occupied_rooms)}
