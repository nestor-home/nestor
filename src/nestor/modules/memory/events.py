"""Memory changes, as the journal records them.

v2 of each: `exchange`, the conversation and turn the change was made in; `None` when it was made
elsewhere (the admin) or recorded in version 1.
"""

from nestor.core import Event, PersonId
from nestor.core.events import JSON
from nestor.modules.channels import Address, Exchange, before_exchanges


class MemoryRecorded(Event, event_type="memory.recorded", version=2):
    memory_id: str
    text: str
    about: PersonId | None = None
    learnt_in: Address | None = None  # `source` is the envelope's emitting component
    told_by: PersonId | None = None
    exchange: Exchange | None = None

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)


class MemoryCorrected(Event, event_type="memory.corrected", version=2):
    memory_id: str
    text: str
    by: PersonId | None = None
    exchange: Exchange | None = None

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)


class MemoryForgotten(Event, event_type="memory.forgotten", version=2):
    """The memory is removed from the store; the agent no longer knows it. The conversation where it
    was said stays in the journal until conversation purging exists."""

    memory_id: str
    by: PersonId | None = None
    exchange: Exchange | None = None

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)
