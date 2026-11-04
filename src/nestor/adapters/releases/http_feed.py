"""The release feed, a JSON file published with each release (`releases.json`), read over HTTPS."""

import json

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
        body = bytearray()
        try:
            async with self._client.stream("GET", self.url) as response:
                if response.status_code != 200:
                    raise ProviderError(PROVIDER, f"{self.url}: HTTP {response.status_code}", transient=True)
                async for chunk in response.aiter_bytes():  # read no further than a feed can weigh
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise ProviderError(PROVIDER, f"{self.url}: over {MAX_BYTES} bytes, not a release feed",
                                            transient=False)  # fmt: skip
        except httpx.HTTPError as error:
            raise ProviderError(PROVIDER, f"{self.url}: {type(error).__name__}", transient=True) from None
        try:
            data = json.loads(body)
        except ValueError:
            raise ProviderError(PROVIDER, f"{self.url}: not JSON", transient=False) from None
        return Releases.from_json(data)
