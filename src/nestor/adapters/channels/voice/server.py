"""The voice channel's HTTP server: WebRTC signalling for satellites and the development browser.

Route sets plug into one FastAPI app served by `uvicorn` inside the channel:
- `SatelliteGateway` (`satellites.gateway`): pairing and authenticated offers for paired devices;
- `BrowserRoutes`: the Pipecat prebuilt client at `/client`, unauthenticated — development on a
  trusted LAN only, enabled by `allow_unpaired_browser`.
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

type SessionHook = Callable[[BaseTransport], Coroutine[Any, Any, None]]


class Routes(ABC):
    """A set of endpoints and the sessions they started."""

    def __init__(self) -> None:
        self.handler = SmallWebRTCRequestHandler()  # one per route set: peers of one set are invisible to others
        self._running: set[asyncio.Task[None]] = set()

    @abstractmethod
    def install(self, app: FastAPI) -> None: ...

    def spawn(self, session: Coroutine[Any, Any, None], name: str) -> None:
        task = asyncio.create_task(session, name=name)
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def close(self) -> None:
        """Hang up every peer and wait for their sessions."""
        await self.handler.close()
        await asyncio.gather(*self._running, return_exceptions=True)


def offer_of(body: dict[str, Any]) -> SmallWebRTCRequest:
    return SmallWebRTCRequest(
        sdp=body["sdp"], type=body["type"], pc_id=body.get("pc_id"), restart_pc=body.get("restart_pc")
    )


def patch_of(body: dict[str, Any]) -> SmallWebRTCPatchRequest:
    return SmallWebRTCPatchRequest(
        pc_id=body["pc_id"], candidates=[IceCandidate(**c) for c in body.get("candidates", [])]
    )


def audio_transport(connection: SmallWebRTCConnection) -> SmallWebRTCTransport:
    return SmallWebRTCTransport(connection, TransportParams(audio_in_enabled=True, audio_out_enabled=True))


class _Server(uvicorn.Server):
    """Leaves signals to the application that embeds it."""

    def capture_signals(self) -> Any:
        return _NoSignals()


class _NoSignals:
    def __enter__(self) -> None: ...

    def __exit__(self, *exc: object) -> None: ...


class SignallingServer:
    def __init__(self, *, host: str, port: int, routes: Sequence[Routes]) -> None:
        self._routes = tuple(routes)
        self.app = FastAPI(title="Nestor voice satellites")
        for route_set in self._routes:
            route_set.install(self.app)
        config = uvicorn.Config(
            self.app, host=host, port=port, log_config=None, lifespan="off", timeout_graceful_shutdown=2
        )
        self._server = _Server(config)

    async def serve(self) -> None:
        """Serve until `stop`; then hang up every peer and wait for their sessions."""
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


class BrowserRoutes(Routes):
    """What the Pipecat prebuilt client calls: `POST /start`, then `POST`/`PATCH`
    `/sessions/{id}/api/offer` (or `/api/offer`). Nobody is authenticated: LAN development only."""

    def __init__(self, *, attach: SessionHook, detach: SessionHook) -> None:
        super().__init__()
        self._attach, self._detach = attach, detach
        self._sessions: set[str] = set()

    def install(self, app: FastAPI) -> None:
        from pipecat_ai_prebuilt.frontend import PipecatPrebuiltUI

        app.mount("/client", PipecatPrebuiltUI)
        app.add_api_route("/", lambda: RedirectResponse("/client/"), methods=["GET"], include_in_schema=False)
        app.add_api_route("/start", self._start, methods=["POST"])
        app.add_api_route("/api/offer", self._offer, methods=["POST", "PATCH"])
        app.add_api_route("/sessions/{session_id}/api/offer", self._session_offer, methods=["POST", "PATCH"])

    async def _start(self) -> dict[str, str]:
        session_id = str(uuid.uuid4())
        self._sessions.add(session_id)
        return {"sessionId": session_id}

    async def _session_offer(self, session_id: str, request: Request) -> Any:
        if session_id not in self._sessions:
            raise HTTPException(404, "unknown session: POST /start first")
        return await self._offer(request)

    async def _offer(self, request: Request) -> Any:
        body = await request.json()
        if request.method == "PATCH":
            await self.handler.handle_patch_request(patch_of(body))
            return {"status": "success"}
        return await self.handler.handle_web_request(offer_of(body), self._connected)

    async def _connected(self, connection: SmallWebRTCConnection) -> None:
        transport = audio_transport(connection)

        async def disconnected(_transport: BaseTransport, _client: object) -> None:
            await self._detach(transport)

        transport.add_event_handler("on_client_disconnected", disconnected)
        self.spawn(self._attach(transport), name=f"browser session {connection.pc_id}")
