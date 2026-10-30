"""Events of watches: created, triggered by an item, ended (matched, cancelled, expired)."""

from datetime import datetime

from nestor.core import Event, PersonId
from nestor.core.events import JSON
from nestor.modules.channels import Address, Exchange, before_exchanges


class WatchCreated(Event, event_type="watch.created", version=2):
    """v2: `exchange`, the conversation and turn that asked for it (`None` in version 1 records)."""

    watch_id: str
    what: str
    keywords: tuple[str, ...]
    kinds: tuple[str, ...]
    once: bool
    owner: PersonId | None = None
    created_in: Address | None = None
    until: datetime | None = None
    exchange: Exchange | None = None

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)


class WatchTriggered(Event, event_type="watch.triggered"):
    watch_id: str
    item_id: str
    item_title: str
    summary: str
    urgent: bool = False


class WatchEnded(Event, event_type="watch.ended"):
    watch_id: str
    reason: str
