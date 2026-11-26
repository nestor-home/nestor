"""A memory as the admin shows it, what the nightly upkeep or an ending changed, and what correcting or moving one
takes."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.access import edits_memory
from nestor.admin.api.v1.security import Caller
from nestor.admin.api.v1.shared import Input, People, PersonRef
from nestor.modules.memory import Memory, MemoryRetired, Place, Retirement, Shelf


class PlaceOut(BaseModel):
    path: str  # people/lea, home, projects/roof-works
    shelf: Shelf
    name: str | None  # a project's or topic's name, a person's id
    person: PersonRef | None  # whom it is about, on a person's place

    @classmethod
    def of(cls, place: Place, people: People) -> "PlaceOut":
        return cls(path=str(place), shelf=place.shelf, name=place.name, person=people.ref(place.person))


class MemoryOut(BaseModel):
    id: str
    text: str
    place: PlaceOut
    about: PersonRef | None  # None: shared by the household
    told_by: PersonRef | None
    tied_to: str | None  # task:<id> or alert:<id>: retired when that ends
    learnt_in: str | None  # the conversation it was learnt in
    session: str | None  # that conversation's session, to open its thread in the journal
    learnt_event: int | None  # the journal position of the entry that recorded it
    created_at: datetime
    updated_at: datetime
    editable: bool  # this account may correct, move or forget it

    @classmethod
    def of(cls, memory: Memory, caller: Caller, people: People, positions: dict[str, int]) -> "MemoryOut":
        return cls(
            id=memory.id,
            text=memory.text,
            place=PlaceOut.of(memory.place, people),
            about=people.ref(memory.about),
            told_by=people.ref(memory.told_by),
            tied_to=memory.tied_to,
            learnt_in=str(memory.source) if memory.source else None,
            session=memory.source.session if memory.source else None,
            learnt_event=positions.get(memory.id),
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            editable=edits_memory(caller, memory),
        )


class RetiredOut(BaseModel):
    """A memory no longer used, and why: its task or alert ended, or the nightly upkeep merged it or found it
    outdated."""

    memory_id: str
    text: str
    place: PlaceOut
    reason: Retirement
    why: str | None  # the consolidation model's words
    tied_to: str | None
    into: str | None  # the memory it was merged into
    at: datetime
    event: int  # its journal position

    @classmethod
    def of(cls, retired: MemoryRetired, position: int, people: People) -> "RetiredOut":
        return cls(
            memory_id=retired.memory_id,
            text=retired.text,
            place=PlaceOut.of(Place.parse(retired.place), people),
            reason=retired.reason,
            why=retired.why,
            tied_to=retired.tied_to,
            into=retired.into,
            at=retired.at,
            event=position,
        )


class CorrectionIn(Input):
    text: str


class MoveIn(Input):
    place: str  # people/<id>, home, household, projects/<name>, topics/<name>
