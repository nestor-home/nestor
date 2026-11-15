"""What adapters calling an HTTP API share: which errors a retry may get past, the detail of an error as the
provider words it, a key never shown in one, a client for JSON APIs, and streamed answers (Server-Sent Events)."""

import contextlib
import email.utils
import hashlib
import hmac
import json
import urllib.parse
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Collection, Iterable, Mapping
from typing import Any

import httpx

from nestor import __version__
from nestor.core import ProviderError, utc_now

MAX_DETAIL = 300
_RETRYABLE_STATUSES = frozenset({408, 409, 425, 429})


def retryable(status: int) -> bool:
    return status in _RETRYABLE_STATUSES or status >= 500


def retry_after(value: str | None) -> float | None:
    """A `Retry-After` header in seconds (it gives seconds or a date); `None` without one or one unreadable."""
    if not value:
        return None
    if value.strip().isdigit():
        return float(value)
    try:
        return max(0.0, (email.utils.parsedate_to_datetime(value) - utc_now()).total_seconds())
    except (TypeError, ValueError):
        return None


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


type Failure = Callable[..., ProviderError]
"""Makes the `ProviderError` of an adapter from a message and `transient`."""


async def streamed_lines(
    client: httpx.AsyncClient, path: str, body: object, error: Failure, **kwargs: Any
) -> AsyncGenerator[str]:
    """The lines of the answer to a streamed POST of `body`. An error status, a timeout or a transport failure is
    `error`'s `ProviderError`, transient when a retry may get past it."""
    try:
        async with client.stream("POST", path, json=body, **kwargs) as response:
            if response.is_error:
                said = detail(await response.aread())
                raise error(f"HTTP {response.status_code}: {said}", transient=retryable(response.status_code))
            async for line in response.aiter_lines():
                yield line
    except httpx.TimeoutException as failure:
        raise error(f"timed out ({type(failure).__name__})", transient=True) from failure
    except httpx.HTTPError as failure:
        raise error(f"transport failure ({type(failure).__name__}: {failure})", transient=True) from failure


async def sse_payloads(lines: AsyncIterator[str], error: Failure) -> AsyncGenerator[dict[str, Any]]:
    """The JSON object of each `data:` field of a Server-Sent Events stream, as Anthropic and Gemini send them (one
    line each); other fields and comments are skipped. One that is not a JSON object is a transient failure."""
    async for line in lines:
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict):
            raise error(f"malformed stream event: {data[:MAX_DETAIL]}", transient=True)
        yield payload


def signature(secret: str, body: bytes) -> str:
    """`sha256=<hex HMAC-SHA256 of body>`, how GitHub, Meta and Nestor's webhook sign a body."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


HOME = "https://nestorhome.dev"
# public services ask clients to name themselves (Nominatim requires it)
USER_AGENT = f"nestor/{__version__} (+{HOME})"
ATTRIBUTION = {  # host → the headers it ranks and names the apps calling it by
    "openrouter.ai": {
        "HTTP-Referer": HOME,
        "X-OpenRouter-Title": "Nestor",
        "X-OpenRouter-Categories": "personal-agent",
    },
    "ai-gateway.vercel.sh": {"HTTP-Referer": HOME, "X-Title": "Nestor"},
}


def host_among(url: str, hosts: Iterable[str]) -> str | None:
    """Which of `hosts` `url` is on, itself or a subdomain of it."""
    host = urllib.parse.urlsplit(url).hostname or ""
    return next((known for known in hosts if host == known or host.endswith(f".{known}")), None)


def identity(base_url: str) -> dict[str, str]:
    """How Nestor names itself to the service at `base_url`: its versioned `User-Agent`, plus the attribution
    headers of the hosts that ask for them."""
    return {"User-Agent": USER_AGENT, **ATTRIBUTION.get(host_among(base_url, ATTRIBUTION) or "", {})}


class StatusError(ProviderError):
    """An API answered with an error: `status` is the HTTP status, `reason` the API's own code when it gives one. It
    is worth retrying when `retryable` says so, or when the API says more (`transient`: a refused token it will
    refresh)."""

    def __init__(
        self,
        provider: str,
        status: int,
        reason: str,
        message: str,
        *,
        transient: bool = False,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(
            provider,
            f"HTTP {status} {reason}".rstrip() + f": {message}",
            transient=transient or retryable(status),
            retry_after_s=retry_after_s,
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


class HttpApi:
    """An HTTP API: one client, opened on the first call and kept until `aclose` (or one the caller owns, shared by
    several accounts), so that a call does not pay a new connection. Every failure, the network's or the provider's,
    becomes a `ProviderError` labelled `provider`, with `secret` redacted; an error answer is a `StatusError` (see
    `failed`). A subclass adds what each call needs (`authorise`: an account's token)."""

    def __init__(
        self,
        provider: str,
        base_url: str = "",
        *,
        headers: Mapping[str, str] | None = None,
        secret: str | None = None,
        timeout_s: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._provider, self._base_url, self._secret = provider, base_url, secret
        self._headers, self._timeout_s, self._transport = headers or {}, timeout_s, transport
        self._client, self._owned = client, client is None

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None and self._owned:
            await client.aclose()

    async def authorise(self) -> Mapping[str, str]:
        """Headers each call carries, worked out when it is made (an access token refreshed meanwhile)."""
        return {}

    async def request(self, method: str, path: str, *, answers: Collection[int] = (), **kwargs: Any) -> httpx.Response:
        """`answers`: error statuses whose body is an answer, not a failure (a route that does not exist)."""
        async with self.stream(method, path, answers=answers, **kwargs) as response:
            await response.aread()
            return response

    async def download(self, path: str, *, max_bytes: int, **kwargs: Any) -> bytes:
        """A file, read until `max_bytes`: a larger one is refused (`ProviderError`, not transient)."""
        async with self.stream("GET", path, **kwargs) as response:
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise self.error(f"{path}: larger than {max_bytes // 1_000_000} MB", transient=False)
                chunks.append(chunk)
            return b"".join(chunks)

    @contextlib.asynccontextmanager
    async def stream(
        self, method: str, path: str, *, answers: Collection[int] = (), **kwargs: Any
    ) -> AsyncGenerator[httpx.Response]:
        """The answer, its body still to read; an error answer (not among `answers`) raises `failed`'s error."""
        headers = {**(await self.authorise()), **(kwargs.pop("headers", None) or {})}
        if not kwargs.get("params"):  # none given: a URL's own query (a next page's link) stays as it is
            kwargs.pop("params", None)
        try:
            async with self._opened().stream(method, path, headers=headers, **kwargs) as response:
                if response.is_error and response.status_code not in answers:
                    await response.aread()
                    raise self.failed(path, response)
                yield response
        except httpx.HTTPError as error:
            raise self.error(f"{path}: {type(error).__name__} {error}".strip(), transient=True) from None

    def failed(self, path: str, response: httpx.Response) -> ProviderError:
        """The error an error answer is: by default its status and the provider's own words."""
        message = self._redacted(f"{path}: {detail(response.content)}")
        waited = retry_after(response.headers.get("retry-after"))
        return StatusError(self._provider, response.status_code, "", message, retry_after_s=waited)

    def error(self, message: str, *, transient: bool) -> ProviderError:
        return ProviderError(self._provider, self._redacted(message), transient=transient)

    def _redacted(self, message: str) -> str:
        return message.replace(self._secret, "[redacted]") if self._secret else message

    def _opened(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = open_client(
                self._base_url, headers=self._headers, timeout=self._timeout_s, transport=self._transport
            )
        return self._client


def open_client(
    base_url: str = "",
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float | httpx.Timeout = 15.0,
    transport: httpx.AsyncBaseTransport | None = None,
    follow_redirects: bool = False,
) -> httpx.AsyncClient:
    """A client that names Nestor to the service at `base_url` (`identity`), for an `HttpApi` or for several (a
    connector's accounts)."""
    return httpx.AsyncClient(
        base_url=base_url,
        headers={**identity(base_url), **(headers or {})},
        timeout=timeout,
        transport=transport,
        follow_redirects=follow_redirects,
    )


class JsonApi(HttpApi):
    """An `HttpApi` that speaks JSON both ways; an answer that is not JSON is a `ProviderError` too."""

    def __init__(self, provider: str, base_url: str, *, headers: Mapping[str, str] | None = None, **kwargs: Any):
        super().__init__(provider, base_url, headers={"Accept": "application/json", **(headers or {})}, **kwargs)

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
