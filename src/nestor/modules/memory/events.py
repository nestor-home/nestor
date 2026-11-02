"""Memory changes, as the journal records them, each with the conversation and turn it was made in
(`exchange`), or `None` when it was made elsewhere (the admin)."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange


class MemoryRecorded(Event, event_type="memory.recorded"):
    """`exchange` is the turn that remembered it; `episode` the past conversation it was drawn from, when the
    consolidation found it there."""

    memory_id: str
    text: str
    about: PersonId | None = None
    learnt_in: Address | None = None  # `source` is the envelope's emitting component
    told_by: PersonId | None = None
    exchange: Exchange | None = None
    episode: str | None = None


class MemoryCorrected(Event, event_type="memory.corrected"):
    memory_id: str
    text: str
    by: PersonId | None = None
    exchange: Exchange | None = None


class MemoryForgotten(Event, event_type="memory.forgotten"):
    """The memory is removed from the store; the agent no longer knows it. The conversation where it
    was said stays in the journal until conversation purging exists."""

    memory_id: str
    by: PersonId | None = None
    exchange: Exchange | None = None
