"""Connections: plugging accounts in from the admin, keeping their tokens fresh, unplugging them cleanly.

The OAuth flow is the authorization code grant with PKCE (S256) and a `state` bound to the pending
request. Like Home Assistant's Application Credentials, each household registers its own OAuth
client with the provider (`set_client`): a self-hosted instance never ships a shared secret.

A service authorised by discovery (a remote MCP server) says how once its address is typed: its
authorization server and the client registered for Nestor there are kept with the connection, not
with its connector, since every server has its own.
"""

import asyncio
import base64
import contextlib
import hashlib
import json
import secrets as random
import time
import urllib.parse
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from nestor.core import Component, ContractError, PersonId, ProviderError, utc_now
from nestor.core.i18n import Message
from nestor.modules.connectors.events import ConnectionChanged, ConnectionCreated, ConnectionRemoved
from nestor.modules.connectors.ports import Access, Connector, CredentialVault, TokenEndpoint
from nestor.modules.connectors.types import AuthKind, Connection, OAuthSpec, SecretField, Secrets, Status, Tokens
from nestor.modules.journal import Journal

PENDING_TTL_S = 600.0


class ClientRequired(ContractError):
    """The service authorises through OAuth but registers no client on the spot: the person types their own."""


class FieldsMissing(ContractError):
    """Fields a connector requires were left empty."""

    def __init__(self, kind: str, fields: Sequence[SecretField]) -> None:
        super().__init__(f"{kind}: missing: {', '.join(f.name for f in fields)}")
        self.fields = tuple(fields)


@dataclass(frozen=True, slots=True)
class _Pending:
    kind: str
    owner: PersonId | None
    verifier: str
    redirect_uri: str
    created: float
    spec: OAuthSpec
    client: Secrets
    settings: Secrets  # the fields typed, kept with a discovered connection


class Connections(Component):
    name = "connections"

    def __init__(
        self, journal: Journal, vault: CredentialVault, tokens: TokenEndpoint, connectors: Iterable[Connector]
    ) -> None:
        self.journal, self.vault, self.tokens = journal, vault, tokens
        self.connectors: Mapping[str, Connector] = {c.info.kind: c for c in connectors}
        self.connections: dict[str, Connection] = {}
        self._pending: dict[str, _Pending] = {}
        self._refreshing: dict[str, asyncio.Lock] = {}  # one refresh at a time per connection

    async def start(self) -> None:
        for event in await self.journal.history(ConnectionCreated, ConnectionChanged, ConnectionRemoved):
            if isinstance(event, ConnectionCreated):
                self.connections[event.connection_id] = Connection(
                    id=event.connection_id,
                    kind=event.kind,
                    owner=event.owner,
                    account=event.account,
                    auth=event.auth,
                    created_at=event.at,
                )
            elif isinstance(event, ConnectionChanged) and event.connection_id in self.connections:
                self.connections[event.connection_id] = replace(
                    self.connections[event.connection_id],
                    status=event.status,
                    disabled_tools=frozenset(event.disabled_tools),
                    confirm_writes=event.confirm_writes,
                    status_reason=event.reason,
                )
            elif isinstance(event, ConnectionRemoved):
                self.connections.pop(event.connection_id, None)

    def connector(self, kind: str) -> Connector:
        try:
            return self.connectors[kind]
        except KeyError:
            raise ContractError(f"no connector {kind!r} is installed") from None

    # -- the household's own OAuth client, per connector kind --------------------------------------

    async def set_client(self, kind: str, client_id: str, client_secret: str) -> None:
        self._oauth(kind)
        await self.vault.put(f"client:{kind}", "client", {"client_id": client_id, "client_secret": client_secret})

    async def has_client(self, kind: str) -> bool:
        return await self.vault.get(f"client:{kind}", "client") is not None

    # -- connecting ---------------------------------------------------------------------------------

    async def begin(self, kind: str, owner: PersonId | None, redirect_uri: str) -> str:
        """The provider URL the person's browser goes to; the provider sends them back to `redirect_uri`."""
        return self._consent(kind, owner, redirect_uri, self._oauth(kind), await self._client(kind), {})

    async def discover(
        self, kind: str, owner: PersonId | None, redirect_uri: str, settings: Secrets
    ) -> str | Connection:
        """For a service authorised by discovery: asks it how, from the fields typed (`settings`), then gives the URL
        the person's browser goes to like `begin`, or, when it needs no consent, the connection made at once.
        `ClientRequired` when it registers no OAuth client and none was typed."""
        connector = self.connector(kind)
        filled = _filled(connector, settings)
        found = await connector.discover(filled, redirect_uri)
        if found.oauth is None:
            return await self._connect(Connection(kind=kind, owner=owner, account="", auth=AuthKind.SECRET), filled)
        if found.client is None:
            raise ClientRequired(f"{kind}: the service registers no OAuth client: type one")
        return self._consent(kind, owner, redirect_uri, found.oauth, found.client, filled)

    async def complete(self, state: str, code: str) -> Connection:
        """Back from the provider: exchange the code, name the account, record the connection."""
        self._drop_stale()
        pending = self._pending.pop(state, None)
        if pending is None:
            raise ContractError("unknown or expired authorization request: start again")
        tokens = await self.tokens.exchange(pending.spec, pending.client, code, pending.verifier, pending.redirect_uri)
        connection = Connection(kind=pending.kind, owner=pending.owner, account="", auth=AuthKind.OAUTH2)
        if self.connector(pending.kind).info.auth is AuthKind.DISCOVERED:
            await self.vault.put(connection.id, "secrets", pending.settings)
            await self.vault.put(connection.id, "oauth", {"spec": _spec_json(pending.spec)})
            await self.vault.put(connection.id, "client", pending.client)
        await self._save_tokens(connection.id, tokens)
        return await self._identify_and_record(connection)

    async def connect(self, kind: str, owner: PersonId | None, secrets: Secrets) -> Connection:
        """Connect a service authorised by typed secrets (API key, app password) or by nothing."""
        connector = self.connector(kind)
        if connector.info.auth in (AuthKind.OAUTH2, AuthKind.DISCOVERED):
            raise ContractError(f"{kind} is connected through begin/complete")
        connection = Connection(kind=kind, owner=owner, account="", auth=connector.info.auth)
        return await self._connect(connection, _filled(connector, secrets))

    async def disconnect(self, connection_id: str, *, revoke: bool = True) -> None:
        """Revoke at the provider when possible, then forget every secret and the connection itself.

        `revoke=False` only forgets: when a reconnection replaced it, revoking the old token could revoke
        the whole grant at the provider (Google does), new tokens included.
        """
        connection = self._existing(connection_id)
        tokens = await self.vault.get(connection_id, "tokens")
        if revoke and tokens and connection.kind in self.connectors:
            token = tokens["refresh_token"] or tokens["access_token"]
            # forgetting locally matters more than a failed courtesy call
            with contextlib.suppress(ProviderError, ContractError):
                spec, client = await self._authorization(connection)
                if spec.revoke_url:
                    await self.tokens.revoke(spec, client, token)
        if connection.kind in self.connectors:  # what it holds goes first: nothing then reads forgotten secrets
            await self.connectors[connection.kind].disconnected(connection)
        await self.vault.forget(connection_id)
        await self.journal.publish(ConnectionRemoved(source=self.name, connection_id=connection_id))
        self.connections.pop(connection_id, None)
        self._refreshing.pop(connection_id, None)

    async def configure(
        self, connection_id: str, *, disabled_tools: Iterable[str] | None = None, confirm_writes: bool | None = None
    ) -> Connection:
        connection = self._existing(connection_id)
        updated = replace(
            connection,
            disabled_tools=frozenset(disabled_tools) if disabled_tools is not None else connection.disabled_tools,
            confirm_writes=connection.confirm_writes if confirm_writes is None else confirm_writes,
        )
        await self._record_change(updated)
        return updated

    def access(self, connection: Connection) -> Access:
        return _VaultAccess(self, connection)

    # -- internals ------------------------------------------------------------------------------------

    async def refreshed_token(self, connection: Connection, *, refused: str | None = None) -> str:
        """A valid access token. One refresh at a time per connection: a refresh token may be good for one use only,
        so a caller that waited takes the token another refreshed meanwhile."""
        async with self._refreshing.setdefault(connection.id, asyncio.Lock()):
            return await self._refreshed(connection, refused)

    async def revoked(self, connection: Connection) -> None:
        """The service refused even a fresh token: the person must authorise again."""
        await self._mark(connection, Status.NEEDS_REAUTH, Message.of("connection-token-refused"))

    async def _refreshed(self, connection: Connection, refused: str | None) -> str:
        stored = await self.vault.get(connection.id, "tokens")
        if stored is None:
            raise ProviderError(connection.kind, "no token: connect again", transient=False)
        tokens = _tokens(stored)
        if tokens.access_token != refused and not tokens.expired(utc_now()):
            return tokens.access_token
        if tokens.refresh_token is None:
            await self._mark(connection, Status.NEEDS_REAUTH, Message.of("connection-no-refresh-token"))
            raise ProviderError(connection.kind, "authorisation expired: connect again", transient=False)
        try:
            fresh = await self.tokens.refresh(*await self._authorization(connection), tokens.refresh_token)
        except ProviderError as error:
            if not error.transient:
                await self._mark(connection, Status.NEEDS_REAUTH, Message.of("connection-refresh-refused"))
            raise
        kept = replace(fresh, refresh_token=fresh.refresh_token or tokens.refresh_token)
        await self._save_tokens(connection.id, kept)
        return fresh.access_token

    def _consent(
        self, kind: str, owner: PersonId | None, redirect_uri: str, spec: OAuthSpec, client: Secrets, settings: Secrets
    ) -> str:
        self._drop_stale()
        state, verifier = random.token_urlsafe(24), random.token_urlsafe(48)
        self._pending[state] = _Pending(kind, owner, verifier, redirect_uri, time.monotonic(), spec, client, settings)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = {
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            **({"scope": " ".join(spec.scopes)} if spec.scopes else {}),
            **({"resource": spec.resource} if spec.resource else {}),
            **spec.extra_authorize,
        }
        return f"{spec.authorize_url}?{urllib.parse.urlencode(query)}"

    async def _connect(self, connection: Connection, filled: Secrets) -> Connection:
        await self.vault.put(connection.id, "secrets", filled)
        return await self._identify_and_record(connection)

    async def _identify_and_record(self, connection: Connection) -> Connection:
        try:
            account = await self.connector(connection.kind).identify(connection, self.access(connection))
        except ProviderError:
            await self.vault.forget(connection.id)
            raise
        connection = replace(connection, account=account)
        await self.journal.publish(
            ConnectionCreated(
                source=self.name,
                connection_id=connection.id,
                kind=connection.kind,
                account=account,
                auth=connection.auth,
                owner=connection.owner,
            )
        )
        self.connections[connection.id] = connection
        return connection

    async def _mark(self, connection: Connection, status: Status, reason: Message) -> None:
        if connection.id in self.connections:
            await self._record_change(self.connections[connection.id].with_status(status, reason))

    async def _record_change(self, connection: Connection) -> None:
        await self.journal.publish(
            ConnectionChanged(
                source=self.name,
                connection_id=connection.id,
                status=connection.status,
                disabled_tools=tuple(sorted(connection.disabled_tools)),
                confirm_writes=connection.confirm_writes,
                reason=connection.status_reason,
            )
        )
        self.connections[connection.id] = connection

    async def _save_tokens(self, connection_id: str, tokens: Tokens) -> None:
        stored = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token or "",
            "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else "",
            "scopes": " ".join(tokens.scopes),
        }
        await self.vault.put(connection_id, "tokens", stored)

    async def _authorization(self, connection: Connection) -> tuple[OAuthSpec, Secrets]:
        """The authorization server of a connection and Nestor's client there: its connector's and the household's,
        or for a discovered service, those found when it was connected."""
        if self.connector(connection.kind).info.auth is not AuthKind.DISCOVERED:
            return self._oauth(connection.kind), await self._client(connection.kind)
        stored, client = await self.vault.get(connection.id, "oauth"), await self.vault.get(connection.id, "client")
        if stored is None or client is None:
            raise ProviderError(connection.kind, "no authorization server kept: connect again", transient=False)
        return _spec(stored["spec"]), client

    def _oauth(self, kind: str) -> OAuthSpec:
        spec = self.connector(kind).info.oauth
        if spec is None:
            raise ContractError(f"{kind} does not connect through OAuth")
        return spec

    async def _client(self, kind: str) -> Secrets:
        client = await self.vault.get(f"client:{kind}", "client")
        if client is None:
            raise ContractError(f"register an OAuth client for {kind} first (see its setup guide)")
        return client

    def _existing(self, connection_id: str) -> Connection:
        try:
            return self.connections[connection_id]
        except KeyError:
            raise ContractError(f"no connection {connection_id!r}") from None

    def _drop_stale(self) -> None:
        now = time.monotonic()
        for state in [s for s, p in self._pending.items() if now - p.created > PENDING_TTL_S]:
            del self._pending[state]


class _VaultAccess(Access):
    def __init__(self, connections: Connections, connection: Connection) -> None:
        self._connections, self._connection = connections, connection

    async def token(self, *, refused: str | None = None) -> str:
        return await self._connections.refreshed_token(self._connection, refused=refused)

    async def revoked(self) -> None:
        await self._connections.revoked(self._connection)

    async def secrets(self) -> Secrets:
        return await self._connections.vault.get(self._connection.id, "secrets") or {}

    async def load_state(self) -> Mapping[str, str]:
        return await self._connections.vault.get(self._connection.id, "state") or {}

    async def save_state(self, state: Mapping[str, str]) -> None:
        await self._connections.vault.put(self._connection.id, "state", dict(state))


def _filled(connector: Connector, secrets: Secrets) -> dict[str, str]:
    """The connector's fields as typed, trimmed, an optional one left empty taking its default; `FieldsMissing` when
    a required one is empty."""
    fields = connector.info.fields
    filled = {f.name: (secrets.get(f.name) or "").strip() or f.default or "" for f in fields}
    if missing := [f for f in fields if not filled[f.name] and f.default is None]:
        raise FieldsMissing(connector.info.kind, missing)
    return filled


def _spec_json(spec: OAuthSpec) -> str:
    return json.dumps(
        {
            "authorize_url": spec.authorize_url,
            "token_url": spec.token_url,
            "scopes": list(spec.scopes),
            "revoke_url": spec.revoke_url,
            "extra_authorize": dict(spec.extra_authorize),
            "resource": spec.resource,
        }
    )


def _spec(stored: str) -> OAuthSpec:
    found = json.loads(stored)
    return OAuthSpec(
        authorize_url=found["authorize_url"],
        token_url=found["token_url"],
        scopes=tuple(found["scopes"]),
        revoke_url=found["revoke_url"],
        extra_authorize=found["extra_authorize"],
        resource=found["resource"],
    )


def _tokens(stored: Secrets) -> Tokens:
    expires = stored.get("expires_at")
    return Tokens(
        access_token=stored["access_token"],
        refresh_token=stored.get("refresh_token") or None,
        expires_at=datetime.fromisoformat(expires) if expires else None,
        scopes=tuple(stored.get("scopes", "").split()),
    )
