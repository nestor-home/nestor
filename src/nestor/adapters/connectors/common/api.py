"""What the API clients of a connected account share: calls authorised with the account's bearer token, and ids kept
to one segment of a URL."""

import urllib.parse
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

import httpx

from nestor.adapters.common.http import HttpApi, json_object
from nestor.modules.connectors import Access


def segment(value: str) -> str:
    """`value` as one segment of a URL's path: an id or words from the model never reach another path, a query or a
    fragment (`/`, `?`, `#`, `..` encoded)."""
    return urllib.parse.quote(value, safe="")


class BearerApi(HttpApi):
    """Calls to an account's API with its OAuth token, through a client the connector owns (one for all accounts).
    Tokens are only ever sent, never logged. `provider` names it in errors; `failed` reads the API's own error
    answers."""

    provider: ClassVar[str]

    def __init__(self, access: Access, client: httpx.AsyncClient) -> None:
        super().__init__(self.provider, client=client)
        self._access = access

    async def authorise(self) -> Mapping[str, str]:
        return {"Authorization": f"Bearer {await self._access.token()}"}

    async def get(
        self, url: str, params: Sequence[tuple[str, str]] = (), headers: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        response = await self.request("GET", url, params=list(params) or None, headers=headers)
        return json_object(self.provider, response)

    async def send(
        self, method: str, url: str, body: dict[str, Any], headers: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        """A `POST` or a `PATCH` of `body`, and what the API answers."""
        return json_object(self.provider, await self.request(method, url, json=body, headers=headers))

    async def fetch(self, url: str, params: Sequence[tuple[str, str]] = (), *, max_bytes: int) -> bytes:
        """A file, read until `max_bytes`."""
        return await self.download(url, max_bytes=max_bytes, params=list(params) or None)
