"""A release feed that says what it is told and an installer that succeeds or fails on demand, for
tests of the updates and the admin."""

import asyncio

from nestor.core import ProviderError
from nestor.modules.system import Installer, ReleaseFeed, Releases
from nestor.modules.system.selfmap import Card, Documentation


class StaticReleaseFeed(ReleaseFeed):
    """Answers `releases`; unreadable (a transient `ProviderError`) while it is `None`."""

    name = "static-release-feed"

    def __init__(self, releases: Releases | None = None) -> None:
        self.releases = releases
        self.reads = 0

    async def fetch(self) -> Releases:
        self.reads += 1
        if self.releases is None:
            raise ProviderError("releases", "unreachable", transient=True)
        return self.releases


class FakeInstaller(Installer):
    """Installs once `release` is set (immediately by default); fails when `fails`."""

    def __init__(self, *, fails: bool = False, wait: bool = False) -> None:
        self.fails = fails
        self.installed: list[str] = []
        self.release = asyncio.Event()
        if not wait:
            self.release.set()

    async def install(self, version: str) -> None:
        await self.release.wait()
        if self.fails:
            raise ProviderError("installer", f"{version} refused the configuration", transient=False)
        self.installed.append(version)


# the card of a plugin that only tests register
DOUBLE = Card(summary="A test double.", docs="plugins")


class StaticDocumentation(Documentation):
    """Serves `pages` by slug; unreadable (a transient `ProviderError`) while `offline` or for a page it lacks."""

    name = "static-documentation"

    def __init__(self, pages: dict[str, str] | None = None, *, offline: bool = False) -> None:
        self.pages, self.offline = dict(pages or {}), offline
        self.read: list[str] = []

    async def page(self, slug: str) -> str:
        self.read.append(slug)
        if self.offline or slug not in self.pages:
            raise ProviderError("docs", f"no page {slug!r}", transient=True)
        return self.pages[slug]
