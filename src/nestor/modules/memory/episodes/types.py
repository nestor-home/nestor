"""An episode: what a past conversation was about, written when it ended, for whoever took part in it."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

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

    def seen_by(self, person: PersonId, since: datetime | None = None, until: datetime | None = None) -> bool:
        """Whether `person` took part in it, and it ended within `since` and `until`."""
        return (
            person in self.participants
            and (since is None or self.ended_at >= since)
            and (until is None or self.ended_at <= until)
        )

    def describe(self, zone: ZoneInfo) -> str:
        """When and where it ended, for the model: "Sunday 18 October 2026, 22:00, in writing (telegram:7)"."""
        return f"{self.ended_at.astimezone(zone):%A %d %B %Y, %H:%M}, {how(self.medium)} ({self.address})"


def how(medium: Medium) -> str:
    """How a conversation was held, in the words the model reads."""
    return "aloud" if medium is Medium.SPOKEN else "in writing"
