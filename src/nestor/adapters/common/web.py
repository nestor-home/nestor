"""Fetching from the public web on the household's behalf (a page the agent reads, a feed or a page watched): only
public addresses, so that nothing reaches the household's own network (the router, Home Assistant, a NAS), whatever
a search result, a message or a redirection asks. Each redirection is checked again and a body is capped while it
streams. A name that resolves to a public address when checked and a private one when fetched (DNS rebinding) is not
caught."""

import asyncio
import ipaddress
import socket
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from nestor.adapters.common.http import USER_AGENT, retryable
from nestor.adapters.common.text import Page, page_text
from nestor.adapters.documents.reader import HTML
from nestor.core import ProviderError
from nestor.modules.conversation import DocumentReader

REDIRECTS = 5
PAGES = "text/html,application/pdf,text/*;q=0.9,*/*;q=0.5"  # what a page read for people may be
FEEDS = "application/rss+xml, application/atom+xml, application/rdf+xml;q=0.9, application/xml;q=0.8, text/xml;q=0.8"


class WebError(ProviderError):
    """What kept an address from being read, worded for whoever asked (the model, a log): `reason`."""

    def __init__(self, reason: str, *, transient: bool) -> None:
        super().__init__("web", reason, transient=transient)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Fetched:
    url: str  # where it was found, after redirections
    status: int  # 200, or 304 for a conditional request that found nothing new
    headers: httpx.Headers
    body: bytes

    @property
    def content_type(self) -> str:
        """The type its server named, else HTML when it starts like markup."""
        return self.headers.get("content-type") or ("text/html" if self.body[:1024].lstrip()[:1] == b"<" else "")


class PublicWeb:
    """An HTTP client for public addresses only: one connection pool, opened on the first fetch, kept until
    `aclose`."""

    def __init__(self, *, accept: str, timeout_s: float = 15.0, max_bytes: int = 5_000_000) -> None:
        self._headers = {"User-Agent": USER_AGENT, "Accept": accept}
        self._timeout_s, self._max_bytes = timeout_s, max_bytes
        self._client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> Fetched:
        """The body at `url`, following redirections on the internet; a `WebError` for an address off it, an error
        status, a body over the cap or a network failure. `headers` (`If-None-Match`…) go with each request."""
        if self._client is None:
            self._client = httpx.AsyncClient(headers=self._headers, timeout=self._timeout_s, follow_redirects=False)
        for _ in range(REDIRECTS + 1):
            await public(url)
            try:
                async with self._client.stream("GET", url, headers=headers) as response:
                    if response.is_redirect and (location := response.headers.get("location")):
                        url = urllib.parse.urljoin(url, location)
                        continue
                    if response.is_error:
                        status = response.status_code
                        raise WebError(f"{url} answered HTTP {status}", transient=retryable(status))
                    return Fetched(url, response.status_code, response.headers, await self._body(response))
            except (httpx.HTTPError, httpx.InvalidURL) as error:
                raise WebError(f"{url} could not be read: {type(error).__name__}", transient=True) from None
        raise WebError(f"{url} redirects too many times", transient=False)

    async def _body(self, response: httpx.Response) -> bytes:
        chunks, size = [], 0
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size > self._max_bytes:
                raise WebError(f"{response.url} is larger than {self._max_bytes // 1_000_000} MB", transient=False)
        return b"".join(chunks)


async def readable(fetched: Fetched, reader: DocumentReader) -> Page:
    """What people read of a fetched body: a web page's title and content (menus and banners left out), a PDF's or a
    text file's text (no title). A `WebError` for what is not a document or has no text."""
    content_type = fetched.content_type
    if not reader.reads(content_type):
        raise WebError(
            f"{fetched.url} is {content_type or 'of an unknown type'}, not a page or a document to read",
            transient=False,
        )
    text = await reader.read(fetched.body, content_type)
    if not text:
        raise WebError(f"{fetched.url} has no text to read", transient=False)
    if content_type.split(";")[0].strip().lower() in HTML:
        return await asyncio.to_thread(page_text, text)
    return Page(title="", text=text)


async def public(url: str) -> None:
    """Refuse an address that is not on the public internet: another scheme, a private, loopback or link-local
    address, or a name that resolves to one."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:  # a port out of range, a malformed IPv6 address
        raise WebError(f"{url} is not a web address", transient=False) from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebError(f"{url} is not a web address", transient=False)
    try:
        found = await asyncio.get_running_loop().getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise WebError(f"{parts.hostname} could not be found", transient=True) from None
    addresses = {str(info[4][0]).split("%")[0] for info in found}  # an IPv6 address may carry its interface
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise WebError(
            f"{parts.hostname} is not a public address: only pages on the internet can be read", transient=False
        )
