"""The API's OpenAPI document, from which the front generates its client.

Operation ids are the route functions' names in camelCase (`list_journal` → `listJournal`): renaming a
route function is a breaking change for the front.
"""

import json
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

TITLE = "Nestor admin API"
VERSION = "1"


def operation_id(route: APIRoute) -> str:
    head, *rest = route.name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def document(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


def text(app: FastAPI) -> str:
    """The document as committed in `web/openapi.json`: stable key order, one trailing newline."""
    return json.dumps(document(app), indent=2, ensure_ascii=False) + "\n"
