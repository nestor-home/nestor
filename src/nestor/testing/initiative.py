"""Double and contract suite for inbound sources."""

import asyncio
from collections.abc import AsyncGenerator

from nestor.modules.initiative import InboundEventSource, Incoming


class Inbox:
    """The provider behind `QueuedSource` (a mailbox): it outlives the source, like a real server."""

    def __init__(self) -> None:
        self.items: list[Incoming] = []
        self.cursor = 0  # what the source acknowledged: its durable resume point
        self.arrived = asyncio.Event()

    def deliver(self, item: Incoming) -> None:
        self.items.append(item)
        self.arrived.set()


class QueuedSource(InboundEventSource):
    """Yields what arrives in its inbox, resuming after the last acknowledged item."""

    name = "queued-source"

    def __init__(self, inbox: Inbox | None = None, *, kinds: tuple[str, ...] = ("mail",)) -> None:
        self.inbox = inbox or Inbox()
        self.kinds = kinds

    async def items(self) -> AsyncGenerator[Incoming]:
        while True:
            while self.inbox.cursor < len(self.inbox.items):
                item = self.inbox.items[self.inbox.cursor]
                self.inbox.cursor += 1
                yield item
            self.inbox.arrived.clear()
            await self.inbox.arrived.wait()


class InboundEventSourceContract:
    """Behaviour every `InboundEventSource` must show. Implement `source()` (a new instance over the same
    provider each call, to play a restart) and `arrive(title)` (make the provider receive an item). A source items
    are pushed to (`pushed`: a webhook) receives only while running: `arrive` is then called on a running source."""

    timeout_s = 5.0
    pushed = False

    def source(self) -> InboundEventSource:
        raise NotImplementedError

    async def arrive(self, title: str) -> None:
        raise NotImplementedError

    async def _take(self, source: InboundEventSource, count: int) -> list[str]:
        feed = source.items()
        titles = [(await asyncio.wait_for(anext(feed), self.timeout_s)).title for _ in range(count)]
        await feed.aclose()
        return titles

    async def _resumed(self, source: InboundEventSource, last: str, count: int) -> list[str]:
        """`count` items after a restart, past `last` (the item handed out before the stop) if it comes again."""
        feed = source.items()
        titles = [(await asyncio.wait_for(anext(feed), self.timeout_s)).title]
        if titles == [last]:
            titles = []
        while len(titles) < count:
            titles.append((await asyncio.wait_for(anext(feed), self.timeout_s)).title)
        await feed.aclose()
        return titles

    async def test_items_come_once_in_order_and_resume_after_a_restart(self) -> None:
        async with self.source() as first:
            await self.arrive("un")
            await self.arrive("deux")
            assert await self._take(first, 2) == ["un", "deux"]
        if not self.pushed:
            await self.arrive("trois")  # arrives while Nestor is down
        async with self.source() as restarted:
            if self.pushed:
                await self.arrive("trois")
            assert await self._resumed(restarted, "deux", 1) == ["trois"]

    async def test_an_item_not_taken_before_a_restart_comes_after_it(self) -> None:
        async with self.source() as first:
            await self.arrive("un")
            await self.arrive("deux")
            assert await self._take(first, 1) == ["un"]
            await self.arrive("trois")  # arrives once nothing reads the source any more
        async with self.source() as restarted:
            assert await self._resumed(restarted, "un", 2) == ["deux", "trois"]
