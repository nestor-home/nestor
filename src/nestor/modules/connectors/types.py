"""Connectors and connections: what a service offers, and an account plugged into it for a person."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from nestor.core import PersonId, new_id, utc_now


class AuthKind(StrEnum):
    OAUTH2 = "oauth2"  # authorization code + PKCE, tokens refreshed by the broker
    SECRET = "secret"  # fields typed by the person (API key, app password…)
    NONE = "none"


@dataclass(frozen=True, slots=True, kw_only=True)
class OAuthSpec:
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    revoke_url: str | None = None
    extra_authorize: Mapping[str, str] = field(default_factory=dict)  # e.g. access_type=offline, prompt=consent
    client_credentials: bool = True  # the person registers their own OAuth client (Home Assistant's model)


@dataclass(frozen=True, slots=True, kw_only=True)
class SecretField:
    name: str
    label: str
    secret: bool = True  # never shown back once saved


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorInfo:
    """What the admin catalogue shows, and what the connector needs to be connected."""

    kind: str  # "google", "imap", "mcp"
    title: str
    description: str
    auth: AuthKind
    oauth: OAuthSpec | None = None
    fields: tuple[SecretField, ...] = ()  # SECRET auth, and non-OAuth settings (server URL…)
    setup: str = ""  # step-by-step guide shown before connecting (create an OAuth client…)
    inbound: tuple[str, ...] = ()  # kinds of items it can feed watches with ("mail")


class Status(StrEnum):
    CONNECTED = "connected"
    NEEDS_REAUTH = "needs_reauth"  # refresh refused: the person must connect again
    ERROR = "error"


@dataclass(frozen=True, slots=True, kw_only=True)
class Connection:
    kind: str
    owner: PersonId | None  # whose account it is; None for a household-wide service
    account: str  # what the person recognises: "mathis@gmail.com"
    status: Status = Status.CONNECTED
    disabled_tools: frozenset[str] = frozenset()
    confirm_writes: bool = True  # tools that write or send ask the person first
    id: str = field(default_factory=lambda: new_id()[:10])
    created_at: datetime = field(default_factory=utc_now)

    def with_status(self, status: Status) -> "Connection":
        return replace(self, status=status)


type Secrets = Mapping[str, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class Tokens:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scopes: tuple[str, ...] = ()

    def expired(self, now: datetime, margin_s: float = 60.0) -> bool:
        return self.expires_at is not None and (self.expires_at - now).total_seconds() < margin_s
