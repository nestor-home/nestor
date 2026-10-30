"""Doubles and contract suites for the journal ports."""

import hashlib
from datetime import datetime, timedelta

from nestor.core import ContractError, Event, SessionId, utc_now
from nestor.modules.journal import BlobRef, BlobStore, Entry, EventLog, LogQuery
from nestor.testing.assertions import raises


class MemoryEventLog(EventLog):
    """An event log kept in memory: for tests and throwaway runs."""

    name = "memory-event-log"

    def __init__(self) -> None:
        self.entries: list[Entry] = []
        self._ids: set[str] = set()

    async def append(self, event: Event) -> int:
        if event.id in self._ids:
            raise ContractError(f"event {event.id} is already logged")
        self._ids.add(event.id)
        entry = Entry(len(self.entries) + 1, event.to_record())
        self.entries.append(entry)
        return entry.position

    async def read(self, query: LogQuery) -> list[Entry]:
        found = [e for e in self.entries if _matches(e, query)]
        if query.newest_first:
            found.reverse()
        return found[: query.limit] if query.limit is not None else found


def _matches(entry: Entry, query: LogQuery) -> bool:
    record = entry.record
    at = datetime.fromisoformat(str(record["at"]))
    return (
        entry.position > query.after
        and (query.types is None or entry.type in query.types)
        and (query.session is None or record["session"] == query.session)
        and (query.since is None or at >= query.since)
        and (query.until is None or at < query.until)
    )


class MemoryBlobStore(BlobStore):
    name = "memory-blob-store"

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    async def put(self, data: bytes, media_type: str) -> BlobRef:
        digest = hashlib.sha256(data).hexdigest()
        self.blobs[digest] = data
        return BlobRef(digest, len(data), media_type)

    async def get(self, digest: str) -> bytes:
        return self.blobs[digest]

    async def delete(self, digest: str) -> None:
        self.blobs.pop(digest, None)


class Probe(Event, event_type="testing.probe"):
    """A neutral event for storage suites."""

    label: str
    count: int = 0


def labels(entries: list[Entry]) -> list[str]:
    return [event.label for entry in entries if isinstance(event := entry.event(), Probe)]


class EventLogContract:
    """Behaviour every `EventLog` must show. Implement `event_log()`; it is used as a context manager."""

    def event_log(self) -> EventLog:
        raise NotImplementedError

    async def test_entries_come_back_in_order_with_growing_positions(self) -> None:
        async with self.event_log() as log:
            events = [Probe(source="test", label=f"p{i}", count=i) for i in range(5)]
            positions = [await log.append(e) for e in events]
            entries = await log.read(LogQuery())
        assert positions == sorted(set(positions))
        assert [e.event() for e in entries] == events

    async def test_an_event_is_logged_only_once(self) -> None:
        async with self.event_log() as log:
            event = Probe(source="test", label="once")
            await log.append(event)
            with raises(ContractError):
                await log.append(event)
            assert len(await log.read(LogQuery())) == 1

    async def test_a_query_combines_its_criteria(self) -> None:
        now = utc_now()
        async with self.event_log() as log:
            await log.append(Probe(source="test", label="old", at=now - timedelta(days=2), session=SessionId("a")))
            await log.append(Probe(source="test", label="kept", at=now, session=SessionId("a")))
            await log.append(Probe(source="test", label="other session", at=now, session=SessionId("b")))
            await log.append(_Other(source="test", at=now, session=SessionId("a")))
            found = await log.read(
                LogQuery(types=frozenset({"testing.probe"}), session=SessionId("a"), since=now - timedelta(hours=1))
            )
        assert labels(found) == ["kept"]

    async def test_reading_pages_through_the_log(self) -> None:
        async with self.event_log() as log:
            for i in range(5):
                await log.append(Probe(source="test", label=f"p{i}"))
            first = await log.read(LogQuery(limit=2))
            rest = await log.read(LogQuery(after=first[-1].position))
            latest = await log.read(LogQuery(newest_first=True, limit=1))
            before = await log.read(LogQuery(until=Event.from_record(rest[0].record).at))
        assert labels(first + rest) == [f"p{i}" for i in range(5)]
        assert labels(latest) == ["p4"]
        assert all(e.position < rest[0].position for e in before)

    async def test_an_empty_log_reads_as_empty(self) -> None:
        async with self.event_log() as log:
            assert await log.read(LogQuery(types=frozenset({"testing.probe"}))) == []


class _Other(Event, event_type="testing.other"):
    pass


class BlobStoreContract:
    """Behaviour every `BlobStore` must show. Implement `blob_store()`."""

    def blob_store(self) -> BlobStore:
        raise NotImplementedError

    async def test_stored_content_comes_back_exactly(self) -> None:
        data = bytes(range(256)) * 10
        async with self.blob_store() as store:
            ref = await store.put(data, "application/octet-stream")
            assert await store.get(ref.digest) == data
        assert ref.size == len(data)

    async def test_same_content_gives_the_same_reference(self) -> None:
        async with self.blob_store() as store:
            first = await store.put(b"identique", "text/plain")
            second = await store.put(b"identique", "text/plain")
            other = await store.put(b"autre", "text/plain")
        assert first == second != other

    async def test_a_deleted_blob_is_gone(self) -> None:
        async with self.blob_store() as store:
            ref = await store.put(b"secret", "text/plain")
            await store.delete(ref.digest)
            await store.delete(ref.digest)
            with raises(KeyError):
                await store.get(ref.digest)
