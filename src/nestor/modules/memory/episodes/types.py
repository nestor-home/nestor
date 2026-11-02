"""An episode: what a past conversation was about, written when it ended, for whoever took part in it."""

from dataclasses import dataclass
from datetime import datetime

from nestor.core import PersonId
from nestor.modules.channels import Address, Medium


@dataclass(frozen=True, slots=True, kw_only=True)
class Episode:
    """`id` is the conversation's. Only its `participants` see it again: what concerns the whole household
    goes to the memories."""

    id: str
    address: Address
    medium: Medium  # of its last turn: said or written
    participants: tuple[PersonId, ...]
    started_at: datetime
    ended_at: datetime
    summary: str
    topics: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """What is searched and embedded."""
        return f"{self.summary} ({', '.join(self.topics)})" if self.topics else self.summary
