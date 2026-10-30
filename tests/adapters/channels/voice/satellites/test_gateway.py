"""Paired satellites reaching the voice channel over HTTP and WebRTC, and everyone else refused."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from nestor.adapters.channels.voice import VoiceChannel
from nestor.adapters.channels.voice.satellites import SatelliteGateway
from nestor.adapters.channels.voice.server import SignallingServer
from nestor.adapters.channels.voice.session import SessionSettings
from nestor.modules.behavior import Behavior, Expression
from nestor.modules.channels import Address
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    AttemptLimiter,
    Pairing,
    PairingMethod,
    PersonDetected,
    Satellite,
    SatelliteConnected,
    SatelliteDisconnected,
    wire,
)
from nestor.testing.journal import MemoryEventLog

from ..doubles import FakeAssistant, FakeSpeech, ScriptedSTT, ToneTTS
from ..replay import ReplayTransport
from ..test_server import _answers, _free_port
from .reference import Faults, ReferenceSatellite
from .test_conformance import MANIFEST

KITCHEN = Address("voice", "cuisine")


async def _until(condition: Callable[[], bool], timeout_s: float = 10) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.05)


@asynccontextmanager
async def home(*, allow_unpaired_browser: bool = False) -> AsyncGenerator[tuple[VoiceChannel, Pairing, Journal, str]]:
    journal = Journal(MemoryEventLog())
    pairing = Pairing(journal)
    port = _free_port()
    replay = ReplayTransport([])
    speech = FakeSpeech(lambda: ScriptedSTT(replay, []), lambda: ToneTTS(replay.clock, secs_per_char=0.02))
    channel = VoiceChannel(
        "voice",
        room="salon",
        speech=speech,
        session=SessionSettings(stt_phrase="Je t'entends mal."),
        host="127.0.0.1",
        port=port,
        allow_unpaired_browser=allow_unpaired_browser,
    )
    channel.host_satellites(pairing, journal)
    async with pairing, channel:
        serving = asyncio.create_task(channel.serve(FakeAssistant([])))
        await _until(lambda: _answers(port))
        try:
            yield channel, pairing, journal, f"http://127.0.0.1:{port}"
        finally:
            await channel.close()
            await serving


async def test_a_paired_satellite_speaks_in_its_room_and_its_body_follows_the_played_laugh() -> None:
    async with home() as (channel, pairing, journal, url):
        satellite = ReferenceSatellite(url, MANIFEST)
        running = asyncio.create_task(satellite.run())
        await satellite.code_shown.wait()
        assert satellite.code is not None
        await pairing.approve(satellite.code)
        await asyncio.wait_for(satellite.welcomed.wait(), 10)
        await _until(lambda: channel.reachable(KITCHEN))
        assert channel.rooms == {"cuisine"}
        await pairing.identify("enceinte-cuisine")
        await _until(lambda: satellite.identified == 1)
        assert not channel.reachable(Address("voice", "salon")), "the satellite speaks in its paired room"

        await channel.send(KITCHEN, "[laughs] Ah, celle-là je ne l'avais pas vue.")
        await _until(lambda: wire.BehaviorIntent(behavior=Behavior.IDLE) in satellite.intents)

        intents = satellite.intents
        speaking = intents.index(wire.BehaviorIntent(behavior=Behavior.SPEAKING))
        laugh = intents.index(wire.ExpressionIntent(expression=Expression.JOY))
        assert speaking < laugh < intents.index(wire.BehaviorIntent(behavior=Behavior.IDLE))
        assert sum(isinstance(i, wire.BeatIntent) for i in intents) == 7, "one beat per word played"
        assert satellite.audio_frames > 0, "the satellite received the spoken audio"
        seen = await journal.history(PersonDetected)
        assert seen and {(e.device_id, e.room) for e in seen} == {("enceinte-cuisine", "cuisine")}

        running.cancel()
        await _until(lambda: not channel.reachable(KITCHEN))
        kinds = [type(e) for e in await journal.history(SatelliteConnected, SatelliteDisconnected)]
        assert kinds == [SatelliteConnected, SatelliteDisconnected]


async def test_a_new_connection_of_a_satellite_replaces_its_previous_session() -> None:
    async with home() as (channel, pairing, journal, url):
        satellite = ReferenceSatellite(url, MANIFEST, faults=Faults(reconnects=False))
        running = asyncio.create_task(satellite.run())
        await satellite.code_shown.wait()
        assert satellite.code is not None
        await pairing.approve(satellite.code)
        await asyncio.wait_for(satellite.welcomed.wait(), 10)
        assert satellite.token is not None

        async with httpx.AsyncClient(base_url=url) as client:
            answer = await _offer(client, MANIFEST.device.id, satellite.token)
            assert answer.status_code == 200
            candidates = {"pc_id": answer.json()["pc_id"], "candidates": []}
            headers = {"Authorization": f"Bearer {satellite.token}"}
            patched = await client.patch(f"/satellites/{MANIFEST.device.id}/offer", json=candidates, headers=headers)
            assert patched.json() == {"status": "success"}, "a device renegotiates its own connection"

        async def replaced() -> None:
            while not await journal.history(SatelliteDisconnected):
                await asyncio.sleep(0.05)

        await asyncio.wait_for(replaced(), 10)
        assert channel.reachable(KITCHEN), "the new connection holds the room"
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
        return await client.post(f"/satellites/{device_id}/offer", json=offer, headers=headers)
    finally:
        await peer.close()


async def test_a_device_without_a_valid_token_is_refused() -> None:
    async with home() as (channel, pairing, _, url), httpx.AsyncClient(base_url=url) as client:
        ticket = await pairing.request(MANIFEST)
        assert ticket.device_code is not None
        satellite = await pairing.approve(ticket.device_code)
        token = pairing.poll(ticket.id).token
        assert token

        assert (await _offer(client, satellite.id, None)).status_code == 401
        assert (await _offer(client, satellite.id, "nst2_guessed")).status_code == 401
        assert (await _offer(client, "reachy-salon", token)).status_code == 401, "a token opens its own device only"
        foreign = await _offer(client, satellite.id, token, pc_id="SmallWebRTCConnection#0-someone-else")
        assert foreign.status_code == 403
        await pairing.revoke(satellite.id)
        refused = await _offer(client, satellite.id, token)
        assert refused.status_code == 401 and refused.headers["www-authenticate"].startswith("Bearer")
        assert not channel.rooms


async def test_without_the_unpaired_browser_setting_the_dev_client_is_not_served() -> None:
    async with home() as (_, _, _, url), httpx.AsyncClient(base_url=url) as client:
        assert (await client.get("/client/")).status_code == 404
        assert (await client.post("/start", json={})).status_code == 404
    async with home(allow_unpaired_browser=True) as (_, _, _, url), httpx.AsyncClient(base_url=url) as client:
        assert (await client.get("/client/")).status_code == 200


def _gateway_client(pairing: Pairing) -> httpx.AsyncClient:
    async def connected(_connection: SmallWebRTCConnection, _satellite: Satellite) -> None: ...

    server = SignallingServer(host="127.0.0.1", port=0, routes=[SatelliteGateway(pairing, connected)])
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
    assert approved["status"] == "approved" and approved["token"].startswith("nst2_")
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
        ({"manifest": {"protocol": "nestor.satellite/2"}}, "invalid_request"),
        ({"manifest": {**MANIFEST.to_json(), "protocol": "nestor.satellite/1"}}, "protocol_unsupported"),
        (MANIFEST.to_json(), "invalid_request"),
    ],
    ids=["no device", "protocol 1", "a bare manifest"],
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


def test_the_voice_channel_says_where_satellites_reach_it() -> None:
    def channel(host: str, port: int | None, public_url: str | None = None) -> VoiceChannel:
        replay = ReplayTransport([])
        speech = FakeSpeech(lambda: ScriptedSTT(replay, []), lambda: ToneTTS(replay.clock))
        settings = SessionSettings(stt_phrase=".")
        voice = VoiceChannel(
            "voice", room="salon", speech=speech, session=settings, host=host, port=port, public_url=public_url
        )
        voice.host_satellites(Pairing(Journal(MemoryEventLog())), Journal(MemoryEventLog()))
        return voice

    assert channel("0.0.0.0", 7860).satellite_url("nestor.local") == "http://nestor.local:7860"
    assert channel("::", 7860).satellite_url("fd00::4") == "http://[fd00::4]:7860"
    assert channel("192.168.1.4", 7870).satellite_url("nestor.local") == "http://192.168.1.4:7870"
    assert channel("0.0.0.0", 7860, "https://n.example.org/").satellite_url("x") == "https://n.example.org"
    assert channel("0.0.0.0", None).satellite_url("nestor.local") is None
