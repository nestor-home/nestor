"""An HTTP server run inside Nestor's event loop (the admin, a channel's): uvicorn, leaving signals to Nestor."""

import contextlib
from collections.abc import Generator
from typing import Any

import uvicorn


class EmbeddedServer(uvicorn.Server):
    """`serve` until `should_exit` is set; Nestor, not the server, answers Ctrl-C."""

    def __init__(self, app: Any, *, host: str, port: int, **options: Any) -> None:
        options = {"log_config": None, "timeout_graceful_shutdown": 2} | options
        super().__init__(uvicorn.Config(app, host=host, port=port, lifespan="off", **options))

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield  # the runtime owns SIGINT and SIGTERM, and closes the server itself
