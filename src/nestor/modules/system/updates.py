"""Whether a newer Nestor was released: the feed is read a minute after starting, then once a day.

The admin shows what changed since the running version, whether a change breaks the data or the
configuration, and which paired satellites the newest release no longer speaks to. Where an
`Installer` can (a Python environment, not a container image), a person installs the newest release
from the admin: only that version, only on their request, and the restart that follows is theirs too.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from nestor.core import Component, ContractError, ProviderError, utc_now
from nestor.modules.journal import Journal
from nestor.modules.system.events import UpdateFailed, UpdateRequested
from nestor.modules.system.ports import Installer, ReleaseFeed
from nestor.modules.system.types import Releases, version_key

log = logging.getLogger(__name__)

FIRST_CHECK_S = 60.0  # after starting: the household's first minutes are not spent on this
CHECK_EVERY_S = 24 * 3600.0


class Updates(Component):
    name = "updates"

    def __init__(
        self,
        feed: ReleaseFeed,
        running: str,
        journal: Journal,
        *,
        installer: Installer | None = None,
        first_check_s: float = FIRST_CHECK_S,
        every_s: float = CHECK_EVERY_S,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.running = running  # the version of this instance
        self._feed = feed
        self._journal = journal
        self.installer = installer  # None: the household updates Nestor the way it installed it
        self.installing: str | None = None  # the version being installed
        self.failed: str | None = None  # the version that last failed to install
        self._install: asyncio.Task[None] | None = None
        self._first_check_s, self._every_s = first_check_s, every_s
        self._clock = clock
        self.releases: Releases | None = None  # the feed as last read
        self.checked_at: datetime | None = None  # when it was last read successfully
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._feed.start()
        self._worker = asyncio.create_task(self._check_regularly(), name="release feed")

    async def close(self) -> None:
        if self._install is not None:
            self._install.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._install
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

    async def install(self, version: str, *, by: str, then: Callable[[], Awaitable[None]]) -> None:
        """Start installing `version`, which must be the newest release read and newer than the running
        one; `then` runs once it is installed (the restart). `ContractError` when it cannot start."""
        latest = self.releases.latest if self.releases else None
        if self.installer is None:
            raise ContractError("this instance updates the way it was installed, not from here")
        if latest is None or version != latest.version or version_key(version) <= version_key(self.running):
            raise ContractError(f"{version} is not the newest release")
        if self.installing is not None:
            raise ContractError(f"{self.installing} is being installed")
        self.installing, self.failed = version, None
        await self._journal.publish(UpdateRequested(source=self.name, by=by, running=self.running, target=version))
        self._install = asyncio.create_task(self._run_install(self.installer, version, then), name="install")

    async def _run_install(self, installer: Installer, version: str, then: Callable[[], Awaitable[None]]) -> None:
        try:
            await installer.install(version)
        except ProviderError as error:
            log.warning("installing %s: %s", version, error)
            self.installing, self.failed = None, version
            await self._journal.publish(UpdateFailed(source=self.name, target=version))
            return
        await then()

    async def _check_regularly(self) -> None:
        await asyncio.sleep(self._first_check_s)
        while True:
            await self.check()
            await asyncio.sleep(self._every_s)
