"""The connectors catalogue, the household's OAuth clients, and what connecting an account takes."""

from fastapi import Request
from pydantic import BaseModel, Field

from nestor.admin.api.v1.shared import Input, connections_of
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState
from nestor.modules.connectors import AuthKind, Connector


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


class ConnectorOut(BaseModel):
    kind: str
    brand: str | None  # the vendor, as a slug ("google")
    title: str
    description: str
    auth: AuthKind
    setup: str  # the step-by-step guide, plain text with line breaks; empty without one
    fields: list[FieldOut]
    inbound: list[str]  # what it brings to watches ("mail")
    oauth: OAuthClientOut | None

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
            oauth=await OAuthClientOut.of(admin, request, info.kind) if info.auth is AuthKind.OAUTH2 else None,
        )


class ClientIn(Input):
    client_id: str
    client_secret: str


class AuthorizationIn(Input):
    person: str | None = None
    replaces: str | None = None  # a broken connection to reconnect: kept until the new one works


class AuthorizationOut(BaseModel):
    authorize_url: str  # navigate the browser there; it comes back to `/connections/callback`


class SecretsIn(Input):
    person: str | None = None
    replaces: str | None = None
    values: dict[str, str] = Field(default_factory=dict)
