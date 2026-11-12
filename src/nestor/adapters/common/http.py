"""What adapters calling an HTTP API share: which errors a retry may get past, the detail of an error as the
provider words it, a key never shown in one, and a client for JSON APIs."""

import json
from collections.abc import Collection, Mapping
from typing import Any

import httpx

from nestor.core import ProviderError

MAX_DETAIL = 300
_RETRYABLE_STATUSES = frozenset({408, 409, 425, 429})


def retryable(status: int) -> bool:
    return status in _RETRYABLE_STATUSES or status >= 500


def detail(body: bytes) -> str:
    """An error body as the provider words it: its `error.message` when it sends one."""
    text = body.decode(errors="replace")
    try:
        error = json.loads(text)["error"]
    except (ValueError, KeyError, TypeError):
        return text[:MAX_DETAIL]
    return message_of(error)


def message_of(error: object) -> str:
    message = error.get("message", error) if isinstance(error, dict) else error
    return str(message)[:MAX_DETAIL]


def provider_error(provider: str, api_key: str | None, message: str, *, transient: bool) -> ProviderError:
    """A `ProviderError` labelled with `provider`, the key redacted wherever the message quotes it."""
    redacted = message.replace(api_key, "[redacted]") if api_key else message
    return ProviderError(provider, redacted, transient=transient)


# public services ask clients to name themselves (Nominatim requires it)
USER_AGENT = "nestor (+https://nestorhome.dev)"


class HttpApi:
    """An HTTP API: one client, opened on the first call and kept until `aclose`, so that a call does not pay a new
    connection. Every failure, the network's or the provider's, becomes a `ProviderError` labelled `provider`, with
    `secret` redacted."""

    def __init__(
        self,
        provider: str,
        base_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        secret: str | None = None,
        timeout_s: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._provider, self._base_url, self._secret = provider, base_url, secret
        self._headers = {"User-Agent": USER_AGENT, **(headers or {})}
        self._timeout_s, self._transport = timeout_s, transport
        self._client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def request(self, method: str, path: str, *, answers: Collection[int] = (), **kwargs: Any) -> httpx.Response:
        """`answers`: error statuses whose body is an answer, not a failure (a route that does not exist)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url, headers=self._headers, timeout=self._timeout_s, transport=self._transport
            )
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise self.error(f"{path}: {type(error).__name__} {error}".strip(), transient=True) from None
        if response.is_error and response.status_code not in answers:
            raise self.error(
                f"{path}: HTTP {response.status_code} {detail(response.content)}",
                transient=retryable(response.status_code),
            )
        return response

    def error(self, message: str, *, transient: bool) -> ProviderError:
        return provider_error(self._provider, self._secret, message, transient=transient)


class JsonApi(HttpApi):
    """An `HttpApi` that speaks JSON both ways; an answer that is not JSON is a `ProviderError` too."""

    async def get(
        self, path: str, params: Mapping[str, str | int | float] | None = None, *, answers: Collection[int] = ()
    ) -> Any:
        return self._json(path, await self.request("GET", path, answers=answers, params=params))

    async def post(self, path: str, body: object) -> Any:
        return self._json(path, await self.request("POST", path, json=body))

    def _json(self, path: str, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise self.error(f"{path}: not JSON: {response.text[:MAX_DETAIL]}", transient=False) from None
