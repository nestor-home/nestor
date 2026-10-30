"""Connections: plugging accounts in from the admin, keeping their tokens fresh, unplugging them cleanly.

The OAuth flow is the authorization code grant with PKCE (S256) and a `state` bound to the pending
request. Like Home Assistant's Application Credentials, each household registers its own OAuth
client with the provider (`set_client`): a self-hosted instance never ships a shared secret.
"""

import base64
import contextlib
import hashlib
import secrets as random
import time
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from nestor.core import Component, ContractError, PersonId, ProviderError, utc_now
from nestor.core.i18n import Message
from nestor.modules.connectors.events import ConnectionChanged, ConnectionCreated, ConnectionRemoved
from nestor.modules.connectors.ports import Access, Connector, CredentialVault, TokenEndpoint
from nestor.modules.connectors.types import AuthKind, Connection, OAuthSpec, Secrets, Status, Tokens
from nestor.modules.journal import Journal

PENDING_TTL_S = 600.0


@dataclass(frozen=True, slots=True)
class _Pending:
    kind: str
    owner: PersonId | None
    verifier: str
    redirect_uri: str
    created: float


class Connections(Component):
    name = "connections"

    def __init__(
        self, journal: Journal, vault: CredentialVault, tokens: TokenEndpoint, connectors: Iterable[Connector]
    ) -> None:
        self.journal, self.vault, self.tokens = journal, vault, tokens
        self.connectors: Mapping[str, Connector] = {c.info.kind: c for c in connectors}
        self.connections: dict[str, Connection] = {}
        self._pending: dict[str, _Pending] = {}

    async def start(self) -> None:
        for event in await self.journal.history(ConnectionCreated, ConnectionChanged, ConnectionRemoved):
            if isinstance(event, ConnectionCreated):
                self.connections[event.connection_id] = Connection(
                    id=event.connection_id,
                    kind=event.kind,
                    owner=event.owner,
                    account=event.account,
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
        spec = self._oauth(kind)
        client = await self._client(kind)
        self._drop_stale()
        state, verifier = random.token_urlsafe(24), random.token_urlsafe(48)
        self._pending[state] = _Pending(kind, owner, verifier, redirect_uri, time.monotonic())
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = {
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "scope": " ".join(spec.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            **spec.extra_authorize,
        }
        return f"{spec.authorize_url}?{urllib.parse.urlencode(query)}"

    async def complete(self, state: str, code: str) -> Connection:
        """Back from the provider: exchange the code, name the account, record the connection."""
        self._drop_stale()
        pending = self._pending.pop(state, None)
        if pending is None:
            raise ContractError("unknown or expired authorization request: start again")
        spec, client = self._oauth(pending.kind), await self._client(pending.kind)
        tokens = await self.tokens.exchange(spec, client, code, pending.verifier, pending.redirect_uri)
        connection = Connection(kind=pending.kind, owner=pending.owner, account="")
        await self._save_tokens(connection.id, tokens)
        return await self._identify_and_record(connection)

    async def connect(self, kind: str, owner: PersonId | None, secrets: Secrets) -> Connection:
        """Connect a service authorised by typed secrets (API key, app password) or by nothing."""
        connector = self.connector(kind)
        if connector.info.auth is AuthKind.OAUTH2:
            raise ContractError(f"{kind} connects through OAuth: use begin/complete")
        filled = {f.name: secrets.get(f.name) or f.default or "" for f in connector.info.fields}
        missing = [name for name, value in filled.items() if not value]
        if missing:
            raise ContractError(f"missing: {', '.join(missing)}")
        connection = Connection(kind=kind, owner=owner, account="")
        await self.vault.put(connection.id, "secrets", {**secrets, **filled})
        return await self._identify_and_record(connection)

    async def disconnect(self, connection_id: str, *, revoke: bool = True) -> None:
        """Revoke at the provider when possible, then forget every secret and the connection itself.

        `revoke=False` only forgets: when a reconnection replaced it, revoking the old token could revoke
        the whole grant at the provider (Google does), new tokens included.
        """
        connection = self._existing(connection_id)
        spec = self.connectors[connection.kind].info.oauth if connection.kind in self.connectors else None
        tokens = await self.vault.get(connection_id, "tokens")
        if revoke and spec and spec.revoke_url and tokens:
            token = tokens["refresh_token"] or tokens["access_token"]
            # forgetting locally matters more than a failed courtesy call
            with contextlib.suppress(ProviderError):
                await self.tokens.revoke(spec, await self._client(connection.kind), token)
        await self.vault.forget(connection_id)
        await self.journal.publish(ConnectionRemoved(source=self.name, connection_id=connection_id))
        self.connections.pop(connection_id, None)

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

    async def refreshed_token(self, connection: Connection) -> str:
        stored = await self.vault.get(connection.id, "tokens")
        if stored is None:
            raise ProviderError(connection.kind, "no token: connect again", transient=False)
        tokens = _tokens(stored)
        if not tokens.expired(utc_now()):
            return tokens.access_token
        if tokens.refresh_token is None:
            await self._mark(connection, Status.NEEDS_REAUTH, Message.of("connection-no-refresh-token"))
            raise ProviderError(connection.kind, "authorisation expired: connect again", transient=False)
        try:
            fresh = await self.tokens.refresh(
                self._oauth(connection.kind), await self._client(connection.kind), tokens.refresh_token
            )
        except ProviderError as error:
            if not error.transient:
                await self._mark(connection, Status.NEEDS_REAUTH, Message.of("connection-refresh-refused"))
            raise
        kept = replace(fresh, refresh_token=fresh.refresh_token or tokens.refresh_token)
        await self._save_tokens(connection.id, kept)
        return fresh.access_token

    async def _identify_and_record(self, connection: Connection) -> Connection:
        try:
            account = await self.connector(connection.kind).identify(self.access(connection))
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

    async def token(self) -> str:
        return await self._connections.refreshed_token(self._connection)

    async def secrets(self) -> Secrets:
        return await self._connections.vault.get(self._connection.id, "secrets") or {}

    async def load_state(self) -> Mapping[str, str]:
        return await self._connections.vault.get(self._connection.id, "state") or {}

    async def save_state(self, state: Mapping[str, str]) -> None:
        await self._connections.vault.put(self._connection.id, "state", dict(state))


def _tokens(stored: Secrets) -> Tokens:
    expires = stored.get("expires_at")
    return Tokens(
        access_token=stored["access_token"],
        refresh_token=stored.get("refresh_token") or None,
        expires_at=datetime.fromisoformat(expires) if expires else None,
        scopes=tuple(stored.get("scopes", "").split()),
    )
