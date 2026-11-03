"""An episode, as the journal records it once its conversation ended. An empty summary marks a conversation
with nothing worth recalling: it is summarized, and never brought back."""

from datetime import datetime

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Medium


class EpisodeSummarized(Event, event_type="memory.episode"):
    conversation_id: str
    address: Address
    medium: Medium
    participants: tuple[PersonId, ...]
    started_at: datetime
    ended_at: datetime
    summary: str
    topics: tuple[str, ...] = ()
