"""The WebRTC side of satellites' audio: their SDP offers answered and their ICE candidates added by
Pipecat's SmallWebRTC handler."""

from collections.abc import Awaitable, Callable
from typing import Any, cast

from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

type Connected = Callable[[SmallWebRTCConnection], Awaitable[None]]


class PeerConnections:
    """The peer connections of the devices' audio, from the bodies of `POST` and `PATCH .../audio`."""

    def __init__(self) -> None:
        self._handler = SmallWebRTCRequestHandler()

    async def answer(self, body: dict[str, Any], connected: Connected) -> dict[str, Any]:
        """Answer an SDP offer (`{sdp, type, pc_id}`); `connected` receives each new connection."""
        request = SmallWebRTCRequest(
            sdp=body["sdp"], type=body["type"], pc_id=body.get("pc_id"), restart_pc=body.get("restart_pc")
        )
        # The handler raises rather than return no answer (Pipecat 1.14), despite its annotation.
        return cast(dict[str, Any], await self._handler.handle_web_request(request, connected))

    async def patch(self, body: dict[str, Any]) -> None:
        """Add ICE candidates to the connection `pc_id`."""
        candidates = [IceCandidate(**c) for c in body.get("candidates", [])]
        await self._handler.handle_patch_request(SmallWebRTCPatchRequest(pc_id=body["pc_id"], candidates=candidates))

    async def close(self) -> None:
        await self._handler.close()
