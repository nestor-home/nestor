"""API v1: what the web front and the local command line call, under `/api/v1`.

Errors are `{"error": {"code", "message"}}`; signed-in requests use the session cookie, and unsafe ones
the `X-CSRF-Token` header (see `security`). `api_app()` builds the API alone, for its OpenAPI document.
"""

from typing import Any

from fastapi import APIRouter, Depends, FastAPI

from nestor.admin.api.v1 import openapi
from nestor.admin.api.v1.errors import ApiError, localized, translate
from nestor.admin.api.v1.models import ErrorOut
from nestor.admin.api.v1.routes import (
    accounts,
    agent,
    config,
    connections,
    connectors,
    household,
    i18n,
    journal,
    memories,
    satellites,
    session,
    system,
    tasks,
    voices,
    watches,
)
from nestor.admin.api.v1.security import CSRF_HEADER, json_only

PREFIX = "/api/v1"
# Written out rather than left to FastAPI, which takes them from `http.HTTPStatus`: Python 3.13 renamed
# some phrases (422 is "Unprocessable Content" since RFC 9110), and the document must not depend on it.
ERROR_DESCRIPTIONS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    502: "Bad Gateway",
}
ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorOut, "description": description} for status, description in ERROR_DESCRIPTIONS.items()
}


def router() -> APIRouter:
    api = APIRouter(prefix=PREFIX, dependencies=[Depends(json_only)], responses=ERRORS)
    for resource in (
        session,
        i18n,
        accounts,
        household,
        agent,
        connectors,
        connections,
        satellites,
        journal,
        tasks,
        watches,
        memories,
        system,
        config,
        voices,
    ):
        api.include_router(resource.router)
    return api


def api_app() -> FastAPI:
    """The API without the rest of the admin (no Nestor needed): what `nestor admin openapi` exports."""
    app = FastAPI(
        title=openapi.TITLE,
        version=openapi.VERSION,
        generate_unique_id_function=openapi.operation_id,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router())
    return app


def openapi_text() -> str:
    return openapi.text(api_app())


browser = connections.browser  # `/connections/callback`, outside the API prefix

__all__ = [
    "CSRF_HEADER",
    "PREFIX",
    "ApiError",
    "api_app",
    "browser",
    "localized",
    "openapi_text",
    "router",
    "translate",
]
