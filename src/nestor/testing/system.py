"""A release feed that says what it is told, for tests of the updates and the admin."""

from nestor.core import ProviderError
from nestor.modules.system import ReleaseFeed, Releases


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
