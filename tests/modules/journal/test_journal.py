"""The journal: events are durable before anyone sees them, and the history reads them back typed."""

import pytest

from nestor.core import ContractError, Event, ProviderError, SessionId
from nestor.modules.journal import Journal, LogQuery
from nestor.testing.journal import (
    BlobStoreContract,
    EventLogContract,
    MemoryBlobStore,
    MemoryEventLog,
    Probe,
)


class Ping(Event, event_type="test.journal.ping"):
    n: int


class TestMemoryEventLog(EventLogContract):
    def event_log(self) -> MemoryEventLog:
        return MemoryEventLog()


class TestMemoryBlobStore(BlobStoreContract):
    def blob_store(self) -> MemoryBlobStore:
        return MemoryBlobStore()


class ForgetfulLog(MemoryEventLog):
    """Accepts everything and keeps nothing: what the contract suite must reject."""

    async def append(self, event: Event) -> int:
        return 1


async def test_the_contract_rejects_a_log_that_loses_events() -> None:
    class Suite(EventLogContract):
        def event_log(self) -> MemoryEventLog:
            return ForgetfulLog()

    with pytest.raises(AssertionError):
        await Suite().test_entries_come_back_in_order_with_growing_positions()


async def test_the_contract_rejects_a_log_that_accepts_duplicates() -> None:
    class Careless(MemoryEventLog):
        async def append(self, event: Event) -> int:
            self._ids.discard(event.id)
            return await super().append(event)

    class Suite(EventLogContract):
        def event_log(self) -> MemoryEventLog:
            return Careless()

    with pytest.raises(AssertionError, match="ContractError was not raised"):
        await Suite().test_an_event_is_logged_only_once()


async def test_subscribers_receive_published_events_of_their_types() -> None:
    journal = Journal(MemoryEventLog())
    pings, everything = journal.subscribe(Ping), journal.subscribe()

    await journal.publish(Probe(source="test", label="x"))
    await journal.publish(Ping(source="test", n=1))

    assert await pings.next(timeout_s=1) == Ping(
        source="test", n=1, id=(await journal.history(Ping))[0].id, at=(await journal.history(Ping))[0].at
    )
    assert [type(await everything.next(timeout_s=1)) for _ in range(2)] == [Probe, Ping]


async def test_an_event_that_could_not_be_written_reaches_no_one() -> None:
    class BrokenLog(MemoryEventLog):
        async def append(self, event: Event) -> int:
            raise ProviderError("disk", "full", transient=False)

    journal = Journal(BrokenLog())
    subscription = journal.subscribe()

    with pytest.raises(ProviderError):
        await journal.publish(Ping(source="test", n=1))
    with pytest.raises(TimeoutError):
        await subscription.next(timeout_s=0.01)


async def test_a_closed_subscription_ends_and_stops_receiving() -> None:
    journal = Journal(MemoryEventLog())
    subscription = journal.subscribe(Ping)
    subscription.close()
    await journal.publish(Ping(source="test", n=1))

    assert [event async for event in subscription] == []
    with pytest.raises(StopAsyncIteration):
        await subscription.next(timeout_s=1)


async def test_history_decodes_past_events_of_the_requested_types() -> None:
    log = MemoryEventLog()
    journal = Journal(log)
    for n in range(3):
        await journal.publish(Ping(source="test", n=n, session=SessionId("s")))
    await journal.publish(Probe(source="test", label="noise", session=SessionId("s")))

    latest = await journal.history(Ping, session=SessionId("s"), newest_first=True, limit=2)

    assert [p.n for p in latest] == [2, 1]
    assert len(await log.read(LogQuery())) == 4


async def test_history_without_a_type_is_refused() -> None:
    with pytest.raises(ContractError):
        await Journal(MemoryEventLog()).history()
