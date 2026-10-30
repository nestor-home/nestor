"""HTTP side of the satellite protocol, realtime profile (WebRTC).

    POST  /satellites/pair                 manifest            → 201 {pairing_id, code, expires_at}
    GET   /satellites/pair/{pairing_id}                        → {status, token?, device_id?, room?, capabilities?}
    POST  /satellites/{device_id}/offer    Bearer token, SDP   → SDP answer {sdp, type, pc_id}
    PATCH /satellites/{device_id}/offer    Bearer token, ICE   → {status}

The token comes once, with the first `approved` answer. Offers without a valid token for that
device are refused (401), and a device can only renegotiate its own peer connections (403).
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from nestor.adapters.channels.voice.server import Routes, offer_of, patch_of
from nestor.core import ContractError
from nestor.modules.satellites import Manifest, Pairing, PairingRefused, Satellite

logger = logging.getLogger(__name__)

type SatelliteHook = Callable[[SmallWebRTCConnection, Satellite], Coroutine[Any, Any, None]]


class SatelliteGateway(Routes):
    """`on_connection` runs a paired device's session on its new peer connection, until it ends."""

    def __init__(self, pairing: Pairing, on_connection: SatelliteHook) -> None:
        super().__init__()
        self._pairing = pairing
        self._on_connection = on_connection
        self._owners: dict[str, str] = {}  # peer connection id → device id

    def install(self, app: FastAPI) -> None:
        app.add_api_route("/satellites/pair", self._pair, methods=["POST"], status_code=201)
        app.add_api_route("/satellites/pair/{pairing_id}", self._poll, methods=["GET"])
        app.add_api_route("/satellites/{device_id}/offer", self._offer, methods=["POST", "PATCH"])

    async def _pair(self, request: Request) -> Any:
        try:
            ticket = await self._pairing.request(Manifest.from_json(await request.json()))
        except PairingRefused as refused:
            return JSONResponse({"detail": str(refused)}, status_code=429)
        except (ContractError, ValueError) as invalid:
            return JSONResponse({"detail": str(invalid)}, status_code=422)
        logger.info("satellite pairing requested (%s): confirm the code the device shows", ticket.id)
        return {"pairing_id": ticket.id, "code": ticket.code, "expires_at": ticket.expires_at.isoformat()}

    async def _poll(self, pairing_id: str) -> dict[str, Any]:
        state = self._pairing.poll(pairing_id)
        answer: dict[str, Any] = {"status": state.status.value}
        if state.token is not None:
            answer["token"] = state.token
        if state.satellite is not None:
            answer |= {
                "device_id": state.satellite.id,
                "room": state.satellite.room,
                "capabilities": sorted(state.satellite.capabilities),
            }
        return answer

    async def _offer(self, device_id: str, request: Request) -> Any:
        satellite = self._authenticate(device_id, request)
        body = await request.json()
        pc_id = body.get("pc_id")
        if pc_id is not None and self._owners.get(pc_id) != device_id:
            raise HTTPException(403, "this peer connection belongs to no session of this device")
        if request.method == "PATCH":
            await self.handler.handle_patch_request(patch_of(body))
            return {"status": "success"}

        async def connected(connection: SmallWebRTCConnection) -> None:
            self.spawn(self._run(connection, satellite), name=f"satellite {device_id}")

        # The handler raises rather than return no answer (Pipecat 1.14), despite its annotation.
        answer = cast(dict[str, str], await self.handler.handle_web_request(offer_of(body), connected))
        self._owners[answer["pc_id"]] = device_id
        return answer

    async def _run(self, connection: SmallWebRTCConnection, satellite: Satellite) -> None:
        try:
            await self._on_connection(connection, satellite)
        finally:
            self._owners.pop(connection.pc_id, None)

    def _authenticate(self, device_id: str, request: Request) -> Satellite:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        satellite = self._pairing.authenticate(device_id, token) if scheme.lower() == "bearer" and token else None
        if satellite is None:
            raise HTTPException(401, "pair this device first", headers={"WWW-Authenticate": 'Bearer realm="nestor"'})
        return satellite
