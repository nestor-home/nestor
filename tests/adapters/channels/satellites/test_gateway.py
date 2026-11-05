"""Paired satellites reaching the satellites channel: their link, their typed text and its answers,
their audio, and everyone else refused."""

import asyncio
import json
import socket
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import websockets

from nestor.adapters.channels.satellites.channel import SatellitesChannel
from nestor.adapters.channels.satellites.gateway import SatelliteGateway
from nestor.adapters.channels.satellites.server import DeviceServer
from nestor.adapters.channels.satellites.voice.audio import SatelliteVoice
from nestor.adapters.channels.satellites.voice.session import SessionSettings
from nestor.core import ContractError, PersonId, ProviderError
from nestor.modules.behavior import Behavior, Expression
from nestor.modules.channels import Address, Assistant, InboundMessage, Medium, MessageEnd, Reply, Sender
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    TEXT_DISPLAY,
    TEXT_INPUT,
    AttemptLimiter,
    Device,
    Manifest,
    Pairing,
    PairingMethod,
    PersonDetected,
    SatelliteConnected,
    SatelliteDisconnected,
    wire,
)
from nestor.modules.satellites.types import DeclaredCapability
from nestor.testing.journal import MemoryEventLog
from nestor.testing.satellites import SOFTWARE

from .reference import Faults, ReferenceSatellite
from .test_conformance import MANIFEST
from .voice.doubles import FakeAssistant, FakeSpeech, ScriptedSTT, ToneTTS
from .voice.replay import ReplayTransport

KITCHEN = Address("satellites", "cuisine")
SCREEN = Manifest(
    Device("ecran-cuisine", "tablet", "cuisine"),
    (DeclaredCapability(TEXT_INPUT), DeclaredCapability(TEXT_DISPLAY)),
    software=SOFTWARE,
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _answers(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


async def _until(condition: Callable[[], bool], timeout_s: float = 10) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.05)


@asynccontextmanager
async def home(
    *, voice: bool = True, assistant: Assistant | None = None
) -> AsyncGenerator[tuple[SatellitesChannel, Pairing, Journal, str]]:
    journal = Journal(MemoryEventLog())
    pairing = Pairing(journal)
    port = _free_port()
    replay = ReplayTransport([])
    speech = FakeSpeech(lambda: ScriptedSTT(replay, []), lambda: ToneTTS(replay.clock, secs_per_char=0.02))
    said = SatelliteVoice("satellites", speech=speech, settings=SessionSettings(stt_phrase="Je t'entends mal."))
    channel = SatellitesChannel("satellites", host="127.0.0.1", port=port, voice=said if voice else None)
    channel.host_satellites(pairing, journal)
    async with pairing, channel:
        serving = asyncio.create_task(channel.serve(assistant or FakeAssistant([])))
        await _until(lambda: _answers(port))
        try:
            yield channel, pairing, journal, f"http://127.0.0.1:{port}"
        finally:
            await channel.close()
            await serving


async def paired(pairing: Pairing, manifest: Manifest) -> str:
    """Pair `manifest`'s device as a person does; its token."""
    ticket = await pairing.request(manifest)
    assert ticket.device_code is not None
    await pairing.approve(ticket.device_code)
    token = pairing.poll(ticket.id).token
    assert token
    return token


def link_url(url: str, device_id: str) -> str:
    return url.replace("http", "ws", 1) + f"/satellites/{device_id}/link"


def hello(manifest: Manifest, token: str) -> str:
    return json.dumps(wire.encode(wire.Hello(manifest=manifest, token=token)))


async def received(link: Any) -> wire.Message:
    return wire.decode(json.loads(await asyncio.wait_for(link.recv(), 10))).message


async def test_a_paired_satellite_speaks_in_its_room_and_its_body_follows_the_played_laugh() -> None:
    async with home() as (channel, pairing, journal, url):
        satellite = ReferenceSatellite(url, MANIFEST)
        running = asyncio.create_task(satellite.run())
        await satellite.code_shown.wait()
        assert satellite.code is not None
        await pairing.approve(satellite.code)
        await asyncio.wait_for(satellite.welcomed.wait(), 10)
        await _until(lambda: channel.reachable(KITCHEN, Medium.SPOKEN))
        assert channel.rooms == {"cuisine"}
        await pairing.identify("enceinte-cuisine")
        await _until(lambda: satellite.identified == 1)
        assert not channel.reachable(Address("satellites", "salon"), Medium.SPOKEN), "it speaks in its paired room"

        await channel.send(KITCHEN, "[laughs] Ah, celle-là je ne l'avais pas vue.", Medium.SPOKEN)
        await _until(lambda: wire.BehaviorIntent(behavior=Behavior.IDLE) in satellite.intents)

        intents = satellite.intents
        speaking = intents.index(wire.BehaviorIntent(behavior=Behavior.SPEAKING))
        laugh = intents.index(wire.ExpressionIntent(expression=Expression.JOY))
        assert speaking < laugh < intents.index(wire.BehaviorIntent(behavior=Behavior.IDLE))
        assert sum(isinstance(i, wire.BeatIntent) for i in intents) == 7, "one beat per word played"
        await _until(lambda: wire.TextIntent(text="[laughs] Ah, celle-là je ne l'avais pas vue.") in intents)
        assert satellite.audio_frames > 0, "the satellite received the spoken audio"
        seen = await journal.history(PersonDetected)
        assert seen and {(e.device_id, e.room) for e in seen} == {("enceinte-cuisine", "cuisine")}

        running.cancel()
        await _until(lambda: not channel.reachable(KITCHEN, Medium.SPOKEN))
        kinds = [type(e) for e in await journal.history(SatelliteConnected, SatelliteDisconnected)]
        assert kinds == [SatelliteConnected, SatelliteDisconnected]


async def test_typed_text_is_answered_in_writing_on_a_screen() -> None:
    assistant = FakeAssistant(["Il fait 21 degrés."], ttft_s=0.01)
    async with home(voice=False, assistant=assistant) as (_, pairing, _, url):
        token = await paired(pairing, SCREEN)
        async with websockets.connect(link_url(url, SCREEN.device.id)) as link:
            await link.send(hello(SCREEN, token))
            welcome = await received(link)
            assert isinstance(welcome, wire.Welcome) and set(welcome.capabilities) == {"text.input", "text.display"}
            await link.send(json.dumps(wire.encode(wire.TextInput(text="Quelle température ?"))))
            answer = await received(link)
    assert answer == wire.TextIntent(text="Il fait 21 degrés.")
    (message,) = assistant.messages
    assert (message.address, message.text, message.medium) == (KITCHEN, "Quelle température ?", Medium.WRITTEN)


class LookingUp(Assistant):
    """Says it looks something up, then answers once the tool returned: two messages, one turn."""

    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        return PersonId(sender.id)

    def respond(self, message: InboundMessage) -> Reply:
        class Answer(Reply):
            async def __aiter__(self) -> AsyncIterator[str | MessageEnd]:
                yield "Je regarde."
                yield MessageEnd(last=False)
                await asyncio.sleep(0.05)
                yield "Il fait 21 degrés."
                yield MessageEnd()

            async def interrupt(self, heard: str) -> None: ...

        return Answer()


async def test_each_message_of_an_answer_is_shown_as_it_ends_final_on_the_last() -> None:
    async with home(voice=False, assistant=LookingUp()) as (_, pairing, _, url):
        token = await paired(pairing, SCREEN)
        async with websockets.connect(link_url(url, SCREEN.device.id)) as link:
            await link.send(hello(SCREEN, token))
            await received(link)
            await link.send(json.dumps(wire.encode(wire.TextInput(text="Quelle température ?"))))
            first, second = await received(link), await received(link)
    assert first == wire.TextIntent(text="Je regarde.", final=False)
    assert second == wire.TextIntent(text="Il fait 21 degrés.", final=True)


async def test_an_unprompted_message_in_writing_goes_to_the_screens_of_the_room() -> None:
    async with home(voice=False) as (channel, pairing, _, url):
        assert channel.media == {Medium.WRITTEN}, "without a voice, satellites only write"
        assert not channel.reachable(KITCHEN, Medium.WRITTEN)
        with pytest.raises(ProviderError):
            await channel.send(KITCHEN, "Ta lessive est terminée.", Medium.WRITTEN)
        token = await paired(pairing, SCREEN)
        async with websockets.connect(link_url(url, SCREEN.device.id)) as link:
            await link.send(hello(SCREEN, token))
            await received(link)
            await _until(lambda: channel.reachable(KITCHEN, Medium.WRITTEN))
            await channel.send(KITCHEN, "Ta lessive est terminée.", Medium.WRITTEN)
            assert await received(link) == wire.TextIntent(text="Ta lessive est terminée.")
        with pytest.raises(ContractError):
            await channel.send(KITCHEN, "Ta lessive est terminée.", Medium.SPOKEN)


async def test_without_a_voice_no_audio_is_allowed_on_the_link() -> None:
    async with home(voice=False) as (_, pairing, _, url):
        token = await paired(pairing, MANIFEST)
        async with websockets.connect(link_url(url, MANIFEST.device.id)) as link:
            await link.send(hello(MANIFEST, token))
            welcome = await received(link)
            assert isinstance(welcome, wire.Welcome)
            assert not {"audio.capture", "audio.playback"} & set(welcome.capabilities)
            async with httpx.AsyncClient(base_url=url) as client:
                assert (await _offer(client, MANIFEST.device.id, token)).status_code == 403


@pytest.mark.parametrize(
    ("first", "code"),
    [
        (
            lambda token: hello(
                Manifest(Device("quelqu-un", "x", "salon"), SCREEN.capabilities, software=SOFTWARE), token
            ),
            4400,
        ),
        (lambda token: hello(SCREEN, "nst1_guessed"), 4401),
        (lambda token: json.dumps(wire.encode(wire.Ack(of="x"))), 4400),
        (lambda token: "pas du JSON", 4400),
    ],
    ids=["someone else's hello", "a guessed token", "no hello first", "not JSON"],
)
async def test_a_link_without_a_valid_hello_is_closed_with_its_reason(first: Callable[[str], str], code: int) -> None:
    async with home(voice=False) as (_, pairing, _, url):
        token = await paired(pairing, SCREEN)
        async with websockets.connect(link_url(url, SCREEN.device.id)) as link:
            await link.send(first(token))
            with pytest.raises(websockets.ConnectionClosed) as closed:
                await asyncio.wait_for(link.recv(), 10)
    assert closed.value.rcvd is not None and closed.value.rcvd.code == code


async def test_a_new_link_of_a_satellite_replaces_the_previous_one() -> None:
    async with home(voice=False) as (channel, pairing, _, url):
        token = await paired(pairing, SCREEN)
        async with websockets.connect(link_url(url, SCREEN.device.id)) as old:
            await old.send(hello(SCREEN, token))
            await received(old)
            async with websockets.connect(link_url(url, SCREEN.device.id)) as new:
                await new.send(hello(SCREEN, token))
                await received(new)
                with pytest.raises(websockets.ConnectionClosed) as closed:
                    await asyncio.wait_for(old.recv(), 10)
                assert closed.value.rcvd is not None and closed.value.rcvd.code == 4409
                await channel.send(KITCHEN, "Toujours là.", Medium.WRITTEN)
                assert await received(new) == wire.TextIntent(text="Toujours là.")


async def test_stopping_the_channel_closes_every_link_so_devices_come_back() -> None:
    async with home(voice=False) as (channel, pairing, _, url):
        token = await paired(pairing, SCREEN)
        async with websockets.connect(link_url(url, SCREEN.device.id)) as link:
            await link.send(hello(SCREEN, token))
            await received(link)
            await channel.close()
            with pytest.raises(websockets.ConnectionClosed) as closed:
                await asyncio.wait_for(link.recv(), 10)
    assert closed.value.rcvd is not None and closed.value.rcvd.code == 1001


async def test_a_satellite_renegotiates_its_own_audio_only() -> None:
    async with home() as (channel, pairing, _, url):
        satellite = ReferenceSatellite(url, MANIFEST, faults=Faults(reconnects=False))
        running = asyncio.create_task(satellite.run())
        await satellite.code_shown.wait()
        assert satellite.code is not None
        await pairing.approve(satellite.code)
        await _until(lambda: channel.reachable(KITCHEN, Medium.SPOKEN))
        assert satellite.token is not None
        async with httpx.AsyncClient(base_url=url) as client:
            answer = await _offer(client, MANIFEST.device.id, satellite.token)
            assert answer.status_code == 200
            candidates = {"pc_id": answer.json()["pc_id"], "candidates": []}
            headers = {"Authorization": f"Bearer {satellite.token}"}
            patched = await client.patch(f"/satellites/{MANIFEST.device.id}/audio", json=candidates, headers=headers)
            assert patched.json() == {"status": "success"}, "a device renegotiates its own connection"
            foreign = await _offer(client, MANIFEST.device.id, satellite.token, pc_id="SmallWebRTCConnection#0-x")
            assert foreign.status_code == 403
        running.cancel()


async def _offer(client: httpx.AsyncClient, device_id: str, token: str | None, **body: Any) -> httpx.Response:
    from aiortc import RTCConfiguration, RTCPeerConnection
    from aiortc.mediastreams import AudioStreamTrack

    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    peer.addTrack(AudioStreamTrack())
    await peer.setLocalDescription(await peer.createOffer())
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    offer = {"sdp": peer.localDescription.sdp, "type": "offer", **body}
    try:
        return await client.post(f"/satellites/{device_id}/audio", json=offer, headers=headers)
    finally:
        await peer.close()


async def test_audio_is_refused_without_a_valid_token_or_a_link() -> None:
    async with home() as (channel, pairing, _, url), httpx.AsyncClient(base_url=url) as client:
        token = await paired(pairing, MANIFEST)
        assert (await _offer(client, MANIFEST.device.id, None)).status_code == 401
        assert (await _offer(client, MANIFEST.device.id, "nst1_guessed")).status_code == 401
        assert (await _offer(client, "reachy-salon", token)).status_code == 401, "a token opens its own device only"
        assert (await _offer(client, MANIFEST.device.id, token)).status_code == 403, "no link up"
        await pairing.revoke(MANIFEST.device.id)
        refused = await _offer(client, MANIFEST.device.id, token)
        assert refused.status_code == 401 and refused.headers["www-authenticate"].startswith("Bearer")
        assert not channel.rooms


def _gateway_client(pairing: Pairing) -> httpx.AsyncClient:
    async def linked(*_: object) -> None: ...

    server = DeviceServer(host="127.0.0.1", port=0, gateway=SatelliteGateway(pairing, on_link=linked))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://core")


async def test_pairing_over_http_hands_out_the_token_once() -> None:
    pairing = Pairing(Journal(MemoryEventLog()))
    async with _gateway_client(pairing) as client:
        asked = await client.post("/satellites/pairings", json={"manifest": MANIFEST.to_json()})
        assert asked.status_code == 201
        ticket = asked.json()
        assert ticket["status"] == "pending" and len(ticket["device_code"]) == 6
        poll = f"/satellites/pairings/{ticket['pairing_id']}"
        await pairing.identify_pending(ticket["pairing_id"])
        assert (await client.get(poll)).json() == {"status": "pending", "identify": True}
        assert (await client.get(poll)).json() == {"status": "pending"}

        await pairing.approve(ticket["device_code"])
        approved, claimed = (await client.get(poll)).json(), (await client.get(poll)).json()
    assert approved["status"] == "approved" and approved["token"].startswith("nst1_")
    assert approved["room"] == "cuisine" and "expression.emotion" in approved["capabilities"]
    assert claimed["status"] == "claimed" and "token" not in claimed


async def test_a_device_with_an_enrollment_code_is_approved_in_its_first_answer() -> None:
    pairing = Pairing(Journal(MemoryEventLog()))
    started = await pairing.start_addition(PairingMethod.PROVISIONING)
    async with _gateway_client(pairing) as client:
        body = {"manifest": MANIFEST.to_json(), "enrollment_code": started.code, "method": "enrollment.provisioning"}
        ticket = (await client.post("/satellites/pairings", json=body)).json()
        assert ticket["status"] == "approved" and "device_code" not in ticket
        state = (await client.get(f"/satellites/pairings/{ticket['pairing_id']}")).json()
        assert state["status"] == "approved" and state["token"]

        again = await client.post("/satellites/pairings", json=body)
    assert again.status_code == 403
    assert again.json() | {"detail": ""} == {"error": "enrollment_refused", "reason": "used", "detail": ""}


async def test_a_pending_device_proves_itself_with_an_enrollment_code_once() -> None:
    pairing = Pairing(Journal(MemoryEventLog()))
    started = await pairing.start_addition(PairingMethod.PROVISIONING)
    async with _gateway_client(pairing) as client:
        ticket = (await client.post("/satellites/pairings", json={"manifest": MANIFEST.to_json()})).json()
        enroll = f"/satellites/pairings/{ticket['pairing_id']}/enrollment"
        proof = {"enrollment_code": started.code, "method": "enrollment.provisioning"}
        approved = await client.post(enroll, json=proof)
        assert approved.status_code == 200 and approved.json()["status"] == "approved"
        late = await client.post(enroll, json=proof)
        assert late.status_code == 409 and late.json()["error"] == "not_pending"
        invalid = await client.post(enroll, json={"enrollment_code": started.code})
        assert invalid.status_code == 422 and invalid.json()["error"] == "invalid_request"


async def test_wrong_enrollment_codes_are_rate_limited_with_retry_after() -> None:
    pairing = Pairing(Journal(MemoryEventLog()), limiter=AttemptLimiter(per_source=1))
    async with _gateway_client(pairing) as client:
        body = {"manifest": MANIFEST.to_json(), "enrollment_code": "ZZZZZZZZ", "method": "enrollment.provisioning"}
        assert (await client.post("/satellites/pairings", json=body)).json()["reason"] == "unknown"
        limited = await client.post("/satellites/pairings", json=body)
    assert limited.status_code == 429 and limited.json()["error"] == "too_many_attempts"
    assert int(limited.headers["retry-after"]) == limited.json()["retry_after_s"] >= 1


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"manifest": {"protocol": "nestor.satellite/1"}}, "invalid_request"),
        ({"manifest": {**MANIFEST.to_json(), "protocol": "nestor.satellite/99"}}, "protocol_unsupported"),
        (MANIFEST.to_json(), "invalid_request"),
    ],
    ids=["no device", "another protocol version", "a bare manifest"],
)
async def test_an_invalid_request_is_refused(body: dict[str, Any], error: str) -> None:
    async with _gateway_client(Pairing(Journal(MemoryEventLog()))) as client:
        answer = await client.post("/satellites/pairings", json=body)
    assert (answer.status_code, answer.json()["error"]) == (422, error)


async def test_too_many_waiting_devices_are_told_to_come_back_later() -> None:
    async with _gateway_client(Pairing(Journal(MemoryEventLog()), max_pending=1)) as client:
        await client.post("/satellites/pairings", json={"manifest": MANIFEST.to_json()})
        other = {**MANIFEST.to_json(), "device": {"id": "x", "model": "esp32", "room": "salon"}}
        answer = await client.post("/satellites/pairings", json={"manifest": other})
    assert answer.status_code == 429 and answer.json()["error"] == "too_many_pending" and answer.headers["retry-after"]


def test_the_channel_says_where_satellites_reach_it() -> None:
    def channel(host: str, port: int, public_url: str | None = None, *, hosting: bool = True) -> SatellitesChannel:
        satellites = SatellitesChannel("satellites", host=host, port=port, public_url=public_url)
        if hosting:
            satellites.host_satellites(Pairing(Journal(MemoryEventLog())), Journal(MemoryEventLog()))
        return satellites

    assert channel("0.0.0.0", 8471).satellite_url("nestor.local") == "http://nestor.local:8471"
    assert channel("::", 8471).satellite_url("fd00::4") == "http://[fd00::4]:8471"
    assert channel("192.168.1.4", 7870).satellite_url("nestor.local") == "http://192.168.1.4:7870"
    assert channel("0.0.0.0", 8471, "https://n.example.org/").satellite_url("x") == "https://n.example.org"
    assert channel("0.0.0.0", 8471, hosting=False).satellite_url("nestor.local") is None
