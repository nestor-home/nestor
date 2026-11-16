"""Watching and calling through satellites over real WebRTC: a camera device linked to the satellites channel, a
browser as the admin opens it, and the core relaying between them. Nothing reaches the device but through its link,
and nothing from it but in a session a person opened."""

import asyncio
import base64
import fractions
import json
import math
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace

import av
import httpx
import numpy as np
import pytest
import websockets
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack

from nestor.adapters.channels.satellites.gateway import secure
from nestor.core import PersonId
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    AUDIO_CAPTURE,
    AUDIO_PLAYBACK,
    VIDEO_CAPTURE,
    Device,
    Manifest,
    MediaAccess,
    MediaEnd,
    MediaRefused,
    MediaSessionClosed,
    MediaSessions,
    Pairing,
    Purpose,
    Refusal,
    Viewer,
    wire,
)
from nestor.modules.satellites.types import DeclaredCapability
from nestor.testing.journal import MemoryBlobStore
from nestor.testing.satellites import SOFTWARE

from .test_gateway import _until, hello, home, link_url, paired

CAMERA = Manifest(
    Device("camera-entree", "raspberry-pi-zero", "entree"),
    tuple(DeclaredCapability(c) for c in (VIDEO_CAPTURE, AUDIO_CAPTURE, AUDIO_PLAYBACK)),
    software=SOFTWARE,
)
BOTH = frozenset(Purpose)
OWNER = Viewer(account_id="a-mathis", person=PersonId("mathis"), may=BOTH, everywhere=BOTH)
LEA = Viewer(account_id="a-lea", person=PersonId("lea"), may=BOTH)
JPEG = b"\xff\xd8\xff\xe0 a picture \xff\xd9"


class Tone(MediaStreamTrack):
    """A 440 Hz tone, as a browser's microphone would send someone speaking."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._pts = 0

    async def recv(self) -> av.AudioFrame:
        await asyncio.sleep(0.02)
        t = (np.arange(960) + self._pts) / 48_000
        samples = (np.sin(2 * math.pi * 440 * t) * 12_000).astype(np.int16).reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
        frame.sample_rate, frame.pts, frame.time_base = 48_000, self._pts, fractions.Fraction(1, 48_000)
        self._pts += 960
        return frame


@dataclass
class Camera:
    """The device: it opens a connection only when its link asks it to (M1), films and, in a call, plays what the
    core sends and records how loud it was."""

    url: str
    token: str
    opened: list[wire.MediaOpenIntent] = field(default_factory=list)
    closed: list[str] = field(default_factory=list)
    loudest: float = 0.0
    connection: RTCPeerConnection | None = None
    listening: asyncio.Future[None] | None = None

    async def run(self) -> None:
        async with websockets.connect(link_url(self.url, CAMERA.device.id), max_size=None) as link:
            await link.send(hello(CAMERA, self.token))
            async for raw in link:
                data = json.loads(raw)
                message = wire.decode(data).message
                if isinstance(message, wire.MediaOpenIntent):
                    self.opened.append(message)
                    await self._offer(message)
                elif isinstance(message, wire.MediaCloseIntent):
                    self.closed.append(message.session)
                    if self.connection:
                        await self.connection.close()
                elif isinstance(message, wire.SnapshotIntent):
                    picture = wire.SnapshotReport(of=data["id"], jpeg=base64.b64encode(JPEG).decode())
                    await link.send(json.dumps(wire.encode(picture)))

    async def _offer(self, intent: wire.MediaOpenIntent) -> None:
        connection = self.connection = RTCPeerConnection()
        if intent.video:
            connection.addTrack(VideoStreamTrack())
        if intent.audio:
            connection.addTransceiver("audio", direction="sendrecv")

            @connection.on("track")
            def played(track: MediaStreamTrack) -> None:
                self.listening = asyncio.ensure_future(self._listen(track))

        await connection.setLocalDescription(await connection.createOffer())
        offer = {"session": intent.session, "sdp": connection.localDescription.sdp, "type": "offer"}
        async with httpx.AsyncClient(base_url=self.url, timeout=10) as http:
            answered = await http.post(
                f"/satellites/{CAMERA.device.id}/media", json=offer, headers={"Authorization": f"Bearer {self.token}"}
            )
        answered.raise_for_status()
        await connection.setRemoteDescription(RTCSessionDescription(**answered.json()))

    async def _listen(self, track: MediaStreamTrack) -> None:
        while True:
            try:
                frame = await track.recv()
            except Exception:
                return
            assert isinstance(frame, av.AudioFrame)
            self.loudest = max(self.loudest, float(np.abs(frame.to_ndarray()).max()))


class Browser:
    """The admin's page: it offers to receive the video, and for a call to send its microphone too."""

    def __init__(self, *, call: bool) -> None:
        self.connection = RTCPeerConnection()
        self.frames = 0
        self.watching: asyncio.Future[None] | None = None
        self.connection.addTransceiver("video", direction="recvonly")
        if call:
            self.connection.addTrack(Tone())

        @self.connection.on("track")
        def received(track: MediaStreamTrack) -> None:
            if track.kind == "video":
                self.watching = asyncio.ensure_future(self._watch(track))

    async def offer(self) -> dict[str, str]:
        await self.connection.setLocalDescription(await self.connection.createOffer())
        return {"sdp": self.connection.localDescription.sdp, "type": "offer"}

    async def answered(self, answer: dict[str, str]) -> None:
        await self.connection.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

    async def _watch(self, track: MediaStreamTrack) -> None:
        while True:
            try:
                await track.recv()
            except Exception:
                return
            self.frames += 1


@asynccontextmanager
async def watched(
    *, viewers: frozenset[PersonId] = frozenset(), voice: bool = False, view_max_s: int = 60
) -> AsyncGenerator[tuple[MediaSessions, Camera, Journal, str, Pairing]]:
    async with home(voice=voice) as (channel, pairing, journal, url):
        relay = channel.media_relay()
        assert relay is not None, "aiortc is installed for the tests"
        media = MediaSessions(journal, pairing, relay, MemoryBlobStore(), view_max_s=view_max_s)
        await media.start()
        camera = Camera(url, await paired(pairing, CAMERA))
        if viewers:
            await pairing.set_access(CAMERA.device.id, MediaAccess(viewers=viewers))
        running = asyncio.create_task(camera.run())
        await _until(lambda: relay.linked(CAMERA.device.id) is not None)
        try:
            yield media, camera, journal, url, pairing
        finally:
            await media.close()
            running.cancel()


async def ended(journal: Journal, reason: MediaEnd) -> None:
    async with asyncio.timeout(15):
        while not any(e.reason is reason for e in await journal.history(MediaSessionClosed)):
            await asyncio.sleep(0.1)


async def opened(media: MediaSessions, purpose: Purpose, viewer: Viewer, browser: Browser) -> str:
    session = await media.open(CAMERA.device.id, purpose, viewer, await browser.offer())
    await browser.answered(dict(session.answer))
    return session.id


async def test_a_person_allowed_watches_the_camera_only_while_the_session_lasts() -> None:
    async with watched(viewers=frozenset({PersonId("lea")})) as (media, camera, journal, _, _):
        browser = Browser(call=False)
        session = await opened(media, Purpose.VIEW, LEA, browser)
        await _until(lambda: browser.frames > 5)
        assert [(i.video, i.audio) for i in camera.opened] == [(True, False)], "asked by its link, video only"
        await media.close_session(session, MediaEnd.CLOSED, by=LEA)
        await _until(lambda: camera.closed == [session])
        [closed] = await journal.history(MediaSessionClosed)
        assert (closed.session_id, closed.reason) == (session, MediaEnd.CLOSED)


async def test_a_call_carries_the_person_s_voice_to_the_device() -> None:
    async with watched() as (media, camera, _, _, _):
        browser = Browser(call=True)
        await opened(media, Purpose.CALL, OWNER, browser)
        await _until(lambda: camera.loudest > 1_000 and browser.frames > 5, timeout_s=15)
        assert [(i.video, i.audio) for i in camera.opened] == [(True, True)], "an owner may watch too"


@pytest.mark.parametrize(
    ("viewer", "purpose", "reason"),
    [(LEA, Purpose.VIEW, Refusal.FORBIDDEN), (LEA, Purpose.CALL, Refusal.FORBIDDEN)],
)
async def test_nobody_unlisted_opens_anything_and_the_device_is_never_asked(
    viewer: Viewer, purpose: Purpose, reason: Refusal
) -> None:
    async with watched() as (media, camera, _, _, _):
        with pytest.raises(MediaRefused) as refused:
            await media.open(CAMERA.device.id, purpose, viewer, await Browser(call=False).offer())
        assert refused.value.reason == reason and camera.opened == []


async def test_a_device_cannot_connect_for_a_session_nobody_opened() -> None:
    async with watched() as (_, camera, _, url, _), httpx.AsyncClient(base_url=url) as http:
        guessed = {"session": "guessed", "sdp": "v=0", "type": "offer"}
        refused = await http.post(
            f"/satellites/{CAMERA.device.id}/media", json=guessed, headers={"Authorization": f"Bearer {camera.token}"}
        )
        stranger = await http.post(f"/satellites/{CAMERA.device.id}/media", json=guessed)
    assert (refused.status_code, stranger.status_code) == (403, 401)


async def test_a_session_ends_when_its_time_is_up_and_the_device_is_told() -> None:
    async with watched(view_max_s=1) as (media, camera, journal, _, _):
        session = await opened(media, Purpose.VIEW, OWNER, Browser(call=False))
        await ended(journal, MediaEnd.TIMED_OUT)
        await _until(lambda: camera.closed == [session])


@pytest.mark.parametrize(
    ("now", "reason"),
    [
        (None, MediaEnd.SIGNED_OUT),  # their admin session ended
        (Viewer(account_id="a-mathis", person=PersonId("mathis"), may=frozenset()), MediaEnd.ACCESS_CHANGED),  # role
    ],
)
async def test_a_session_ends_as_soon_as_its_person_is_gone_or_may_no_longer(
    now: Viewer | None, reason: MediaEnd
) -> None:
    gone = asyncio.Event()
    viewer = replace(OWNER, now=lambda: now if gone.is_set() else OWNER)
    async with watched() as (media, camera, journal, _, _):
        session = await opened(media, Purpose.VIEW, viewer, Browser(call=False))
        gone.set()
        await media.check()
        await ended(journal, reason)
        await _until(lambda: camera.closed == [session])


async def test_taking_someone_off_the_list_ends_what_they_watch() -> None:
    async with watched(viewers=frozenset({PersonId("lea")})) as (media, _, journal, _, pairing):
        await opened(media, Purpose.VIEW, LEA, Browser(call=False))
        await pairing.set_access(CAMERA.device.id, MediaAccess())
        await media.check()
        await ended(journal, MediaEnd.ACCESS_CHANGED)
        with pytest.raises(MediaRefused):
            await media.open(CAMERA.device.id, Purpose.VIEW, LEA, await Browser(call=False).offer())


async def test_the_voice_of_the_core_steps_aside_during_a_call() -> None:
    """Nothing of a call reaches the assistant: the device may not open its voice session meanwhile."""
    async with watched(voice=True) as (media, camera, _, url, _), httpx.AsyncClient(base_url=url) as http:
        await opened(media, Purpose.CALL, OWNER, Browser(call=True))
        voice = await http.post(
            f"/satellites/{CAMERA.device.id}/audio",
            json={"sdp": "v=0", "type": "offer"},
            headers={"Authorization": f"Bearer {camera.token}"},
        )
    assert voice.status_code == 403


async def test_a_picture_comes_from_the_device_and_is_kept_with_its_name() -> None:
    async with watched() as (media, _, _, _, _):
        taken, jpeg = await media.snapshot(CAMERA.device.id, OWNER)
        assert taken.name.startswith("entree-") and taken.name.endswith(".jpg") and jpeg == JPEG


@pytest.mark.parametrize(
    ("scope", "safe"),
    [
        ({"scheme": "wss", "client": ("192.168.1.20", 50000)}, True),
        ({"scheme": "ws", "client": ("127.0.0.1", 50000)}, True),
        ({"scheme": "ws", "client": ("192.168.1.20", 50000)}, False),
    ],
)
def test_a_device_that_films_links_over_tls_unless_on_the_core_s_machine(scope: dict[str, object], safe: bool) -> None:
    assert secure(scope) is safe
