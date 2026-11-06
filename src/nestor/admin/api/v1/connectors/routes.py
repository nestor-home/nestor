"""The connectors catalogue: what can be plugged in, the household's OAuth clients, connecting an account.

Connecting for someone needs to reach that person: one's own person with `own.connections.manage`,
anyone or the whole household with `household.connections.manage`. Without `person`, the connection is
for the caller's own person when that is all they reach, else for the whole household.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor.admin.api.v1.access import connection_owner, replaced_connection
from nestor.admin.api.v1.connectors.schemas import (
    AuthorizationIn,
    AuthorizationOut,
    ClientIn,
    ConnectorOut,
    SecretsIn,
)
from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.language import reader_locale
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import ConnectionDetail, Usage, connecting_of, connections_of
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import state
from nestor.core import ProviderError
from nestor.modules.accounts import Scope
from nestor.modules.connectors import AuthKind, Connector

router = APIRouter(tags=["connectors"])
Plugging = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_CONNECTIONS, Scope.OWN_CONNECTIONS))]
Household = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_CONNECTIONS))]


def connector_of(request: Request, kind: str) -> Connector:
    """The installed connector of that kind, else 404."""
    connector = connections_of(state(request)).connectors.get(kind)
    if connector is None:
        raise ApiError(404, "connector_unknown", kind=kind)
    return connector


Plugged = Annotated[Connector, Depends(connector_of)]


def oauth_connector(request: Request, connector: Plugged) -> Connector:
    """The connector, when it is authorised through OAuth; else 400."""
    if connector.info.auth is not AuthKind.OAUTH2:
        title = Phrasebook(state(request).nestor.localizer, reader_locale(request)).text(connector.info.title)
        raise ApiError(400, "not_oauth", connector=title)
    return connector


OAuthPlugged = Annotated[Connector, Depends(oauth_connector)]


@router.get("/connectors")
async def list_connectors(request: Request, caller: Plugging) -> list[ConnectorOut]:
    admin = state(request)
    connectors = connections_of(admin).connectors.values()
    return [await ConnectorOut.of(admin, request, c, caller.phrasebook) for c in connectors]


@router.get("/connectors/{kind}")
async def get_connector(request: Request, caller: Plugging, connector: Plugged) -> ConnectorOut:
    return await ConnectorOut.of(state(request), request, connector, caller.phrasebook)


@router.put("/connectors/{kind}/client")
async def register_connector_client(
    request: Request, caller: Household, connector: OAuthPlugged, body: ClientIn
) -> ConnectorOut:
    """The household's own OAuth client at the provider (its secret is kept encrypted, never shown again)."""
    admin = state(request)
    if not body.client_id.strip() or not body.client_secret.strip():
        raise ApiError(400, "client_incomplete")
    await connections_of(admin).set_client(connector.info.kind, body.client_id.strip(), body.client_secret.strip())
    return await ConnectorOut.of(admin, request, connector, caller.phrasebook)


@router.post("/connectors/{kind}/authorizations")
async def begin_authorization(
    request: Request, caller: Plugging, connector: OAuthPlugged, body: AuthorizationIn
) -> AuthorizationOut:
    admin = state(request)
    kind = connector.info.kind
    owner = connection_owner(admin, caller, body.person)
    replaced = replaced_connection(admin, caller, kind, body.replaces)
    if not await connections_of(admin).has_client(kind):
        raise ApiError(400, "client_missing")
    url = await connecting_of(admin).begin(
        kind, owner, base_url=admin.base_url(request), account_id=caller.account_id, replaces=replaced
    )
    return AuthorizationOut(authorize_url=url)


@router.post("/connectors/{kind}/connections", status_code=201)
async def connect_with_secrets(
    request: Request, caller: Plugging, connector: Plugged, body: SecretsIn
) -> ConnectionDetail:
    """Connect a service authorised by typed fields (an app password, a server…)."""
    admin = state(request)
    info = connector.info
    if info.auth is AuthKind.OAUTH2:
        raise ApiError(400, "oauth", connector=caller.phrasebook.text(info.title))
    owner = connection_owner(admin, caller, body.person)
    replaced = replaced_connection(admin, caller, info.kind, body.replaces)
    values = {f.name: body.values.get(f.name, "").strip() for f in info.fields}
    if missing := [f.label for f in info.fields if not values[f.name] and f.default is None]:
        raise ApiError(400, "fields_missing", fields=", ".join(caller.phrasebook.text(m) for m in missing))
    try:
        connection = await connections_of(admin).connect(info.kind, owner, values)
    except ProviderError as failure:
        raise ApiError(502, "provider_refused", detail=str(failure)) from None
    connection = await connecting_of(admin).settled(connection, replaced.id if replaced else None)
    return ConnectionDetail.of(admin, connection, caller.phrasebook, await Usage.of(admin))
