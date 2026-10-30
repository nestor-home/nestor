"""What every page shares: the running Nestor, the settings, sessions, throttling and templates."""

from typing import cast

from fastapi import Request

from nestor.admin.auth.sessions import SessionStore
from nestor.admin.auth.throttle import LoginThrottle
from nestor.admin.rendering import Pages
from nestor.admin.settings import AdminSettings
from nestor.runtime import Nestor


class AdminState:
    def __init__(self, nestor: Nestor, settings: AdminSettings) -> None:
        self.nestor, self.settings = nestor, settings
        self.sessions = SessionStore(ttl_s=settings.session_ttl_s)
        self.throttle = LoginThrottle()
        self.pages = Pages(assistant=nestor.config.persona.name, timezone=nestor.config.persona.timezone)
        self.api_token: str | None = None  # issued by the server at startup; the API is closed until then

    def base_url(self, request: Request) -> str:
        """The admin's own address, as the household's browsers reach it."""
        return self.settings.base_url(str(request.base_url))


def state(request: Request) -> AdminState:
    return cast(AdminState, request.app.state.admin)
