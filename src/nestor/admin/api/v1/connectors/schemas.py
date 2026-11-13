"""The connectors catalogue, the household's OAuth clients, and what connecting an account takes."""

from fastapi import Request
from pydantic import BaseModel, Field

from nestor.admin.api.v1.access import connections_of
from nestor.admin.api.v1.connections.schemas import ConnectionDetail
from nestor.admin.api.v1.shared import Input
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState
from nestor.modules.connectors import AuthKind, Connector

OAUTH = (AuthKind.OAUTH2, AuthKind.DISCOVERED)  # what the person may be sent to consent for


class FieldOut(BaseModel):
    name: str
    label: str
    secret: bool  # typed once, never shown back
    default: str | None


class OAuthClientOut(BaseModel):
    registered: bool
    client_id: str | None  # not a secret; the client secret is never returned
    redirect_uri: str  # what to declare at the provider
    relayed: bool  # the redirect goes through the public relay (the admin is not on HTTPS nor this machine)

    @classmethod
    async def of(cls, admin: AdminState, request: Request, kind: str) -> "OAuthClientOut":
        client = await connections_of(admin).vault.get(f"client:{kind}", "client")
        redirect_uri = admin.settings.redirect_uri(admin.base_url(request))
        return cls(
            registered=client is not None,
            client_id=client["client_id"] if client else None,
            redirect_uri=redirect_uri,
            relayed=redirect_uri == admin.settings.relay_url,
        )


class PresetOut(BaseModel):
    name: str  # the service's own name
    brand: str | None
    values: dict[str, str]  # what it fills in the connector's fields


class ConnectorOut(BaseModel):
    kind: str
    brand: str | None  # the vendor, as a slug ("google")
    title: str
    description: str
    auth: AuthKind
    setup: str  # the step-by-step guide, plain text with line breaks; empty without one
    fields: list[FieldOut]
    inbound: list[str]  # what it brings to watches ("mail")
    presets: list[PresetOut]  # well-known services, filling the fields
    oauth: OAuthClientOut | None  # the household's client; for a discovered service, where people come back

    @classmethod
    async def of(cls, admin: AdminState, request: Request, connector: Connector, words: Phrasebook) -> "ConnectorOut":
        info = connector.info
        return cls(
            kind=info.kind,
            brand=info.brand,
            title=words.text(info.title),
            description=words.text(info.description),
            auth=info.auth,
            setup=words.text(info.setup) if info.setup else "",
            fields=[
                FieldOut(name=f.name, label=words.text(f.label), secret=f.secret, default=f.default)
                for f in info.fields
            ],
            inbound=list(info.inbound),
            presets=[PresetOut(name=p.name, brand=p.brand, values=dict(p.values)) for p in info.presets],
            oauth=await OAuthClientOut.of(admin, request, info.kind) if info.auth in OAUTH else None,
        )


class ClientIn(Input):
    client_id: str
    client_secret: str


class AuthorizationIn(Input):
    person: str | None = None
    replaces: str | None = None  # a broken connection to reconnect: kept until the new one works
    values: dict[str, str] = Field(default_factory=dict)  # a discovered service's fields (its address…)


class AuthorizationOut(BaseModel):
    """Either where the browser goes, or, for a discovered service that needs no consent, the connection made."""

    authorize_url: str | None  # navigate the browser there; it comes back to `/connections/callback`
    connection: ConnectionDetail | None


class SecretsIn(Input):
    person: str | None = None
    replaces: str | None = None
    values: dict[str, str] = Field(default_factory=dict)
