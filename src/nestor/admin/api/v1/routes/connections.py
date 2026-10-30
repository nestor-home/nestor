"""Connections: accounts plugged into services, their tools, reconnecting and disconnecting them.

Everyone reaches the connections of their own person (`own.connections.manage`); household-wide ones
and everyone else's need `household.connections.manage`. A connection out of reach is reported as
missing, never as forbidden: its existence is not disclosed.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.models import Input, People, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.connecting import Connecting
from nestor.admin.presentation import Phrasebook
from nestor.admin.settings import CALLBACK_PATH
from nestor.admin.state import AdminState, state
from nestor.core import ContractError, PersonId, ProviderError
from nestor.modules.accounts import Principal, Scope
from nestor.modules.cognition.tools import Risk
from nestor.modules.connectors import Connection, Connections, Status

router = APIRouter(tags=["connections"])
browser = APIRouter(include_in_schema=False)  # where the provider sends the browser back
Connector = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_CONNECTIONS, Scope.OWN_CONNECTIONS))]


class ToolOut(BaseModel):
    name: str
    description: str
    risk: Risk
    risk_label: str
    enabled: bool


class ConnectionOut(BaseModel):
    id: str
    kind: str
    brand: str | None  # the connector's vendor
    title: str  # the connector's name
    account: str  # what the person recognises: "mathis@gmail.com"
    owner: PersonRef | None  # None: the whole household
    status: Status
    status_label: str
    confirm_writes: bool
    disabled_tools: list[str]
    created_at: datetime


class ConnectionDetail(ConnectionOut):
    tools: list[ToolOut]


class ConnectionSettingsIn(Input):
    disabled_tools: list[str] | None = None
    confirm_writes: bool | None = None


def reaches(principal: Principal, owner: PersonId | None) -> bool:
    return principal.reaches(owner, every=Scope.HOUSEHOLD_CONNECTIONS, own=Scope.OWN_CONNECTIONS)


def connections_of(admin: AdminState) -> Connections:
    if admin.nestor.connections is None:
        raise ApiError(404, "no_connectors")
    return admin.nestor.connections


def connecting_of(admin: AdminState) -> Connecting:
    connections_of(admin)
    assert admin.connecting is not None  # built whenever connections are
    return admin.connecting


def connection_out(admin: AdminState, connection: Connection, words: Phrasebook) -> ConnectionOut:
    connections = connections_of(admin)
    connector = connections.connectors.get(connection.kind)
    return ConnectionOut(
        id=connection.id,
        kind=connection.kind,
        brand=connector.info.brand if connector else None,
        title=words.text(connector.info.title) if connector else connection.kind,
        account=connection.account,
        owner=People(admin.nestor.household).ref(connection.owner),
        status=connection.status,
        status_label=words.connection_status(connection.status),
        confirm_writes=connection.confirm_writes,
        disabled_tools=sorted(connection.disabled_tools),
        created_at=connection.created_at,
    )


def connection_detail(admin: AdminState, connection: Connection, words: Phrasebook) -> ConnectionDetail:
    connections = connections_of(admin)
    connector = connections.connectors.get(connection.kind)
    tools = connector.tools(connection, connections.access(connection)) if connector else ()
    return ConnectionDetail(
        **connection_out(admin, connection, words).model_dump(),
        tools=[
            ToolOut(
                name=t.name,
                description=t.spec.description,
                risk=t.risk,
                risk_label=words.risk(t.risk),
                enabled=t.name not in connection.disabled_tools,
            )
            for t in tools
        ],
    )


def reachable(admin: AdminState, caller: Caller, connection_id: str) -> Connection:
    connection = connections_of(admin).connections.get(connection_id)
    if connection is None or not reaches(caller.principal, connection.owner):
        raise not_found("connection_unknown")
    return connection


@router.get("/connections")
async def list_connections(request: Request, caller: Connector) -> list[ConnectionOut]:
    admin = state(request)
    connections = sorted(connections_of(admin).connections.values(), key=lambda c: c.created_at)
    return [connection_out(admin, c, caller.phrasebook) for c in connections if reaches(caller.principal, c.owner)]


@router.get("/connections/{connection_id}")
async def get_connection(request: Request, caller: Connector, connection_id: str) -> ConnectionDetail:
    admin = state(request)
    return connection_detail(admin, reachable(admin, caller, connection_id), caller.phrasebook)


@router.patch("/connections/{connection_id}")
async def configure_connection(
    request: Request, caller: Connector, connection_id: str, body: ConnectionSettingsIn
) -> ConnectionDetail:
    """Turn tools off (`disabled_tools`: every tool not listed is on) and choose whether writes ask first."""
    admin = state(request)
    connection = reachable(admin, caller, connection_id)
    if body.disabled_tools is not None:
        known = {t.name for t in connection_detail(admin, connection, caller.phrasebook).tools}
        if unknown := set(body.disabled_tools) - known:
            raise ApiError(400, "unknown_tool", tools=", ".join(sorted(unknown)))
    updated = await connections_of(admin).configure(
        connection.id, disabled_tools=body.disabled_tools, confirm_writes=body.confirm_writes
    )
    return connection_detail(admin, updated, caller.phrasebook)


@router.delete("/connections/{connection_id}", status_code=204)
async def disconnect_connection(request: Request, caller: Connector, connection_id: str) -> Response:
    """Revoke at the provider when it allows it, then forget every secret of the connection."""
    admin = state(request)
    connection = reachable(admin, caller, connection_id)
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
        return _failed("unknown_flow")
    account = admin.accounts.accounts.get(flow.account_id or "")
    if account is None or not reaches(account.principal(), flow.owner):
        return _failed("forbidden")
    if error == "access_denied":
        return _failed("access_denied")
    if error or not code:
        return _failed("provider_error")
    try:
        connection = await connecting.connections.complete(issued, code)
    except ContractError:
        return _failed("expired")
    except ProviderError:
        return _failed("exchange_failed")
    connection = await connecting.settled(connection, flow.replaces)
    return RedirectResponse(f"/connections/{connection.id}?connected=1", status_code=303)


def _failed(code: str) -> RedirectResponse:
    return RedirectResponse(f"/connections?oauth_error={code}", status_code=303)
