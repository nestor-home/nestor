"""HTTP side of the satellite protocol `nestor.satellite/1`.

    POST  /satellites/pairings                         pairing.request     → 201 pairing.ticket
    POST  /satellites/pairings/{pairing_id}/enrollment pairing.enrollment  → 200 pairing.state
    GET   /satellites/pairings/{pairing_id}                                → 200 pairing.state
    WS    /satellites/{device_id}/link     hello (manifest, token) first   → welcome, then messages
    POST  /satellites/{device_id}/audio    Bearer token, SDP   → SDP answer {sdp, type, pc_id}
    PATCH /satellites/{device_id}/audio    Bearer token, ICE   → {status}

Errors follow `pairing.error`. The token comes once, with the first `approved` answer. A link whose
`hello` is late, off-contract or for another device is closed with 4400, one with a refused token
with 4401. Audio is for a device whose link is up and that was allowed audio; it can only renegotiate
its own peer connections. Wrong enrollment codes are counted per client address.
"""

import asyncio
import contextlib
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from enum import IntEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse

from nestor.core import Capability, ContractError
from nestor.modules.satellites import (
    AUDIO,
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
HELLO_DEADLINE_S = 10.0  # a link says hello within this (L2)


class Close(IntEnum):
    """Why the core closes a link (L2, L4, L5)."""

    STOPPING = 1001  # the core stops: reconnect
    OFF_CONTRACT = 4400  # `hello` late, off-contract or for another device
    TOKEN_REFUSED = 4401  # forget the token and pair again
    REPLACED = 4409  # a newer link of this device took over


class AudioOffers(ABC):
    """Where the audio of a linked device is negotiated (the voice); `PermissionError` refuses with 403."""

    @abstractmethod
    async def offer(self, device_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Answer the device's SDP offer: `{sdp, type, pc_id}`."""

    @abstractmethod
    async def patch(self, device_id: str, body: dict[str, Any]) -> None:
        """Add the device's ICE candidates to one of its own peer connections."""


type Linked = Callable[[WebSocket, Satellite, frozenset[Capability]], Awaitable[None]]
type Refused = Callable[[str, Close, str], None]


class SatelliteGateway:
    """`on_link` holds the link of a device whose `hello` was accepted (the socket, the paired device,
    what it is granted) until it ends; `allowed` says what a paired device is granted (the voice may be
    missing); `refused` hears why a link was turned away."""

    def __init__(
        self,
        pairing: Pairing,
        *,
        on_link: Linked,
        allowed: Callable[[Satellite], frozenset[Capability]] = lambda satellite: satellite.capabilities,
        audio: AudioOffers | None = None,
        refused: Refused | None = None,
        hello_deadline_s: float = HELLO_DEADLINE_S,
    ) -> None:
        self._pairing = pairing
        self._on_link, self._allowed, self._audio, self._refused = on_link, allowed, audio, refused
        self._hello_deadline_s = hello_deadline_s
        self._links: dict[str, tuple[WebSocket, frozenset[Capability]]] = {}  # device id → its link, what it may do

    def install(self, app: FastAPI) -> None:
        app.add_api_route("/satellites/pairings", self._pair, methods=["POST"], status_code=201)
        app.add_api_route("/satellites/pairings/{pairing_id}/enrollment", self._enroll, methods=["POST"])
        app.add_api_route("/satellites/pairings/{pairing_id}", self._poll, methods=["GET"])
        app.add_api_websocket_route("/satellites/{device_id}/link", self._link)
        app.add_api_route("/satellites/{device_id}/audio", self._offer, methods=["POST", "PATCH"])

    async def close(self) -> None:
        """Close every link (1001): its device reconnects once the core is back."""
        await asyncio.gather(*(_close(socket, Close.STOPPING) for socket, _ in self._links.values()))

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

    async def _link(self, socket: WebSocket, device_id: str) -> None:
        await socket.accept()
        satellite = await self._greet(socket, device_id)
        if satellite is None:
            return
        allowed = self._allowed(satellite)
        if previous := self._links.get(device_id):
            await _close(previous[0], Close.REPLACED)
        self._links[device_id] = (socket, allowed)
        try:
            await self._on_link(socket, satellite, allowed)
        finally:
            if self._links.get(device_id, (None,))[0] is socket:
                del self._links[device_id]

    async def _greet(self, socket: WebSocket, device_id: str) -> Satellite | None:
        """The paired device behind the link's `hello`, or `None` once the link is closed (L1, L2)."""
        try:
            received = await asyncio.wait_for(socket.receive_text(), self._hello_deadline_s)
            hello = wire.decode(json.loads(received)).message
        except TimeoutError:
            return await self._turn_away(socket, device_id, Close.OFF_CONTRACT, "no hello in time")
        except (ContractError, ValueError, KeyError, RuntimeError) as error:
            return await self._turn_away(socket, device_id, Close.OFF_CONTRACT, str(error))
        if not isinstance(hello, wire.Hello):
            return await self._turn_away(socket, device_id, Close.OFF_CONTRACT, f"first {hello.message_type}")
        if hello.manifest.device.id != device_id:
            said = f"introduced as {hello.manifest.device.id}"
            return await self._turn_away(socket, device_id, Close.OFF_CONTRACT, said)
        satellite = self._pairing.authenticate(device_id, hello.token)
        if satellite is None:
            return await self._turn_away(socket, device_id, Close.TOKEN_REFUSED, "token refused")
        return satellite

    async def _turn_away(self, socket: WebSocket, device_id: str, code: Close, why: str) -> None:
        logger.warning("satellite %s: link closed (%d, %s)", device_id, code, why)
        if self._refused is not None:
            self._refused(device_id, code, why)
        await _close(socket, code)

    async def _offer(self, device_id: str, request: Request) -> Any:
        self._authenticate(device_id, request)
        link = self._links.get(device_id)
        if self._audio is None or link is None or not link[1] & AUDIO:
            raise HTTPException(403, "audio needs this device's link up and audio allowed")
        body = await request.json()
        try:
            if request.method == "PATCH":
                await self._audio.patch(device_id, body)
                return {"status": "success"}
            return await self._audio.offer(device_id, body)
        except PermissionError as refusal:
            raise HTTPException(403, str(refusal)) from None

    def _authenticate(self, device_id: str, request: Request) -> Satellite:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        satellite = self._pairing.authenticate(device_id, token) if scheme.lower() == "bearer" and token else None
        if satellite is None:
            raise HTTPException(401, "pair this device first", headers={"WWW-Authenticate": 'Bearer realm="nestor"'})
        return satellite


async def _close(socket: WebSocket, code: Close) -> None:
    with contextlib.suppress(RuntimeError):  # closed already, or the device left first
        await socket.close(code)


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
