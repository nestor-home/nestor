"""FastAPI dependencies: every page needs a logged-in session, every form its CSRF token."""

import hmac
from typing import Annotated

from fastapi import Depends, Request, Response

from nestor.admin.auth.sessions import Session
from nestor.admin.errors import Refused
from nestor.admin.state import state

COOKIE = "nestor_admin"


class LoginRequired(Exception):
    """No logged-in session: the browser is sent to the login page, then back to `next`."""

    def __init__(self, next_path: str) -> None:
        super().__init__(next_path)
        self.next_path = next_path


def remember(response: Response, request: Request, session: Session) -> None:
    """Hand the browser its session cookie: HttpOnly, SameSite=Lax, Secure when the admin is served over HTTPS."""
    admin = state(request)
    response.set_cookie(
        COOKIE,
        admin.sessions.cookie(session),
        max_age=int(admin.settings.session_ttl_s),
        httponly=True,
        samesite="lax",
        secure=admin.base_url(request).startswith("https://"),
        path="/",
    )


def forget(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def current(request: Request) -> Session | None:
    return state(request).sessions.find(request.cookies.get(COOKIE))


async def authenticated(request: Request) -> Session:
    session = current(request)
    if session is None or not session.authenticated:
        query = f"?{request.url.query}" if request.url.query else ""
        raise LoginRequired(f"{request.url.path}{query}" if request.method == "GET" else "/")
    return session


async def checked(request: Request, session: Annotated[Session, Depends(authenticated)]) -> Session:
    """A logged-in session whose form carries its CSRF token."""
    token = (await request.form()).get("csrf")
    if not isinstance(token, str) or not hmac.compare_digest(token, session.csrf):
        raise Refused(
            403,
            "Formulaire refusé",
            "Ce formulaire a expiré ou ne vient pas de l'administration. Rechargez la page et recommencez.",
        )
    return session


LoggedIn = Annotated[Session, Depends(authenticated)]
Checked = Annotated[Session, Depends(checked)]
