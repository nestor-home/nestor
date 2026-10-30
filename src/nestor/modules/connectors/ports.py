"""Connector ports: the service plugins, the vault keeping their secrets, the OAuth token endpoint."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from nestor.core import Component
from nestor.modules.cognition.tools import Tool
from nestor.modules.connectors.types import Connection, ConnectorInfo, OAuthSpec, Secrets, Tokens
from nestor.modules.initiative import InboundEventSource


class Access(ABC):
    """What connector code gets to reach its account; secrets never leave it towards the model or the log."""

    @abstractmethod
    async def token(self) -> str:
        """A valid OAuth access token, refreshed when needed (`ProviderError` when the person must reconnect)."""

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

    Contract (checked by `nestor.testing.connectors.ConnectorContract`):
    - `identify` returns the account label once authorised, or raises `ProviderError`;
    - `tools` are named `<kind>_<action>` and declare their risk; reading tools are `Risk.READ`;
    - `inbound` returns a source only if `info.inbound` declares kinds, and it resumes from `Access` state.
    """

    info: ConnectorInfo

    @abstractmethod
    async def identify(self, access: Access) -> str: ...

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        return ()

    def inbound(self, connection: Connection, access: Access) -> InboundEventSource | None:
        return None


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
