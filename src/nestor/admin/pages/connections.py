"""Connectors and connections: the catalogue, the household's OAuth clients, connecting, per-tool settings.

Like Home Assistant's Application Credentials, the household registers its own OAuth client with each
provider. The provider sends the browser back to the admin's `/connections/callback` when the admin
is served over HTTPS; otherwise to a public relay page (`relay_url`) that only forwards the browser
here. The relay learns where to forward from the `state` it receives — `<state>.<base64url(callback)>`
— and never sees a token: the code it forwards is worthless without the PKCE verifier kept by Nestor.
"""

import base64
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from nestor.admin.auth import Checked, Flow, LoggedIn, Session
from nestor.admin.errors import Refused
from nestor.admin.settings import CALLBACK_PATH
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
    return admin.pages.render(
        request,
        "connections.html",
        session,
        connectors=connectors,
        accounts=accounts,
        owner=lambda c: _owner(admin, c.owner),
        statuses=STATUS,
        auth=AUTH,
    )


# -- the provider sends the browser back here (declared before /connections/{id}) ------------------


@router.get(CALLBACK_PATH)
async def callback(
    request: Request,
    session: LoggedIn,
    state_: Annotated[str, Query(alias="state")] = "",
    code: str = "",
    error: str = "",
) -> Response:
    admin = state(request)
    connections = _connections(admin)
    issued = state_.split(".", 1)[0]
    flow = session.flows.pop(issued, None)
    if flow is None:
        raise Refused(
            400,
            "Demande d'autorisation inconnue ou expirée",
            "Ce retour ne correspond à aucune connexion lancée depuis cette session. Recommencez depuis le catalogue.",
            back="/connections",
        )
    back = f"/connectors/{flow.kind}"
    if error == "access_denied":
        raise Refused(
            400,
            "Autorisation refusée",
            "L'accès a été refusé sur la page du service : rien n'a été connecté.",
            back=back,
        )
    if error or not code:
        raise Refused(
            400,
            "Le service a renvoyé une erreur",
            f"Erreur indiquée par le service : « {error or 'aucun code'} ».",
            back=back,
        )
    try:
        connection = await connections.complete(issued, code)
    except ContractError:
        raise Refused(
            400, "Demande d'autorisation expirée", "Plus de dix minutes se sont écoulées : recommencez.", back=back
        ) from None
    except ProviderError as failure:
        raise Refused(
            502, "Échange refusé par le service", f"{failure}. Vérifiez le client OAuth puis recommencez.", back=back
        ) from None
    connection = await _settled(connections, connection, flow)
    session.notify(f"Compte {connection.account} connecté.")
    return RedirectResponse(f"/connections/{connection.id}", status_code=303)


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
        raise Refused(400, "Pas de client OAuth", f"{connector.info.title} ne se connecte pas par OAuth.")
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
    replaced = _replaced(connections, kind, str(form.get("replaces", "")))
    if connector.info.auth is AuthKind.OAUTH2:
        return await _authorize(request, admin, session, connections, kind, owner, replaced)
    values = {f.name: str(form.get(f.name, "")).strip() for f in connector.info.fields}
    try:
        connection = await connections.connect(kind, owner, values)
    except ContractError:
        missing = ", ".join(f.label for f in connector.info.fields if not values[f.name])
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
    flow = Flow(kind=kind, owner=owner, replaces=replaced.id if replaced else None)
    connection = await _settled(connections, connection, flow)
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
    return admin.pages.render(
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
    return admin.pages.render(
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
    base = admin.base_url(request)
    redirect_uri = admin.settings.redirect_uri(base)
    if not await connections.has_client(kind):
        return await _connector_page(request, session, kind, status=400, error="Enregistrez d'abord le client OAuth.")
    url = await connections.begin(kind, owner, redirect_uri)
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    issued = dict(query)["state"]
    # the broken connection stays until the new one works: a refused consent loses nothing
    session.flows[issued] = Flow(kind=kind, owner=owner, replaces=replaced.id if replaced else None)
    if redirect_uri != f"{base}{CALLBACK_PATH}":  # through the relay: tell it where this admin is
        target = base64.urlsafe_b64encode(f"{base}{CALLBACK_PATH}".encode()).rstrip(b"=").decode()
        query = [(k, f"{v}.{target}" if k == "state" else v) for k, v in query]
        url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    return RedirectResponse(url, status_code=303)


async def _settled(connections: Connections, connection: Connection, flow: Flow) -> Connection:
    """The new connection, with the settings of the one it replaces (which is then forgotten)."""
    old = connections.connections.get(flow.replaces) if flow.replaces else None
    if old is None:
        return connection
    await connections.disconnect(old.id, revoke=False)  # revoking could take the new grant down with it
    return await connections.configure(
        connection.id, disabled_tools=old.disabled_tools, confirm_writes=old.confirm_writes
    )


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


def _replaced(connections: Connections, kind: str, connection_id: str) -> Connection | None:
    """The broken connection being reconnected; a working one is never replaced."""
    connection = connections.connections.get(connection_id) if connection_id else None
    if connection is None or connection.kind != kind or connection.status is Status.CONNECTED:
        return None
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
