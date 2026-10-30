"""Connectors and connections: the catalogue, the household's OAuth clients, connecting, per-tool settings.

The provider sends the browser back to `/connections/callback` (`nestor.admin.api.v1`), which then
shows the new connection at `/connections/<id>`; see `nestor.admin.connecting` for the relay.
"""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from nestor.admin.auth import Session
from nestor.admin.connecting import Connecting
from nestor.admin.pages.errors import Refused
from nestor.admin.pages.guard import Checked, LoggedIn
from nestor.admin.pages.rendering import pages_of
from nestor.admin.state import AdminState, state
from nestor.core import ContractError, PersonId, ProviderError
from nestor.modules.cognition.tools import Risk
from nestor.modules.connectors import AuthKind, Connection, Connections, Connector, Status

router = APIRouter()

STATUS = {Status.CONNECTED: "connectée", Status.NEEDS_REAUTH: "à réautoriser", Status.ERROR: "erreur"}
RISK = {Risk.READ: "lecture", Risk.WRITE: "écriture", Risk.SENSITIVE: "sensible"}
AUTH = {AuthKind.OAUTH2: "OAuth", AuthKind.SECRET: "identifiants", AuthKind.NONE: "aucune"}


# -- catalogue ----------------------------------------------------------------------------------------


@router.get("/connections")
async def catalogue(request: Request, session: LoggedIn) -> HTMLResponse:
    admin = state(request)
    connections = admin.nestor.connections
    connectors = list(connections.connectors.values()) if connections else []
    accounts = sorted(connections.connections.values(), key=lambda c: c.created_at) if connections else []
    return pages_of(request).render(
        request,
        "connections.html",
        session,
        connectors=connectors,
        accounts=accounts,
        owner=lambda c: _owner(admin, c.owner),
        statuses=STATUS,
        auth=AUTH,
    )


# -- one connector: setup guide, OAuth client, connecting ------------------------------------------------


@router.get("/connectors/{kind}")
async def connector_page(request: Request, session: LoggedIn, kind: str, replaces: str = "") -> HTMLResponse:
    return await _connector_page(request, session, kind, replaces=replaces)


@router.post("/connectors/{kind}/client")
async def register_client(
    request: Request,
    session: Checked,
    kind: str,
    client_id: Annotated[str, Form()] = "",
    client_secret: Annotated[str, Form()] = "",
) -> Response:
    connections = _connections(state(request))
    connector = _connector(connections, kind)
    if connector.info.auth is not AuthKind.OAUTH2:
        raise Refused(
            400,
            "Pas de client OAuth",
            f"{pages_of(request).phrasebook.text(connector.info.title)} ne se connecte pas par OAuth.",
        )
    if not client_id.strip() or not client_secret.strip():
        return await _connector_page(
            request, session, kind, status=400, error="Indiquez l'identifiant et le secret du client OAuth."
        )
    await connections.set_client(kind, client_id.strip(), client_secret.strip())
    session.notify("Client OAuth enregistré : vous pouvez connecter un compte.")
    return RedirectResponse(f"/connectors/{kind}", status_code=303)


@router.post("/connectors/{kind}/connect")
async def connect(request: Request, session: Checked, kind: str) -> Response:
    admin = state(request)
    connections = _connections(admin)
    connector = _connector(connections, kind)
    form = await request.form()
    owner = _person(admin, str(form.get("person", "")))
    replaced = _connecting(admin).replaced(kind, str(form.get("replaces", "")))
    if connector.info.auth is AuthKind.OAUTH2:
        return await _authorize(request, admin, session, connections, kind, owner, replaced)
    values = {f.name: str(form.get(f.name, "")).strip() for f in connector.info.fields}
    try:
        connection = await connections.connect(kind, owner, values)
    except ContractError:
        words = pages_of(request).phrasebook
        missing = ", ".join(words.text(f.label) for f in connector.info.fields if not values[f.name])
        return await _connector_page(
            request,
            session,
            kind,
            replaces=replaced.id if replaced else "",
            status=400,
            error=f"Champs manquants : {missing}.",
            values=values,
        )
    except ProviderError as failure:
        return await _connector_page(
            request,
            session,
            kind,
            replaces=replaced.id if replaced else "",
            status=502,
            error=f"Le service a refusé la connexion : {failure}.",
            values=values,
        )
    connection = await _connecting(admin).settled(connection, replaced.id if replaced else None)
    session.notify(f"Compte {connection.account} connecté.")
    return RedirectResponse(f"/connections/{connection.id}", status_code=303)


# -- one connection: status, tools, disconnecting --------------------------------------------------------


@router.get("/connections/{connection_id}")
async def connection_page(request: Request, session: LoggedIn, connection_id: str) -> HTMLResponse:
    admin = state(request)
    connections = _connections(admin)
    connection = _connection(connections, connection_id)
    connector = connections.connectors.get(connection.kind)
    tools = connector.tools(connection, connections.access(connection)) if connector else ()
    return pages_of(request).render(
        request,
        "connection.html",
        session,
        connection=connection,
        connector=connector,
        tools=tools,
        owner=_owner(admin, connection.owner),
        statuses=STATUS,
        risk=RISK,
    )


@router.post("/connections/{connection_id}/tools")
async def configure_tools(request: Request, session: Checked, connection_id: str) -> Response:
    connections = _connections(state(request))
    connection = _connection(connections, connection_id)
    connector = _connector(connections, connection.kind)
    form = await request.form()
    enabled = {str(v) for v in form.getlist("enabled")}
    names = {t.name for t in connector.tools(connection, connections.access(connection))}
    await connections.configure(
        connection_id, disabled_tools=sorted(names - enabled), confirm_writes=form.get("confirm_writes") == "on"
    )
    session.notify("Réglages des outils enregistrés.")
    return RedirectResponse(f"/connections/{connection_id}", status_code=303)


@router.post("/connections/{connection_id}/disconnect")
async def disconnect(
    request: Request, session: Checked, connection_id: str, confirm: Annotated[str, Form()] = ""
) -> Response:
    connections = _connections(state(request))
    connection = _connection(connections, connection_id)
    if confirm != "yes":
        raise Refused(
            400,
            "Confirmation manquante",
            "Cochez la case de confirmation pour déconnecter.",
            back=f"/connections/{connection_id}",
        )
    await connections.disconnect(connection_id)
    session.notify(f"Compte {connection.account} déconnecté : ses accès ont été révoqués et oubliés.")
    return RedirectResponse("/connections", status_code=303)


# -- internals ---------------------------------------------------------------------------------------


async def _connector_page(
    request: Request,
    session: Session,
    kind: str,
    *,
    replaces: str = "",
    status: int = 200,
    error: str = "",
    values: dict[str, str] | None = None,
) -> HTMLResponse:
    admin = state(request)
    connections = _connections(admin)
    connector = _connector(connections, kind)
    info = connector.info
    oauth = info.auth is AuthKind.OAUTH2
    client = await connections.vault.get(f"client:{kind}", "client") if oauth else None
    base = admin.base_url(request)
    shown = {f.name: v for f, v in ((f, (values or {}).get(f.name, "")) for f in info.fields) if not f.secret}
    return pages_of(request).render(
        request,
        "connector.html",
        session,
        status=status,
        info=info,
        oauth=oauth,
        client_id=client["client_id"] if client else None,
        redirect_uri=admin.settings.redirect_uri(base),
        relayed=not base.startswith("https://"),
        people=admin.nestor.household.people,
        replaces=replaces if replaces in connections.connections else "",
        error=error,
        values=shown,
    )


async def _authorize(
    request: Request,
    admin: AdminState,
    session: Session,
    connections: Connections,
    kind: str,
    owner: PersonId | None,
    replaced: Connection | None,
) -> Response:
    if not await connections.has_client(kind):
        return await _connector_page(request, session, kind, status=400, error="Enregistrez d'abord le client OAuth.")
    url = await _connecting(admin).begin(
        kind, owner, base_url=admin.base_url(request), account_id=session.account_id, replaces=replaced
    )
    return RedirectResponse(url, status_code=303)


def _connecting(admin: AdminState) -> Connecting:
    _connections(admin)
    assert admin.connecting is not None  # built whenever connections are
    return admin.connecting


def _connections(admin: AdminState) -> Connections:
    if admin.nestor.connections is None:
        raise Refused(
            404, "Aucun connecteur", "Aucun connecteur n'est installé sur cette instance.", back="/connections"
        )
    return admin.nestor.connections


def _connector(connections: Connections, kind: str) -> Connector:
    connector = connections.connectors.get(kind)
    if connector is None:
        raise Refused(404, "Connecteur inconnu", f"Aucun connecteur « {kind} » n'est installé.", back="/connections")
    return connector


def _connection(connections: Connections, connection_id: str) -> Connection:
    connection = connections.connections.get(connection_id)
    if connection is None:
        raise Refused(
            404, "Connexion inconnue", "Cette connexion n'existe pas ou a été supprimée.", back="/connections"
        )
    return connection


def _person(admin: AdminState, person: str) -> PersonId | None:
    if not person:
        return None
    if person not in {p.id for p in admin.nestor.household.people}:
        raise Refused(400, "Personne inconnue", "Choisissez une personne du foyer.")
    return PersonId(person)


def _owner(admin: AdminState, person: PersonId | None) -> str:
    if person is None:
        return "Tout le foyer"
    return next((p.name for p in admin.nestor.household.people if p.id == person), str(person))
