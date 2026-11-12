"""What adapters calling an HTTP API share: which errors a retry may get past, the detail of an error as the
provider words it, a key never shown in one, and a client for JSON APIs."""

import json
from collections.abc import Mapping
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


class JsonApi:
    """A JSON API over HTTP: one client, opened on the first call and kept until `aclose`. Every failure, the network
    or the provider's, becomes a `ProviderError` labelled `provider`, with `secret` redacted."""

    def __init__(
        self,
        provider: str,
        base_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        secret: str | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._provider, self._base_url, self._secret = provider, base_url, secret
        self._headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        self._timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def get(self, path: str, params: Mapping[str, str | int | float] | None = None) -> Any:
        return await self._call("GET", path, params=params)

    async def post(self, path: str, body: object) -> Any:
        return await self._call("POST", path, json=body)

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=self._timeout_s)
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise self._error(f"{path}: {type(error).__name__} {error}".strip(), transient=True) from None
        if response.is_error:
            raise self._error(
                f"{path}: HTTP {response.status_code} {detail(response.content)}",
                transient=retryable(response.status_code),
            )
        try:
            return response.json()
        except ValueError:
            raise self._error(f"{path}: not JSON: {response.text[:MAX_DETAIL]}", transient=False) from None

    def _error(self, message: str, *, transient: bool) -> ProviderError:
        return provider_error(self._provider, self._secret, message, transient=transient)
