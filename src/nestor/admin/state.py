"""What every route shares: the running Nestor, the settings, sessions, throttling, pending OAuth flows."""

import asyncio
from collections.abc import Callable
from typing import cast

from fastapi import Request

from nestor.admin.auth import LoginThrottle, PendingFlows, SessionCookie, SessionStore
from nestor.admin.connecting import Connecting
from nestor.admin.settings import AdminSettings
from nestor.runtime import Nestor
from nestor.runtime.editing import ConfigEditor
from nestor.runtime.secrets import ConfigSecrets


class AdminState:
    def __init__(self, nestor: Nestor, settings: AdminSettings) -> None:
        self.nestor, self.settings = nestor, settings
        self.accounts = nestor.accounts
        self.sessions = SessionStore(ttl_s=settings.session_ttl_s)
        self.cookie = SessionCookie(self.sessions)
        self.throttle = LoginThrottle()
        self.flows = PendingFlows()
        self.connecting = Connecting(nestor.connections, settings, self.flows) if nestor.connections else None
        self.api_token: str | None = None  # issued by the server at startup; the CLI routes are closed until then
        self.closing = asyncio.Event()  # set when the server stops: live streams end instead of holding it
        self.secrets = ConfigSecrets(nestor.vault, nestor.journal) if nestor.vault else None
        self.editor = (
            ConfigEditor(
                nestor.source,
                registry=nestor.registry,
                environ=nestor.environ,
                data_dir=nestor.config.data_dir,
                journal=nestor.journal,
                secrets=self.secrets,
                build=lambda config: Nestor(config, nestor.registry, environ=nestor.environ),
            )
            if nestor.source
            else None
        )
        self.pending_changes: list[str] = []  # written to the file since this process started: a restart applies them
        self.restart: Callable[[], None] = nestor.restart.request

    def base_url(self, request: Request) -> str:
        """The admin's own address, as the household's browsers reach it."""
        return self.settings.base_url(str(request.base_url))

    def secure(self, request: Request) -> bool:
        return self.base_url(request).startswith("https://")


def state(request: Request) -> AdminState:
    return cast(AdminState, request.app.state.admin)
