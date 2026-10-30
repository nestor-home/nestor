"""HTTP side of the satellite protocol `nestor.satellite/2`, realtime profile (WebRTC).

    POST  /satellites/pairings                         pairing.request     → 201 pairing.ticket
    POST  /satellites/pairings/{pairing_id}/enrollment pairing.enrollment  → 200 pairing.state
    GET   /satellites/pairings/{pairing_id}                                → 200 pairing.state
    POST  /satellites/{device_id}/offer    Bearer token, SDP   → SDP answer {sdp, type, pc_id}
    PATCH /satellites/{device_id}/offer    Bearer token, ICE   → {status}

Errors follow `pairing.error`. The token comes once, with the first `approved` answer. Offers without
a valid token for that device are refused (401), and a device can only renegotiate its own peer
connections (403). Wrong enrollment codes are counted per client address.
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from nestor.adapters.channels.voice.server import Routes, offer_of, patch_of
from nestor.core import ContractError
from nestor.modules.satellites import (
    EnrollmentRefused,
    NotPending,
    Pairing,
    ProtocolUnsupported,
    Satellite,
    TooManyAttempts,
    TooManyPending,
    wire,
)

logger = logging.getLogger(__name__)

PENDING_RETRY_S = 30  # when too many devices wait: about the time a person takes to approve one

type SatelliteHook = Callable[[SmallWebRTCConnection, Satellite], Coroutine[Any, Any, None]]


class SatelliteGateway(Routes):
    """`on_connection` runs a paired device's session on its new peer connection, until it ends."""

    def __init__(self, pairing: Pairing, on_connection: SatelliteHook) -> None:
        super().__init__()
        self._pairing = pairing
        self._on_connection = on_connection
        self._owners: dict[str, str] = {}  # peer connection id → device id

    def install(self, app: FastAPI) -> None:
        app.add_api_route("/satellites/pairings", self._pair, methods=["POST"], status_code=201)
        app.add_api_route("/satellites/pairings/{pairing_id}/enrollment", self._enroll, methods=["POST"])
        app.add_api_route("/satellites/pairings/{pairing_id}", self._poll, methods=["GET"])
        app.add_api_route("/satellites/{device_id}/offer", self._offer, methods=["POST", "PATCH"])

    async def _pair(self, request: Request) -> Any:
        try:
            asked = wire.PairingRequest.from_json(await request.json())
            ticket = await self._pairing.request(
                asked.manifest, enrollment_code=asked.enrollment_code, method=asked.method, source=_client(request)
            )
        except Exception as error:
            return _refusal(error)
        logger.info("satellite pairing %s: %s", ticket.id, ticket.status.value)
        return wire.ticket_json(ticket)

    async def _enroll(self, pairing_id: str, request: Request) -> Any:
        try:
            proof = wire.EnrollmentProof.from_json(await request.json())
            state = await self._pairing.enroll(
                pairing_id, proof.enrollment_code, method=proof.method, source=_client(request)
            )
        except Exception as error:
            return _refusal(error)
        return wire.state_json(state)

    async def _poll(self, pairing_id: str) -> dict[str, Any]:
        return wire.state_json(self._pairing.poll(pairing_id))

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


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _refusal(error: Exception) -> JSONResponse:
    match error:
        case TooManyAttempts(retry_after_s=wait):
            code, headers = "too_many_attempts", {"Retry-After": str(round(wait))}
            body = wire.error_json(code, str(error), retry_after_s=wait)
        case EnrollmentRefused(reason=reason):
            code, headers, body = "enrollment_refused", {}, wire.error_json("enrollment_refused", str(error),
                                                                             reason=reason)  # fmt: skip
        case TooManyPending():
            code, headers = "too_many_pending", {"Retry-After": str(PENDING_RETRY_S)}
            body = wire.error_json(code, str(error), retry_after_s=PENDING_RETRY_S)
        case NotPending() | ProtocolUnsupported():
            code = "not_pending" if isinstance(error, NotPending) else "protocol_unsupported"
            headers, body = {}, wire.error_json(code, str(error))
        case ContractError() | ValueError():
            code, headers, body = "invalid_request", {}, wire.error_json("invalid_request", str(error))
        case _:
            raise error
    return JSONResponse(body, status_code=wire.ERRORS[code], headers=headers)
