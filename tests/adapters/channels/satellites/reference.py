"""A minimal satellite driver in Python, written only against the published protocol.

It pairs (with the enrollment code it was launched with, else by "showing" its device code in
`code`, falling back to it when the enrollment code is refused), opens its link with its token in
`hello`, acknowledges every intent, offers audio when allowed and plays what it receives, reports one
observation, types what it is asked to (`type`) when allowed, reports a newer version of its software when allowed to
update (and installs only that one), reconnects when the core closes its link, and pairs again
when its token is refused. Its faults can be switched on to prove the conformance suite catches them.
"""

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import websockets
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError, MediaStreamTrack

from nestor.adapters.channels.satellites.conformance import Launch
from nestor.modules.behavior import Behavior
from nestor.modules.satellites import (
    AUDIO_CAPTURE,
    AUDIO_PLAYBACK,
    PERSON_DETECTION,
    TEXT_INPUT,
    UPDATE,
    Device,
    Manifest,
    PairingMethod,
    UpdateState,
    parse_pairing_uri,
    wire,
)

TOKEN_REFUSED = 4401
FOUND = "9.9.9"  # the newer version of its software it finds at its own source


@dataclass(frozen=True, slots=True)
class Faults:
    claims_token: bool = True  # polls until approved (otherwise never comes back for its token)
    connects: bool = True  # crashes once paired otherwise
    says_hello: bool = True
    acks: bool = True
    honest_hello: bool = True  # say hello with its own device id
    reconnects: bool = True
    valid_messages: bool = True
    reads_uri: bool = True  # pairs with the enrollment code of its launch
    falls_back: bool = True  # asks for a device code once its enrollment code is refused
    retries_refused: bool = False  # presents a refused enrollment code again
    honours_retry_after: bool = True
    forgets_refused_token: bool = True  # pairs again once its token is refused
    offers_unallowed_audio: bool = False  # offers audio although welcome allowed none
    reports_update: bool = True  # says where its software stands when allowed device.update
    installs_unreported: bool = False  # installs whatever version intent.update names


class ReferenceSatellite:
    def __init__(
        self,
        url: str,
        manifest: Manifest,
        *,
        faults: Faults | None = None,
        observe: bool | None = None,
    ) -> None:
        """`observe`: report people seen; by default only when it declared person detection."""
        self.url, self.manifest, self.faults = url, manifest, faults or Faults()
        self.observe = PERSON_DETECTION in manifest.names if observe is None else observe
        self.code: str | None = None
        self.token: str | None = None
        self.code_shown = asyncio.Event()
        self.welcomed = asyncio.Event()
        self.intents: list[wire.Message] = []
        self.allowed: frozenset[str] = frozenset()
        self.audio_frames = 0
        self.connections = 0
        self.identified = 0
        self.enrollment_code: str | None = None
        self._send: Callable[[wire.Message], Awaitable[None]] | None = None  # on its current link

    async def type(self, text: str) -> None:
        """A person types `text` on it (when allowed `text.input`), over its current link."""
        assert self._send is not None and TEXT_INPUT in self.allowed, "not linked, or not allowed to type"
        await self._send(wire.TextInput(text=text))

    async def __call__(self, launch: Launch) -> None:
        """The driver entry point the conformance suite launches: a fresh device each time."""
        self.url, self.token, self.code = launch.url, None, None
        self.enrollment_code = None
        if launch.pairing_uri and self.faults.reads_uri:
            _, self.enrollment_code = parse_pairing_uri(launch.pairing_uri)
        await self.run()

    async def run(self) -> None:
        async with httpx.AsyncClient(base_url=self.url, timeout=10) as http:
            token = await self._pair(http)
            if not self.faults.connects:
                raise RuntimeError("driver bug after pairing")
            while True:
                if await self._link_once(http, token) == TOKEN_REFUSED and self.faults.forgets_refused_token:
                    token = await self._pair(http)
                    continue
                if not self.faults.reconnects:
                    await asyncio.Event().wait()
                await asyncio.sleep(0.1)

    async def _pair(self, http: httpx.AsyncClient) -> str:
        code = self.enrollment_code
        while True:
            body: dict[str, Any] = {"manifest": self.manifest.to_json()}
            if code is not None:
                body |= {"enrollment_code": code, "method": PairingMethod.PROVISIONING.value}
            response = await http.post("/satellites/pairings", json=body)
            if response.status_code == 429:
                await asyncio.sleep(float(response.headers["Retry-After"]) if self.faults.honours_retry_after else 0.1)
                continue
            if response.status_code == 403:  # the enrollment code is refused: never again
                if not self.faults.falls_back:
                    await asyncio.Event().wait()
                code = code if self.faults.retries_refused else None
                await asyncio.sleep(0.1)
                continue
            ticket = response.raise_for_status().json()
            if "device_code" in ticket:
                self.code = ticket["device_code"]
                self.code_shown.set()
            if not self.faults.claims_token:
                await asyncio.Event().wait()
            state = await self._poll(http, ticket["pairing_id"])
            if state is not None:
                return state

    async def _poll(self, http: httpx.AsyncClient, pairing_id: str) -> str | None:
        while True:
            state = (await http.get(f"/satellites/pairings/{pairing_id}")).json()
            if state.get("identify"):
                self.identified += 1
            if state["status"] == "approved":
                self.token = state["token"]
                return state["token"]
            if state["status"] == "expired":
                return None
            await asyncio.sleep(0.1)

    async def _link_once(self, http: httpx.AsyncClient, token: str) -> int | None:
        """One link, until the core closes it; its close code."""
        url = self.url.replace("http", "ws", 1) + f"/satellites/{self.manifest.device.id}/link"
        async with websockets.connect(url) as link:
            audio: asyncio.Task[None] | None = None

            async def send(message: wire.Message | dict[str, Any]) -> None:
                await link.send(json.dumps(message if isinstance(message, dict) else wire.encode(message)))

            if self.faults.says_hello:
                device = self.manifest.device if self.faults.honest_hello else Device("someone-else", "x", "salon")
                hello = Manifest(
                    device, self.manifest.capabilities, self.manifest.pairing_methods, software=self.manifest.software
                )
                await send(wire.Hello(manifest=hello, token=token))
            else:
                await send(wire.SpeechActivityObservation(active=True))
            self._send = send
            self.connections += 1
            try:
                async for raw in link:
                    envelope = wire.decode(json.loads(raw))
                    message = envelope.message
                    if isinstance(message, wire.Welcome):
                        self.allowed = frozenset(message.capabilities)
                        self.welcomed.set()
                        if self.allowed & {AUDIO_CAPTURE, AUDIO_PLAYBACK} or self.faults.offers_unallowed_audio:
                            audio = asyncio.create_task(self._audio(http, token))
                        if self.observe:
                            await send(wire.PersonObservation(count=1, confidence=0.92))
                        if UPDATE in self.allowed and self.faults.reports_update:
                            await send(wire.UpdateStatusReport(state=UpdateState.AVAILABLE, version=FOUND))
                        if not self.faults.valid_messages:
                            await send({"type": "observation.mood", "id": "x", "at": "2026-10-30T12:00:00+00:00",
                                        "payload": {}})  # fmt: skip
                            await send(wire.BeatIntent())  # only the core sends intents
                        continue
                    self.intents.append(message)
                    if isinstance(message, wire.IdentifyIntent):
                        self.identified += 1
                    if self.faults.acks:
                        await send(wire.Ack(of=envelope.id))
                    if isinstance(message, wire.UpdateIntent) and (
                        message.version == FOUND or self.faults.installs_unreported
                    ):
                        await send(wire.UpdateStatusReport(state=UpdateState.INSTALLING, version=message.version))
                    if self.observe and message == wire.BehaviorIntent(behavior=Behavior.IDLE):
                        await send(wire.PersonObservation(count=1, confidence=0.9))  # still there once it stopped
            except websockets.ConnectionClosed:
                pass
            finally:
                self._send = None
                if audio is not None:
                    audio.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await audio
            return link.close_code

    async def _audio(self, http: httpx.AsyncClient, token: str) -> None:
        """Offer WebRTC audio and play what comes, until cancelled with the link."""
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        players: set[asyncio.Task[None]] = set()
        peer.addTrack(AudioStreamTrack())  # the microphone: silence is enough here

        @peer.on("track")
        def track(incoming: MediaStreamTrack) -> None:
            players.add(asyncio.ensure_future(self._play(incoming)))

        try:
            await peer.setLocalDescription(await peer.createOffer())
            offer = {"sdp": peer.localDescription.sdp, "type": peer.localDescription.type}
            headers = {"Authorization": f"Bearer {token}"}
            response = await http.post(f"/satellites/{self.manifest.device.id}/audio", json=offer, headers=headers)
            if response.status_code != 200:
                return
            answer = response.json()
            await peer.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
            await asyncio.Event().wait()
        finally:
            await peer.close()
            for player in players:
                player.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await player

    async def _play(self, track: MediaStreamTrack) -> None:
        with contextlib.suppress(MediaStreamError):
            while True:
                await track.recv()
                self.audio_frames += 1


if __name__ == "__main__":  # a driver process: `python -m ….reference <core url> <state> <manifest json>`
    import os
    import sys
    from pathlib import Path

    launch = Launch(sys.argv[1], os.environ.get("NESTOR_PAIRING_URI"), Path(sys.argv[2]))
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(ReferenceSatellite(launch.url, Manifest.from_json(json.loads(sys.argv[3])))(launch))
