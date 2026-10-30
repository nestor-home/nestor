"""A minimal satellite driver in Python, written only against the published protocol.

It pairs (and "shows" its code in `code`), connects with its token, says `hello` on the `nestor`
data channel, acknowledges every intent, plays the audio it receives, reports one observation, and
reconnects when the core hangs up. Its faults can be switched on to prove the conformance suite
catches them.
"""

import asyncio
import contextlib
import json
from dataclasses import dataclass
from typing import Any

import httpx
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError, MediaStreamTrack

from nestor.modules.behavior import Behavior
from nestor.modules.satellites import PERSON_DETECTION, Device, Manifest, wire


@dataclass(frozen=True, slots=True)
class Faults:
    claims_token: bool = True  # polls until approved (otherwise never comes back for its token)
    connects: bool = True  # crashes once paired otherwise
    says_hello: bool = True
    acks: bool = True
    honest_hello: bool = True  # say hello with its own device id
    reconnects: bool = True
    valid_messages: bool = True


class ReferenceSatellite:
    def __init__(
        self, url: str, manifest: Manifest, *, faults: Faults | None = None, observe: bool | None = None
    ) -> None:
        """`observe`: report people seen; by default only when it declared person detection."""
        self.url, self.manifest, self.faults = url, manifest, faults or Faults()
        self.observe = PERSON_DETECTION in manifest.names if observe is None else observe
        self.code: str | None = None
        self.token: str | None = None
        self.code_shown = asyncio.Event()
        self.welcomed = asyncio.Event()
        self.intents: list[wire.Message] = []
        self.audio_frames = 0
        self.connections = 0

    async def __call__(self, url: str) -> None:
        """The driver entry point the conformance suite launches."""
        self.url = url
        await self.run()

    async def run(self) -> None:
        async with httpx.AsyncClient(base_url=self.url, timeout=10) as http:
            token = await self._pair(http)
            if not self.faults.connects:
                raise RuntimeError("driver bug after pairing")
            while True:
                await self._connect_once(http, token)
                if not self.faults.reconnects:
                    await asyncio.Event().wait()

    async def _pair(self, http: httpx.AsyncClient) -> str:
        ticket = (await http.post("/satellites/pair", json=self.manifest.to_json())).json()
        self.code = ticket["code"]
        self.code_shown.set()
        if not self.faults.claims_token:
            await asyncio.Event().wait()
        while True:
            state = (await http.get(f"/satellites/pair/{ticket['pairing_id']}")).json()
            if state["status"] == "approved":
                self.token = state["token"]
                return state["token"]
            if state["status"] == "expired":
                raise RuntimeError("pairing expired")
            await asyncio.sleep(0.1)

    async def _connect_once(self, http: httpx.AsyncClient, token: str) -> None:
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        ended = asyncio.Event()
        players: set[asyncio.Task[None]] = set()
        peer.addTrack(AudioStreamTrack())  # the microphone: silence is enough here
        channel = peer.createDataChannel("nestor")

        def send(message: wire.Message | dict[str, Any]) -> None:
            data = message if isinstance(message, dict) else wire.encode(message)
            channel.send(json.dumps(data))

        @channel.on("open")
        def opened() -> None:
            if not self.faults.says_hello:
                send(wire.SpeechActivityObservation(active=True))
                return
            device = self.manifest.device if self.faults.honest_hello else Device("someone-else", "x", "salon")
            send(wire.Hello(manifest=Manifest(device, self.manifest.capabilities)))

        @channel.on("message")
        def received(raw: str) -> None:
            data = json.loads(raw)
            if data.get("type") == "signalling":
                if data.get("message", {}).get("type") == "peerLeft":
                    ended.set()
                return
            envelope = wire.decode(data)
            message = envelope.message
            if isinstance(message, wire.Welcome):
                self.welcomed.set()
                if self.observe:
                    send(wire.PersonObservation(count=1, confidence=0.92))
                if not self.faults.valid_messages:
                    send({"type": "observation.mood", "id": "x", "at": "2026-10-30T12:00:00+00:00", "payload": {}})
                    send(wire.BeatIntent())  # only the core sends intents
            else:
                self.intents.append(message)
                if self.faults.acks:
                    send(wire.Ack(of=envelope.id))
                if self.observe and message == wire.BehaviorIntent(behavior=Behavior.IDLE):
                    send(wire.PersonObservation(count=1, confidence=0.9))  # still there once it stopped talking

        @peer.on("track")
        def track(incoming: MediaStreamTrack) -> None:
            players.add(asyncio.ensure_future(self._play(incoming)))

        @peer.on("connectionstatechange")
        def state() -> None:
            if peer.connectionState in {"failed", "closed"}:
                ended.set()

        await peer.setLocalDescription(await peer.createOffer())
        offer = {"sdp": peer.localDescription.sdp, "type": peer.localDescription.type}
        headers = {"Authorization": f"Bearer {token}"}
        response = await http.post(f"/satellites/{self.manifest.device.id}/offer", json=offer, headers=headers)
        response.raise_for_status()
        answer = response.json()
        await peer.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
        self.connections += 1
        try:
            await ended.wait()
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


if __name__ == "__main__":  # a driver process: `python -m ….reference <core url> <manifest json>`
    import sys

    url, manifest = sys.argv[1], Manifest.from_json(json.loads(sys.argv[2]))
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(ReferenceSatellite(url, manifest).run())
