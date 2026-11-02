"""Black-box conformance of a satellite driver to `nestor.satellite/1`.

`check_satellite` runs a fake core (the real pairing service and satellite gateway, with no assistant
behind them) and launches the driver against it once per scenario. A driver is a Python coroutine
function taking a `Launch`, or a command where `{url}` is replaced by the core's URL and `{state}` by
a fresh folder for its token. The enrollment code is handed over in `NESTOR_PAIRING_URI` (environment
of a command, `Launch.pairing_uri` of a coroutine), the way a person would configure a headless
device. Each check names the rule of the standard (https://nestorhome.dev/docs/satellites/protocol/) it
proves; checks and what was seen instead are `Message`s of the `conformance.ftl` catalogue.
`nestor satellites conformance` runs the suite on a command and prints them.

1. device code (P1, P2, P8, I1, I2, L1-L5, T2, A1, A2): it declares `enrollment.provisioning`, asks to
   pair, keeps polling after a pending identify, claims its token once a person types its code, opens
   its link with a `hello`, acknowledges each intent (`intent.identify` when it declared
   `device.identify`, `intent.text` when it declared `text.display`), exchanges audio when it declared
   some, reconnects with the same token after the core closes its link, and pairs again once its
   token is refused;
2. enrollment code (P3, P4, A1): configured with a pairing URI that grants no audio, it pairs at once,
   with no code typed, and offers no audio;
3. refused codes, wrong, expired and already used (P5): it presents a refused code once, never
   again, and falls back to a device code so a person can still pair it;
4. rate limit (P6): told to wait (429, `Retry-After`), it waits, then pairs.

Checking audio needs the `voice` extra (WebRTC); the rest does not.

    report = await check_satellite(["./my-driver", "--core", "{url}", "--token-file", "{state}/token"])
    assert report.passed, report.failures()
"""

import asyncio
import contextlib
import json
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

from fastapi import Request, WebSocket

from nestor.adapters.channels.satellites.gateway import AudioOffers, Close, SatelliteGateway
from nestor.adapters.channels.satellites.server import DeviceServer
from nestor.core import Capability, utc_now
from nestor.core.i18n import Message
from nestor.modules.behavior import EXPRESSION, HEAD_MOTION
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    AUDIO,
    AUDIO_CAPTURE,
    AUDIO_PLAYBACK,
    IDENTIFY,
    PERSON_DETECTION,
    SPEECH_ACTIVITY,
    TEXT_DISPLAY,
    TEXT_INPUT,
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

# What the enrolled device may do: anything it declares but audio (A1: it must not offer any).
SILENT = (TEXT_INPUT, TEXT_DISPLAY, SPEECH_ACTIVITY, PERSON_DETECTION, EXPRESSION, HEAD_MOTION, IDENTIFY)
AUDIO_RATE = 48000
PAIRING_URI = "NESTOR_PAIRING_URI"
IDENTIFY_WAIT_S = 5.0  # how long the person waits for a pending device to see its identify
NO_AUDIO_WAIT_S = 2.0  # how long a device allowed no audio is watched for an offer


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


class _Link(SatelliteSession):
    """A device's link, as the probe sees it: the messages after its accepted `hello`."""

    def __init__(self, socket: WebSocket, satellite: Satellite, allowed: frozenset[Capability]) -> None:
        self.socket, self.satellite, self.allowed = socket, satellite, allowed
        self._outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.ended = asyncio.Event()

    async def receive(self) -> Any:
        while True:
            try:
                received = await self.socket.receive()
            except RuntimeError:
                received = {"type": "websocket.disconnect"}
            if received["type"] == "websocket.disconnect":
                self.ended.set()
                await asyncio.Event().wait()  # nothing more will come
            if (text := received.get("text")) is not None:
                try:
                    return json.loads(text)
                except ValueError:
                    return text  # off-contract: the probe says so

    def send(self, data: dict[str, Any]) -> None:
        self._outbox.put_nowait(data)

    async def write(self) -> None:
        while True:
            data = await self._outbox.get()
            with contextlib.suppress(Exception):
                await self.socket.send_text(json.dumps(data))

    async def close(self, code: Close) -> None:
        with contextlib.suppress(RuntimeError):
            await self.socket.close(code)
        self.ended.set()


class _Audio(AudioOffers):
    """Answers audio offers with a real WebRTC peer (the `voice` extra), each connection queued for
    the checks; `None` without the extra."""

    def __init__(self) -> None:
        from nestor.adapters.channels.satellites.voice.webrtc import PeerConnections

        self._peers = PeerConnections()
        self.connections: asyncio.Queue[Any] = asyncio.Queue()

    async def offer(self, device_id: str, body: dict[str, Any]) -> dict[str, Any]:
        async def connected(connection: Any) -> None:
            await connection.connect()
            self.connections.put_nowait(connection)

        return await self._peers.answer(body, connected)

    async def patch(self, device_id: str, body: dict[str, Any]) -> None:
        await self._peers.patch(body)

    async def close(self) -> None:
        await self._peers.close()


def _audio() -> tuple[_Audio | None, str | None]:
    """The audio checker, or the missing module that prevents it."""
    try:
        return _Audio(), None
    except ModuleNotFoundError as missing:
        return None, (missing.name or "pipecat").partition(".")[0]


@dataclass(slots=True)
class _Core:
    """One fake core, serving one scenario."""

    pairing: _WatchedPairing
    url: str = ""
    links: asyncio.Queue[_Link] = field(default_factory=asyncio.Queue)
    refusals: list[tuple[Close, str]] = field(default_factory=list)
    audio_offers: int = 0  # every audio offer received, allowed or not
    audio: _Audio | None = None
    missing: str | None = None  # the module audio checks need, when missing

    @contextlib.asynccontextmanager
    async def serving(self) -> Any:
        self.audio, self.missing = _audio()
        port = _free_port()
        gateway = SatelliteGateway(
            self.pairing,
            on_link=self._linked,
            audio=self.audio,
            refused=lambda _device, code, why: self.refusals.append((code, why)),
        )
        server = DeviceServer(host="127.0.0.1", port=port, gateway=gateway)

        @server.app.middleware("http")
        async def count_offers(request: Request, call_next: Any) -> Any:
            if request.method == "POST" and request.url.path.endswith("/audio"):
                self.audio_offers += 1
            return await call_next(request)

        serving = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.01)
        self.url = f"http://127.0.0.1:{port}"
        try:
            yield self
        finally:
            server.stop()
            await serving
            if self.audio is not None:
                await self.audio.close()

    async def _linked(self, socket: WebSocket, satellite: Satellite, allowed: frozenset[Capability]) -> None:
        link = _Link(socket, satellite, allowed)
        writer = asyncio.create_task(link.write())
        try:
            with self.pairing.online(satellite.id, lambda: None):
                self.links.put_nowait(link)
                await link.ended.wait()
        finally:
            writer.cancel()


class FakeCore:
    def __init__(self, *, deadline_s: float = 10.0, approve_after_s: float = 0.5, probe: ProtocolProbe | None = None):
        self.deadline_s = deadline_s
        self.probe = probe or ProtocolProbe()
        self._approve_after_s = approve_after_s

    async def check(self, driver: Driver) -> Findings:
        findings = Findings()
        await self._device_code(driver, findings)
        if not findings.passed:
            return findings  # the other scenarios build on pairing and linking
        await self._enrollment(driver, findings)
        for refusal in ("wrong", "expired", "used"):
            await self._refused(driver, findings, refusal)
        await self._rate_limited(driver, findings)
        return findings

    async def _device_code(self, driver: Driver, findings: Findings) -> None:
        core = _Core(_WatchedPairing(approve_after_s=self._approve_after_s))
        async with core.serving(), _running(driver, core.url, None, findings):
            pairing = core.pairing
            if not findings.add(Message.of("conformance-asks-to-pair"),
                                await _within(pairing.requested.wait(), self.deadline_s)):  # fmt: skip
                return
            manifest = pairing.attempts[0].manifest
            findings.add(
                Message.of("conformance-declares-provisioning"), PairingMethod.PROVISIONING in manifest.pairing_methods
            )
            if not findings.add(Message.of("conformance-claims-token"),
                                await _within(pairing.claimed.wait(), self.deadline_s)):  # fmt: skip
                return
            if IDENTIFY in manifest.names:
                findings.add(Message.of("conformance-polls-after-identify"),
                             pairing.identify_seen and pairing.polled_after_identify.is_set(),
                             Message.of("conformance-never-polled-after-identify"))  # fmt: skip
            first = await self._next(core, findings, Message.of("conformance-connects"))
            if first is None:
                return
            self.probe.welcome(first, first.satellite, first.allowed)
            await self._check_audio(core, first, findings)
            await self.probe.run(first, first.satellite, findings)
            await first.close(Close.STOPPING)
            again = await self._next(core, findings, Message.of("conformance-reconnects"))
            if again is None:
                return
            self.probe.welcome(again, again.satellite, again.allowed)
            await self.probe.run(again, again.satellite, findings, connection="reconnected")
            asked = len(pairing.attempts)
            await pairing.revoke(again.satellite.id)
            await again.close(Close.STOPPING)
            findings.add(Message.of("conformance-pairs-again"),
                         await _within(_until(lambda: len(pairing.attempts) > asked), self.deadline_s),
                         Message.of("conformance-never-asked-again"))  # fmt: skip

    async def _enrollment(self, driver: Driver, findings: Findings) -> None:
        core = _Core(_WatchedPairing(approve_after_s=None))
        async with core.serving():
            started = await core.pairing.start_addition(PairingMethod.PROVISIONING, capabilities=SILENT)
            assert started.code is not None
            async with _running(driver, core.url, pairing_uri(core.url, started.code), findings):
                claimed = await _within(core.pairing.claimed.wait(), self.deadline_s)
                sent = any(a.code for a in core.pairing.attempts)
                seen = Message.of("conformance-no-code-sent" if claimed else "conformance-no-token")
                findings.add(Message.of("conformance-enrolls", variable=PAIRING_URI), claimed and sent, seen)
                if not claimed:
                    return
                link = await self._next(core, findings, Message.of("conformance-connects-enrolled"))
                if link is None:
                    return
                self.probe.welcome(link, link.satellite, link.allowed)
                await self.probe.run(link, link.satellite, findings, connection="enrolled")
                if core.pairing.attempts[-1].manifest.names & AUDIO:
                    await asyncio.sleep(NO_AUDIO_WAIT_S)
                    findings.add(Message.of("conformance-no-unallowed-audio"), core.audio_offers == 0,
                                 Message.of("conformance-audio-offers", count=core.audio_offers))  # fmt: skip
                await link.close(Close.STOPPING)

    async def _refused(self, driver: Driver, findings: Findings, refusal: str) -> None:
        core = _Core(_WatchedPairing(approve_after_s=None))
        async with core.serving():
            code = await _refused_code(core.pairing, refusal)
            async with _running(driver, core.url, pairing_uri(core.url, code), findings):
                fell_back = await _within(core.pairing.fell_back.wait(), self.deadline_s)
                await asyncio.sleep(1.0)  # time to retry, if it wrongly would
                findings.add(Message.of("conformance-falls-back", refusal=refusal), fell_back)
                tries = sum(a.code is not None for a in core.pairing.attempts)
                findings.add(Message.of("conformance-refused-once", refusal=refusal), tries == 1,
                             Message.of("conformance-tries", count=tries))  # fmt: skip

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
                seen = (
                    Message.of("conformance-attempts", times=", ".join(f"{t - coded[0]:.2f}" for t in coded))
                    if coded
                    else Message.of("conformance-no-attempt")
                )
                findings.add(Message.of("conformance-waits-retry-after"), waited, seen)
                findings.add(Message.of("conformance-pairs-after-limit"), paired)

    async def _next(self, core: _Core, findings: Findings, check: Message) -> _Link | None:
        try:
            link = await asyncio.wait_for(core.links.get(), self.deadline_s)
        except TimeoutError:
            if core.refusals:
                code, why = core.refusals[-1]
                findings.add(check, False, Message.of("conformance-link-refused", code=int(code), why=why))
            else:
                findings.add(check, False, Message.of("conformance-no-link", seconds=self.deadline_s))
            return None
        findings.add(check, True)
        return link

    async def _check_audio(self, core: _Core, link: _Link, findings: Findings) -> None:
        wanted = link.allowed & AUDIO
        if not wanted:
            return
        if core.audio is None:
            findings.add(Message.of("conformance-exchanges-audio"), False,
                         Message.of("conformance-voice-missing", module=core.missing or "pipecat"))  # fmt: skip
            return
        try:
            connection = await asyncio.wait_for(core.audio.connections.get(), self.deadline_s)
        except TimeoutError:
            findings.add(Message.of("conformance-exchanges-audio"), False,
                         Message.of("conformance-no-audio-offer", seconds=self.deadline_s))  # fmt: skip
            return
        if AUDIO_PLAYBACK in wanted:
            import numpy as np
            from pipecat.transports.smallwebrtc.transport import RawAudioTrack

            track = RawAudioTrack(AUDIO_RATE)
            connection.replace_audio_track(track)
            t = np.arange(AUDIO_RATE) / AUDIO_RATE
            track.add_audio_bytes((6000 * np.sin(2 * np.pi * 440 * t)).astype(np.int16).tobytes())
            findings.add(Message.of("conformance-receives-audio"),
                         await _within(_reports_reception(connection), 5.0),
                         Message.of("conformance-no-receiver-report"))  # fmt: skip
        if AUDIO_CAPTURE in wanted:
            findings.add(Message.of("conformance-sends-audio"),
                         await _within(connection.audio_input_track().recv(), 5.0),
                         Message.of("conformance-no-audio-frame"))  # fmt: skip
        await connection.disconnect()


async def _until(condition: Callable[[], bool]) -> None:
    while not condition():
        await asyncio.sleep(0.05)


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


async def _reports_reception(connection: Any) -> None:
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
                findings.add(Message.of("conformance-runs"), False, crash)


async def _stop(task: asyncio.Task[None] | None, process: subprocess.Popen[bytes] | None) -> Message | None:
    """Stop the driver; how it crashed, if it did before being stopped."""
    if task is not None:
        if task.done() and not task.cancelled() and (error := task.exception()):
            return Message.of("conformance-raised", error=repr(error))
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if process is not None:
        if (code := process.poll()) is not None:
            return Message.of("conformance-exited", status=code)
        process.terminate()
        await asyncio.to_thread(process.wait, 10)
    return None
