"""Memories: what the assistant retains, searched, corrected or forgotten.

`memory.manage.all` reaches every memory. `memory.manage.own` reads the memories about the account's
person and the household-wide ones, and corrects or forgets only the former. A memory out of reach
is reported as missing.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from nestor.admin.api.v1.access import editable_memory, reads_memory
from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.memories.recorded import recorded
from nestor.admin.api.v1.memories.schemas import CorrectionIn, MemoryOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.modules.accounts import Scope

router = APIRouter(tags=["memories"])
Keeper = Annotated[Caller, Depends(allowed(Scope.MEMORY_MANAGE_ALL, Scope.MEMORY_MANAGE_OWN))]


@router.get("/memories")
async def list_memories(
    request: Request,
    caller: Keeper,
    q: str = "",
    about: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[MemoryOut]:
    """The latest memories, or those matching `q`; `about` keeps one person's (and the household's)."""
    admin = state(request)
    if not caller.principal.can(Scope.MEMORY_MANAGE_ALL):
        if about and about != caller.person:
            raise ApiError(403, "forbidden")
        about = caller.person or ""
    person = PersonId(about) if about else None
    memories = admin.nestor.memories
    found = (
        await memories.recall(q, about=person, limit=limit)
        if q.strip()
        else await memories.recent(about=person, limit=limit)
    )
    people, positions = People(admin.nestor.household), await recorded(admin)
    return [MemoryOut.of(m, caller, people, positions) for m in found if reads_memory(caller, m)]


@router.patch("/memories/{memory_id}")
async def correct_memory(request: Request, caller: Keeper, memory_id: str, body: CorrectionIn) -> MemoryOut:
    admin = state(request)
    memory = await editable_memory(admin, caller, memory_id)
    if not body.text.strip():
        raise ApiError(400, "empty_memory")
    corrected = await admin.nestor.memories.correct(memory.id, body.text, by=caller.person)
    return MemoryOut.of(corrected, caller, People(admin.nestor.household), await recorded(admin))


@router.delete("/memories/{memory_id}", status_code=204)
async def forget_memory(request: Request, caller: Keeper, memory_id: str) -> Response:
    admin = state(request)
    memory = await editable_memory(admin, caller, memory_id)
    await admin.nestor.memories.forget(memory.id, by=caller.person)
    return Response(status_code=204)
