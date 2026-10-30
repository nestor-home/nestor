"""The household: who the assistant serves, how each channel knows them, what is plugged in for them."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from nestor.admin.guard import LoggedIn
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.modules.connectors import Connection

router = APIRouter()


@router.get("/people")
async def people_page(request: Request, session: LoggedIn) -> HTMLResponse:
    admin = state(request)
    nestor = admin.nestor
    owned: dict[PersonId | None, list[Connection]] = {}
    for connection in nestor.connections.connections.values() if nestor.connections else ():
        owned.setdefault(connection.owner, []).append(connection)
    presence = nestor.presence.presence() if nestor.presence else None
    return admin.pages.render(
        request,
        "people.html",
        session,
        people=nestor.household.people,
        owned=owned,
        whereabouts={p.id: presence.of(p.id) for p in nestor.household.people} if presence else {},
    )
