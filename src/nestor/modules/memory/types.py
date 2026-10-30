"""A memory: one fact, about someone or the whole household, with where it came from."""

from dataclasses import dataclass, field, replace
from datetime import datetime

from nestor.core import PersonId, new_id, utc_now
from nestor.modules.channels import Address


@dataclass(frozen=True, slots=True, kw_only=True)
class Memory:
    text: str
    about: PersonId | None = None  # None: the household as a whole
    source: Address | None = None  # the conversation it was learnt in
    told_by: PersonId | None = None
    id: str = field(default_factory=lambda: new_id()[:12])
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def corrected(self, text: str) -> "Memory":
        return replace(self, text=text, updated_at=utc_now())
