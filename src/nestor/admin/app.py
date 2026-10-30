"""The admin web application, built on an assembled `Nestor`.

Every page needs the household password, except the login page, `/health`, static files and the OAuth
callback's own check (it needs the session that started the flow). Pages are plain HTML forms: they
work without JavaScript.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from nestor.admin.auth.guard import LoginRequired, current
from nestor.admin.errors import Refused
from nestor.admin.pages import connections, journal, login, memories, people, tasks, watches
from nestor.admin.rendering import HERE
from nestor.admin.settings import AdminSettings
from nestor.admin.state import AdminState, state
from nestor.core import ContractError, ProviderError
from nestor.runtime import Nestor

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",  # the OAuth callback URL carries a code: never leak it
}


def create_app(nestor: Nestor, settings: AdminSettings) -> FastAPI:
    app = FastAPI(title="Nestor — administration", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.admin = AdminState(nestor, settings)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    for page in (login, journal, connections, tasks, watches, memories, people):
        app.include_router(page.router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def home() -> RedirectResponse:
        return RedirectResponse("/journal", status_code=303)

    @app.middleware("http")
    async def protect(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_exception_handler(LoginRequired, _login_required)
    app.add_exception_handler(Refused, _refused)
    app.add_exception_handler(ContractError, _contract_error)
    app.add_exception_handler(ProviderError, _provider_error)
    app.add_exception_handler(HTTPException, _http_error)
    return app


async def _login_required(request: Request, error: Exception) -> Response:
    assert isinstance(error, LoginRequired)
    target = "/login" if error.next_path in ("", "/") else f"/login?next={quote(error.next_path, safe='')}"
    return RedirectResponse(target, status_code=303)


async def _refused(request: Request, error: Exception) -> Response:
    assert isinstance(error, Refused)
    return _error_page(request, error)


async def _contract_error(request: Request, error: Exception) -> Response:
    return _error_page(request, Refused(400, "Action impossible", str(error)))


async def _provider_error(request: Request, error: Exception) -> Response:
    message = f"Le service n'a pas pu répondre : {error}. Réessayez dans un instant."
    return _error_page(request, Refused(502, "Service indisponible", message))


async def _http_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, HTTPException)
    if error.status_code == 404:
        return _error_page(request, Refused(404, "Page introuvable", "Cette page n'existe pas.", back="/"))
    return _error_page(request, Refused(error.status_code, "Requête refusée", "Cette adresse ne s'utilise pas ainsi."))


def _error_page(request: Request, error: Refused) -> Response:
    session = current(request)
    return state(request).pages.render(
        request, "error.html", session, status=error.status, title=error.title, message=error.message, back=error.back
    )
