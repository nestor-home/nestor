"""Events of watches: created, an item sorted against them, triggered by it, ended (matched, cancelled, expired)."""

from datetime import datetime

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange


class WatchCreated(Event, event_type="watch.created"):
    """`exchange` is the conversation and turn that asked for it, when one did."""

    watch_id: str
    what: str
    kinds: tuple[str, ...]
    once: bool
    owner: PersonId | None = None
    created_in: Address | None = None
    until: datetime | None = None
    exchange: Exchange | None = None


class WatchSorted(Event, event_type="watch.sorted"):
    """An item read against the watches it may concern: those it matched, or none when it stayed unsorted
    (the triage model could not be reached or read: nothing is announced). `item_source` is what brought the
    item: a connection's id, or a source's name."""

    item_id: str
    item_title: str
    item_source: str
    asked: tuple[str, ...]
    matched: tuple[str, ...] = ()
    unsorted: bool = False


class WatchTriggered(Event, event_type="watch.triggered"):
    """`item_source` as in `WatchSorted`."""

    watch_id: str
    item_id: str
    item_title: str
    item_source: str
    summary: str
    urgent: bool = False


class WatchEnded(Event, event_type="watch.ended"):
    watch_id: str
    reason: str
