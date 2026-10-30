"""Signing in with an account, and out (server-rendered pages)."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from nestor.admin.auth import Session
from nestor.admin.pages.errors import Refused
from nestor.admin.pages.guard import Checked, current
from nestor.admin.pages.rendering import pages_of
from nestor.admin.state import state

router = APIRouter()


@router.get("/login")
async def login_page(request: Request, next: str = "/") -> Response:
    admin = state(request)
    session = current(request)
    if session is not None and session.authenticated:
        return RedirectResponse(_safe(next), status_code=303)
    session = session or admin.sessions.open()
    response = pages_of(request).render(request, "login.html", session, next=_safe(next))
    admin.cookie.give(response, session, secure=admin.secure(request))
    return response


@router.post("/login")
async def login(
    request: Request,
    login: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
) -> Response:
    admin = state(request)
    anonymous = current(request)
    if anonymous is None or not hmac.compare_digest(csrf, anonymous.csrf):
        raise Refused(403, "Formulaire refusé", "La page de connexion a expiré : rechargez-la.", back="/login")
    client = request.client.host if request.client else "inconnu"
    if wait := admin.throttle.wait_s(client):
        minutes = max(1, round(wait / 60))
        return _again(request, anonymous, next, 429, f"Trop d'essais. Réessayez dans {minutes} min.")
    account = await admin.accounts.authenticate(login, password, client=client)
    if account is None:
        admin.throttle.failed(client)
        return _again(request, anonymous, next, 401, "Identifiant ou mot de passe incorrect.")
    admin.throttle.succeeded(client)
    admin.sessions.close(anonymous)  # a fresh id once signed in: a planted session id is worth nothing
    session = admin.sessions.open(account.id)
    response = RedirectResponse(_safe(next), status_code=303)
    admin.cookie.give(response, session, secure=admin.secure(request))
    return response


@router.post("/logout")
async def logout(request: Request, session: Checked) -> Response:
    state(request).sessions.close(session)
    response = RedirectResponse("/login", status_code=303)
    state(request).cookie.clear(response)
    return response


def _again(request: Request, session: Session, next: str, status: int, error: str) -> HTMLResponse:
    return pages_of(request).render(request, "login.html", session, status=status, next=_safe(next), error=error)


def _safe(target: str) -> str:
    """Only a path of this site: never `//evil.example` or `https://…` (no open redirect)."""
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/"
