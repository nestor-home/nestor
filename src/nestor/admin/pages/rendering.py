"""Server-rendered pages: Jinja2 templates (autoescaped), the navigation and what every page shows."""

from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from nestor.admin.auth import Session
from nestor.admin.presentation import Phrasebook
from nestor.core.i18n import Message

TEMPLATES = Path(__file__).parents[1] / "templates"
NAVIGATION = (
    ("/journal", "Journal"),
    ("/connections", "Connexions"),
    ("/satellites", "Satellites"),
    ("/tasks", "Tâches"),
    ("/watches", "Veilles"),
    ("/memories", "Souvenirs"),
    ("/people", "Foyer"),
)


class Pages:
    """Rendered in the household's language (these pages predate accounts' own choices)."""

    def __init__(self, *, assistant: str, timezone: str, phrasebook: Phrasebook) -> None:
        self.assistant, self.timezone, self.phrasebook = assistant, timezone, phrasebook
        self.templates = Jinja2Templates(directory=TEMPLATES)
        self.templates.env.filters["when"] = self.when
        self.templates.env.filters["say"] = phrasebook.text
        self.templates.env.filters["kind"] = phrasebook.kind
        self.templates.env.filters["summary"] = phrasebook.summary

    def when(self, moment: datetime | None) -> str:
        if moment is None:
            return ""
        local = moment.astimezone(ZoneInfo(self.timezone)).replace(tzinfo=None)
        return self.phrasebook.text(Message("admin-when", {"at": local}))  # ty: ignore[invalid-argument-type]

    def render(
        self, request: Request, template: str, session: Session | None, *, status: int = 200, **context: Any
    ) -> HTMLResponse:
        context |= {
            "assistant": self.assistant,
            "session": session if session and session.authenticated else None,
            "csrf": session.csrf if session else "",
            "notices": session.take_notices() if session else [],
            "here": request.url.path,
            "navigation": NAVIGATION,
        }
        return self.templates.TemplateResponse(request, template, context, status_code=status)


def pages_of(request: Request) -> Pages:
    return cast(Pages, request.app.state.pages)
