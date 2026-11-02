"""The satellites' HTTP server: route sets plug into one FastAPI app served by `uvicorn` inside the
channel. The gateway (`gateway`) is one: pairing, the link of each paired device, its audio offers."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Coroutine, Sequence
from typing import Any

import uvicorn
from fastapi import FastAPI

PING_INTERVAL_S = 20.0  # the core pings every link this often (L4)


class Routes(ABC):
    """A set of endpoints and the sessions they started."""

    def __init__(self) -> None:
        self._running: set[asyncio.Task[None]] = set()

    @abstractmethod
    def install(self, app: FastAPI) -> None: ...

    def spawn(self, session: Coroutine[Any, Any, None], name: str) -> None:
        task = asyncio.create_task(session, name=name)
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def close(self) -> None:
        """End what the routes started and wait for it."""
        await asyncio.gather(*self._running, return_exceptions=True)


class _Server(uvicorn.Server):
    """Leaves signals to the application that embeds it."""

    def capture_signals(self) -> Any:
        return _NoSignals()


class _NoSignals:
    def __enter__(self) -> None: ...

    def __exit__(self, *exc: object) -> None: ...


class DeviceServer:
    def __init__(self, *, host: str, port: int, routes: Sequence[Routes]) -> None:
        self._routes = tuple(routes)
        self.app = FastAPI(title="Nestor satellites")
        for route_set in self._routes:
            route_set.install(self.app)
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_config=None,
            lifespan="off",
            timeout_graceful_shutdown=2,
            ws_ping_interval=PING_INTERVAL_S,
            ws_ping_timeout=PING_INTERVAL_S,
        )
        self._server = _Server(config)

    async def serve(self) -> None:
        """Serve until `stop`; then end every route set's sessions and wait for them."""
        try:
            await self._server.serve()
        finally:
            for route_set in self._routes:
                await route_set.close()

    def stop(self) -> None:
        self._server.should_exit = True

    @property
    def started(self) -> bool:
        """Whether it accepts connections yet."""
        return self._server.started
