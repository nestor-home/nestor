"""What the API clients of a connected account share: an API's error with its status, the JSON object it answers,
and calls authorised with the account's bearer token."""

import contextlib
import urllib.parse
from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Any, ClassVar

import httpx

from nestor.adapters.common.http import retryable
from nestor.core import ProviderError
from nestor.modules.connectors import Access


class StatusError(ProviderError):
    """The account's API answered with an error: `status` is the HTTP status, `reason` the API's own code. It is worth
    retrying when `retryable` says so, or when the API says more (`transient`: a refused token it will refresh)."""

    def __init__(self, provider: str, status: int, reason: str, message: str, *, transient: bool = False) -> None:
        super().__init__(
            provider, f"HTTP {status} {reason}".rstrip() + f": {message}", transient=transient or retryable(status)
        )
        self.status, self.reason = status, reason


def json_object(provider: str, response: httpx.Response) -> dict[str, Any]:
    """The JSON object an API answered: `{}` for a call that answers nothing (204), a `ProviderError` for anything
    else than an object."""
    if not response.content:
        return {}
    try:
        found = response.json()
    except ValueError:
        raise ProviderError(provider, "answered with something other than JSON", transient=True) from None
    if not isinstance(found, dict):
        raise ProviderError(provider, "answered with an unexpected JSON document", transient=True)
    return found


def segment(value: str) -> str:
    """`value` as one segment of a URL's path: an id or words from the model never reach another path, a query or a
    fragment (`/`, `?`, `#`, `..` encoded)."""
    return urllib.parse.quote(value, safe="")


class BearerApi:
    """Calls to an account's API with its OAuth token, through a client the caller owns. Tokens are only ever sent,
    never logged. `provider` names it in errors; `error` reads the API's own error answers."""

    provider: ClassVar[str]

    def __init__(self, access: Access, client: httpx.AsyncClient) -> None:
        self._access, self._client = access, client

    def error(self, response: httpx.Response) -> StatusError:
        return StatusError(self.provider, response.status_code, "", response.reason_phrase)

    async def get(
        self, url: str, params: Sequence[tuple[str, str]] = (), headers: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        async with self._opened("GET", url, params=params, headers=headers) as response:
            await response.aread()
            return json_object(self.provider, response)

    async def send(
        self, method: str, url: str, body: dict[str, Any], headers: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        """A `POST` or a `PATCH` of `body`, and what the API answers."""
        async with self._opened(method, url, json=body, headers=headers) as response:
            await response.aread()
            return json_object(self.provider, response)

    async def download(self, url: str, params: Sequence[tuple[str, str]] = (), *, max_bytes: int) -> bytes:
        """A file, read until `max_bytes`: a larger one is refused (`ProviderError`, not transient)."""
        async with self._opened("GET", url, params=params) as response:
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise ProviderError(
                        self.provider, f"the file is larger than {max_bytes // 1_000_000} MB", transient=False
                    )
                chunks.append(chunk)
            return b"".join(chunks)

    @contextlib.asynccontextmanager
    async def _opened(
        self,
        method: str,
        url: str,
        *,
        params: Sequence[tuple[str, str]] = (),
        json: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> AsyncGenerator[httpx.Response]:
        sent = {**(headers or {}), "Authorization": f"Bearer {await self._access.token()}"}
        try:
            async with self._client.stream(
                method, url, params=list(params) or None, json=json, headers=sent
            ) as response:
                if not response.is_success:
                    await response.aread()
                    raise self.error(response)
                yield response
        except httpx.HTTPError as error:
            raise ProviderError(self.provider, f"unreachable ({type(error).__name__})", transient=True) from None
