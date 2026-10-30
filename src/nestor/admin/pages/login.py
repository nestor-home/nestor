"""Logging in with the household password, and out."""

import asyncio
import hmac
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from nestor.admin.auth import Checked, Session, current, forget, remember, verify_password
from nestor.admin.errors import Refused
from nestor.admin.state import state

router = APIRouter()


@router.get("/login")
async def login_page(request: Request, next: str = "/") -> Response:
    admin = state(request)
    session = current(request)
    if session is not None and session.authenticated:
        return RedirectResponse(_safe(next), status_code=303)
    session = session or admin.sessions.open()
    response = admin.pages.render(request, "login.html", session, next=_safe(next))
    remember(response, request, session)
    return response


@router.post("/login")
async def login(
    request: Request,
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
    if not await asyncio.to_thread(verify_password, password, admin.settings.password_hash):
        admin.throttle.failed(client)
        return _again(request, anonymous, next, 401, "Mot de passe incorrect.")
    admin.throttle.succeeded(client)
    admin.sessions.close(anonymous)  # a fresh id once logged in: a planted session id is worth nothing
    session = admin.sessions.open(authenticated=True)
    response = RedirectResponse(_safe(next), status_code=303)
    remember(response, request, session)
    return response


@router.post("/logout")
async def logout(request: Request, session: Checked) -> Response:
    state(request).sessions.close(session)
    response = RedirectResponse("/login", status_code=303)
    forget(response)
    return response


def _again(request: Request, session: Session, next: str, status: int, error: str) -> HTMLResponse:
    return state(request).pages.render(request, "login.html", session, status=status, next=_safe(next), error=error)


def _safe(target: str) -> str:
    """Only a path of this site: never `//evil.example` or `https://…` (no open redirect)."""
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/"
