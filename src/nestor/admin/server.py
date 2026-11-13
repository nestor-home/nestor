"""The admin served by uvicorn inside Nestor's event loop, started and stopped with the assistant."""

import logging

import uvicorn

from nestor.admin.app import create_app
from nestor.admin.auth.api_token import issue_token, token_path
from nestor.admin.settings import AdminSettings
from nestor.core import Component, ContractError, ProviderError
from nestor.runtime import Nestor
from nestor.runtime.server import EmbeddedServer

log = logging.getLogger(__name__)


class AdminServer(Component):
    name = "admin"

    def __init__(self, nestor: Nestor, settings: AdminSettings) -> None:
        self.settings = settings
        self.app = create_app(nestor, settings)
        self.token_file = token_path(nestor.config.data_dir)
        self._server: EmbeddedServer | None = None

    @classmethod
    def from_config(cls, nestor: Nestor) -> "AdminServer":
        config = nestor.config.admin
        if config is None:
            raise ContractError("the configuration has no admin section")
        return cls(nestor, AdminSettings(**config.model_dump()))

    @property
    def port(self) -> int:
        """The port actually listened on (useful when configured as 0)."""
        # uvicorn only creates `servers` once it has started listening: until then, the configured port.
        listening = getattr(self._server, "servers", None) if self._server is not None else None
        if not listening:
            return self.settings.port
        return listening[0].sockets[0].getsockname()[1]

    async def start(self) -> None:
        if self._server is not None:
            return
        admin = self.app.state.admin
        admin.closing.clear()
        admin.api_token = issue_token(self.token_file)
        if not admin.accounts.owners():
            log.warning("no account can sign in to the admin yet: run `nestor accounts create-owner`")
        self._server = server = EmbeddedServer(
            self.app,
            host=self.settings.host,
            port=self.settings.port,
            log_config=uvicorn.config.LOGGING_CONFIG,
            log_level="warning",
            timeout_graceful_shutdown=None,
        )
        try:
            await server.listen(self.name)
        except ProviderError:
            await self.close()
            raise
        log.info("admin listening on http://%s:%s", self.settings.host, self.port)

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        self.app.state.admin.closing.set()  # live streams end, so that the server can stop
        await server.stop()
        self.app.state.admin.api_token = None
        self.token_file.unlink(missing_ok=True)
