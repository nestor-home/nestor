"""API v1 assembled: one router per resource under `/api/v1`, the errors every route may answer, and the
OpenAPI document the web front generates its client from.

Operation ids are the route functions' names in camelCase (`list_journal` → `listJournal`): renaming a
route function is a breaking change for the front.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute

from nestor.admin.api.v1.accounts import routes as accounts
from nestor.admin.api.v1.agent import routes as agent
from nestor.admin.api.v1.chat import routes as chat
from nestor.admin.api.v1.config import routes as config
from nestor.admin.api.v1.config.schemas import ConfigSchemaOut
from nestor.admin.api.v1.confirmations import routes as confirmations
from nestor.admin.api.v1.connections import routes as connections
from nestor.admin.api.v1.connectors import routes as connectors
from nestor.admin.api.v1.errors import ErrorOut
from nestor.admin.api.v1.home import routes as home
from nestor.admin.api.v1.household import routes as household
from nestor.admin.api.v1.i18n import routes as i18n
from nestor.admin.api.v1.journal import routes as journal
from nestor.admin.api.v1.memories import routes as memories
from nestor.admin.api.v1.messages import routes as messages
from nestor.admin.api.v1.satellites import routes as satellites
from nestor.admin.api.v1.schedules import routes as schedules
from nestor.admin.api.v1.security import json_only
from nestor.admin.api.v1.session import routes as session
from nestor.admin.api.v1.system import routes as system
from nestor.admin.api.v1.tasks import routes as tasks
from nestor.admin.api.v1.voices import routes as voices
from nestor.admin.api.v1.watches import routes as watches
from nestor.admin.presentation import CATEGORIES, Phrasebook
from nestor.core.i18n import Localizer
from nestor.modules.accounts import GRANTS
from nestor.runtime import Registry
from nestor.runtime.editing import ConfigSchema
from nestor.runtime.plugins import BUILT_IN

PREFIX = "/api/v1"
TITLE = "Nestor admin API"
VERSION = "1"
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
RESOURCES = (
    session,
    i18n,
    accounts,
    household,
    home,
    agent,
    chat,
    connectors,
    connections,
    satellites,
    journal,
    tasks,
    watches,
    schedules,
    messages,
    confirmations,
    memories,
    system,
    config,
    voices,
)
browser = connections.browser  # `/connections/callback`, outside the API prefix


def operation_id(route: APIRoute) -> str:
    head, *rest = route.name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def router() -> APIRouter:
    api = APIRouter(prefix=PREFIX, dependencies=[Depends(json_only)], responses=ERRORS)
    for resource in RESOURCES:
        api.include_router(resource.router)
    return api


def api_app() -> FastAPI:
    """The API without the rest of the admin (no Nestor needed): what `nestor admin openapi` exports."""
    app = FastAPI(
        title=TITLE,
        version=VERSION,
        generate_unique_id_function=operation_id,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router())
    return app


def openapi_text() -> str:
    """The document as committed in `web/openapi.json`: stable key order, one trailing newline."""
    return json.dumps(api_app().openapi(), indent=2, ensure_ascii=False) + "\n"


def mock_answers(localizer: Localizer) -> dict[str, str]:
    """What the admin's mock server answers as an instance of this version would, by file name: the configuration's
    schemas in each shipped locale (Nestor's own plugins only, whatever else is installed), the journal kind of each
    event type, and the scopes each role grants, said with Nestor's own catalogue. What `nestor admin mocks` writes."""
    schema = ConfigSchema(Registry.installed(distribution=BUILT_IN))
    answers: dict[str, Any] = {
        f"config-schema.{locale}.json": ConfigSchemaOut.of(schema, Phrasebook(localizer, locale)).model_dump(
            mode="json"
        )
        for locale in localizer.locales
    }
    answers["journal-kinds.json"] = {e.event_type: kind for kind, events in CATEGORIES.items() for e in events}
    answers["role-scopes.json"] = {role: sorted(scopes) for role, scopes in GRANTS.items()}
    return {name: json.dumps(answer, indent=2, ensure_ascii=False) + "\n" for name, answer in sorted(answers.items())}
