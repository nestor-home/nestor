"""The release feed, a JSON file published with each release (`releases.json`), read over HTTPS."""

import httpx

from nestor.core import ProviderError
from nestor.modules.system import ReleaseFeed, Releases

PROVIDER = "releases"
MAX_BYTES = 1_000_000  # a feed is a few kilobytes; anything far larger is not one


class HttpReleaseFeed(ReleaseFeed):
    name = "release-feed"

    def __init__(self, url: str, *, timeout_s: float = 15.0, client: httpx.AsyncClient | None = None) -> None:
        self.url = url
        self._client = client
        self._own_client = client is None
        self._timeout_s = timeout_s

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s, follow_redirects=True)

    async def close(self) -> None:
        if self._own_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch(self) -> Releases:
        assert self._client is not None, "start the feed first"
        try:
            response = await self._client.get(self.url)
        except httpx.HTTPError as error:
            raise ProviderError(PROVIDER, f"{self.url}: {type(error).__name__}", transient=True) from None
        if response.status_code != 200:
            raise ProviderError(PROVIDER, f"{self.url}: HTTP {response.status_code}", transient=True)
        if len(response.content) > MAX_BYTES:
            raise ProviderError(
                PROVIDER, f"{self.url}: {len(response.content)} bytes, not a release feed", transient=False
            )
        try:
            data = response.json()
        except ValueError:
            raise ProviderError(PROVIDER, f"{self.url}: not JSON", transient=False) from None
        return Releases.from_json(data)
