"""Black-box conformance of a satellite driver, realtime profile (HTTP + WebRTC).

`check_satellite` runs a fake core — the real pairing service and satellite gateway, with no
assistant behind them — launches the driver against it (a Python coroutine function taking the
core's URL, or a command whose `{url}` is replaced), plays the household member who confirms the
code, then checks that the driver:

1. pairs with the code and claims its token;
2. connects with that token, sends a valid `hello`, acknowledges each intent in time and sends only
   valid messages (`nestor.testing.satellites.ProtocolProbe`);
3. receives the core's audio (its receiver reports reach the core) and, with `audio.capture`,
   sends audio;
4. reconnects with the same token after the core hangs up, and says `hello` again.

    report = await check_satellite(["./my-driver", "--core", "{url}"])
    assert report.passed, report.failures()
"""

import asyncio
import contextlib
import socket
import subprocess
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

import numpy as np
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import RawAudioTrack

from nestor.adapters.channels.voice.satellites.gateway import SatelliteGateway
from nestor.adapters.channels.voice.server import SignallingServer
from nestor.modules.journal import Journal
from nestor.modules.satellites import AUDIO_CAPTURE, AUDIO_PLAYBACK, Manifest, Pairing, PairingState, Satellite
from nestor.modules.satellites import PairingTicket as Ticket
from nestor.testing.journal import MemoryEventLog
from nestor.testing.satellites import Findings, ProtocolProbe, SatelliteSession

type Driver = Callable[[str], Coroutine[Any, Any, None]] | Sequence[str]

AUDIO_RATE = 48000


class _ApprovingPairing(Pairing):
    """The pairing service, plus the household member who reads the code and confirms it."""

    def __init__(self, journal: Journal, *, approve_after_s: float) -> None:
        super().__init__(journal)
        self._approve_after_s = approve_after_s
        self.requested = asyncio.Event()
        self.claimed = asyncio.Event()
        self._approvals: set[asyncio.Task[None]] = set()

    async def request(self, manifest: Manifest) -> Ticket:
        ticket = await super().request(manifest)
        self.requested.set()
        task = asyncio.create_task(self._approve_later(ticket.code))
        self._approvals.add(task)
        task.add_done_callback(self._approvals.discard)
        return ticket

    def poll(self, pairing_id: str) -> PairingState:
        state = super().poll(pairing_id)
        if state.token is not None:
            self.claimed.set()
        return state

    async def _approve_later(self, code: str) -> None:
        await asyncio.sleep(self._approve_after_s)
        await self.approve(code)


class _Connection(SatelliteSession):
    def __init__(self, connection: SmallWebRTCConnection, satellite: Satellite) -> None:
        self.connection, self.satellite = connection, satellite
        self._messages: asyncio.Queue[Any] = asyncio.Queue()
        self.ended = asyncio.Event()
        connection.add_event_handler("app-message", self._received)
        connection.add_event_handler("closed", self._closed)

    async def receive(self) -> Any:
        return await self._messages.get()

    def send(self, data: dict[str, Any]) -> None:
        self.connection.send_app_message(data)

    async def _received(self, _connection: SmallWebRTCConnection, data: Any) -> None:
        self._messages.put_nowait(data)

    async def _closed(self, _connection: SmallWebRTCConnection) -> None:
        self.ended.set()


class FakeCore:
    def __init__(self, *, deadline_s: float = 10.0, approve_after_s: float = 0.5, probe: ProtocolProbe | None = None):
        self.deadline_s = deadline_s
        self.probe = probe or ProtocolProbe()
        self._approve_after_s = approve_after_s
        self._connections: asyncio.Queue[_Connection] = asyncio.Queue()

    async def check(self, driver: Driver) -> Findings:
        findings = Findings()
        pairing = _ApprovingPairing(Journal(MemoryEventLog()), approve_after_s=self._approve_after_s)
        port = _free_port()
        server = SignallingServer(host="127.0.0.1", port=port, routes=[SatelliteGateway(pairing, self._connected)])
        serving = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.01)
        running = _launch(driver, f"http://127.0.0.1:{port}")
        try:
            await self._run(pairing, findings)
        finally:
            if crash := await running.stop():
                findings.add("runs without crashing", False, crash)
            server.stop()
            await serving
        return findings

    async def _run(self, pairing: _ApprovingPairing, findings: Findings) -> None:
        if not findings.add("asks to pair", await _within(pairing.requested.wait(), self.deadline_s)):
            return
        if not findings.add("claims its token once approved", await _within(pairing.claimed.wait(), self.deadline_s)):
            return
        first = await self._next_connection(findings, "connects with its token")
        if first is None or not await self.probe.run(first, first.satellite, findings):
            return
        await self._check_audio(first, findings)
        await first.connection.disconnect()
        again = await self._next_connection(findings, "reconnects with the same token after a hang-up")
        if again is not None:
            await self.probe.run(again, again.satellite, findings, label="after reconnecting: ")
            await again.connection.disconnect()

    async def _next_connection(self, findings: Findings, check: str) -> _Connection | None:
        try:
            connection = await asyncio.wait_for(self._connections.get(), self.deadline_s)
        except TimeoutError:
            findings.add(check, False, f"no authenticated offer within {self.deadline_s:g} s")
            return None
        findings.add(check, True)
        return connection

    async def _check_audio(self, link: _Connection, findings: Findings) -> None:
        capabilities = link.satellite.capabilities
        if AUDIO_PLAYBACK in capabilities:
            track = RawAudioTrack(AUDIO_RATE)
            link.connection.replace_audio_track(track)
            t = np.arange(AUDIO_RATE) / AUDIO_RATE
            track.add_audio_bytes((6000 * np.sin(2 * np.pi * 440 * t)).astype(np.int16).tobytes())
            findings.add("receives the core's audio", await _within(_reports_reception(link.connection), 5.0),
                         "no RTCP receiver report from the satellite")  # fmt: skip
        if AUDIO_CAPTURE in capabilities:
            findings.add("sends its microphone audio", await _within(link.connection.audio_input_track().recv(), 5.0),
                         "no audio frame from the satellite")  # fmt: skip

    async def _connected(self, connection: SmallWebRTCConnection, satellite: Satellite) -> None:
        link = _Connection(connection, satellite)
        await connection.connect()  # what a transport does once its pipeline is up: messages flow from here
        self._connections.put_nowait(link)
        await link.ended.wait()


async def check_satellite(driver: Driver, **options: Any) -> Findings:
    return await FakeCore(**options).check(driver)


async def _reports_reception(connection: SmallWebRTCConnection) -> None:
    sender = connection.pc.getTransceivers()[0].sender
    while not any(s.type == "remote-inbound-rtp" for s in (await sender.getStats()).values()):
        await asyncio.sleep(0.1)


async def _within(work: Coroutine[Any, Any, Any], timeout_s: float) -> bool:
    try:
        await asyncio.wait_for(work, timeout_s)
    except TimeoutError:
        return False
    return True


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class _Running:
    def __init__(self, task: asyncio.Task[None] | None = None, process: subprocess.Popen[bytes] | None = None):
        self._task, self._process = task, process

    async def stop(self) -> str | None:
        """Stop the driver; how it crashed, if it did before being stopped."""
        if self._task is not None:
            if self._task.done() and not self._task.cancelled() and (error := self._task.exception()):
                return repr(error)
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._process is not None:
            if (code := self._process.poll()) is not None:
                return f"exited with status {code}"
            self._process.terminate()
            await asyncio.to_thread(self._process.wait, 10)
        return None


def _launch(driver: Driver, url: str) -> _Running:
    if isinstance(driver, Sequence):
        return _Running(process=subprocess.Popen([part.replace("{url}", url) for part in driver]))
    return _Running(task=asyncio.create_task(driver(url), name="satellite under test"))
