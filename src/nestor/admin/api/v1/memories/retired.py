"""The memories retired lately, read from the journal: what the nightly upkeep changed, and what went when what it
was tied to ended."""

from collections.abc import Callable

from nestor.admin.state import AdminState
from nestor.modules.journal import LogQuery
from nestor.modules.memory import MemoryRetired, Place


async def retired(admin: AdminState, limit: int, reads: Callable[[Place], bool]) -> list[tuple[MemoryRetired, int]]:
    """The latest `limit` retirements of the places one `reads`, newest first, each with its journal position."""
    found: list[tuple[MemoryRetired, int]] = []
    before: int | None = None
    while len(found) < limit:
        query = LogQuery(types=frozenset({MemoryRetired.event_type}), limit=limit, newest_first=True, before=before)
        entries = await admin.nestor.journal.log.read(query)
        found += [
            (event, e.position)
            for e in entries
            if isinstance(event := e.event(), MemoryRetired) and reads(Place.parse(event.place))
        ]
        if len(entries) < limit:
            break
        before = entries[-1].position
    return found[:limit]
