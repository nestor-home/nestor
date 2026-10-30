"""Black-box conformance of a satellite driver to `nestor.satellite/2`, realtime profile (HTTP + WebRTC).

`check_satellite` runs a fake core (the real pairing service and satellite gateway, with no assistant
behind them) and launches the driver against it once per scenario. A driver is a Python coroutine
function taking a `Launch`, or a command where `{url}` is replaced by the core's URL and `{state}` by
a fresh folder for its token. The enrollment code is handed over in `NESTOR_PAIRING_URI` (environment
of a command, `Launch.pairing_uri` of a coroutine), the way a person would configure a headless
device. Each check names the rule of the standard (`docs/satellite-protocol.md`) it proves.

1. device code (P1, P2, P8, I1, I2, W1-W4): it declares `enrollment.provisioning`, asks to pair,
   keeps polling after a pending identify, claims its token once a person types its code, connects,
   says `hello`, acknowledges each intent (`intent.identify` when it declared `device.identify`),
   exchanges audio, and reconnects with the same token after a hang-up;
2. enrollment code (P3, P4): configured with a pairing URI, it pairs at once, with no code typed;
3. refused codes, wrong, expired and already used (P5): it presents a refused code once, never
   again, and falls back to a device code so a person can still pair it;
4. rate limit (P6): told to wait (429, `Retry-After`), it waits, then pairs.

    report = await check_satellite(["./my-driver", "--core", "{url}", "--token-file", "{state}/token"])
    assert report.passed, report.failures()
"""

import asyncio
import contextlib
import os
import secrets
import socket
import subprocess
import tempfile
import time
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import RawAudioTrack

from nestor.adapters.channels.voice.satellites.gateway import SatelliteGateway
from nestor.adapters.channels.voice.server import SignallingServer
from nestor.core import utc_now
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    AUDIO_CAPTURE,
    AUDIO_PLAYBACK,
    IDENTIFY,
    AttemptLimiter,
    Device,
    Manifest,
    Pairing,
    PairingMethod,
    PairingState,
    PairingStatus,
    PairingTicket,
    Satellite,
    pairing_uri,
)
from nestor.modules.satellites.codes import ALPHABET
from nestor.testing.journal import MemoryEventLog
from nestor.testing.satellites import Findings, ProtocolProbe, SatelliteSession

AUDIO_RATE = 48000
PAIRING_URI = "NESTOR_PAIRING_URI"
IDENTIFY_WAIT_S = 5.0  # how long the person waits for a pending device to see its identify


@dataclass(frozen=True, slots=True)
class Launch:
    """What a driver is started with: the core, the enrollment code if a person gave one, and a fresh
    folder where it may keep its token."""

    url: str
    pairing_uri: str | None
    state: Path


type Driver = Callable[[Launch], Coroutine[Any, Any, None]] | Sequence[str]


@dataclass(slots=True)
class _Attempt:
    at: float
    code: str | None
    manifest: Manifest


class _Clock:
    def __init__(self) -> None:
        self.offset = timedelta()

    def __call__(self) -> datetime:
        return utc_now() + self.offset


class _WatchedPairing(Pairing):
    """The pairing service, watched: every request and poll is noted, and the household member who
    types the device code (when `approve_after_s` is set) and asks a pending device to identify."""

    def __init__(self, *, approve_after_s: float | None, limiter: AttemptLimiter | None = None) -> None:
        self.clock = _Clock()
        super().__init__(Journal(MemoryEventLog()), limiter=limiter, clock=self.clock)
        self._approve_after_s = approve_after_s
        self.attempts: list[_Attempt] = []
        self.requested = asyncio.Event()
        self.fell_back = asyncio.Event()  # a request without a code came after one with a code
        self.claimed = asyncio.Event()
        self.polled_after_identify = asyncio.Event()
        self.identify_seen = False  # the device received the pending identify in a poll answer
        self.limit_first_code = False  # rate-limit the first enrollment code, wherever it comes from
        self._approvals: set[asyncio.Task[None]] = set()

    async def request(
        self,
        manifest: Manifest,
        *,
        enrollment_code: str | None = None,
        method: PairingMethod | None = None,
        source: str = "unknown",
    ) -> PairingTicket:
        self.attempts.append(_Attempt(time.monotonic(), enrollment_code, manifest))
        if enrollment_code is not None and self.limit_first_code:
            self.limit_first_code = False
            self._limiter.failed(source, self.clock())  # as if someone had just tried a wrong code from there
        if enrollment_code is None and any(a.code for a in self.attempts):
            self.fell_back.set()
        self.requested.set()
        ticket = await super().request(manifest, enrollment_code=enrollment_code, method=method, source=source)
        if ticket.device_code is not None and self._approve_after_s is not None:
            task = asyncio.create_task(self._person(ticket, manifest))
            self._approvals.add(task)
            task.add_done_callback(self._approvals.discard)
        return ticket

    def poll(self, pairing_id: str) -> PairingState:
        state = super().poll(pairing_id)
        if state.identify:
            self.identify_seen = True
        elif self.identify_seen and state.status is PairingStatus.PENDING:
            self.polled_after_identify.set()
        if state.token is not None:
            self.claimed.set()
        return state

    async def _person(self, ticket: PairingTicket, manifest: Manifest) -> None:
        """Asks a device that can identify to do so, waits until it polled past it (or a while), then
        types its code."""
        assert self._approve_after_s is not None and ticket.device_code is not None
        if IDENTIFY in manifest.names:
            await self.identify_pending(ticket.id)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.polled_after_identify.wait(), IDENTIFY_WAIT_S)
        await asyncio.sleep(self._approve_after_s)
        await self.approve(ticket.device_code, pairing_id=ticket.id)


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


@dataclass(slots=True)
class _Core:
    """One fake core, serving one scenario."""

    pairing: _WatchedPairing
    url: str = ""
    connections: asyncio.Queue[_Connection] = field(default_factory=asyncio.Queue)

    @contextlib.asynccontextmanager
    async def serving(self) -> Any:
        port = _free_port()
        server = SignallingServer(host="127.0.0.1", port=port, routes=[SatelliteGateway(self.pairing, self._connected)])
        serving = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.01)
        self.url = f"http://127.0.0.1:{port}"
        try:
            yield self
        finally:
            server.stop()
            await serving

    async def _connected(self, connection: SmallWebRTCConnection, satellite: Satellite) -> None:
        link = _Connection(connection, satellite)
        await connection.connect()  # what a transport does once its pipeline is up: messages flow from here
        with self.pairing.online(satellite.id, lambda: None):
            self.connections.put_nowait(link)
            await link.ended.wait()


class FakeCore:
    def __init__(self, *, deadline_s: float = 10.0, approve_after_s: float = 0.5, probe: ProtocolProbe | None = None):
        self.deadline_s = deadline_s
        self.probe = probe or ProtocolProbe()
        self._approve_after_s = approve_after_s

    async def check(self, driver: Driver) -> Findings:
        findings = Findings()
        await self._device_code(driver, findings)
        if not findings.passed:
            return findings  # the other scenarios build on pairing and connecting
        await self._enrollment(driver, findings)
        for refusal in ("wrong", "expired", "used"):
            await self._refused(driver, findings, refusal)
        await self._rate_limited(driver, findings)
        return findings

    async def _device_code(self, driver: Driver, findings: Findings) -> None:
        core = _Core(_WatchedPairing(approve_after_s=self._approve_after_s))
        async with core.serving(), _running(driver, core.url, None, findings):
            pairing = core.pairing
            if not findings.add("asks to pair", await _within(pairing.requested.wait(), self.deadline_s)):
                return
            manifest = pairing.attempts[0].manifest
            findings.add(
                "declares enrollment.provisioning (P1)", PairingMethod.PROVISIONING in manifest.pairing_methods
            )
            if not findings.add("claims its token once its device code is typed (P2)",
                                await _within(pairing.claimed.wait(), self.deadline_s)):  # fmt: skip
                return
            if IDENTIFY in manifest.names:
                findings.add("keeps polling after a pending identify (I1)",
                             pairing.identify_seen and pairing.polled_after_identify.is_set(),
                             "never polled past the identify")  # fmt: skip
            first = await self._next(core, findings, "connects with its token (W1)")
            if first is None or not await self.probe.run(first, first.satellite, findings):
                return
            await self._check_audio(first, findings)
            await first.connection.disconnect()
            again = await self._next(core, findings, "reconnects with the same token after a hang-up (W4)")
            if again is not None:
                await self.probe.run(again, again.satellite, findings, label="after reconnecting: ")
                await again.connection.disconnect()

    async def _enrollment(self, driver: Driver, findings: Findings) -> None:
        core = _Core(_WatchedPairing(approve_after_s=None))
        async with core.serving():
            started = await core.pairing.start_addition(PairingMethod.PROVISIONING)
            assert started.code is not None
            async with _running(driver, core.url, pairing_uri(core.url, started.code), findings):
                claimed = await _within(core.pairing.claimed.wait(), self.deadline_s)
                sent = any(a.code for a in core.pairing.attempts)
                findings.add(f"pairs with the enrollment code of {PAIRING_URI}, no code typed (P3, P4)",
                             claimed and sent, "no token claimed" if not claimed else "")  # fmt: skip
                if claimed:
                    link = await self._next(core, findings, "connects after pairing with an enrollment code")
                    if link is not None:
                        await self.probe.run(link, link.satellite, findings, label="enrolled: ")
                        await link.connection.disconnect()

    async def _refused(self, driver: Driver, findings: Findings, refusal: str) -> None:
        core = _Core(_WatchedPairing(approve_after_s=None))
        async with core.serving():
            code = await _refused_code(core.pairing, refusal)
            async with _running(driver, core.url, pairing_uri(core.url, code), findings):
                fell_back = await _within(core.pairing.fell_back.wait(), self.deadline_s)
                await asyncio.sleep(1.0)  # time to retry, if it wrongly would
                findings.add(
                    f"falls back to a device code after its enrollment code is refused ({refusal}) (P5)", fell_back
                )
                tries = sum(a.code is not None for a in core.pairing.attempts)
                findings.add(
                    f"presents a refused enrollment code ({refusal}) only once (P5)", tries == 1, f"{tries} times"
                )

    async def _rate_limited(self, driver: Driver, findings: Findings) -> None:
        limiter = AttemptLimiter(per_source=1, window_s=1.5)
        core = _Core(_WatchedPairing(approve_after_s=None, limiter=limiter))
        async with core.serving():
            started = await core.pairing.start_addition(PairingMethod.PROVISIONING)
            assert started.code is not None
            core.pairing.limit_first_code = True
            async with _running(driver, core.url, pairing_uri(core.url, started.code), findings):
                paired = await _within(core.pairing.claimed.wait(), self.deadline_s + limiter.window_s)
                coded = [a.at for a in core.pairing.attempts if a.code is not None]
                waited = len(coded) >= 2 and coded[1] - coded[0] >= 1.0
                seen = f"attempts at {[round(t - coded[0], 2) for t in coded]} s" if coded else "no attempt"
                findings.add("waits for Retry-After when rate-limited (P6)", waited, seen)
                findings.add("pairs once the rate limit lifts (P6)", paired)

    async def _next(self, core: _Core, findings: Findings, check: str) -> _Connection | None:
        try:
            connection = await asyncio.wait_for(core.connections.get(), self.deadline_s)
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
            findings.add("receives the core's audio (W3)", await _within(_reports_reception(link.connection), 5.0),
                         "no RTCP receiver report from the satellite")  # fmt: skip
        if AUDIO_CAPTURE in capabilities:
            findings.add("sends its microphone audio (W3)",
                         await _within(link.connection.audio_input_track().recv(), 5.0),
                         "no audio frame from the satellite")  # fmt: skip


async def check_satellite(driver: Driver, **options: Any) -> Findings:
    return await FakeCore(**options).check(driver)


async def _refused_code(pairing: Pairing, refusal: str) -> str:
    """An enrollment code the core refuses for `refusal`: wrong, expired or used."""
    if refusal == "wrong":
        return "".join(secrets.choice(ALPHABET) for _ in range(8))
    started = await pairing.start_addition(PairingMethod.PROVISIONING, ttl_s=60)
    assert started.code is not None
    if refusal == "expired":
        assert isinstance(pairing, _WatchedPairing)
        pairing.clock.offset = timedelta(seconds=61)
    else:
        other = Manifest(Device("deja-appaire", "test", "salon"), pairing_methods=(PairingMethod.PROVISIONING,))
        await Pairing.request(pairing, other, enrollment_code=started.code, method=PairingMethod.PROVISIONING)
    return started.code


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


@contextlib.asynccontextmanager
async def _running(driver: Driver, url: str, uri: str | None, findings: Findings) -> Any:
    """The driver, running for the scenario; a crash before it is stopped is a failure."""
    with tempfile.TemporaryDirectory(prefix="nestor-satellite-") as state:
        launch = Launch(url, uri, Path(state))
        task, process = None, None
        if isinstance(driver, Sequence):
            env = {k: v for k, v in os.environ.items() if k != PAIRING_URI} | ({PAIRING_URI: uri} if uri else {})
            command = [part.replace("{url}", url).replace("{state}", state) for part in driver]
            process = subprocess.Popen(command, env=env)
        else:
            task = asyncio.create_task(driver(launch), name="satellite under test")
        try:
            yield launch
        finally:
            if crash := await _stop(task, process):
                findings.add("runs without crashing", False, crash)


async def _stop(task: asyncio.Task[None] | None, process: subprocess.Popen[bytes] | None) -> str | None:
    """Stop the driver; how it crashed, if it did before being stopped."""
    if task is not None:
        if task.done() and not task.cancelled() and (error := task.exception()):
            return repr(error)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if process is not None:
        if (code := process.poll()) is not None:
            return f"exited with status {code}"
        process.terminate()
        await asyncio.to_thread(process.wait, 10)
    return None
