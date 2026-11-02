"""The satellites' HTTP server: the gateway's routes (pairing, the link of each paired device, its
audio offers) on one FastAPI app, served by `uvicorn` inside the channel."""

from typing import Any

import uvicorn
from fastapi import FastAPI

from nestor.adapters.channels.satellites.gateway import SatelliteGateway

PING_INTERVAL_S = 20.0  # the core pings every link this often (L4)


class _Server(uvicorn.Server):
    """Leaves signals to the application that embeds it."""

    def capture_signals(self) -> Any:
        return _NoSignals()


class _NoSignals:
    def __enter__(self) -> None: ...

    def __exit__(self, *exc: object) -> None: ...


class DeviceServer:
    def __init__(self, *, host: str, port: int, gateway: SatelliteGateway) -> None:
        self._gateway = gateway
        self.app = FastAPI(title="Nestor satellites")
        gateway.install(self.app)
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
        """Serve until `stop`; then close the links still up."""
        try:
            await self._server.serve()
        finally:
            await self._gateway.close()

    def stop(self) -> None:
        self._server.should_exit = True

    @property
    def started(self) -> bool:
        """Whether it accepts connections yet."""
        return self._server.started
