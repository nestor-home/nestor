"""Memories: what the assistant retains, filed by place, searched, corrected, moved or forgotten, and those retired
lately with why.

`memory.manage.all` reaches every memory. `memory.manage.own` reads the memories about the account's
person and those every member shares, and corrects, moves or forgets only the former. A memory out of reach
is reported as missing.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from nestor.admin.api.v1.access import editable_memory, reads_memory, reads_place
from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.memories.recorded import recorded
from nestor.admin.api.v1.memories.retired import retired
from nestor.admin.api.v1.memories.schemas import CorrectionIn, MemoryOut, MoveIn, RetiredOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import ADMIN_CHANNEL, People
from nestor.admin.state import state
from nestor.core import ContractError, PersonId
from nestor.modules.accounts import Scope
from nestor.modules.memory import Place, filed, placed
from nestor.modules.usage import CallPurpose, attributed

router = APIRouter(tags=["memories"])
Keeper = Annotated[Caller, Depends(allowed(Scope.MEMORY_MANAGE_ALL, Scope.MEMORY_MANAGE_OWN))]


@router.get("/memories")
async def list_memories(
    request: Request,
    caller: Keeper,
    q: str = "",
    about: str = "",
    place: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[MemoryOut]:
    """The latest memories, or those matching `q`; `about` keeps one person's (and the shared ones), `place` those of
    a place or a shelf (`projects`)."""
    admin = state(request)
    if not caller.principal.can(Scope.MEMORY_MANAGE_ALL):
        if about and about != caller.person:
            raise ApiError(403, "forbidden")
        about = caller.person or ""
    person = PersonId(about) if about else None
    try:
        within = Place.parse(place) if place else None
    except ContractError:
        raise ApiError(400, "unknown_place") from None
    memories = admin.nestor.memories
    with attributed(purpose=CallPurpose.SEARCH, person=caller.person, channel=ADMIN_CHANNEL):
        found = (
            await memories.recall(q, about=person, place=within, limit=limit)
            if q.strip()
            else await memories.recent(about=person, place=within, limit=limit)
        )
    people, positions = People(admin.nestor.household), await recorded(admin)
    return [MemoryOut.of(m, caller, people, positions) for m in found if reads_memory(caller, m)]


@router.get("/memories/retired")
async def list_retired(
    request: Request, caller: Keeper, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[RetiredOut]:
    """The memories retired lately, newest first: tied to what ended, or merged or found outdated
    by the nightly upkeep."""
    admin = state(request)
    people = People(admin.nestor.household)
    found = await retired(admin, limit, lambda place: reads_place(caller, place))
    return [RetiredOut.of(event, position, people) for event, position in found]


@router.patch("/memories/{memory_id}")
async def correct_memory(request: Request, caller: Keeper, memory_id: str, body: CorrectionIn) -> MemoryOut:
    admin = state(request)
    memory = await editable_memory(admin, caller, memory_id)
    if not body.text.strip():
        raise ApiError(400, "empty_memory")
    corrected = await admin.nestor.memories.correct(memory.id, body.text, by=caller.person)
    return MemoryOut.of(corrected, caller, People(admin.nestor.household), await recorded(admin))


@router.post("/memories/{memory_id}/move")
async def move_memory(request: Request, caller: Keeper, memory_id: str, body: MoveIn) -> MemoryOut:
    admin = state(request)
    memory = await editable_memory(admin, caller, memory_id)
    try:
        place = filed(placed(body.place, admin.nestor.household))
    except ContractError:
        raise ApiError(400, "unknown_place") from None
    if not reads_place(caller, place):
        raise ApiError(403, "memory_shared")
    moved = await admin.nestor.memories.move(memory.id, place, by=caller.person)
    return MemoryOut.of(moved, caller, People(admin.nestor.household), await recorded(admin))


@router.delete("/memories/{memory_id}", status_code=204)
async def forget_memory(request: Request, caller: Keeper, memory_id: str) -> Response:
    admin = state(request)
    memory = await editable_memory(admin, caller, memory_id)
    await admin.nestor.memories.forget(memory.id, by=caller.person)
    return Response(status_code=204)
