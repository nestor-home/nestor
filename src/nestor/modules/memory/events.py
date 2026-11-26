"""Memory changes, as the journal records them, each with the conversation and turn it was made in
(`exchange`), or `None` when it was made elsewhere (the admin, the nightly upkeep). A place is written as its path
(`people/lea`, `projects/roof`)."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.memory.types import Retirement


class MemoryRecorded(Event, event_type="memory.recorded"):
    """`exchange` is the turn that remembered it; `episode` the past conversation it was drawn from, when the
    consolidation found it there; `task` the task whose note it was kept from; `tied_to` what it holds while."""

    memory_id: str
    text: str
    place: str
    learnt_in: Address | None = None  # `source` is the envelope's emitting component
    told_by: PersonId | None = None
    exchange: Exchange | None = None
    episode: str | None = None
    task: str | None = None
    tied_to: str | None = None


class MemoryCorrected(Event, event_type="memory.corrected"):
    """`merged`: the memories the upkeep merged into this one, retired with it (`MemoryRetired`)."""

    memory_id: str
    text: str
    by: PersonId | None = None
    exchange: Exchange | None = None
    merged: tuple[str, ...] = ()


class MemoryMoved(Event, event_type="memory.moved"):
    memory_id: str
    place: str
    by: PersonId | None = None
    exchange: Exchange | None = None


class MemoryForgotten(Event, event_type="memory.forgotten"):
    """The memory is removed from the store; the agent no longer knows it. The conversation where it
    was said stays in the journal until conversation purging exists."""

    memory_id: str
    by: PersonId | None = None
    exchange: Exchange | None = None


class MemoryRetired(Event, event_type="memory.retired"):
    """No longer used, and kept here with what it said: its task or alert ended (`tied_to`), or the nightly upkeep
    found it outdated or merged it `into` another (`merged_text`: what that one says now), `why` in the consolidation
    model's words."""

    memory_id: str
    text: str
    place: str
    reason: Retirement
    why: str | None = None
    tied_to: str | None = None
    into: str | None = None
    merged_text: str | None = None


class MemoryUpkept(Event, event_type="memory.upkept"):
    """A nightly upkeep went through the memories: how many places it read, merged and retired from, and those it
    could not read (the model failed)."""

    places: int
    merged: int
    retired: int
    failed: tuple[str, ...] = ()
