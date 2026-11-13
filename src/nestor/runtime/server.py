"""An HTTP server run inside Nestor's event loop (the admin, a channel's): uvicorn, leaving signals to Nestor."""

import asyncio
import contextlib
import logging
from collections.abc import Generator
from typing import Any

import uvicorn

from nestor.core import ProviderError

log = logging.getLogger(__name__)


class EmbeddedServer(uvicorn.Server):
    """`serve` until `should_exit` is set; Nestor, not the server, answers Ctrl-C."""

    def __init__(self, app: Any, *, host: str, port: int, **options: Any) -> None:
        options = {"log_config": None, "timeout_graceful_shutdown": 2} | options
        super().__init__(uvicorn.Config(app, host=host, port=port, lifespan="off", **options))
        self._serving: asyncio.Task[None] | None = None

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield  # the runtime owns SIGINT and SIGTERM, and closes the server itself

    async def listen(self, name: str) -> None:
        """Serve in the background, returning once the port listens; a `ProviderError` labelled `name` when it
        cannot be listened on (uvicorn exits then), the server stopped."""
        self._serving = serving = asyncio.create_task(self._served(), name=f"{name} server")
        while not self.started:
            if serving.done():
                self._serving = None
                raise ProviderError(name, f"cannot listen on {self.config.host}:{self.config.port}", transient=False)
            await asyncio.sleep(0.01)

    async def stop(self) -> None:
        """Stop what `listen` started, once its connections are closed."""
        serving, self._serving = self._serving, None
        self.should_exit = True
        if serving is not None:
            await asyncio.gather(serving, return_exceptions=True)

    async def _served(self) -> None:
        try:
            await self.serve()
        except SystemExit:  # uvicorn exits when it cannot bind; `listen` reports it
            log.error("the server on %s:%s could not start", self.config.host, self.config.port)
