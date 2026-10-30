"""The book of watches: which watches are active, rebuilt from the journal, created and ended there."""

from collections.abc import Iterable

from nestor.core import Component, utc_now
from nestor.modules.channels import Exchange
from nestor.modules.initiative.watches.events import WatchCreated, WatchEnded
from nestor.modules.initiative.watches.types import Watch
from nestor.modules.journal import Journal


class WatchBook(Component):
    name = "watch-book"

    def __init__(self, journal: Journal, kinds: Iterable[str] = ()) -> None:
        self.journal = journal
        self.kinds = frozenset(kinds)  # what the connected sources can bring
        self.watches: dict[str, Watch] = {}

    async def start(self) -> None:
        ended = {e.watch_id for e in await self.journal.history(WatchEnded)}
        for created in await self.journal.history(WatchCreated):
            if created.watch_id not in ended:
                self.watches[created.watch_id] = _watch(created)
        await self.expire()

    async def create(self, watch: Watch, *, exchange: Exchange | None = None) -> Watch:
        await self.journal.publish(
            WatchCreated(
                source=self.name,
                session=watch.created_in.session if watch.created_in else None,
                watch_id=watch.id,
                what=watch.what,
                keywords=watch.keywords,
                kinds=watch.kinds,
                once=watch.once,
                owner=watch.owner,
                created_in=watch.created_in,
                until=watch.until,
                exchange=exchange,
            )
        )
        self.watches[watch.id] = watch
        return watch

    async def end(self, watch_id: str, reason: str) -> bool:
        if self.watches.pop(watch_id, None) is None:
            return False
        await self.journal.publish(WatchEnded(source=self.name, watch_id=watch_id, reason=reason))
        return True

    async def expire(self) -> None:
        now = utc_now()
        for watch in tuple(self.watches.values()):
            if watch.until and watch.until <= now:
                await self.end(watch.id, "expired")


def _watch(event: WatchCreated) -> Watch:
    return Watch(
        id=event.watch_id,
        what=event.what,
        keywords=event.keywords,
        kinds=event.kinds,
        once=event.once,
        owner=event.owner,
        created_in=event.created_in,
        until=event.until,
        created_at=event.at,
    )
