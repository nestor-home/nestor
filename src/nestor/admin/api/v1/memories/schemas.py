"""A memory as the admin shows it, and what correcting one takes."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.access import edits_memory
from nestor.admin.api.v1.security import Caller
from nestor.admin.api.v1.shared import Input, People, PersonRef
from nestor.modules.memory import Memory


class MemoryOut(BaseModel):
    id: str
    text: str
    about: PersonRef | None  # None: the whole household
    told_by: PersonRef | None
    learnt_in: str | None  # the conversation it was learnt in
    session: str | None  # that conversation's session, to open its thread in the journal
    learnt_event: int | None  # the journal position of the entry that recorded it
    created_at: datetime
    updated_at: datetime
    editable: bool  # this account may correct or forget it

    @classmethod
    def of(cls, memory: Memory, caller: Caller, people: People, positions: dict[str, int]) -> "MemoryOut":
        return cls(
            id=memory.id,
            text=memory.text,
            about=people.ref(memory.about),
            told_by=people.ref(memory.told_by),
            learnt_in=str(memory.source) if memory.source else None,
            session=memory.source.session if memory.source else None,
            learnt_event=positions.get(memory.id),
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            editable=edits_memory(caller, memory),
        )


class CorrectionIn(Input):
    text: str
