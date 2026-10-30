"""The server-rendered pages (French HTML forms, no JavaScript), one router per subject.

They predate the web front and go away with it in one cut: `install` is their only entry point.
"""

from typing import cast
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException

from nestor.admin.api.v1.language import household_locale
from nestor.admin.pages import connections, journal, login, memories, people, satellites, tasks, watches
from nestor.admin.pages.errors import Refused
from nestor.admin.pages.guard import LoginRequired, current
from nestor.admin.pages.rendering import Pages, pages_of
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState
from nestor.core import ProviderError


def install(app: FastAPI) -> None:
    admin = cast(AdminState, app.state.admin)
    persona = admin.nestor.config.persona
    phrasebook = Phrasebook(admin.nestor.localizer, household_locale(admin))
    app.state.pages = Pages(assistant=persona.name, timezone=persona.timezone, phrasebook=phrasebook)
    admin.page_errors = _page_error
    for page in (login, journal, connections, satellites, tasks, watches, memories, people):
        app.include_router(page.router, include_in_schema=False)

    @app.get("/", include_in_schema=False)
    async def home() -> RedirectResponse:
        return RedirectResponse("/journal", status_code=303)

    app.add_exception_handler(LoginRequired, _login_required)
    app.add_exception_handler(Refused, _refused)


async def _login_required(request: Request, error: Exception) -> Response:
    assert isinstance(error, LoginRequired)
    target = "/login" if error.next_path in ("", "/") else f"/login?next={quote(error.next_path, safe='')}"
    return RedirectResponse(target, status_code=303)


async def _refused(request: Request, error: Exception) -> Response:
    assert isinstance(error, Refused)
    return _error_page(request, error)


async def _page_error(request: Request, error: Exception) -> Response:
    if isinstance(error, ProviderError):
        message = f"Le service n'a pas pu répondre : {error}. Réessayez dans un instant."
        return _error_page(request, Refused(502, "Service indisponible", message))
    if isinstance(error, HTTPException):
        refused = Refused(error.status_code, "Requête refusée", "Cette adresse ne s'utilise pas ainsi.", back="/")
        return _error_page(request, refused)
    return _error_page(request, Refused(400, "Action impossible", str(error)))


def _error_page(request: Request, error: Refused) -> Response:
    return pages_of(request).render(
        request,
        "error.html",
        current(request),
        status=error.status,
        title=error.title,
        message=error.message,
        back=error.back,
    )
