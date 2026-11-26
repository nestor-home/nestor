"""The memories retired lately, read from the journal: what the nightly upkeep and the endings of tasks and alerts
changed."""

from nestor.admin.state import AdminState
from nestor.modules.journal import LogQuery
from nestor.modules.memory import MemoryRetired


async def retired(admin: AdminState, limit: int) -> list[tuple[MemoryRetired, int]]:
    """The latest retirements, newest first, each with its journal position."""
    query = LogQuery(types=frozenset({MemoryRetired.event_type}), limit=limit, newest_first=True)
    entries = await admin.nestor.journal.log.read(query)
    return [(event, e.position) for e in entries if isinstance(event := e.event(), MemoryRetired)]
