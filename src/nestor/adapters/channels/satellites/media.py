"""The media path of satellites (`MediaRelay`): a session a person opened, relayed by the core with aiortc.

The core asks the device over its link (`intent.media.open`); the device connects to the core
(`POST /satellites/{device_id}/media`, its token and the session's id), sending its camera's video when the session
has it, and for a call its microphone while it plays what the core sends back. The core relays the device's tracks to
the person's browser, and for a call the browser's microphone to the device. The device and the browser never reach
each other, and nothing is written to disk.
"""

import asyncio
import contextlib
import fractions
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import av
from aiortc import MediaStreamTrack, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay as TrackRelay
from aiortc.mediastreams import MediaStreamError

from nestor.adapters.channels.satellites.link import SatelliteLink
from nestor.core import Capability, ProviderError
from nestor.modules.satellites import MediaEnd, MediaRelay, wire
from nestor.modules.satellites.media import Ended

logger = logging.getLogger(__name__)

PROVIDER = "satellites"
OFFER_WAIT_S = 30.0  # the device connects within this once asked: ICE gathering alone takes seconds on some hosts
SNAPSHOT_WAIT_S = 10.0
SAMPLE_RATE = 48_000
FRAME_SAMPLES = 960  # 20 ms
LOCAL = RTCConfiguration(iceServers=[])  # the device and the browser reach the core directly: no STUN to wait for


class Forwarded(MediaStreamTrack):
    """The audio the core plays on a device in a call: the browser's microphone once it is there, silence until."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self.source: MediaStreamTrack | None = None
        self._pts = 0
        self._next = time.monotonic()

    async def recv(self) -> av.AudioFrame:
        if self.source is not None:
            try:
                heard = await self.source.recv()
                if isinstance(heard, av.AudioFrame):
                    return heard
            except MediaStreamError:
                self.source = None
        self._next += FRAME_SAMPLES / SAMPLE_RATE
        await asyncio.sleep(max(0.0, self._next - time.monotonic()))
        frame = av.AudioFrame(format="s16", layout="mono", samples=FRAME_SAMPLES)
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        frame.sample_rate, frame.pts, frame.time_base = SAMPLE_RATE, self._pts, fractions.Fraction(1, SAMPLE_RATE)
        self._pts += FRAME_SAMPLES
        return frame


@dataclass(slots=True)
class _Session:
    id: str
    device_id: str
    video: bool
    audio: bool
    device: asyncio.Future[RTCPeerConnection]  # the device's connection, once it offered
    tracks: list[MediaStreamTrack] = field(default_factory=list)  # what the device sends
    played: Forwarded | None = None  # what the device plays, in a call
    viewer: RTCPeerConnection | None = None


class SatelliteMedia(MediaRelay):
    """`links` are the channel's (device id → its link while it is up); `calling` hears a call start (`True`) or end
    on a device, so that its voice steps aside meanwhile."""

    def __init__(
        self,
        links: Mapping[str, SatelliteLink],
        *,
        calling: Callable[[SatelliteLink, bool], Any] | None = None,
        offer_wait_s: float = OFFER_WAIT_S,
    ) -> None:
        self._links, self._calling, self._offer_wait_s = links, calling, offer_wait_s
        self._relay = TrackRelay()
        self._sessions: dict[str, _Session] = {}
        self._ended: Ended | None = None

    def on_ended(self, ended: Ended) -> None:
        self._ended = ended

    def linked(self, device_id: str) -> frozenset[Capability] | None:
        link = self._links.get(device_id)
        return link.allowed if link else None

    async def start(
        self, session_id: str, device_id: str, *, video: bool, audio: bool, max_s: int, offer: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        link = self._links.get(device_id)
        if link is None:
            raise ProviderError(PROVIDER, f"{device_id} is not connected", transient=True)
        session = self._sessions[session_id] = _Session(
            session_id, device_id, video, audio, asyncio.get_running_loop().create_future()
        )
        if audio and self._calling is not None:
            await self._calling(link, True)
        link.send(wire.MediaOpenIntent(session=session_id, video=video, audio=audio, max_s=max_s))
        try:
            async with asyncio.timeout(self._offer_wait_s):
                await session.device
        except TimeoutError:
            raise ProviderError(
                PROVIDER, f"{device_id} did not connect in {self._offer_wait_s:g} s", transient=True
            ) from None
        viewer = session.viewer = RTCPeerConnection(LOCAL)
        self._watch(viewer, session_id, MediaEnd.CLOSED)
        if audio:

            @viewer.on("track")
            def heard(track: MediaStreamTrack) -> None:
                if track.kind == "audio" and session.played is not None:
                    session.played.source = track

        await viewer.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type=offer["type"]))
        for track in session.tracks:
            viewer.addTrack(self._relay.subscribe(track))
        await viewer.setLocalDescription(await viewer.createAnswer())
        return {"sdp": viewer.localDescription.sdp, "type": viewer.localDescription.type}

    async def device_offer(self, device_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """The device connects for its session `body["session"]` (`{session, sdp, type}`); `PermissionError` when no
        session of this device waits for it."""
        session = self._sessions.get(str(body.get("session", "")))
        if session is None or session.device_id != device_id or session.device.done():
            raise PermissionError("no session of this device waits for its connection")
        connection = RTCPeerConnection(LOCAL)
        self._watch(connection, session.id, MediaEnd.DEVICE_LEFT)

        @connection.on("track")
        def received(track: MediaStreamTrack) -> None:
            if (track.kind == "video" and session.video) or (track.kind == "audio" and session.audio):
                session.tracks.append(track)

        await connection.setRemoteDescription(RTCSessionDescription(sdp=body["sdp"], type=body["type"]))
        if session.audio:
            session.played = Forwarded()
            connection.addTrack(session.played)
        await connection.setLocalDescription(await connection.createAnswer())
        if session.device.done():  # given up meanwhile: too late
            await connection.close()
            raise PermissionError("this session ended before the device connected")
        session.device.set_result(connection)
        return {"sdp": connection.localDescription.sdp, "type": connection.localDescription.type}

    async def stop(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        if link := self._links.get(session.device_id):
            link.send(wire.MediaCloseIntent(session=session_id))
            if session.audio and self._calling is not None:
                await self._calling(link, False)
        if session.device.done() and not session.device.cancelled():
            await session.device.result().close()
        else:
            session.device.cancel()
        if session.viewer is not None:
            await session.viewer.close()

    async def left(self, device_id: str) -> None:
        """The device's link went down: its sessions end."""
        for session in [s for s in self._sessions.values() if s.device_id == device_id]:
            await self._end(session.id, MediaEnd.DEVICE_LEFT)

    async def snapshot(self, device_id: str) -> bytes:
        link = self._links.get(device_id)
        if link is None:
            raise ProviderError(PROVIDER, f"{device_id} is not connected", transient=True)
        return await link.snapshot(SNAPSHOT_WAIT_S)

    async def close(self) -> None:
        for session_id in list(self._sessions):
            await self.stop(session_id)

    def _watch(self, connection: RTCPeerConnection, session_id: str, reason: MediaEnd) -> None:
        @connection.on("connectionstatechange")
        async def changed() -> None:
            if connection.connectionState in ("failed", "closed"):
                await self._end(session_id, reason)

    async def _end(self, session_id: str, reason: MediaEnd) -> None:
        if session_id not in self._sessions:
            return
        if self._ended is not None:
            await self._ended(session_id, reason)  # the sessions' service journals it and calls `stop`
        else:
            with contextlib.suppress(Exception):
                await self.stop(session_id)
        logger.info("media session %s ended: %s", session_id, reason)
