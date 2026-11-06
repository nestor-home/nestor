"""Connections: accounts plugged into services, their tools, reconnecting and disconnecting them.

Everyone reaches the connections of their own person (`own.connections.manage`); household-wide ones
and everyone else's need `household.connections.manage`. A connection out of reach is reported as
missing, never as forbidden: its existence is not disclosed.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from nestor.admin.api.v1.access import reachable_connection, reaches_connections_of
from nestor.admin.api.v1.connections.callback import connected, failed
from nestor.admin.api.v1.connections.schemas import ConnectionSettingsIn
from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import ConnectionDetail, ConnectionOut, Usage, connections_of
from nestor.admin.settings import CALLBACK_PATH
from nestor.admin.state import state
from nestor.core import ContractError, ProviderError
from nestor.modules.accounts import Scope

router = APIRouter(tags=["connections"])
browser = APIRouter(include_in_schema=False)  # where the provider sends the browser back
Connector = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_CONNECTIONS, Scope.OWN_CONNECTIONS))]


@router.get("/connections")
async def list_connections(request: Request, caller: Connector) -> list[ConnectionOut]:
    admin = state(request)
    connections = sorted(connections_of(admin).connections.values(), key=lambda c: c.created_at)
    usage = await Usage.of(admin)
    return [
        ConnectionOut.of(admin, c, caller.phrasebook, usage)
        for c in connections
        if reaches_connections_of(caller.principal, c.owner)
    ]


@router.get("/connections/{connection_id}")
async def get_connection(request: Request, caller: Connector, connection_id: str) -> ConnectionDetail:
    admin = state(request)
    connection = reachable_connection(admin, caller, connection_id)
    return ConnectionDetail.of(admin, connection, caller.phrasebook, await Usage.of(admin))


@router.patch("/connections/{connection_id}")
async def configure_connection(
    request: Request, caller: Connector, connection_id: str, body: ConnectionSettingsIn
) -> ConnectionDetail:
    """Turn tools off (`disabled_tools`: every tool not listed is on) and choose whether writes ask first."""
    admin = state(request)
    connection = reachable_connection(admin, caller, connection_id)
    usage = await Usage.of(admin)
    if body.disabled_tools is not None:
        known = {t.name for t in ConnectionDetail.of(admin, connection, caller.phrasebook, usage).tools}
        if unknown := set(body.disabled_tools) - known:
            raise ApiError(400, "unknown_tool", tools=", ".join(sorted(unknown)))
    updated = await connections_of(admin).configure(
        connection.id, disabled_tools=body.disabled_tools, confirm_writes=body.confirm_writes
    )
    return ConnectionDetail.of(admin, updated, caller.phrasebook, usage)


@router.delete("/connections/{connection_id}", status_code=204)
async def disconnect_connection(request: Request, caller: Connector, connection_id: str) -> Response:
    """Revoke at the provider when it allows it, then forget every secret of the connection."""
    admin = state(request)
    connection = reachable_connection(admin, caller, connection_id)
    await connections_of(admin).disconnect(connection.id)
    return Response(status_code=204)


@browser.get(CALLBACK_PATH)
async def oauth_callback(
    request: Request,
    state_: Annotated[str, Query(alias="state")] = "",
    code: str = "",
    error: str = "",
) -> RedirectResponse:
    """Back from the provider (directly or through the relay): complete, then show the connection in the
    front — `/connections/<id>?connected=1` — or the catalogue with `?oauth_error=<code>`."""
    admin = state(request)
    issued = state_.split(".", 1)[0]
    connecting, flow = admin.connecting, admin.flows.take(issued)
    if flow is None or connecting is None:  # flows are only started where connections are installed
        return failed("unknown_flow")
    account = admin.accounts.accounts.get(flow.account_id or "")
    if account is None or not reaches_connections_of(account.principal(), flow.owner):
        return failed("forbidden")
    if error == "access_denied":
        return failed("access_denied")
    if error or not code:
        return failed("provider_error")
    try:
        connection = await connecting.connections.complete(issued, code)
    except ContractError:
        return failed("expired")
    except ProviderError:
        return failed("exchange_failed")
    connection = await connecting.settled(connection, flow.replaces)
    return connected(connection.id)
