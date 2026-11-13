"""Doubles and contract suites for connectors: an in-memory vault, a fake OAuth provider, a scripted connector."""

import asyncio
import base64
import hashlib
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import timedelta

from nestor.core import ProviderError, new_id, utc_now
from nestor.core.i18n import Message
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext
from nestor.modules.connectors import (
    Access,
    AuthKind,
    Connection,
    Connector,
    ConnectorInfo,
    CredentialVault,
    Discovery,
    OAuthSpec,
    SecretField,
    Secrets,
    TokenEndpoint,
    Tokens,
)
from nestor.modules.initiative import InboundEventSource
from nestor.testing.initiative import Inbox, QueuedSource


class MemoryVault(CredentialVault):
    name = "memory-vault"

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], dict[str, str]] = {}

    async def put(self, owner: str, name: str, secrets: Secrets) -> None:
        self.entries[(owner, name)] = dict(secrets)

    async def get(self, owner: str, name: str) -> Secrets | None:
        found = self.entries.get((owner, name))
        return dict(found) if found is not None else None

    async def forget(self, owner: str) -> None:
        for key in [k for k in self.entries if k[0] == owner]:
            del self.entries[key]


class FakeProvider(TokenEndpoint):
    """An OAuth provider: issues tokens for codes it handed out, refreshes them until revoked."""

    name = "fake-oauth"

    def __init__(self, *, lifetime_s: float = 3600.0, rotating: bool = False) -> None:
        self.lifetime_s = lifetime_s
        self.rotating = rotating  # each refresh token serves once, and a new one comes with each refresh
        self.codes: dict[str, tuple[str, str, str]] = {}  # code → (client_id, redirect_uri, S256 challenge)
        self.revoked: list[str] = []
        self.used: list[tuple[str, str]] = []  # the token endpoint and the client of every exchange and refresh
        self.refreshes = 0
        self.refusing = False
        self.unreachable = False

    def consent(self, authorize_url: str) -> dict[str, str]:
        """What the provider's consent page does with the authorisation URL once the person approves: the
        query it sends back to `redirect_uri`, a code bound to the client, the redirect and the PKCE challenge."""
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(authorize_url).query))
        if query.get("code_challenge_method") != "S256":
            raise ProviderError(self.name, "invalid_request: PKCE S256 required", transient=False)
        code = new_id()
        self.codes[code] = (query["client_id"], query["redirect_uri"], query["code_challenge"])
        return {"state": query["state"], "code": code}

    async def exchange(self, spec: OAuthSpec, client: Secrets, code: str, verifier: str, redirect_uri: str) -> Tokens:
        self.used.append((spec.token_url, client["client_id"]))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if self.codes.pop(code, None) != (client["client_id"], redirect_uri, challenge):
            raise ProviderError(self.name, "invalid_grant", transient=False)
        return self._issue(refresh=new_id())

    async def refresh(self, spec: OAuthSpec, client: Secrets, refresh_token: str) -> Tokens:
        self.used.append((spec.token_url, client["client_id"]))
        await asyncio.sleep(0)  # a request over the network: other calls run meanwhile
        if self.unreachable:
            raise ProviderError(self.name, "timeout", transient=True)
        if self.refusing or refresh_token in self.revoked:
            raise ProviderError(self.name, "invalid_grant", transient=False)
        self.refreshes += 1
        if self.rotating:
            self.revoked.append(refresh_token)
            return self._issue(refresh=new_id())
        return self._issue(refresh=None)

    async def revoke(self, spec: OAuthSpec, client: Secrets, token: str) -> None:
        self.revoked.append(token)

    def _issue(self, *, refresh: str | None) -> Tokens:
        return Tokens(
            access_token=f"at-{new_id()}",
            refresh_token=refresh,
            expires_at=utc_now() + timedelta(seconds=self.lifetime_s),
        )


OAUTH = OAuthSpec(
    authorize_url="https://provider.example/authorize",
    token_url="https://provider.example/token",
    revoke_url="https://provider.example/revoke",
    scopes=("mail.read",),
    extra_authorize={"access_type": "offline"},
)


DISCOVERED_OAUTH = OAuthSpec(
    authorize_url="https://auth.server.example/authorize",
    token_url="https://auth.server.example/token",
    scopes=("tickets",),
    resource="https://server.example/mcp",
)


class ScriptedConnector(Connector):
    """A mail-like service: a read tool, a send tool, and an inbox feeding watches.

    Authorised by discovery, it is reached at the `server` typed; what it answers is `found`, which registers an
    OAuth client by default. With `found` registering none, the client typed (`client_id`, `client_secret`) is used.
    """

    def __init__(self, kind: str = "mailbox", *, auth: AuthKind = AuthKind.OAUTH2, account: str = "mathis@example.com"):
        fields = {
            AuthKind.SECRET: (SecretField(name="password", label=Message.of("connector-scripted-field-password")),),
            AuthKind.DISCOVERED: (
                SecretField(name="server", label=Message.of("connector-scripted-field-server"), secret=False),
                SecretField(name="client_id", label=Message.of("connector-scripted-field-client"), default=""),
                SecretField(name="client_secret", label=Message.of("connector-scripted-field-secret"), default=""),
            ),
        }
        self.info = ConnectorInfo(
            kind=kind,
            title=Message.of("connector-scripted-title"),
            description=Message.of("connector-scripted-description"),
            auth=auth,
            oauth=OAUTH if auth is AuthKind.OAUTH2 else None,
            fields=fields.get(auth, ()),
            inbound=("mail",),
        )
        self.account = account
        self.found = Discovery(oauth=DISCOVERED_OAUTH, client={"client_id": "registered-for-nestor"})
        self.discovered: list[tuple[Secrets, str]] = []  # what `discover` was asked: the fields, the redirect
        self.released: list[str] = []  # the connections it was told were gone
        self.inbox = Inbox()
        self.sent: list[Mapping[str, object]] = []
        self.tokens_seen: list[str] = []

    async def discover(self, settings: Secrets, redirect_uri: str) -> Discovery:
        if self.info.auth is not AuthKind.DISCOVERED:
            return await super().discover(settings, redirect_uri)
        self.discovered.append((dict(settings), redirect_uri))
        typed = {k: settings[k] for k in ("client_id", "client_secret") if settings.get(k)}
        if self.found.oauth is not None and self.found.client is None and typed:
            return Discovery(oauth=self.found.oauth, client=typed)
        return self.found

    async def identify(self, connection: Connection, access: Access) -> str:
        if connection.auth is AuthKind.OAUTH2:
            self.tokens_seen.append(await access.token())
        else:
            await access.secrets()
        return self.account

    async def disconnected(self, connection: Connection) -> None:
        self.released.append(connection.id)

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        async def search(arguments: Mapping[str, object], context: ToolContext) -> str:
            if connection.auth is AuthKind.OAUTH2:
                self.tokens_seen.append(await access.token())
            return f"2 mails about {arguments.get('query')}"

        async def send(arguments: Mapping[str, object], context: ToolContext) -> str:
            self.sent.append(dict(arguments))
            return "sent"

        kind = self.info.kind
        return (
            Tool(spec=ToolSpec(f"{kind}_search", "Search mail"), run=search),
            Tool(
                spec=ToolSpec(f"{kind}_send", "Send a mail", {"type": "object", "properties": {"to": {}}}),
                run=send,
                risk=Risk.SENSITIVE,
            ),
        )

    def inbound(self, connection: Connection, access: Access) -> InboundEventSource | None:
        return QueuedSource(self.inbox)


class CredentialVaultContract:
    """Behaviour every `CredentialVault` must show. Implement `vault()` (used as a context manager) and
    `stored_bytes()`: everything the vault wrote to disk, to check secrets are not readable there."""

    def vault(self) -> CredentialVault:
        raise NotImplementedError

    def stored_bytes(self) -> bytes:
        raise NotImplementedError

    async def test_secrets_come_back_exactly_and_are_forgotten_by_owner(self) -> None:
        async with self.vault() as vault:
            await vault.put("c1", "tokens", {"access_token": "très-secret-éàü", "refresh_token": ""})
            await vault.put("c1", "state", {"cursor": "42"})
            await vault.put("c2", "tokens", {"access_token": "autre"})
            assert await vault.get("c1", "tokens") == {"access_token": "très-secret-éàü", "refresh_token": ""}
            await vault.put("c1", "state", {"cursor": "43"})
            assert await vault.get("c1", "state") == {"cursor": "43"}
            await vault.forget("c1")
            assert await vault.get("c1", "tokens") is None and await vault.get("c1", "state") is None
            assert await vault.get("c2", "tokens") == {"access_token": "autre"}

    async def test_nothing_is_readable_at_rest(self) -> None:
        async with self.vault() as vault:
            await vault.put("c1", "tokens", {"access_token": "ya29.sentinel-token-value"})
        assert b"sentinel-token-value" not in self.stored_bytes()
