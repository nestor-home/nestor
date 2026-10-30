"""The admin served by uvicorn inside Nestor's event loop, started and stopped with the assistant."""

import asyncio
import contextlib
import logging
from collections.abc import Generator

import uvicorn

from nestor.admin.app import create_app
from nestor.admin.auth.api_token import issue_token, token_path
from nestor.admin.settings import AdminSettings
from nestor.core import Component, ContractError, ProviderError
from nestor.runtime import Nestor

log = logging.getLogger(__name__)


class _Server(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield  # the runtime owns SIGINT/SIGTERM and closes the admin itself


class AdminServer(Component):
    name = "admin"

    def __init__(self, nestor: Nestor, settings: AdminSettings) -> None:
        self.settings = settings
        self.app = create_app(nestor, settings)
        self.token_file = token_path(nestor.config.data_dir)
        self._server: _Server | None = None
        self._serving: asyncio.Task[None] | None = None

    @classmethod
    def from_config(cls, nestor: Nestor) -> "AdminServer":
        config = nestor.config.admin
        if config is None:
            raise ContractError("the configuration has no admin section")
        if config.password_hash is not None:
            log.warning(
                "admin.password_hash is no longer used: accounts replaced it. Create the first owner with "
                "`nestor accounts create-owner`, then remove the line"
            )
        return cls(nestor, AdminSettings(**config.model_dump(exclude={"password_hash"})))

    @property
    def port(self) -> int:
        """The port actually listened on (useful when configured as 0)."""
        if self._server is None or not self._server.servers:
            return self.settings.port
        return self._server.servers[0].sockets[0].getsockname()[1]

    async def start(self) -> None:
        if self._serving is not None:
            return
        config = uvicorn.Config(
            self.app, host=self.settings.host, port=self.settings.port, lifespan="off", log_level="warning"
        )
        admin = self.app.state.admin
        admin.closing.clear()
        admin.api_token = issue_token(self.token_file)
        if not admin.accounts.owners():
            log.warning("no account can sign in to the admin yet: run `nestor accounts create-owner`")
        self._server = server = _Server(config)
        self._serving = serving = asyncio.create_task(self._serve(server), name="admin server")
        while not server.started:
            if serving.done():
                await self.close()
                raise ProviderError(
                    self.name, f"cannot listen on {self.settings.host}:{self.settings.port}", transient=False
                )
            await asyncio.sleep(0.01)
        log.info("admin listening on http://%s:%s", self.settings.host, self.port)

    async def close(self) -> None:
        server, serving = self._server, self._serving
        self._server = self._serving = None
        if server is None or serving is None:
            return
        self.app.state.admin.closing.set()  # live streams end, so that the server can stop
        server.should_exit = True
        await asyncio.gather(serving, return_exceptions=True)
        self.app.state.admin.api_token = None
        self.token_file.unlink(missing_ok=True)

    @staticmethod
    async def _serve(server: uvicorn.Server) -> None:
        try:
            await server.serve()
        except SystemExit:  # uvicorn exits when it cannot bind; start() reports it
            log.error("admin server could not start")
