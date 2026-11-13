"""Connector ports: the service plugins, the vault keeping their secrets, the OAuth token endpoint."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from nestor.core import Component, ContractError
from nestor.modules.cognition.tools import Tool
from nestor.modules.connectors.types import Connection, ConnectorInfo, Discovery, OAuthSpec, Secrets, Service, Tokens
from nestor.modules.initiative import InboundEventSource


class Access(ABC):
    """What connector code gets to reach its account; secrets never leave it towards the model or the log."""

    @abstractmethod
    async def token(self, *, refused: str | None = None) -> str:
        """A valid OAuth access token, refreshed when needed (`ProviderError` when the person must reconnect).
        `refused`: the token the service refused before it expired; a fresh one comes back, refreshed now unless
        another caller already did."""

    @abstractmethod
    async def revoked(self) -> None:
        """The service refused even a fresh token: the connection asks the person to authorise it again."""

    @abstractmethod
    async def secrets(self) -> Secrets:
        """The fields typed by the person (SECRET auth) and non-secret settings."""

    @abstractmethod
    async def load_state(self) -> Mapping[str, str]:
        """The connector's own durable state for this connection (a mailbox cursor…)."""

    @abstractmethod
    async def save_state(self, state: Mapping[str, str]) -> None: ...


class Connector(ABC):
    """A third-party service Nestor can be connected to from the admin.

    Contract:
    - `identify` returns the label of the account being connected once authorised, or raises `ProviderError`;
    - `tools` are named `<kind>_<action>`, or after the service reached (a remote MCP server's `<service>_<tool>`),
      and declare their risk; reading tools are `Risk.READ`;
    - `inbound` returns a source only if `info.inbound` declares kinds, and it resumes from `Access` state;
    - a connector authorised `DISCOVERED` asks its service how in `discover`;
    - a connector that is a `Component` is started and closed with Nestor.
    """

    info: ConnectorInfo

    @abstractmethod
    async def identify(self, connection: Connection, access: Access) -> str: ...

    async def discover(self, settings: Secrets, redirect_uri: str) -> Discovery:
        """How the service at `settings` is authorised, registering an OAuth client sending people back to
        `redirect_uri` when it allows it. `ProviderError` when it cannot be reached or answers nonsense."""
        raise ContractError(f"{self.info.kind} is not authorised by discovery")

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        return ()

    def services(self, connection: Connection) -> Sequence[Service]:
        """What a message names of the account with `@`; by default what `info` declares."""
        return self.info.services

    def brand_of(self, connection: Connection) -> str | None:
        """The mark of the account: the connector's vendor, or the service it reached (a remote MCP server's)."""
        return self.info.brand

    def inbound(self, connection: Connection, access: Access) -> InboundEventSource | None:
        return None

    async def disconnected(self, connection: Connection) -> None:
        """The connection is gone: let go of what was held for it (an open session)."""
        return


class CredentialVault(Component, ABC):
    """Secrets by owner and name, encrypted at rest.

    Contract (checked by `nestor.testing.connectors.CredentialVaultContract`): what is put comes back
    exactly; `forget(owner)` removes every name of that owner; nothing readable on disk.
    """

    @abstractmethod
    async def put(self, owner: str, name: str, secrets: Secrets) -> None: ...

    @abstractmethod
    async def get(self, owner: str, name: str) -> Secrets | None: ...

    @abstractmethod
    async def forget(self, owner: str) -> None: ...


class TokenEndpoint(Component, ABC):
    """OAuth 2 token requests (RFC 6749), done by an HTTP adapter."""

    @abstractmethod
    async def exchange(self, spec: OAuthSpec, client: Secrets, code: str, verifier: str, redirect_uri: str) -> Tokens:
        """Authorization code → tokens. `ProviderError` when refused."""

    @abstractmethod
    async def refresh(self, spec: OAuthSpec, client: Secrets, refresh_token: str) -> Tokens:
        """`ProviderError(transient=False)` when the grant was revoked: the person must reconnect."""

    @abstractmethod
    async def revoke(self, spec: OAuthSpec, client: Secrets, token: str) -> None: ...
