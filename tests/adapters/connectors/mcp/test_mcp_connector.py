"""Remote MCP servers connected like any account, against servers built with the SDK and served over HTTP: one with
the SDK's own OAuth authorization server (metadata, client registration, tokens bound to their resource, refresh,
revocation), one that registers no client, one that needs nothing, one that takes a token."""

import json
import secrets
import socket
import time
import urllib.parse
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from mcp.types import ToolAnnotations

from nestor.adapters.connectors.mcp.catalogue import account, known, service_name
from nestor.adapters.connectors.mcp.connector import McpConnector
from nestor.adapters.oauth import HttpxTokenEndpoint
from nestor.core import PersonId, ProviderError
from nestor.core.i18n import Message
from nestor.modules.channels import Address
from nestor.modules.cognition.tools import Risk, Tool, Toolbox, ToolContext, ToolFailed
from nestor.modules.connectors import AuthKind, ClientRequired, Connection, Connections, ConnectorTools, Status
from nestor.modules.household import Person
from nestor.modules.identity import Speaker
from nestor.modules.journal import Journal
from nestor.testing.connectors import MemoryVault
from nestor.testing.journal import MemoryEventLog

from ...served import Asgi, Served, bearer, eventually

MATHIS = PersonId("mathis")
REDIRECT = "https://nestor.example/connections/callback"
CONTEXT = ToolContext(address=Address("telegram", "42"), speaker=Speaker.account(MATHIS))


class Authority:
    """The OAuth authorization server of one MCP server: consents at once, issues tokens bound to the resource asked
    for and expiring after `lifetime_s`, refreshes and revokes them; registers clients unless `registers` is off,
    knowing then only `preregistered`."""

    def __init__(self, *, registers: bool = True, lifetime_s: int = 3600) -> None:
        self.registers, self.lifetime_s = registers, lifetime_s
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.access: dict[str, AccessToken] = {}
        self.refresh: dict[str, RefreshToken] = {}
        self.refreshed = 0
        self.refusing = False  # every access token refused, even a fresh one
        self.listing_broken = False  # the tools listing answered with something that is not MCP
        self.resources: list[str | None] = []  # the resource of every token issued

    def preregister(self, client_id: str, secret: str, redirect: str) -> None:
        self.clients[client_id] = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=secret,
            redirect_uris=[redirect],
            token_endpoint_auth_method="client_secret_post",
            scope="tickets",
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        code = AuthorizationCode(
            code=secrets.token_hex(16),
            scopes=params.scopes or [],
            expires_at=time.time() + 300,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        self.codes[code.code] = code
        return construct_redirect_uri(str(params.redirect_uri), code=code.code, state=params.state)

    async def load_authorization_code(self, client: OAuthClientInformationFull, code: str) -> AuthorizationCode | None:
        return self.codes.get(code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, code: AuthorizationCode
    ) -> OAuthToken:
        del self.codes[code.code]
        return self._issue(client.client_id, code.scopes, code.resource)

    async def load_refresh_token(self, client: OAuthClientInformationFull, token: str) -> RefreshToken | None:
        return self.refresh.get(token)

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        self.refreshed += 1
        del self.refresh[refresh_token.token]
        return self._issue(client.client_id, scopes or refresh_token.scopes, refresh_token.resource)

    async def load_access_token(self, token: str) -> AccessToken | None:
        if self.refusing:
            return None
        found = self.access.get(token)
        return found if found and (found.expires_at or 0) > time.time() else None

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self.access = {k: v for k, v in self.access.items() if v.client_id != token.client_id}
        self.refresh = {k: v for k, v in self.refresh.items() if v.client_id != token.client_id}

    def forget_access_tokens(self) -> None:
        """Access tokens revoked server-side, before they expire; refresh tokens still valid."""
        self.access.clear()

    def _issue(self, client_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        access, refresh = secrets.token_hex(16), secrets.token_hex(16)
        expires = int(time.time()) + self.lifetime_s
        self.access[access] = AccessToken(
            token=access, client_id=client_id, scopes=scopes, expires_at=expires, resource=resource
        )
        self.refresh[refresh] = RefreshToken(token=refresh, client_id=client_id, scopes=scopes, resource=resource)
        self.resources.append(resource)
        return OAuthToken(
            access_token=access, expires_in=self.lifetime_s, refresh_token=refresh, scope=" ".join(scopes)
        )


def tickets(**options: Any) -> MCPServer:
    server = MCPServer("tickets", **options)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def list_issues(team: str) -> str:
        """Lists the open issues of a team."""
        return f"{team}: 2 open issues"

    @server.tool()
    def create_issue(title: str) -> str:
        """Creates an issue."""
        return f"created {title}"

    return server


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def oauth_server(authority: Authority, *, legacy: bool = False) -> Served:
    """The tickets server behind the SDK's authorization server, both at the same origin; `legacy`: like servers of
    the 2025-03-26 era, without protected resource metadata."""
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    def app() -> Asgi:
        auth = AuthSettings(
            issuer_url=base,
            resource_server_url=None if legacy else f"{base}/mcp",
            validate_token_resource=not legacy,
            required_scopes=["tickets"],
            client_registration_options=ClientRegistrationOptions(
                enabled=authority.registers, valid_scopes=["tickets"]
            ),
            revocation_options=RevocationOptions(enabled=True),
        )
        return listing(tickets(auth=auth, auth_server_provider=authority).streamable_http_app(), authority)

    served = Served(app)
    served.port = port
    await served.start()
    return served


def listing(app: Asgi, authority: Authority) -> Asgi:
    """While `authority.listing_broken`, answers the listing of tools with something that is not MCP at all."""

    async def broken(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            return await app(scope, receive, send)
        body, more = b"", True
        while more:
            message = await receive()
            body, more = body + message.get("body", b""), message.get("more_body", False)
        if b'"tools/list"' in body and authority.listing_broken:
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/html")]})
            await send({"type": "http.response.body", "body": b"<html>maintenance</html>"})
            return None

        replayed = False

        async def replay() -> dict[str, Any]:  # the body once, then what the client does (it disconnects)
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        return await app(scope, replay, send)

    return broken


class Setup:
    def __init__(self) -> None:
        self.journal = Journal(MemoryEventLog())
        self.mcp = McpConnector(timeout_s=5.0)
        self.endpoint = HttpxTokenEndpoint()
        self.connections = Connections(self.journal, MemoryVault(), self.endpoint, [self.mcp])

    def tools(self) -> dict[str, Tool]:
        return {t.name: t for t in ConnectorTools(self.connections).tools()}

    async def consent(self, begun: str | Connection) -> Connection:
        """The person's browser at the authorization server: it approves and is sent back with a code."""
        assert isinstance(begun, str), "the server asked for consent"
        async with httpx.AsyncClient() as browser:
            back = (await browser.get(begun)).headers["location"]
        assert back.startswith(REDIRECT)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(back).query))
        return await self.connections.complete(query["state"], query["code"])


@pytest.fixture
async def setup() -> AsyncIterator[Setup]:
    setup = Setup()
    async with setup.endpoint, setup.mcp:
        yield setup


@pytest.fixture
async def authority() -> AsyncIterator[tuple[Authority, Served]]:
    authority = Authority()
    served = await oauth_server(authority)
    yield authority, served
    await served.stop()


async def test_a_server_found_by_its_address_is_authorised_with_a_client_it_registered_and_its_tools_offered(
    setup: Setup, authority: tuple[Authority, Served]
) -> None:
    server, served = authority
    begun = await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()})
    sent = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(str(begun)).query))
    assert str(begun).startswith(f"{served.url('/authorize')}?")
    assert sent["client_id"] in server.clients, "registered on the spot"
    assert (sent["resource"], sent["scope"], sent["code_challenge_method"]) == (served.url(), "tickets", "S256")

    connection = await setup.consent(begun)
    assert (connection.account, connection.auth, connection.owner) == (
        f"mathis@127.0.0.1:{served.port}",
        AuthKind.OAUTH2,
        MATHIS,
    )
    assert server.resources == [served.url()], "the token is for this server"
    tools = setup.tools()
    assert {name: tool.risk for name, tool in tools.items()} == {
        "127_list_issues": Risk.READ,
        "127_create_issue": Risk.SENSITIVE,  # a write, confirmed first as the connection asks by default
    }
    assert await tools["127_list_issues"].run({"team": "home"}, CONTEXT) == "home: 2 open issues"
    assert tools["127_list_issues"].owner == MATHIS


async def test_an_expired_token_is_refreshed_for_its_resource_and_one_refused_early_is_renewed(
    setup: Setup, authority: tuple[Authority, Served]
) -> None:
    server, served = authority
    connection = await setup.consent(await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()}))
    server.forget_access_tokens()  # revoked by the service before it expires: the next request is refused
    assert await setup.tools()["127_list_issues"].run({"team": "home"}, CONTEXT) == "home: 2 open issues"
    assert server.refreshed == 1 and server.resources[-1] == served.url()
    assert setup.connections.connections[connection.id].status is Status.CONNECTED


async def test_a_grant_revoked_at_the_service_asks_the_person_to_connect_again(
    setup: Setup, authority: tuple[Authority, Served]
) -> None:
    server, served = authority
    connection = await setup.consent(await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()}))
    server.access.clear()
    server.refresh.clear()
    with pytest.raises(ToolFailed):
        await setup.tools()["127_list_issues"].run({"team": "home"}, CONTEXT)
    assert setup.connections.connections[connection.id].status is Status.NEEDS_REAUTH
    assert setup.tools() == {}


async def test_a_server_that_registers_no_client_takes_the_one_the_person_typed(setup: Setup) -> None:
    server = Authority(registers=False)
    served = await oauth_server(server)
    try:
        with pytest.raises(ClientRequired):
            await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()})
        server.preregister("my-app", "app-secret", REDIRECT)
        typed = {"url": served.url(), "client_id": "my-app", "client_secret": "app-secret"}
        connection = await setup.consent(await setup.connections.discover("mcp", MATHIS, REDIRECT, typed))
        assert connection.auth is AuthKind.OAUTH2 and setup.tools()
    finally:
        await served.stop()


async def test_a_server_that_needs_nothing_is_connected_at_once(setup: Setup) -> None:
    served = Served(lambda: tickets().streamable_http_app())
    await served.start()
    try:
        connection = await setup.connections.discover("mcp", None, REDIRECT, {"url": served.url()})
        assert isinstance(connection, Connection) and connection.auth is AuthKind.SECRET
        assert sorted(setup.tools()) == ["127_create_issue", "127_list_issues"]
    finally:
        await served.stop()


async def test_a_server_guarded_by_a_token_takes_the_one_typed_and_refuses_without(setup: Setup) -> None:
    served = Served(lambda: bearer(tickets().streamable_http_app(), "personal-token"))
    await served.start()
    try:
        with pytest.raises(ProviderError) as refused:
            await setup.connections.discover("mcp", None, REDIRECT, {"url": served.url()})
        assert refused.value.reason is not None and refused.value.reason.id == "mcp-refused"
        typed = {"url": served.url(), "token": "personal-token"}
        connection = await setup.connections.discover("mcp", None, REDIRECT, typed)
        assert isinstance(connection, Connection) and setup.tools()
        await setup.connections.disconnect(connection.id)
        assert setup.tools() == {}
    finally:
        await served.stop()


async def test_an_address_that_is_not_a_server_is_refused(setup: Setup) -> None:
    with pytest.raises(ProviderError) as refused:
        await setup.connections.discover("mcp", None, REDIRECT, {"url": "mcp.linear.app"})
    assert refused.value.reason == Message.of("connector-mcp-not-an-address", url="mcp.linear.app")


@pytest.mark.parametrize(
    ("url", "named", "brand"),
    [
        ("https://mcp.linear.app/mcp", "linear", "linear"),
        ("https://api.githubcopilot.com/mcp/", "github", "github"),
        ("https://huggingface.co/mcp", "hugging-face", "huggingface"),
        ("https://mcp.tickets.example/mcp", "tickets", None),
        ("http://localhost:8080/mcp", "localhost", None),
    ],
)
def test_an_account_is_named_after_its_service_or_its_host(url: str, named: str, brand: str | None) -> None:
    label = account("mathis", url)
    preset = known(label)
    assert (service_name(label), preset.brand if preset else None) == (named, brand)


async def test_a_message_names_the_server_by_its_service_with_its_mark(setup: Setup) -> None:
    served = Served(lambda: tickets().streamable_http_app())
    await served.start()
    try:
        connection = await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()})
        assert isinstance(connection, Connection)
        # the same server as a well-known service would be named after it, with its mark
        linear = replace(connection, account="mathis@mcp.linear.app")
        setup.connections.connections[connection.id] = linear
        [mentioned] = ConnectorTools(setup.connections).mentionable(Person(id=MATHIS, name="Mathis"))
        assert (mentioned.handle, mentioned.brand) == ("linear", "linear")
    finally:
        await served.stop()


async def test_a_server_of_the_first_authorization_era_is_authorised_at_its_own_origin(setup: Setup) -> None:
    server = Authority()
    served = await oauth_server(server, legacy=True)
    try:
        begun = await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()})
        assert str(begun).startswith(f"{served.url('/authorize')}?")
        connection = await setup.consent(begun)
        assert connection.auth is AuthKind.OAUTH2 and setup.tools()
    finally:
        await served.stop()


async def test_two_accounts_on_one_server_are_told_apart_by_name_tool_and_handle(setup: Setup) -> None:
    served = Served(lambda: tickets().streamable_http_app())
    await served.start()
    try:
        owners = (MATHIS, MATHIS, PersonId("lea"))
        made = [await setup.connections.discover("mcp", owner, REDIRECT, {"url": served.url()}) for owner in owners]
        accounts = [c.account for c in made if isinstance(c, Connection)]
        host = f"127.0.0.1:{served.port}"
        assert accounts == [f"mathis@{host}", f"mathis-2@{host}", f"lea@{host}"]
        listed = Toolbox(setup.journal, providers=[ConnectorTools(setup.connections)]).specs()  # no name twice
        assert len({spec.name for spec in listed}) == 6
        handles = {m.handle for m in ConnectorTools(setup.connections).mentionable(Person(id=MATHIS, name="Mathis"))}
        assert handles == {"127-mathis", "127-mathis-2"}
    finally:
        await served.stop()


async def test_a_tool_switched_off_stays_off_after_a_restart(setup: Setup) -> None:
    served = Served(lambda: tickets().streamable_http_app())
    await served.start()
    try:
        first, second = [
            await setup.connections.discover("mcp", owner, REDIRECT, {"url": served.url()})
            for owner in (MATHIS, PersonId("lea"))
        ]
        assert isinstance(first, Connection) and isinstance(second, Connection)
        named = [t.name for t in setup.mcp.tools(second, setup.connections.access(second))]
        await setup.connections.configure(second.id, disabled_tools=[n for n in named if "create_issue" in n])
        await setup.connections.disconnect(first.id)

        restarted = Connections(setup.journal, setup.connections.vault, setup.endpoint, [mcp := McpConnector()])
        async with mcp:
            await restarted.start()
            tools = ConnectorTools(restarted)
            await tools.start()
            await eventually(lambda: bool(tools.tools()))
            assert [t.name for t in tools.tools()] == ["127_list_issues"]
    finally:
        await served.stop()


async def test_a_fresh_token_the_service_still_refuses_asks_to_connect_again(
    setup: Setup, authority: tuple[Authority, Served]
) -> None:
    server, served = authority
    connection = await setup.consent(await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()}))
    server.refusing = True
    with pytest.raises(ToolFailed):
        await setup.tools()["127_list_issues"].run({"team": "home"}, CONTEXT)
    refused = setup.connections.connections[connection.id]
    assert (refused.status, refused.status_reason) == (Status.NEEDS_REAUTH, Message.of("connection-token-refused"))


async def test_an_account_unplugged_while_its_tool_runs_fails_the_call_cleanly(setup: Setup) -> None:
    served = Served(lambda: tickets().streamable_http_app())
    await served.start()
    connection = await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()})
    assert isinstance(connection, Connection)
    tool = setup.tools()["127_list_issues"]
    await setup.connections.vault.forget(connection.id)  # its secrets gone, its session not yet closed
    await served.stop()
    await served.start()  # the session drops: the next call opens another
    try:
        for _ in range(2):
            with pytest.raises(ToolFailed):
                await tool.run({"team": "home"}, CONTEXT)
    finally:
        await served.stop()


async def test_a_refusal_recovered_by_a_fresh_token_does_not_make_a_later_failure_look_refused(
    setup: Setup,
) -> None:
    server = Authority()
    served = await oauth_server(server)
    try:
        connection = await setup.consent(
            await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()})
        )
        server.forget_access_tokens()  # the next session opens with a 401, renewed, then its listing breaks
        server.listing_broken = True
        await setup.mcp.disconnected(connection)
        with pytest.raises(ProviderError) as failed:
            await setup.mcp.identify(connection, setup.connections.access(connection))
        assert failed.value.transient, "worth trying again: the credentials were fine"
    finally:
        await served.stop()


def metadata(documents: dict[str, tuple[int, dict[str, Any]]]) -> Asgi:
    """A server refusing `/mcp` with a 401 and serving fixed metadata documents, by path."""

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        status, body = (401, {}) if scope["path"] == "/mcp" else documents.get(scope["path"], (404, {}))
        await send(
            {"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]}
        )
        await send({"type": "http.response.body", "body": json.dumps(body).encode()})

    return app


def authorization_server(issuer: str, **more: object) -> dict[str, Any]:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        **more,
    }


@pytest.mark.parametrize(
    ("documents", "refusal", "transient"),
    [
        (  # its metadata is about another server
            lambda base: {
                "/.well-known/oauth-protected-resource/mcp": (
                    200,
                    {"resource": "https://elsewhere.example/mcp", "authorization_servers": [base]},
                )
            },
            "connector-mcp-metadata-elsewhere",
            False,
        ),
        (  # another authorization server's metadata
            lambda base: {
                "/.well-known/oauth-authorization-server": (200, authorization_server("https://impostor.example"))
            },
            "connector-mcp-metadata-elsewhere",
            False,
        ),
        (  # a client Nestor could not authenticate
            lambda base: {
                "/.well-known/oauth-authorization-server": (
                    200,
                    authorization_server(
                        base,
                        registration_endpoint=f"{base}/register",
                        token_endpoint_auth_methods_supported=["private_key_jwt"],
                    ),
                )
            },
            "connector-mcp-auth-methods",
            False,
        ),
        (  # an outage
            lambda base: {"/.well-known/oauth-authorization-server": (503, {})},
            "connector-mcp-metadata-unavailable",
            True,
        ),
    ],
)
async def test_metadata_that_cannot_be_trusted_or_used_is_refused(
    setup: Setup, documents: Callable[[str], dict[str, tuple[int, dict[str, Any]]]], refusal: str, transient: bool
) -> None:
    port = free_port()
    served = Served(lambda: metadata(documents(f"http://127.0.0.1:{port}")))
    served.port = port
    await served.start()
    try:
        with pytest.raises(ProviderError) as refused:
            await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": served.url()})
        assert refused.value.reason is not None
        assert (refused.value.reason.id, refused.value.transient) == (refusal, transient)
    finally:
        await served.stop()


async def test_a_server_that_does_not_answer_is_worth_trying_again(setup: Setup) -> None:
    with pytest.raises(ProviderError) as refused:
        await setup.connections.discover("mcp", MATHIS, REDIRECT, {"url": f"http://127.0.0.1:{free_port()}/mcp"})
    assert refused.value.transient and refused.value.reason is not None
    assert refused.value.reason.id == "mcp-unreachable"
