"""The development signalling server, as the Pipecat prebuilt client uses it."""

import asyncio
import socket
import uuid
from collections.abc import Callable

import httpx
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack
from pipecat.transports.base_transport import BaseTransport

from nestor.adapters.channels.voice import VoiceChannel
from nestor.adapters.channels.voice.server import BrowserRoutes, SignallingServer
from nestor.adapters.channels.voice.session import SessionSettings
from nestor.modules.channels import Address

from .doubles import FakeAssistant, FakeSpeech, ScriptedSTT, ToneTTS
from .replay import ReplayTransport


async def _ignore(_transport: BaseTransport) -> None: ...


def client_of(server: SignallingServer) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://satellite")


async def test_the_root_leads_to_the_prebuilt_client() -> None:
    server = SignallingServer(host="localhost", port=0, routes=[BrowserRoutes(attach=_ignore, detach=_ignore)])
    async with client_of(server) as client:
        root = await client.get("/")
        page = await client.get("/client/")
    assert root.status_code in {307, 308} and root.headers["location"] == "/client/"
    assert page.status_code == 200 and "<html" in page.text.lower()


async def test_start_opens_a_session_and_offers_need_one() -> None:
    server = SignallingServer(host="localhost", port=0, routes=[BrowserRoutes(attach=_ignore, detach=_ignore)])
    async with client_of(server) as client:
        started = await client.post("/start", json={"transport": "webrtc"})
        unknown = await client.post(f"/sessions/{uuid.uuid4()}/api/offer", json={"sdp": "", "type": "offer"})
    assert uuid.UUID(started.json()["sessionId"])
    assert unknown.status_code == 404


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def _until(condition: Callable[[], bool], timeout_s: float = 10) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.05)


ROOM = Address("voice", "salon")


class Satellite:
    """The channel serving on a free local port, and a WebRTC peer playing the browser."""

    def __init__(self) -> None:
        self.port = _free_port()
        replay = ReplayTransport([])
        speech = FakeSpeech(ScriptedSTT(replay, []), ToneTTS(replay.clock))
        session = SessionSettings(stt_phrase="Je t'entends mal.")
        self.channel = VoiceChannel(
            "voice", room="salon", speech=speech, session=session, host="127.0.0.1", port=self.port
        )
        self.peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))  # local only: no STUN lookup

    async def connect(self) -> None:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{self.port}") as client:
            await _until(lambda: _answers(self.port))
            session_id = (await client.post("/start", json={})).json()["sessionId"]
            self.peer.addTrack(AudioStreamTrack())
            await self.peer.setLocalDescription(await self.peer.createOffer())
            offer = {"sdp": self.peer.localDescription.sdp, "type": self.peer.localDescription.type}
            answer = (await client.post(f"/sessions/{session_id}/api/offer", json=offer)).json()
            await self.peer.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
            candidates = {"pc_id": answer["pc_id"], "candidates": []}
            assert (await client.patch(f"/sessions/{session_id}/api/offer", json=candidates)).json() == {
                "status": "success"
            }
        await _until(lambda: self.peer.connectionState == "connected" and self.channel.reachable(ROOM))


async def test_a_webrtc_peer_gets_a_voice_session_until_it_leaves() -> None:
    satellite = Satellite()
    async with satellite.channel:
        serving = asyncio.create_task(satellite.channel.serve(FakeAssistant([])))
        await satellite.connect()
        await satellite.peer.close()
        await _until(lambda: not satellite.channel.reachable(ROOM))
        await satellite.channel.close()
        async with asyncio.timeout(10):
            await serving


async def test_closing_the_channel_ends_the_sessions_of_connected_peers_and_stops_serving() -> None:
    satellite = Satellite()
    async with satellite.channel:
        serving = asyncio.create_task(satellite.channel.serve(FakeAssistant([])))
        await satellite.connect()
        await satellite.channel.close()
        async with asyncio.timeout(10):
            await serving
        assert not satellite.channel.reachable(ROOM)
        assert not _answers(satellite.port)
    await satellite.peer.close()


def _answers(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0
