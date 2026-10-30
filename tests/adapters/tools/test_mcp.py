"""MCP tool provider: against real MCP servers built with the SDK and served over HTTP on
127.0.0.1, in both protocol eras (`auto` negotiates 2026-07-28 with them, `legacy` uses the
initialize handshake Home Assistant speaks)."""

import asyncio
import json
import logging
import os
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, ClassVar

import pytest
import uvicorn
from mcp import MCPError
from mcp.server import Server
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    AudioContent,
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    ListToolsResult,
    ResourceLink,
    TextContent,
    ToolAnnotations,
)
from mcp.types import Tool as RemoteTool
from pydantic import SecretStr

from nestor.adapters.tools.mcp import BearerToken, McpSettings, McpToolProvider, McpTransport
from nestor.adapters.tools.mcp.plugin import plugin
from nestor.core import Health, ProviderError
from nestor.core.i18n import Locale
from nestor.modules.channels import Address
from nestor.modules.cognition.model import ToolCall
from nestor.modules.cognition.tools import Risk, Tool, Toolbox, ToolCalled, ToolCompleted, ToolContext, ToolFailed
from nestor.modules.journal import Journal
from nestor.runtime import Family, Services
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryEventLog

type LogCapture = pytest.LogCaptureFixture

TOKEN = "long-lived-token"
CONTEXT = ToolContext(address=Address("voice", "living-room"))
ERAS = pytest.mark.parametrize("negotiation", ["auto", "legacy"])

type Asgi = Callable[[dict[str, Any], Any, Any], Awaitable[None]]


def home_server() -> MCPServer:
    """A small home: tools shaped like Home Assistant's Assist API tools."""
    server = MCPServer("home")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def get_live_context() -> str:
        """The state of every exposed entity."""
        return "kitchen light: on"

    @server.tool()
    def turn_on(name: str) -> str:
        """Turns a device on."""
        return f"{name} is on"

    @server.tool(annotations=ToolAnnotations(destructive_hint=True))
    def unlock(door: str) -> str:
        """Unlocks a door."""
        return f"{door} unlocked"

    @server.tool()
    def offline() -> str:
        """Always fails, like a device that does not answer."""
        raise ToolError("the device is offline")

    @server.tool()
    def silent_failure() -> CallToolResult:
        return CallToolResult(content=[], is_error=True)

    @server.tool()
    def dump(size: int) -> str:
        return "x" * size

    @server.tool()
    def snapshot() -> CallToolResult:
        return CallToolResult(
            content=[
                TextContent(text="camera: front door"),
                ImageContent(data="aGk=", mime_type="image/png"),
                AudioContent(data="aGk=", mime_type="audio/wav"),
                ResourceLink(name="clip", uri="file:///clip.mp4"),
                EmbeddedResource(resource=BlobResourceContents(uri="file:///raw.bin", blob="aGk=")),
            ]
        )

    @server.tool()
    def energy() -> CallToolResult:
        return CallToolResult(content=[], structured_content={"kwh": 12.5, "unit": "kWh"})

    @server.tool()
    async def slow() -> str:
        await asyncio.sleep(30)
        return "finally"

    @server.tool()
    async def chatty(ctx: Context) -> str:
        await ctx.session.send_resource_list_changed()  # a notification this provider has no use for
        return "done"

    @server.tool()
    async def add_scene(ctx: Context) -> str:
        """Adds a tool and announces it, in both eras' ways."""
        server.add_tool(lambda: "movie mode on", name="movie_mode", description="Starts movie mode.")
        await ctx.session.send_tool_list_changed()  # handshake era: pushed on the session
        await ctx.notify_tools_changed()  # 2026-07-28: delivered on subscriptions/listen streams
        return "scene added"

    return server


class ToughServer:
    """Lists one tool per page, with awkward names, and answers no call properly: `/` fails as if
    the session had expired, `report` breaks its own output schema, the others refuse their arguments."""

    names = ("light.turn on", "light_turn_on", "a" * 80, "/", "report")
    report_schema: ClassVar = {"type": "object", "properties": {"kwh": {"type": "number"}}, "required": ["kwh"]}

    def __init__(self) -> None:
        self.listings = 0  # complete listings started, one per session and per change

    def app(self) -> Asgi:
        return bearer(Server("paged", on_list_tools=self._list, on_call_tool=self._call).streamable_http_app())

    async def _list(self, ctx: Any, params: Any) -> ListToolsResult:
        index = int(params.cursor) if params is not None and params.cursor else 0
        self.listings += index == 0
        name = self.names[index]
        schema = self.report_schema if name == "report" else None
        tool = RemoteTool(name=name, input_schema={"type": "object"}, output_schema=schema)
        return ListToolsResult(tools=[tool], next_cursor=str(index + 1) if index + 1 < len(self.names) else None)

    async def _call(self, ctx: Any, params: Any) -> CallToolResult:
        if params.name == "/":
            raise MCPError(INVALID_REQUEST, "session expired")
        if params.name == "report":
            return CallToolResult(content=[], structured_content={"kwh": "lots"})
        raise MCPError(INVALID_PARAMS, f"invalid arguments for {params.name}")


@pytest.fixture
async def tough() -> AsyncIterator[tuple[ToughServer, McpToolProvider]]:
    server = ToughServer()
    served = Served(server.app)
    await served.start()
    async with provider_for(served) as provider:
        yield server, provider
    await served.stop()


def bearer(app: Asgi, token: str = TOKEN) -> Asgi:
    """Refuses requests without the token, like Home Assistant's HTTP layer."""

    async def guarded(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and dict(scope["headers"]).get(b"authorization") != f"Bearer {token}".encode():
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"401: Unauthorized"})
            return
        await app(scope, receive, send)

    return guarded


def failing(status: int) -> Asgi:
    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": status, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    return app


class Served:
    """An ASGI app served over real HTTP on 127.0.0.1; stopping and starting again keeps the port.
    `app` builds a fresh application each time: an MCP session manager only runs once."""

    def __init__(self, app: Callable[[], Asgi]) -> None:
        self._app = app
        self.port = 0
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    def url(self, path: str = "/mcp") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    async def start(self) -> None:
        config = uvicorn.Config(
            self._app(), host="127.0.0.1", port=self.port, log_level="warning", timeout_graceful_shutdown=1
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            await asyncio.sleep(0.01)
        self.port = self._server.servers[0].sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None and self._task is not None:
            self._server.should_exit = True
            await self._task
            self._server = self._task = None


@pytest.fixture
async def served_home() -> AsyncIterator[Served]:
    served = Served(lambda: bearer(home_server().streamable_http_app()))
    await served.start()
    yield served
    await served.stop()


def provider_for(served: Served, **options: Any) -> McpToolProvider:
    options.setdefault("auth", BearerToken(TOKEN))
    options.setdefault("timeout_s", 5.0)
    return McpToolProvider(served.url(), name="home", **options)


@pytest.fixture
async def home(served_home: Served) -> AsyncIterator[McpToolProvider]:
    async with provider_for(served_home, negotiation="legacy") as provider:
        yield provider


def tool(provider: McpToolProvider, name: str) -> Tool:
    return next(t for t in provider.tools() if t.name == name)


async def call(provider: McpToolProvider, tool_name: str, /, **arguments: object) -> str:
    output = await tool(provider, tool_name).run(arguments, CONTEXT)
    assert isinstance(output, str)
    return output


async def eventually(condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.02)


# --- discovery -------------------------------------------------------------------------------


@ERAS
async def test_tools_are_discovered_with_their_description_and_parameters(
    served_home: Served, negotiation: str
) -> None:
    async with provider_for(served_home, negotiation=negotiation) as provider:
        turn_on = tool(provider, "turn_on")

    assert turn_on.spec.description == "Turns a device on."
    assert turn_on.spec.parameters["type"] == "object"
    assert turn_on.spec.parameters["required"] == ["name"]
    assert turn_on.spec.parameters["properties"] == {"name": {"title": "Name", "type": "string"}}


async def test_risk_follows_the_annotations_unless_overridden(served_home: Served) -> None:
    async with provider_for(served_home, risks={"turn_on": Risk.SENSITIVE}) as provider:
        risks = {t.name: t.risk for t in provider.tools()}

    assert risks["get_live_context"] is Risk.READ
    assert risks["unlock"] is Risk.SENSITIVE  # destructive
    assert risks["dump"] is Risk.WRITE  # no annotation: it may change something
    assert risks["turn_on"] is Risk.SENSITIVE  # overridden


async def test_only_included_tools_minus_excluded_ones_are_offered(served_home: Served) -> None:
    async with provider_for(served_home, include=["turn_on", "unlock", "dump"], exclude=["unlock"]) as provider:
        assert {t.name for t in provider.tools()} == {"turn_on", "dump"}


async def test_every_page_is_listed_and_names_are_made_valid_and_unique(
    tough: tuple[ToughServer, McpToolProvider],
) -> None:
    _, provider = tough

    assert [t.name for t in provider.tools()] == ["light_turn_on", "light_turn_on_2", "a" * 64, "_", "report"]
    assert provider.tools()[0].spec.description == "light.turn on"  # none given: its own name says what it is


# --- calls -----------------------------------------------------------------------------------


@ERAS
async def test_a_call_returns_the_text_of_the_result(served_home: Served, negotiation: str) -> None:
    async with provider_for(served_home, negotiation=negotiation) as provider:
        assert await call(provider, "turn_on", name="kitchen light") == "kitchen light is on"


async def test_a_tool_error_reaches_the_model_with_the_server_message(home: McpToolProvider) -> None:
    with pytest.raises(ToolFailed, match="the device is offline"):
        await call(home, "offline")


async def test_a_tool_error_without_a_message_still_says_which_tool_failed(home: McpToolProvider) -> None:
    with pytest.raises(ToolFailed, match="silent_failure failed"):
        await call(home, "silent_failure")


async def test_a_refused_call_is_reported_and_the_session_kept(tough: tuple[ToughServer, McpToolProvider]) -> None:
    server, provider = tough

    for _ in range(2):
        with pytest.raises(ToolFailed, match="light_turn_on failed: invalid arguments for light_turn_on"):
            await call(provider, "light_turn_on_2")

    assert server.listings == 1


async def test_after_a_session_error_the_next_call_opens_a_new_session(
    tough: tuple[ToughServer, McpToolProvider],
) -> None:
    server, provider = tough
    expired = tool(provider, "_")

    for _ in range(2):
        with pytest.raises(ToolFailed, match="/ failed"):
            await expired.run({}, CONTEXT)

    assert server.listings == 2


async def test_a_reply_breaking_the_output_schema_is_refused(tough: tuple[ToughServer, McpToolProvider]) -> None:
    _, provider = tough

    with pytest.raises(ToolFailed, match=r"report failed .*Invalid structured content"):
        await call(provider, "report")


async def test_media_and_resources_are_summarised_not_inlined(home: McpToolProvider) -> None:
    assert await call(home, "snapshot") == "\n".join(
        [
            "camera: front door",
            "[image (image/png) not shown]",
            "[audio (audio/wav) not shown]",
            "[resource link: file:///clip.mp4]",
            "[resource: file:///raw.bin]",
        ]
    )


async def test_structured_content_without_text_is_given_as_json(home: McpToolProvider) -> None:
    assert json.loads(await call(home, "energy")) == {"kwh": 12.5, "unit": "kWh"}


async def test_an_oversized_result_is_cut_with_a_marker(served_home: Served) -> None:
    async with provider_for(served_home, max_result_chars=100) as provider:
        output = await call(provider, "dump", size=250)

    assert output == "x" * 100 + "\n[truncated: 150 more characters]"


async def test_a_result_within_the_limit_is_unchanged(home: McpToolProvider) -> None:
    assert await call(home, "dump", size=16_000) == "x" * 16_000


@ERAS
async def test_a_changed_tool_list_is_fetched_again(served_home: Served, negotiation: str) -> None:
    async with provider_for(served_home, negotiation=negotiation) as provider:
        assert "movie_mode" not in {t.name for t in provider.tools()}
        await call(provider, "add_scene")

        await eventually(lambda: "movie_mode" in {t.name for t in provider.tools()})
        assert await call(provider, "movie_mode") == "movie mode on"


async def test_a_cancelled_call_leaves_the_session_usable(home: McpToolProvider) -> None:
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.3):
            await call(home, "slow")

    assert await call(home, "turn_on", name="hall") == "hall is on"


async def test_a_server_without_tools_offers_none() -> None:
    served = Served(lambda: bearer(Server("prompts-only").streamable_http_app()))
    await served.start()
    try:
        async with provider_for(served) as provider:
            assert provider.tools() == ()
    finally:
        await served.stop()


async def test_other_server_notifications_leave_the_session_as_it_is(home: McpToolProvider) -> None:
    before = home.tools()

    assert await call(home, "chatty") == "done"
    assert home.tools() == before


async def test_the_sse_transport_of_older_servers_works_too() -> None:
    served = Served(lambda: bearer(home_server().sse_app()))
    await served.start()
    try:
        provider = McpToolProvider(
            served.url("/sse"), name="home", transport=McpTransport.SSE, auth=BearerToken(TOKEN), timeout_s=5.0
        )
        async with provider:
            assert await call(provider, "turn_on", name="hall") == "hall is on"
    finally:
        await served.stop()


async def test_static_headers_are_sent_on_every_request(served_home: Served) -> None:
    async with provider_for(served_home, auth=None, headers={"Authorization": f"Bearer {TOKEN}"}) as provider:
        assert await call(provider, "turn_on", name="hall") == "hall is on"


# --- failures --------------------------------------------------------------------------------


async def test_a_wrong_token_fails_start_without_retry_hope_or_leaking_it(served_home: Served) -> None:
    provider = provider_for(served_home, auth=BearerToken("stolen-secret"))

    with pytest.raises(ProviderError, match=r"refused the credentials \(HTTP 401\)") as raised:
        await provider.start()

    assert not raised.value.transient
    assert "stolen-secret" not in str(raised.value) and "stolen-secret" not in repr(BearerToken("stolen-secret"))
    assert provider.tools() == ()
    await provider.close()


async def test_the_token_never_reaches_the_logs(served_home: Served, caplog: LogCapture) -> None:
    with caplog.at_level(logging.DEBUG):
        async with provider_for(served_home) as provider:
            await call(provider, "turn_on", name="hall")

    assert caplog.text and TOKEN not in caplog.text


async def test_a_failing_server_at_start_leaves_its_tools_missing_without_failing(caplog: LogCapture) -> None:
    served = Served(lambda: failing(503))
    await served.start()
    try:
        async with provider_for(served) as provider:
            assert provider.tools() == ()
    finally:
        await served.stop()

    assert "answered HTTP 503" in caplog.text


async def test_a_server_that_never_answers_times_out_at_start(caplog: LogCapture) -> None:
    async def mute(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read()  # holds the connection, answers nothing
        writer.close()

    listener = await asyncio.start_server(mute, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with McpToolProvider(f"http://127.0.0.1:{port}/mcp", timeout_s=0.3, retry_after_s=60) as provider:
            assert provider.tools() == ()
    finally:
        listener.close()

    assert "no answer within 0.3 s" in caplog.text


async def test_an_unreachable_server_at_start_leaves_its_tools_missing(caplog: LogCapture) -> None:
    async with McpToolProvider(f"http://127.0.0.1:{free_port()}/mcp", name="home", retry_after_s=60) as provider:
        assert provider.tools() == ()
        assert provider.health() is Health.UNAVAILABLE and provider.brand == "mcp"

    assert "home: MCP server unavailable" in caplog.text and "unreachable" in caplog.text


async def test_a_dropped_server_empties_the_list_and_calls_fail_clearly(served_home: Served) -> None:
    async with provider_for(served_home, retry_after_s=60) as provider:
        turn_on = tool(provider, "turn_on")
        assert provider.health() is Health.STARTED
        await served_home.stop()

        with pytest.raises(ToolFailed, match="home is unreachable"):
            await turn_on.run({"name": "hall"}, CONTEXT)
        assert provider.tools() == ()

        with pytest.raises(ToolFailed, match="home: unreachable"):  # the next call tries again
            await turn_on.run({"name": "hall"}, CONTEXT)


async def test_a_call_reconnects_once_the_server_is_back(served_home: Served) -> None:
    async with provider_for(served_home, retry_after_s=60) as provider:
        turn_on = tool(provider, "turn_on")
        await served_home.stop()
        with pytest.raises(ToolFailed):
            await turn_on.run({"name": "hall"}, CONTEXT)

        await served_home.start()
        assert await turn_on.run({"name": "hall"}, CONTEXT) == "hall is on"
        assert provider.tools()


async def test_the_tools_come_back_on_their_own_once_the_server_is_back() -> None:
    served = Served(lambda: bearer(home_server().streamable_http_app()))
    served.port = free_port()
    provider = provider_for(served, retry_after_s=0.05)
    await provider.start()
    try:
        assert provider.tools() == ()  # and a reconnection attempt, which fails: nothing listens yet
        await asyncio.sleep(0.2)
        await served.start()
        await eventually(lambda: bool(provider.tools()))
    finally:
        await provider.close()
        await served.stop()


async def test_a_lost_sse_stream_ends_the_session() -> None:
    served = Served(lambda: bearer(home_server().sse_app()))
    await served.start()
    provider = McpToolProvider(
        served.url("/sse"), name="home", transport=McpTransport.SSE, auth=BearerToken(TOKEN), retry_after_s=60
    )
    async with provider:
        assert provider.tools()
        await served.stop()
        await eventually(lambda: provider.tools() == ())


async def test_a_closed_provider_refuses_calls(home: McpToolProvider) -> None:
    turn_on = tool(home, "turn_on")
    await home.close()

    with pytest.raises(ToolFailed, match="closed"):
        await turn_on.run({"name": "hall"}, CONTEXT)
    assert home.tools() == ()


def test_looking_at_the_tools_outside_the_event_loop_lists_none() -> None:
    assert McpToolProvider("http://127.0.0.1:9/mcp").tools() == ()


# --- with the toolbox and the runtime --------------------------------------------------------


async def test_a_call_through_the_toolbox_is_logged(home: McpToolProvider) -> None:
    journal = Journal(MemoryEventLog())
    toolbox = Toolbox(journal, providers=[home])

    output = await toolbox.call(ToolCall("c1", "turn_on", {"name": "kitchen light"}), CONTEXT)

    assert output == "kitchen light is on"
    assert "turn_on" in {spec.name for spec in toolbox.specs()}
    [called] = await journal.history(ToolCalled)
    [completed] = await journal.history(ToolCompleted)
    assert (called.name, dict(called.arguments)) == ("turn_on", {"name": "kitchen light"})
    assert (completed.ok, completed.output) == (True, "kitchen light is on")


async def test_a_failed_call_through_the_toolbox_is_logged_as_failed(home: McpToolProvider) -> None:
    journal = Journal(MemoryEventLog())

    output = await Toolbox(journal, providers=[home]).call(ToolCall("c1", "offline", {}), CONTEXT)

    assert "the device is offline" in json.loads(output)["error"]
    [completed] = await journal.history(ToolCompleted)
    assert not completed.ok and completed.output == output


def test_settings_keep_header_values_secret() -> None:
    settings = McpSettings(url="http://ha.local/api/mcp", headers={"X-Api-Key": SecretStr("hidden-value")})

    assert "hidden-value" not in repr(settings) and "hidden-value" not in str(settings.model_dump())


async def test_the_plugin_builds_a_provider_from_its_configuration(served_home: Served, tmp_path: Any) -> None:
    raw = {"url": served_home.url(), "token": TOKEN, "include": ["turn_on"], "risks": {"turn_on": "sensitive"}}

    provider = plugin.create(
        raw, "home", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    )

    assert plugin.family is Family.TOOLS and isinstance(provider, McpToolProvider)
    async with provider:
        assert provider.name == "home"
        assert [(t.name, t.risk) for t in provider.tools()] == [("turn_on", Risk.SENSITIVE)]


# --- live ------------------------------------------------------------------------------------


@pytest.mark.live
async def test_live_home_assistant_exposes_its_assist_tools() -> None:
    url, token = os.environ.get("HOME_ASSISTANT_MCP_URL"), os.environ.get("HOME_ASSISTANT_TOKEN")
    if not url or not token:
        pytest.skip("HOME_ASSISTANT_MCP_URL and HOME_ASSISTANT_TOKEN are not set")
    async with McpToolProvider(url, name="home", auth=BearerToken(token)) as provider:
        # Home Assistant prefixes tool names with their domain: homeassistant__GetLiveContext (verified 30/10/2026).
        live = next(t.name for t in provider.tools() if t.name.endswith("GetLiveContext"))
        assert "Live Context" in await call(provider, live)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
