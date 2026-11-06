"""Where each memory was recorded in the journal, to open the entry it came from."""

from nestor.admin.state import AdminState
from nestor.modules.journal import LogQuery
from nestor.modules.memory import MemoryRecorded


async def recorded(admin: AdminState) -> dict[str, int]:
    """The journal position where each memory was recorded."""
    entries = await admin.nestor.journal.log.read(LogQuery(types=frozenset({MemoryRecorded.event_type})))
    return {
        str(payload.get("memory_id")): e.position for e in entries if isinstance(payload := e.record["payload"], dict)
    }
