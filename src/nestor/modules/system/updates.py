"""Whether a newer Nestor was released: the feed is read a minute after starting, then once a day.

The admin shows what changed since the running version, and whether a change breaks the data or
the configuration. Nothing is installed from here: the household updates Nestor the way it installed it.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import datetime

from nestor.core import Component, ContractError, ProviderError, utc_now
from nestor.modules.system.ports import ReleaseFeed
from nestor.modules.system.types import Release, Releases

log = logging.getLogger(__name__)

FIRST_CHECK_S = 60.0  # after starting: the household's first minutes are not spent on this
CHECK_EVERY_S = 24 * 3600.0


class Updates(Component):
    name = "updates"

    def __init__(
        self,
        feed: ReleaseFeed,
        running: str,
        *,
        first_check_s: float = FIRST_CHECK_S,
        every_s: float = CHECK_EVERY_S,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.running = running  # the version of this instance
        self._feed = feed
        self._first_check_s, self._every_s = first_check_s, every_s
        self._clock = clock
        self.releases: Releases | None = None  # the feed as last read
        self.checked_at: datetime | None = None  # when it was last read successfully
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._feed.start()
        self._worker = asyncio.create_task(self._check_regularly(), name="release feed")

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None
        await self._feed.close()

    async def check(self) -> None:
        """Read the feed now; a feed that cannot be read keeps the last one read."""
        try:
            self.releases = await self._feed.fetch()
        except (ProviderError, ContractError) as error:
            log.warning("release feed: %s", error)
            return
        self.checked_at = self._clock()

    def newer(self) -> tuple[Release, ...]:
        """The releases read after the running version, newest first."""
        return self.releases.newer_than(self.running) if self.releases else ()

    async def _check_regularly(self) -> None:
        await asyncio.sleep(self._first_check_s)
        while True:
            await self.check()
            await asyncio.sleep(self._every_s)
