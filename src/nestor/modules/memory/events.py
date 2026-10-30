"""Memory changes, as the journal records them."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address


class MemoryRecorded(Event, event_type="memory.recorded"):
    memory_id: str
    text: str
    about: PersonId | None = None
    learnt_in: Address | None = None  # `source` is the envelope's emitting component
    told_by: PersonId | None = None


class MemoryCorrected(Event, event_type="memory.corrected"):
    memory_id: str
    text: str
    by: PersonId | None = None


class MemoryForgotten(Event, event_type="memory.forgotten"):
    """The memory is removed from the store; the agent no longer knows it. The conversation where it
    was said stays in the journal until conversation purging exists."""

    memory_id: str
    by: PersonId | None = None
