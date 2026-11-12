"""Reading a web page for the agent (`read_page`): its title and the text of its content, a PDF's text, a text file
as it is. Only public addresses: a page never reaches the household's own network (the router, Home Assistant, a
NAS), whatever a search result or a message asks. Each redirection is checked again. A name that resolves to a
public address when checked and a private one when fetched (DNS rebinding) is not caught."""

import asyncio
import ipaddress
import socket
import urllib.parse
from collections.abc import Mapping, Sequence

import httpx
from pydantic import Field, PositiveFloat, PositiveInt

from nestor.adapters.common.http import USER_AGENT
from nestor.adapters.common.text import page_text
from nestor.adapters.documents import FileReader
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolOutput, ToolProvider
from nestor.modules.conversation import DocumentReader
from nestor.modules.web import UNTRUSTED
from nestor.runtime import Family, Plugin, Services
from nestor.runtime.plugins import AdapterSettings

REDIRECTS = 5
HTML = frozenset({"text/html", "application/xhtml+xml"})

READ = ToolSpec(
    "read_page",
    "Read a public web page by its address: its title and the text of its content (menus and banners left out), or "
    f"the text of a PDF. Long pages come back in parts, readable with read_result. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "the page's full address, https://…"}},
        "required": ["url"],
    },
)


class WebPages(ToolProvider):
    def __init__(self, reader: DocumentReader, *, timeout_s: float = 15.0, max_bytes: int = 5_000_000) -> None:
        self._reader, self._timeout_s, self._max_bytes = reader, timeout_s, max_bytes
        self._client: httpx.AsyncClient | None = None

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=READ, run=self.read, risk=Risk.READ, timeout_s=self._timeout_s + 5.0),)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def read(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ToolFailed("give the page's address")
        if "://" not in url:
            url = f"https://{url}"
        if self._client is None:
            headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/*;q=0.9,*/*;q=0.5"}
            self._client = httpx.AsyncClient(headers=headers, timeout=self._timeout_s, follow_redirects=False)
        for _ in range(REDIRECTS + 1):
            await _public(url)
            try:
                async with self._client.stream("GET", url) as response:
                    if response.is_redirect and (location := response.headers.get("location")):
                        url = urllib.parse.urljoin(url, location)
                        continue
                    if response.is_error:
                        raise ToolFailed(f"{url} answered HTTP {response.status_code}")
                    body = await self._body(response)
                    content_type = response.headers.get("content-type") or (
                        "text/html" if body[:1024].lstrip()[:1] == b"<" else ""
                    )
                return await self._content(url, content_type, body)
            except httpx.HTTPError as error:
                raise ToolFailed(f"{url} could not be read: {type(error).__name__}") from None
        raise ToolFailed(f"{url} redirects too many times")

    async def _content(self, url: str, content_type: str, body: bytes) -> ToolOutput:
        if not self._reader.reads(content_type):
            raise ToolFailed(f"{url} is {content_type or 'of an unknown type'}, not a page or a document to read")
        text = await self._reader.read(body, content_type)
        if not text:
            raise ToolFailed(f"{url} has no text to read")
        if content_type.split(";")[0].strip().lower() in HTML:
            page = await asyncio.to_thread(page_text, text)
            return {"url": url, "title": page.title, "text": page.text, "note": UNTRUSTED}
        return {"url": url, "text": text, "note": UNTRUSTED}

    async def _body(self, response: httpx.Response) -> bytes:
        chunks, size = [], 0
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size > self._max_bytes:
                raise ToolFailed(f"{response.url} is larger than {self._max_bytes // 1_000_000} MB")
        return b"".join(chunks)


def _sniffed(body: bytes) -> str:
    """The type of a body its server did not name: HTML when it starts like markup."""
    return "text/html" if body[:1024].lstrip()[:1] == b"<" else ""


async def _public(url: str) -> None:
    """Refuse an address that is not on the public internet: another scheme, a private, loopback or link-local
    address, or a name that resolves to one."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ToolFailed(f"{url} is not a web address")
    try:
        found = await asyncio.get_running_loop().getaddrinfo(parts.hostname, parts.port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise ToolFailed(f"{parts.hostname} could not be found") from None
    addresses = {str(info[4][0]).split("%")[0] for info in found}  # an IPv6 address may carry its interface
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise ToolFailed(f"{parts.hostname} is not a public address: only pages on the internet can be read")


class WebPagesSettings(AdapterSettings):
    timeout_s: PositiveFloat = 15.0
    max_bytes: PositiveInt = Field(default=5_000_000, json_schema_extra={"advanced": True})


def build(settings: WebPagesSettings, name: str, services: Services) -> WebPages:
    pages = WebPages(FileReader(), timeout_s=settings.timeout_s, max_bytes=settings.max_bytes)
    pages.name = name
    return pages


plugin = Plugin(Family.TOOLS, "web-pages", WebPagesSettings, build)
