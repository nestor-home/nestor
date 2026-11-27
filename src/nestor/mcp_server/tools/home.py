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
        presence, rooms = source.presence(), nestor.home.overview().rooms if nestor.home else ()
        people = {nestor.household.person(person).name: said for person, said in presence.told(rooms).items()}
        occupied = sorted(next((r.name for r in rooms if r.id == room), room) for room in presence.occupied_rooms)
        return {"people": people, "occupied_rooms": occupied}
