"""FastAPI dependencies of the server-rendered pages: a signed-in account that reads everything (these
pages show the whole household), and the form's CSRF token on every POST."""

import hmac
from typing import Annotated

from fastapi import Depends, Request

from nestor.admin.auth import Session
from nestor.admin.pages.errors import Refused
from nestor.admin.state import state
from nestor.modules.accounts import Scope


class LoginRequired(Exception):
    """No signed-in session: the browser is sent to the login page, then back to `next`."""

    def __init__(self, next_path: str) -> None:
        super().__init__(next_path)
        self.next_path = next_path


def current(request: Request) -> Session | None:
    return state(request).cookie.read(request)


async def authenticated(request: Request) -> Session:
    admin = state(request)
    session = current(request)
    account = admin.accounts.accounts.get(session.account_id or "") if session else None
    if session is None or account is None or account.disabled:
        query = f"?{request.url.query}" if request.url.query else ""
        raise LoginRequired(f"{request.url.path}{query}" if request.method == "GET" else "/")
    if not account.principal().can(Scope.JOURNAL_READ_ALL):
        raise Refused(403, "Accès réservé", "Ces pages sont réservées à l'administration du foyer.")
    return session


async def checked(request: Request, session: Annotated[Session, Depends(authenticated)]) -> Session:
    """A signed-in session whose form carries its CSRF token."""
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
