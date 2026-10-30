"""The journal service: write events durably, then fan them out to live subscribers."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import cast

from nestor.core import ContractError, Event, SessionId
from nestor.modules.journal.ports import EventLog
from nestor.modules.journal.types import LogQuery


class Subscription:
    """Live events of the requested types, in publication order, until `close`."""

    def __init__(self, journal: "Journal", types: tuple[type[Event], ...]) -> None:
        self._journal, self._types = journal, types
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()

    def wants(self, event: Event) -> bool:
        return not self._types or isinstance(event, self._types)

    def push(self, event: Event | None) -> None:
        self._queue.put_nowait(event)

    def close(self) -> None:
        self._journal.unsubscribe(self)
        self.push(None)

    async def __aiter__(self) -> AsyncIterator[Event]:
        while True:
            try:
                yield await self.next()
            except StopAsyncIteration:
                return

    async def next(self, timeout_s: float | None = None) -> Event:
        """The next event; `TimeoutError` if none arrives in time, `StopAsyncIteration` once closed."""
        event = await asyncio.wait_for(self._queue.get(), timeout_s)
        if event is None:
            self.push(None)  # stay closed for every later call
            raise StopAsyncIteration
        return event


class Journal:
    """Single entry point to the log. An event reaches subscribers only once it is durably written."""

    def __init__(self, log: EventLog) -> None:
        self.log = log
        self._subscriptions: list[Subscription] = []

    async def publish(self, event: Event) -> None:
        await self.log.append(event)
        for subscription in tuple(self._subscriptions):
            if subscription.wants(event):
                subscription.push(event)

    def subscribe(self, *types: type[Event]) -> Subscription:
        """Events published from now on; no types means every event."""
        subscription = Subscription(self, types)
        self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    async def history[E: Event](
        self,
        *types: type[E],
        session: SessionId | None = None,
        since: datetime | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> list[E]:
        """Past events of the given types, decoded. Asking for types keeps the log readable when a
        plugin that wrote other events has been removed."""
        if not types:
            raise ContractError("history needs at least one event type")
        query = LogQuery(
            types=frozenset(t.event_type for t in types),
            session=session,
            since=since,
            limit=limit,
            newest_first=newest_first,
        )
        events = [entry.event() for entry in await self.log.read(query)]
        return cast(list[E], [e for e in events if isinstance(e, types)])  # ty cannot narrow on a TypeVar tuple
