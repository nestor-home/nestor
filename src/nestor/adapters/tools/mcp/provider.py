"""The tools of a remote MCP server, offered to the central agent as direct tools.

One session stays open per server, held by a background task: the SDK's transports are anyio
task groups, whose cancel scopes must be left by the task that entered them. Calls run from the
caller's task over that session. The SDK (mcp 2.3) negotiates the protocol era: `auto` probes
`server/discover` (2026-07-28) and falls back to the `initialize` handshake of older servers such as
Home Assistant's; `legacy` skips the probe.

Change notifications arrive differently per era: handshake-era servers push
`notifications/tools/list_changed` to the message handler; 2026-07-28 servers deliver them only on a
`subscriptions/listen` stream the client opens. Either way the tool list is fetched again.

A dropped session (transport error, closed stream, protocol error) is not retried in a loop: the
provider then lists no tools, and the next call — or the next look at `tools()`, at most every
`retry_after_s` — opens a new session. Tool results are passed on unchanged, only capped in size.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncGenerator, Callable, Coroutine, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from enum import StrEnum
from typing import Any, Literal

import anyio
import httpx2
from mcp import Client, MCPError
from mcp.client.session import MessageHandlerFnT
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.subscriptions import Subscription
from mcp.types import (
    CONNECTION_CLOSED,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    AudioContent,
    CallToolResult,
    ContentBlock,
    ImageContent,
    Implementation,
    ResourceLink,
    ServerNotification,
    TextContent,
    ToolAnnotations,
    ToolListChangedNotification,
)
from mcp.types import Tool as RemoteTool
from mcp.types.version import MODERN_PROTOCOL_VERSIONS

from nestor import __version__
from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider

logger = logging.getLogger(__name__)

type Negotiation = Literal["auto", "legacy"]
MAX_NAME_LENGTH = 64
SSE_READ_TIMEOUT_S = 300.0  # an idle event stream is dropped after this; the next call reconnects
_INVALID_NAME_CHARACTERS = re.compile(r"[^A-Za-z0-9_-]")
# What the SDK reports for a closed connection, an expired session (HTTP 404) or an HTTP error status;
# other protocol errors (invalid arguments, unknown tool) concern the call only.
_SESSION_ERRORS = frozenset({CONNECTION_CLOSED, INVALID_REQUEST, INTERNAL_ERROR})


class McpTransport(StrEnum):
    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"  # the transport of 2024-11-05 servers, still offered by older Home Assistant versions


class BearerToken(httpx2.Auth):
    """A fixed bearer token, such as a Home Assistant long-lived access token.

    Credentials are an `httpx2.Auth`, so an OAuth 2.1 provider (the SDK's `OAuthClientProvider`)
    plugs in the same place. The token never appears in a repr or a log.
    """

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx2.Request) -> Any:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request

    def __repr__(self) -> str:
        return "BearerToken(<hidden>)"


class _Unreachable(Exception):
    """The session could not be opened; `transient` says whether trying again may help."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


class _HttpErrors:
    """Remembers the last HTTP error status: the SDK reports a 401 as a bare internal error."""

    def __init__(self) -> None:
        self.status: int | None = None

    async def __call__(self, response: httpx2.Response) -> None:
        if response.is_error:
            self.status = response.status_code


class _Session:
    """One open MCP session and the tools it lists; `closing` ends it."""

    def __init__(
        self,
        client: Callable[[MessageHandlerFnT], Client],
        hold: Callable[["_Session"], Coroutine[Any, Any, None]],
        name: str,
    ) -> None:
        self.client = client(self.on_message)
        self.tools: tuple[Tool, ...] = ()
        self.changed = asyncio.Event()
        self.closing = asyncio.Event()
        self.task = asyncio.create_task(hold(self), name=name)

    @property
    def alive(self) -> bool:
        return not self.task.done() and not self.closing.is_set()

    async def on_message(self, message: ServerNotification | Exception) -> None:
        if isinstance(message, Exception):  # the transport broke: this session is over
            self.closing.set()
        elif isinstance(message, ToolListChangedNotification):
            self.changed.set()

    async def close(self) -> None:
        self.closing.set()
        await self.task

    async def abort(self) -> None:
        """Stops a session still opening: it may be stuck waiting for a server that never answers."""
        self.task.cancel()
        await asyncio.wait([self.task])


class McpToolProvider(ToolProvider):
    """Offers the tools of one MCP server; tool names are the server's, made valid and unique.

    `include` and `exclude` select tools by their name on the server; `risks` overrides the risk
    derived from the tool's annotations (read-only → read, destructive → sensitive, else write).
    Annotations are hints from the server: set `risks` for anything that matters.
    """

    def __init__(
        self,
        url: str,
        *,
        name: str = "mcp",
        transport: McpTransport = McpTransport.STREAMABLE_HTTP,
        auth: httpx2.Auth | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 10.0,
        include: Sequence[str] | None = None,
        exclude: Sequence[str] = (),
        risks: Mapping[str, Risk] | None = None,
        max_result_chars: int = 16_000,
        retry_after_s: float = 30.0,
        negotiation: Negotiation = "auto",
    ) -> None:
        self.name = name
        self._url, self._transport, self._auth = url, transport, auth
        self._headers = dict(headers or {})
        self._timeout_s, self._max_result_chars, self._retry_after_s = timeout_s, max_result_chars, retry_after_s
        self._include = None if include is None else frozenset(include)
        self._exclude = frozenset(exclude)
        self._risks = dict(risks or {})
        self._negotiation: Negotiation = negotiation
        self._session: _Session | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._next_retry = 0.0
        self._retry: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Opens the session now. Refused credentials fail loudly; a server that is down or failing
        only leaves its tools missing — the home may reboot with Nestor — until it answers again."""
        self._closed = False
        try:
            await self._open()
        except _Unreachable as error:
            if not error.transient:
                raise ProviderError(self.name, str(error), transient=False) from None
            logger.warning("%s: MCP server unavailable, its tools are missing until it answers (%s)", self.name, error)

    def tools(self) -> Sequence[Tool]:
        session = self._session
        if session is not None and session.alive:
            return session.tools
        self._reconnect_soon()
        return ()

    async def close(self) -> None:
        self._closed = True
        if self._retry is not None:
            self._retry.cancel()
        async with self._lock:
            session, self._session = self._session, None
            if session is not None:
                await session.close()

    # --- session --------------------------------------------------------------------------------

    async def _open(self) -> _Session:
        """The live session, opening a new one if there is none."""
        async with self._lock:
            if self._closed:
                raise _Unreachable("the provider is closed", transient=False)
            session = self._session
            if session is not None and session.alive:
                return session
            self._session = None
            if session is not None:
                await session.close()
            self._session = await self._connect()
            return self._session

    async def _connect(self) -> _Session:
        errors = _HttpErrors()
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        session = _Session(
            lambda handler: Client(
                self._transport_streams(errors),
                mode=self._negotiation,
                message_handler=handler,
                read_timeout_seconds=self._timeout_s,
                client_info=Implementation(name="nestor", version=__version__),
                cache=None,  # the provider keeps its own list, refreshed on change notifications
            ),
            lambda session: self._hold(session, ready),
            f"mcp:{self.name}",
        )
        try:
            async with asyncio.timeout(self._timeout_s):
                await ready
        except TimeoutError:
            await session.abort()
            raise _Unreachable(f"no answer within {self._timeout_s:g} s", transient=True) from None
        except Exception as error:
            await session.close()
            raise _refusal(error, errors.status) from None
        return session

    async def _hold(self, session: _Session, ready: asyncio.Future[None]) -> None:
        """Runs in its own task for the whole life of the session."""
        try:
            async with session.client as client, AsyncExitStack() as stack:
                # Listen before listing: a change between the two would otherwise be missed.
                changes = None
                if _pushes_changes_on_listen(client):
                    changes = await stack.enter_async_context(client.listen(tools_list_changed=True))
                session.tools = self._convert(await _list_tools(client))
                ready.set_result(None)
                async with anyio.create_task_group() as group:
                    group.start_soon(self._refresh, session)
                    if changes is not None:
                        group.start_soon(_follow, changes, session)
                    await session.closing.wait()
                    group.cancel_scope.cancel()
        except Exception as error:
            if ready.done():
                logger.warning("%s: MCP session lost (%s)", self.name, _reason(error))
            else:
                ready.set_exception(error)
        finally:
            session.closing.set()

    async def _refresh(self, session: _Session) -> None:
        while True:
            await session.changed.wait()
            session.changed.clear()
            session.tools = self._convert(await _list_tools(session.client))
            logger.info("%s: tool list changed, %d tools", self.name, len(session.tools))

    def _reconnect_soon(self) -> None:
        """Schedules one attempt to reopen the session, at most every `retry_after_s`."""
        if self._closed or time.monotonic() < self._next_retry:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # looked at outside the event loop: nothing to schedule on
            return
        self._next_retry = time.monotonic() + self._retry_after_s
        self._retry = loop.create_task(self._try_open(), name=f"mcp:{self.name}:reconnect")

    async def _try_open(self) -> None:
        try:
            await self._open()
        except _Unreachable as error:
            logger.info("%s: still unavailable (%s)", self.name, error)

    def _transport_streams(self, errors: _HttpErrors) -> Any:
        hooks: dict[str, list[Callable[..., Any]]] = {"response": [errors]}
        timeout = httpx2.Timeout(self._timeout_s, read=SSE_READ_TIMEOUT_S)
        if self._transport is McpTransport.SSE:

            def factory(
                headers: dict[str, str] | None = None,
                timeout: httpx2.Timeout | None = None,
                auth: httpx2.Auth | None = None,
            ) -> httpx2.AsyncClient:
                return httpx2.AsyncClient(headers=headers, timeout=timeout, auth=auth, event_hooks=hooks)

            return sse_client(
                self._url,
                headers=dict(self._headers),
                timeout=self._timeout_s,
                sse_read_timeout=SSE_READ_TIMEOUT_S,
                auth=self._auth,
                httpx_client_factory=factory,
            )
        http = httpx2.AsyncClient(headers=self._headers, auth=self._auth, timeout=timeout, event_hooks=hooks)
        return _streamable_http(self._url, http)

    # --- tools ----------------------------------------------------------------------------------

    def _convert(self, listed: Sequence[RemoteTool]) -> tuple[Tool, ...]:
        taken: set[str] = set()
        tools: list[Tool] = []
        for remote in listed:
            if (self._include is not None and remote.name not in self._include) or remote.name in self._exclude:
                continue
            name = _unique(_INVALID_NAME_CHARACTERS.sub("_", remote.name)[:MAX_NAME_LENGTH] or "tool", taken)
            taken.add(name)
            spec = ToolSpec(name, remote.description or remote.title or remote.name, dict(remote.input_schema))
            tools.append(
                Tool(spec=spec, run=self._runner(remote.name), risk=self._risk(remote), timeout_s=self._timeout_s)
            )
        return tuple(tools)

    def _risk(self, remote: RemoteTool) -> Risk:
        if remote.name in self._risks:
            return self._risks[remote.name]
        hints = remote.annotations or ToolAnnotations()
        if hints.read_only_hint:
            return Risk.READ
        return Risk.SENSITIVE if hints.destructive_hint else Risk.WRITE

    def _runner(self, remote_name: str) -> Callable[[Mapping[str, object], ToolContext], Any]:
        async def run(arguments: Mapping[str, object], context: ToolContext) -> str:
            return await self._call(remote_name, arguments)

        return run

    async def _call(self, remote_name: str, arguments: Mapping[str, object]) -> str:
        try:
            session = await self._open()
        except _Unreachable as error:
            raise ToolFailed(f"{self.name}: {error}") from None
        try:
            result = await session.client.call_tool(remote_name, dict(arguments))
        except MCPError as error:
            if error.code in _SESSION_ERRORS:  # the session is in doubt: the next call opens another
                session.closing.set()
            if error.code == CONNECTION_CLOSED:
                raise ToolFailed(f"{self.name} is unreachable (connection closed)") from None
            raise ToolFailed(f"{self.name}: {remote_name} failed: {error.message}") from None
        except Exception as error:  # the SDK rejects a reply that breaks the tool's output schema
            session.closing.set()
            raise ToolFailed(f"{self.name}: {remote_name} failed ({_reason(error)})") from None
        output = _cap(_render(result), self._max_result_chars)
        if result.is_error:
            raise ToolFailed(output or f"{remote_name} failed without saying why")
        return output


@asynccontextmanager
async def _streamable_http(url: str, http: httpx2.AsyncClient) -> AsyncGenerator[Any]:
    """The SDK leaves a client it was given open; this closes it with the transport."""
    async with http, streamable_http_client(url, http_client=http) as streams:
        yield streams


async def _list_tools(client: Client) -> list[RemoteTool]:
    """Every page of the listing; none for a server without the tools capability (prompts only…)."""
    tools: list[RemoteTool] = []
    if client.server_capabilities.tools is None:
        return tools
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        cursor = page.next_cursor
        if cursor is None:
            return tools


def _pushes_changes_on_listen(client: Client) -> bool:
    """2026-07-28 servers announce tool changes only on a `subscriptions/listen` stream."""
    tools = client.server_capabilities.tools
    return client.protocol_version in MODERN_PROTOCOL_VERSIONS and tools is not None and bool(tools.list_changed)


async def _follow(changes: Subscription, session: _Session) -> None:
    async for _event in changes:
        session.changed.set()


def _unique(name: str, taken: set[str]) -> str:
    candidate, count = name, 1
    while candidate in taken:
        count += 1
        suffix = f"_{count}"
        candidate = name[: MAX_NAME_LENGTH - len(suffix)] + suffix
    return candidate


def _render(result: CallToolResult) -> str:
    """Text parts as they are; structured content as JSON when no text carries it; media as a note."""
    parts = [_describe(block) for block in result.content]
    has_text = any(isinstance(block, TextContent) for block in result.content)
    if result.structured_content is not None and not has_text:
        parts.append(json.dumps(result.structured_content, ensure_ascii=False))
    return "\n".join(parts)


def _describe(block: ContentBlock) -> str:
    if isinstance(block, TextContent):
        return block.text
    if isinstance(block, ImageContent | AudioContent):
        return f"[{block.type} ({block.mime_type}) not shown]"
    if isinstance(block, ResourceLink):
        return f"[resource link: {block.uri}]"
    return f"[resource: {block.resource.uri}]"


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n[truncated: {len(text) - limit} more characters]"


def _refusal(error: Exception, status: int | None) -> _Unreachable:
    if status in (401, 403):
        return _Unreachable(f"the server refused the credentials (HTTP {status})", transient=False)
    if status is not None:
        return _Unreachable(f"the server answered HTTP {status}", transient=status == 429 or status >= 500)
    return _Unreachable(f"unreachable ({_reason(error)})", transient=True)


def _reason(error: BaseException) -> str:
    """The innermost cause of a failure: anyio wraps transport errors in exception groups."""
    while isinstance(error, BaseExceptionGroup):
        error = error.exceptions[0]
    return f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
