"""Development signalling: the Pipecat prebuilt browser client talking WebRTC to the channel.

It serves the client at `/client` and implements what it calls: `POST /start` opens a session,
`POST`/`PATCH` `/sessions/{id}/api/offer` (or `/api/offer`) negotiate the peer connection. Each
connection gets its own voice session. This is a satellite for development; a proper satellite
protocol replaces it later.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
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

logger = logging.getLogger(__name__)

type SessionHook = Callable[[BaseTransport], Coroutine[Any, Any, None]]


class _Server(uvicorn.Server):
    """Leaves signals to the application that embeds it."""

    def capture_signals(self) -> Any:
        return _NoSignals()


class _NoSignals:
    def __enter__(self) -> None: ...

    def __exit__(self, *exc: object) -> None: ...


class SignallingServer:
    """`attach` runs a voice session on a new transport until it ends; `detach` ends it."""

    def __init__(self, *, host: str, port: int, attach: SessionHook, detach: SessionHook) -> None:
        self._attach, self._detach = attach, detach
        self._handler = SmallWebRTCRequestHandler()
        self._sessions: set[str] = set()
        self._running: set[asyncio.Task[None]] = set()
        self.app = self._routes()
        self._server = _Server(
            uvicorn.Config(self.app, host=host, port=port, log_config=None, lifespan="off", timeout_graceful_shutdown=2)
        )

    async def serve(self) -> None:
        """Serve until `stop`; then close every peer connection and wait for their sessions."""
        try:
            await self._server.serve()
        finally:
            await self._handler.close()
            await asyncio.gather(*self._running, return_exceptions=True)

    def stop(self) -> None:
        self._server.should_exit = True

    def _routes(self) -> FastAPI:
        from pipecat_ai_prebuilt.frontend import PipecatPrebuiltUI

        app = FastAPI(title="Nestor voice satellite (development)")
        app.mount("/client", PipecatPrebuiltUI)
        app.add_api_route("/", lambda: RedirectResponse("/client/"), methods=["GET"], include_in_schema=False)
        app.add_api_route("/start", self._start, methods=["POST"])
        app.add_api_route("/api/offer", self._offer, methods=["POST", "PATCH"])
        app.add_api_route("/sessions/{session_id}/api/offer", self._session_offer, methods=["POST", "PATCH"])
        return app

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
            candidates = [IceCandidate(**c) for c in body.get("candidates", [])]
            await self._handler.handle_patch_request(
                SmallWebRTCPatchRequest(pc_id=body["pc_id"], candidates=candidates)
            )
            return {"status": "success"}
        offer = SmallWebRTCRequest(
            sdp=body["sdp"], type=body["type"], pc_id=body.get("pc_id"), restart_pc=body.get("restart_pc")
        )
        return await self._handler.handle_web_request(offer, self._connected)

    async def _connected(self, connection: SmallWebRTCConnection) -> None:
        transport = SmallWebRTCTransport(connection, TransportParams(audio_in_enabled=True, audio_out_enabled=True))

        async def disconnected(_transport: BaseTransport, _client: object) -> None:
            await self._detach(transport)

        transport.add_event_handler("on_client_disconnected", disconnected)
        task = asyncio.create_task(self._attach(transport), name=f"voice session {connection.pc_id}")
        self._running.add(task)
        task.add_done_callback(self._running.discard)
