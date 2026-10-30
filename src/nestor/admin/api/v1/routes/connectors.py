"""The connectors catalogue: what can be plugged in, the household's OAuth clients, connecting an account.

Connecting for someone needs to reach that person: one's own person with `own.connections.manage`,
anyone or the whole household with `household.connections.manage`. Without `person`, the connection is
for the caller's own person when that is all they reach, else for the whole household.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.models import Input, People
from nestor.admin.api.v1.routes.connections import (
    ConnectionDetail,
    connecting_of,
    connection_detail,
    connections_of,
    reachable,
    reaches,
)
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import AdminState, state
from nestor.core import PersonId, ProviderError
from nestor.modules.accounts import Scope
from nestor.modules.connectors import AuthKind, Connection, Connector

router = APIRouter(tags=["connectors"])
Plugging = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_CONNECTIONS, Scope.OWN_CONNECTIONS))]
Household = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_CONNECTIONS))]

AUTH = {AuthKind.OAUTH2: "OAuth", AuthKind.SECRET: "identifiants", AuthKind.NONE: "aucune"}


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


class ConnectorOut(BaseModel):
    kind: str
    brand: str | None  # the vendor, as a slug ("google")
    title: str
    description: str
    auth: AuthKind
    auth_label: str
    setup: str  # the step-by-step guide, plain text with line breaks
    fields: list[FieldOut]
    inbound: list[str]  # what it brings to watches ("mail")
    oauth: OAuthClientOut | None


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


@router.get("/connectors")
async def list_connectors(request: Request, caller: Plugging) -> list[ConnectorOut]:
    admin = state(request)
    return [await _connector_out(admin, request, c) for c in connections_of(admin).connectors.values()]


@router.get("/connectors/{kind}")
async def get_connector(request: Request, caller: Plugging, kind: str) -> ConnectorOut:
    admin = state(request)
    return await _connector_out(admin, request, _connector(admin, kind))


@router.put("/connectors/{kind}/client")
async def register_connector_client(request: Request, caller: Household, kind: str, body: ClientIn) -> ConnectorOut:
    """The household's own OAuth client at the provider (its secret is kept encrypted, never shown again)."""
    admin = state(request)
    connector = _connector(admin, kind)
    if connector.info.auth is not AuthKind.OAUTH2:
        raise ApiError(400, "not_oauth", f"{connector.info.title} ne se connecte pas par OAuth.")
    if not body.client_id.strip() or not body.client_secret.strip():
        raise ApiError(400, "client_incomplete", "Indiquez l'identifiant et le secret du client OAuth.")
    await connections_of(admin).set_client(kind, body.client_id.strip(), body.client_secret.strip())
    return await _connector_out(admin, request, connector)


@router.post("/connectors/{kind}/authorizations")
async def begin_authorization(request: Request, caller: Plugging, kind: str, body: AuthorizationIn) -> AuthorizationOut:
    admin = state(request)
    connector = _connector(admin, kind)
    if connector.info.auth is not AuthKind.OAUTH2:
        raise ApiError(400, "not_oauth", f"{connector.info.title} ne se connecte pas par OAuth.")
    owner = _owner(admin, caller, body.person)
    replaced = _replaced(admin, caller, kind, body.replaces)
    if not await connections_of(admin).has_client(kind):
        raise ApiError(400, "client_missing", "Enregistrez d'abord le client OAuth de ce service.")
    url = await connecting_of(admin).begin(
        kind, owner, base_url=admin.base_url(request), account_id=caller.account_id, replaces=replaced
    )
    return AuthorizationOut(authorize_url=url)


@router.post("/connectors/{kind}/connections", status_code=201)
async def connect_with_secrets(request: Request, caller: Plugging, kind: str, body: SecretsIn) -> ConnectionDetail:
    """Connect a service authorised by typed fields (an app password, a server…)."""
    admin = state(request)
    connector = _connector(admin, kind)
    if connector.info.auth is AuthKind.OAUTH2:
        raise ApiError(400, "oauth", f"{connector.info.title} se connecte par OAuth.")
    owner = _owner(admin, caller, body.person)
    replaced = _replaced(admin, caller, kind, body.replaces)
    values = {f.name: body.values.get(f.name, "").strip() for f in connector.info.fields}
    if missing := [f.label for f in connector.info.fields if not values[f.name] and f.default is None]:
        raise ApiError(400, "fields_missing", f"Champs manquants : {', '.join(missing)}.")
    try:
        connection = await connections_of(admin).connect(kind, owner, values)
    except ProviderError as failure:
        raise ApiError(502, "provider_refused", f"Le service a refusé la connexion : {failure}.") from None
    connection = await connecting_of(admin).settled(connection, replaced.id if replaced else None)
    return connection_detail(admin, connection)


async def _connector_out(admin: AdminState, request: Request, connector: Connector) -> ConnectorOut:
    info = connector.info
    oauth = None
    if info.auth is AuthKind.OAUTH2:
        client = await connections_of(admin).vault.get(f"client:{info.kind}", "client")
        base = admin.base_url(request)
        redirect_uri = admin.settings.redirect_uri(base)
        oauth = OAuthClientOut(
            registered=client is not None,
            client_id=client["client_id"] if client else None,
            redirect_uri=redirect_uri,
            relayed=redirect_uri == admin.settings.relay_url,
        )
    return ConnectorOut(
        kind=info.kind,
        brand=info.brand,
        title=info.title,
        description=info.description,
        auth=info.auth,
        auth_label=AUTH[info.auth],
        setup=info.setup,
        fields=[FieldOut(name=f.name, label=f.label, secret=f.secret, default=f.default) for f in info.fields],
        inbound=list(info.inbound),
        oauth=oauth,
    )


def _connector(admin: AdminState, kind: str) -> Connector:
    connector = connections_of(admin).connectors.get(kind)
    if connector is None:
        raise not_found(f"Aucun connecteur « {kind} » n'est installé.")
    return connector


def _owner(admin: AdminState, caller: Caller, person: str | None) -> PersonId | None:
    if person is not None and not People(admin.nestor.household).known(person):
        raise ApiError(400, "unknown_person", "Choisissez une personne du foyer.")
    if person is not None:
        chosen = PersonId(person)
    else:
        chosen = None if caller.principal.can(Scope.HOUSEHOLD_CONNECTIONS) else caller.principal.person
    if not reaches(caller.principal, chosen):
        raise ApiError(403, "forbidden", "Vous ne pouvez connecter un compte que pour vous-même.")
    return chosen


def _replaced(admin: AdminState, caller: Caller, kind: str, connection_id: str | None) -> Connection | None:
    if connection_id is None:
        return None
    reachable(admin, caller, connection_id)
    return connecting_of(admin).replaced(kind, connection_id)
