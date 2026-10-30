"""Adding and pairing satellites through the API: additions with their method, enrollment codes and
pairing URIs, pending devices without their code, approval with the pairing id, identify, narrowed
capabilities, revocation, and the local command line's bearer token."""

import asyncio
import re
from pathlib import Path

import pytest

from nestor.core import Capability
from nestor.modules.accounts import Role
from nestor.modules.channels import Medium
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    IDENTIFY,
    DeclaredCapability,
    Device,
    Manifest,
    Pairing,
    PairingMethod,
    PairingStatus,
    PairingTicket,
    SatelliteAdditionCompleted,
    SatelliteHost,
    SatellitePaired,
)
from nestor.testing.channels import InMemoryChannel
from nestor.testing.satellites import pair_by_code

from ...harness import Harness

REACHY = Manifest(
    Device("reachy-salon", "reachy-mini", "salon"),
    tuple(
        DeclaredCapability(Capability(c))
        for c in ("audio.capture", "audio.playback", "vision.person_detection", "device.identify")
    ),
    (PairingMethod.PROVISIONING, PairingMethod.SPEECH),
)
MIC = Manifest(Device("mic-bureau", "esp32", "bureau"), (DeclaredCapability(Capability("audio.capture")),))


def code(ticket: PairingTicket) -> str:
    assert ticket.device_code is not None
    return ticket.device_code


class Host(InMemoryChannel, SatelliteHost):
    """Serves satellites on every interface, port 7860."""

    def host_satellites(self, pairing: Pairing, journal: Journal) -> None: ...

    def satellite_url(self, seen_as: str) -> str | None:
        return f"http://{seen_as}:7860"


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
        assert code(ticket) not in listed.text
        assert [m["id"] for m in pending["methods"]] == ["device_code.speech", "enrollment.provisioning"]
        assert pending["recommended_method"] == "device_code.speech" and pending["can_identify"] is True
        assert pending["methods"][0]["label"] == "Code dit à voix haute"


async def test_the_code_typed_on_a_request_pairs_that_device_with_what_was_checked(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        reachy, mic = await pairing.request(REACHY), await pairing.request(MIC)
        api = await admin.api()
        crossed = await api.post("/api/v1/satellites/approvals", {"code": code(mic), "pairing_id": reachy.id})
        assert crossed.status_code == 400 and crossed.json()["error"]["code"] == "pairing_refused"
        invalid = await api.post("/api/v1/satellites/approvals", {"code": "12ab", "pairing_id": reachy.id})
        assert invalid.json()["error"]["code"] == "invalid_code"

        response = await api.post(
            "/api/v1/satellites/approvals",
            {
                "code": f"{code(reachy)[:3]} {code(reachy)[3:]}",
                "pairing_id": reachy.id,
                "capabilities": ["audio.capture"],
            },
        )
        assert response.status_code == 201
        paired = response.json()
        assert [c["name"] for c in paired["capabilities"]] == ["audio.capture"] and not paired["can_identify"]
        assert paired["approved_by"] == {"id": "mathis", "name": "Mathis"} and paired["connected"] is None
        state = pairing.poll(reachy.id)
        assert state.status is PairingStatus.APPROVED and state.token
        assert state.token not in str(admin.seen)
        assert pairing.poll(mic.id).status is PairingStatus.PENDING


async def test_paired_satellites_say_whether_their_room_is_heard(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        await pair_by_code(pairing, REACHY)
        await pair_by_code(pairing, MIC)
        admin.nestor.channels.append(Voice())
        listed = (await (await admin.api()).get("/api/v1/satellites")).json()
        assert {s["id"]: s["connected"] for s in listed["paired"]} == {"mic-bureau": False, "reachy-salon": True}


async def test_a_revoked_satellite_is_gone(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        await pair_by_code(pairing, REACHY)
        api = await admin.api()
        assert (await api.delete("/api/v1/satellites/reachy-salon")).status_code == 204
        assert pairing.satellites() == []
        again = await api.delete("/api/v1/satellites/reachy-salon")
        assert again.status_code == 404 and again.json()["error"]["code"] == "satellite_unknown"


async def test_the_command_line_token_opens_pairing_and_nothing_else(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        ticket = await admin.nestor.pairing.request(REACHY)
        api = await admin.api(None)
        closed = await api.send(
            "POST", "/api/v1/satellites/approvals", {"code": code(ticket)}, Authorization="Bearer x"
        )
        assert closed.status_code == 401, "no token issued yet: closed"
        admin.app.state.admin.api_token = "the-right-token"
        for header in ("Bearer wrong", "Basic the-right-token"):
            refused = await api.send(
                "POST", "/api/v1/satellites/approvals", {"code": code(ticket)}, Authorization=header
            )
            assert refused.status_code == 401 and refused.headers["www-authenticate"] == "Bearer"
        bearer = {"Authorization": "Bearer the-right-token"}
        approved = await api.send("POST", "/api/v1/satellites/approvals", {"code": code(ticket)}, **bearer)
        assert approved.status_code == 201 and approved.json()["approved_by"] is None
        assert len(approved.json()["capabilities"]) == 4, "everything it declared by default"
        assert (await api.send("GET", "/api/v1/journal", **bearer)).status_code == 401
        assert (await api.send("GET", "/api/v1/satellites", **bearer)).status_code == 200
        assert (await api.send("DELETE", "/api/v1/satellites/reachy-salon", **bearer)).status_code == 204


async def test_every_pairing_method_is_offered_for_a_device_not_seen_yet(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        answer = (await (await admin.api()).get("/api/v1/satellites/pairing-methods")).json()
    assert [m["id"] for m in answer["methods"]] == [
        "device_code.display", "device_code.speech", "enrollment.qr", "enrollment.input", "enrollment.provisioning"
    ]  # fmt: skip
    assert answer["recommended"] == "device_code.display"
    assert {m["proof"] for m in answer["methods"]} == {"device_code", "enrollment_code"}
    assert all(m["label"] and m["hint"] for m in answer["methods"])


async def test_an_enrollment_addition_gives_its_code_and_uri_once_then_pairs_its_device(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        admin.nestor.channels.append(Host())
        api = await admin.api()
        started = await api.post(
            "/api/v1/satellites/additions",
            {"method": "enrollment.qr", "name": "Reachy", "room": "bureau", "capabilities": ["audio.capture"]},
        )
        assert started.status_code == 201
        body = started.json()
        addition, shown = body["addition"], body["code"]
        assert re.fullmatch(r"[0-9A-Z]{4}-[0-9A-Z]{4}", shown)
        assert body["uri"] == f"nestor+http://admin.test:7860/?code={shown.replace('-', '')}"
        assert (addition["stage"], addition["room"], addition["method"]["id"]) == ("waiting", "bureau", "enrollment.qr")
        listed = await api.get("/api/v1/satellites")
        assert [a["id"] for a in listed.json()["additions"]] == [addition["id"]] and shown not in listed.text

        ticket = await admin.nestor.pairing.request(REACHY, enrollment_code=shown, method=PairingMethod.PROVISIONING)
        assert ticket.status is PairingStatus.APPROVED
        done = (await api.get(f"/api/v1/satellites/additions/{addition['id']}")).json()
        assert (done["stage"], done["device_id"]) == ("paired", "reachy-salon")
        (paired,) = (await api.get("/api/v1/satellites")).json()["paired"]
        assert (paired["name"], paired["room"], [c["name"] for c in paired["capabilities"]]) == (
            "Reachy", "bureau", ["audio.capture"]
        )  # fmt: skip
        assert (await api.get("/api/v1/satellites/additions")).json() == {"additions": []}


async def test_without_a_satellite_host_an_addition_has_no_uri(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        body = (await (await admin.api()).post("/api/v1/satellites/additions", {"method": "enrollment.input"})).json()
    assert body["code"] and body["uri"] is None


async def test_a_device_code_addition_sees_waiting_devices_and_pairs_the_one_whose_code_is_typed(
    tmp_path: Path,
) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        started = (
            await api.post("/api/v1/satellites/additions", {"method": "device_code.speech", "room": "cuisine"})
        ).json()
        addition = started["addition"]
        assert (started["code"], started["uri"], addition["stage"]) == (None, None, "waiting")
        ticket = await admin.nestor.pairing.request(REACHY)
        seen = (await api.get(f"/api/v1/satellites/additions/{addition['id']}")).json()
        assert (seen["stage"], seen["candidates"]) == ("device_seen", [ticket.id])
        identify = await api.post(f"/api/v1/satellites/pending/{ticket.id}/identify", {})
        assert identify.status_code == 204 and admin.nestor.pairing.poll(ticket.id).identify

        approval = {"code": code(ticket), "pairing_id": ticket.id, "addition_id": addition["id"]}
        paired = await api.post("/api/v1/satellites/approvals", approval)
        assert paired.status_code == 201 and paired.json()["room"] == "cuisine"
        again = await api.post("/api/v1/satellites/approvals", approval)
        assert (again.status_code, again.json()["error"]["code"]) == (409, "addition_over")


@pytest.mark.parametrize("same_device", [False, True], ids=["two devices", "one device"])
async def test_two_people_typing_codes_for_one_addition_at_once_pair_one_device(
    tmp_path: Path, same_device: bool
) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("lea", Role.ADMIN)
        mathis, lea = await admin.api(), await admin.api("lea")
        addition = (await mathis.post("/api/v1/satellites/additions", {"method": "device_code.speech"})).json()
        reachy = await admin.nestor.pairing.request(REACHY)
        other = reachy if same_device else await admin.nestor.pairing.request(MIC)
        approvals = [
            {"code": code(ticket), "pairing_id": ticket.id, "addition_id": addition["addition"]["id"]}
            for ticket in (reachy, other)
        ]

        answers = await asyncio.gather(
            mathis.post("/api/v1/satellites/approvals", approvals[0]),
            lea.post("/api/v1/satellites/approvals", approvals[1]),
        )

        [won] = [a for a in answers if a.status_code == 201]
        [lost] = [a for a in answers if a.status_code != 201]
        assert lost.json()["error"]["code"] in {"addition_over", "pairing_refused"}
        journal = admin.nestor.journal
        [paired] = await journal.history(SatellitePaired)
        [completed] = await journal.history(SatelliteAdditionCompleted)
        assert paired.device.id == completed.device_id == won.json()["id"]
        assert [s.id for s in admin.nestor.pairing.satellites()] == [won.json()["id"]]


async def test_an_addition_can_be_cancelled_once(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        addition = (await api.post("/api/v1/satellites/additions", {"method": "enrollment.provisioning"})).json()
        path = f"/api/v1/satellites/additions/{addition['addition']['id']}"
        assert (await api.delete(path)).status_code == 204
        assert (await api.get(path)).json()["stage"] == "cancelled"
        gone = await api.delete(path)
        assert (gone.status_code, gone.json()["error"]["code"]) == (404, "addition_unknown")
        assert (await api.get("/api/v1/satellites/additions/nope")).status_code == 404


async def test_an_addition_is_checked(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        for body in ({"method": "fax"}, {"method": "enrollment.qr", "ttl_s": 10}, {"method": "enrollment.qr", "x": 1}):
            assert (await api.post("/api/v1/satellites/additions", body)).status_code == 422
        room = await api.post("/api/v1/satellites/additions", {"method": "enrollment.qr", "room": "Le Salon"})
        assert room.status_code == 400
        admin.nestor.pairing._max_additions = 0
        full = await api.post("/api/v1/satellites/additions", {"method": "enrollment.qr"})
        assert (full.status_code, full.json()["error"]["code"]) == (409, "too_many_additions")


async def test_an_approval_with_an_enrollment_method_is_refused(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        ticket = await admin.nestor.pairing.request(REACHY)
        api = await admin.api()
        refused = await api.post("/api/v1/satellites/approvals", {"code": code(ticket), "method": "enrollment.qr"})
        assert refused.json()["error"]["code"] == "not_a_device_code_method"
        qr = (await api.post("/api/v1/satellites/additions", {"method": "enrollment.qr"})).json()["addition"]["id"]
        crossed = await api.post("/api/v1/satellites/approvals", {"code": code(ticket), "addition_id": qr})
        assert crossed.json()["error"]["code"] == "not_a_device_code_method"


async def test_identify_says_why_a_device_cannot(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        mic = await pairing.request(MIC)
        await pair_by_code(pairing, REACHY)
        api = await admin.api()
        cases = {
            f"/api/v1/satellites/pending/{mic.id}/identify": (409, "identify_unsupported"),
            "/api/v1/satellites/pending/nope/identify": (404, "pending_unknown"),
            "/api/v1/satellites/reachy-salon/identify": (409, "satellite_offline"),
            "/api/v1/satellites/nope/identify": (404, "satellite_unknown"),
        }
        for path, (status, error) in cases.items():
            answer = await api.post(path, {})
            assert (answer.status_code, answer.json()["error"]["code"]) == (status, error), path
        asked: list[str] = []
        with pairing.online("reachy-salon", lambda: asked.append("now")):
            assert (await api.post("/api/v1/satellites/reachy-salon/identify", {})).status_code == 204
        assert asked == ["now"]
        assert (await api.get("/api/v1/satellites/reachy-salon")).json()["can_identify"] is True
        assert IDENTIFY in pairing.satellites()[0].capabilities
