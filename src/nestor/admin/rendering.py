"""Server-rendered pages: Jinja2 templates (autoescaped), the navigation and what every page shows."""

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from nestor.admin.auth.sessions import Session
from nestor.admin.presentation import french_time
from nestor.core import utc_now

HERE = Path(__file__).parent
NAVIGATION = (
    ("/journal", "Journal"),
    ("/connections", "Connexions"),
    ("/tasks", "Tâches"),
    ("/watches", "Veilles"),
    ("/memories", "Souvenirs"),
    ("/people", "Foyer"),
)


class Pages:
    def __init__(self, *, assistant: str, timezone: str) -> None:
        self.assistant, self.timezone = assistant, timezone
        self.templates = Jinja2Templates(directory=HERE / "templates")
        self.templates.env.filters["when"] = self.when

    def when(self, moment: datetime | None) -> str:
        return french_time(moment, self.timezone, now=utc_now()) if moment else ""

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
