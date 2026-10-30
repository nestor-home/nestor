"""Memories: what the assistant retains, searched, corrected or forgotten.

`memory.manage.all` reaches every memory. `memory.manage.own` reads the memories about the account's
person and the household-wide ones, and corrects or forgets only the former. A memory out of reach
is reported as missing.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel

from nestor.admin.api.v1.errors import FORBIDDEN, ApiError, not_found
from nestor.admin.api.v1.models import Input, People, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.modules.accounts import Scope
from nestor.modules.memory import Memory

router = APIRouter(tags=["memories"])
Keeper = Annotated[Caller, Depends(allowed(Scope.MEMORY_MANAGE_ALL, Scope.MEMORY_MANAGE_OWN))]


class MemoryOut(BaseModel):
    id: str
    text: str
    about: PersonRef | None  # None: the whole household
    told_by: PersonRef | None
    learnt_in: str | None  # the conversation it was learnt in
    created_at: datetime
    updated_at: datetime
    editable: bool  # this account may correct or forget it


class CorrectionIn(Input):
    text: str


def _reads(caller: Caller, memory: Memory) -> bool:
    return caller.principal.reaches(
        memory.about, every=Scope.MEMORY_MANAGE_ALL, own=Scope.MEMORY_MANAGE_OWN, shared=True
    )


def _edits(caller: Caller, memory: Memory) -> bool:
    return caller.principal.reaches(memory.about, every=Scope.MEMORY_MANAGE_ALL, own=Scope.MEMORY_MANAGE_OWN)


def _memory(caller: Caller, memory: Memory, people: People) -> MemoryOut:
    return MemoryOut(
        id=memory.id,
        text=memory.text,
        about=people.ref(memory.about),
        told_by=people.ref(memory.told_by),
        learnt_in=str(memory.source) if memory.source else None,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        editable=_edits(caller, memory),
    )


@router.get("/memories")
async def list_memories(
    request: Request,
    caller: Keeper,
    q: str = "",
    about: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[MemoryOut]:
    """The latest memories, or those matching `q`; `about` keeps one person's (and the household's)."""
    nestor = state(request).nestor
    if not caller.principal.can(Scope.MEMORY_MANAGE_ALL):
        if about and about != caller.person:
            raise ApiError(403, "forbidden", FORBIDDEN)
        about = caller.person or ""
    person = PersonId(about) if about else None
    memories = nestor.memories
    found = (
        await memories.recall(q, about=person, limit=limit)
        if q.strip()
        else await memories.recent(about=person, limit=limit)
    )
    people = People(nestor.household)
    return [_memory(caller, m, people) for m in found if _reads(caller, m)]


@router.patch("/memories/{memory_id}")
async def correct_memory(request: Request, caller: Keeper, memory_id: str, body: CorrectionIn) -> MemoryOut:
    nestor = state(request).nestor
    memory = await _editable(request, caller, memory_id)
    if not body.text.strip():
        raise ApiError(400, "empty_memory", "Pour effacer un souvenir, oubliez-le.")
    corrected = await nestor.memories.correct(memory.id, body.text, by=caller.person)
    return _memory(caller, corrected, People(nestor.household))


@router.delete("/memories/{memory_id}", status_code=204)
async def forget_memory(request: Request, caller: Keeper, memory_id: str) -> Response:
    memory = await _editable(request, caller, memory_id)
    await state(request).nestor.memories.forget(memory.id, by=caller.person)
    return Response(status_code=204)


async def _editable(request: Request, caller: Caller, memory_id: str) -> Memory:
    memory = await state(request).nestor.memories.store.get(memory_id)
    if memory is None or not _reads(caller, memory):
        raise not_found("Ce souvenir n'existe pas ou plus.")
    if not _edits(caller, memory):
        raise ApiError(403, "forbidden", "Seule l'administration du foyer modifie les souvenirs communs.")
    return memory
