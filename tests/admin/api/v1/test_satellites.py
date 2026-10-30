"""Pairing satellites through the API: pending devices without their code, approval with the pairing id,
narrowed capabilities, revocation, and the local command line's bearer token."""

from pathlib import Path

from nestor.core import Capability
from nestor.modules.channels import Medium
from nestor.modules.satellites import DeclaredCapability, Device, Manifest, PairingStatus
from nestor.testing.channels import InMemoryChannel

from ...harness import Harness

REACHY = Manifest(
    Device("reachy-salon", "reachy-mini", "salon"),
    tuple(DeclaredCapability(Capability(c)) for c in ("audio.capture", "audio.playback", "vision.person_detection")),
)
MIC = Manifest(Device("mic-bureau", "esp32", "bureau"), (DeclaredCapability(Capability("audio.capture")),))


class Voice(InMemoryChannel):
    medium = Medium.SPOKEN

    @property
    def rooms(self) -> frozenset[str]:
        return frozenset({"salon"})


async def test_a_waiting_device_is_listed_without_its_code(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        ticket = await admin.nestor.pairing.request(REACHY)
        listed = await (await admin.api()).get("/api/v1/satellites")
        (pending,) = listed.json()["pending"]
        assert pending["pairing_id"] == ticket.id and pending["device"]["room"] == "salon"
        assert {"name": "vision.person_detection", "label": "détection de personnes (sans image transmise)"} in (
            pending["capabilities"]
        )
        assert 0 < pending["expires_in_s"] <= 600
        assert ticket.code not in listed.text


async def test_the_code_typed_on_a_request_pairs_that_device_with_what_was_checked(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        reachy, mic = await pairing.request(REACHY), await pairing.request(MIC)
        api = await admin.api()
        crossed = await api.post("/api/v1/satellites/approvals", {"code": mic.code, "pairing_id": reachy.id})
        assert crossed.status_code == 400 and crossed.json()["error"]["code"] == "pairing_refused"
        invalid = await api.post("/api/v1/satellites/approvals", {"code": "12ab", "pairing_id": reachy.id})
        assert invalid.json()["error"]["code"] == "invalid_code"

        response = await api.post(
            "/api/v1/satellites/approvals",
            {
                "code": f"{reachy.code[:3]} {reachy.code[3:]}",
                "pairing_id": reachy.id,
                "capabilities": ["audio.capture"],
            },
        )
        assert response.status_code == 201
        paired = response.json()
        assert [c["name"] for c in paired["capabilities"]] == ["audio.capture"]
        assert paired["approved_by"] == {"id": "mathis", "name": "Mathis"} and paired["connected"] is None
        state = pairing.poll(reachy.id)
        assert state.status is PairingStatus.APPROVED and state.token
        assert state.token not in str(admin.seen)
        assert pairing.poll(mic.id).status is PairingStatus.PENDING


async def test_paired_satellites_say_whether_their_room_is_heard(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        await pairing.approve((await pairing.request(REACHY)).code)
        await pairing.approve((await pairing.request(MIC)).code)
        admin.nestor.channels.append(Voice())
        listed = (await (await admin.api()).get("/api/v1/satellites")).json()
        assert {s["id"]: s["connected"] for s in listed["paired"]} == {"mic-bureau": False, "reachy-salon": True}


async def test_a_revoked_satellite_is_gone(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        await pairing.approve((await pairing.request(REACHY)).code)
        api = await admin.api()
        assert (await api.delete("/api/v1/satellites/reachy-salon")).status_code == 204
        assert pairing.satellites() == []
        again = await api.delete("/api/v1/satellites/reachy-salon")
        assert again.status_code == 404 and again.json()["error"]["code"] == "satellite_unknown"


async def test_the_command_line_token_opens_pairing_and_nothing_else(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        ticket = await admin.nestor.pairing.request(REACHY)
        api = await admin.api(None)
        closed = await api.send("POST", "/api/v1/satellites/approvals", {"code": ticket.code}, Authorization="Bearer x")
        assert closed.status_code == 401, "no token issued yet: closed"
        admin.app.state.admin.api_token = "the-right-token"
        for header in ("Bearer wrong", "Basic the-right-token"):
            refused = await api.send(
                "POST", "/api/v1/satellites/approvals", {"code": ticket.code}, Authorization=header
            )
            assert refused.status_code == 401 and refused.headers["www-authenticate"] == "Bearer"
        bearer = {"Authorization": "Bearer the-right-token"}
        approved = await api.send("POST", "/api/v1/satellites/approvals", {"code": ticket.code}, **bearer)
        assert approved.status_code == 201 and approved.json()["approved_by"] is None
        assert len(approved.json()["capabilities"]) == 3, "everything it declared by default"
        assert (await api.send("GET", "/api/v1/journal", **bearer)).status_code == 401
        assert (await api.send("GET", "/api/v1/satellites", **bearer)).status_code == 200
        assert (await api.send("DELETE", "/api/v1/satellites/reachy-salon", **bearer)).status_code == 204
