"""The admin web application, built on an assembled `Nestor`.

- `/api/v1/…`: the JSON API (accounts, sessions, every resource), the only thing the front talks to;
- `/connections/callback`: where OAuth providers send the browser back, then on to the front;
- `/health`, `/static/…` (the OAuth relay page);
- the server-rendered pages of `nestor.admin.pages`, until the front replaces them;
- every other GET: the web front (`nestor.admin.front`).
"""

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from nestor.admin import front, pages
from nestor.admin.api import v1
from nestor.admin.api.v1.openapi import operation_id
from nestor.admin.settings import AdminSettings
from nestor.admin.state import AdminState, state
from nestor.core import ContractError, ProviderError
from nestor.modules.accounts import AccessDenied
from nestor.runtime import Nestor

STATIC = Path(__file__).parent / "static"
CACHED = ("/static/", "/assets/")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",  # the OAuth callback URL carries a code: never leak it
}


def create_app(nestor: Nestor, settings: AdminSettings) -> FastAPI:
    app = FastAPI(
        title="Nestor — administration",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        generate_unique_id_function=operation_id,
    )
    app.state.admin = AdminState(nestor, settings)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.include_router(v1.router())
    app.include_router(v1.browser)  # before the pages' `/connections/{id}`

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    pages.install(app)
    app.include_router(front.router)  # last: it answers every GET left

    @app.middleware("http")
    async def protect(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if not request.url.path.startswith(CACHED):
            response.headers["Cache-Control"] = "no-store"
        return response

    for error in (v1.ApiError, AccessDenied, ContractError, ProviderError, RequestValidationError, HTTPException):
        app.add_exception_handler(error, _error)
    return app


async def _error(request: Request, error: Exception) -> Response:
    """JSON for the API (and wherever no page renders errors), an HTML page for the server-rendered pages."""
    page_errors = state(request).page_errors
    if request.url.path.startswith("/api/") or page_errors is None:
        return v1.localized(request, error)
    return await page_errors(request, error)
