"""Doubles and contract suites for connectors: an in-memory vault, a fake OAuth provider, a scripted connector."""

from collections.abc import Mapping, Sequence
from datetime import timedelta

from nestor.core import ProviderError, new_id, utc_now
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext
from nestor.modules.connectors import (
    Access,
    AuthKind,
    Connection,
    Connector,
    ConnectorInfo,
    CredentialVault,
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

    def __init__(self, *, lifetime_s: float = 3600.0) -> None:
        self.lifetime_s = lifetime_s
        self.codes: dict[str, tuple[str, str]] = {}  # code → (client_id, verifier)
        self.revoked: list[str] = []
        self.refreshes = 0
        self.refusing = False
        self.unreachable = False

    def authorize(self, client_id: str, verifier: str) -> str:
        """What the provider's consent page does: hand out a code for this client and PKCE verifier."""
        code = new_id()
        self.codes[code] = (client_id, verifier)
        return code

    async def exchange(self, spec: OAuthSpec, client: Secrets, code: str, verifier: str, redirect_uri: str) -> Tokens:
        if self.codes.pop(code, None) != (client["client_id"], verifier):
            raise ProviderError(self.name, "invalid_grant", transient=False)
        return self._issue(refresh=new_id())

    async def refresh(self, spec: OAuthSpec, client: Secrets, refresh_token: str) -> Tokens:
        if self.unreachable:
            raise ProviderError(self.name, "timeout", transient=True)
        if self.refusing or refresh_token in self.revoked:
            raise ProviderError(self.name, "invalid_grant", transient=False)
        self.refreshes += 1
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


class ScriptedConnector(Connector):
    """A mail-like service: a read tool, a send tool, and an inbox feeding watches."""

    def __init__(self, kind: str = "mailbox", *, auth: AuthKind = AuthKind.OAUTH2, account: str = "mathis@example.com"):
        self.info = ConnectorInfo(
            kind=kind,
            title="Mailbox",
            description="Read and send mail",
            auth=auth,
            oauth=OAUTH if auth is AuthKind.OAUTH2 else None,
            fields=(SecretField(name="password", label="App password"),) if auth is AuthKind.SECRET else (),
            inbound=("mail",),
        )
        self.account = account
        self.inbox = Inbox()
        self.sent: list[Mapping[str, object]] = []
        self.tokens_seen: list[str] = []

    async def identify(self, access: Access) -> str:
        if self.info.auth is AuthKind.OAUTH2:
            self.tokens_seen.append(await access.token())
        else:
            await access.secrets()
        return self.account

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        async def search(arguments: Mapping[str, object], context: ToolContext) -> str:
            if self.info.auth is AuthKind.OAUTH2:
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
