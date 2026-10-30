"""Pairing satellites from the server-rendered pages and the command line (the API: `api/v1/test_satellites`)."""

import asyncio
import json
import socket
import stat
from pathlib import Path

import pytest
import respx

from nestor.admin import AdminServer, AdminSettings, read_token, token_path
from nestor.cli import main
from nestor.core import Capability, PersonId
from nestor.modules.channels import Medium
from nestor.modules.satellites import (
    DeclaredCapability,
    Device,
    Manifest,
    PairingStatus,
    PersonDetected,
    SatelliteConnected,
    SatelliteDisconnected,
    SatelliteRevoked,
    SpeechActivityObserved,
)
from nestor.testing.channels import InMemoryChannel

from .harness import CONFIG, Harness

REACHY = Manifest(
    Device("reachy-salon", "reachy-mini", "salon"),
    (
        DeclaredCapability(Capability("audio.capture")),
        DeclaredCapability(Capability("audio.playback")),
        DeclaredCapability(Capability("vision.person_detection")),
    ),
)


async def test_a_waiting_device_is_listed_without_its_code(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        ticket = await admin.nestor.pairing.request(REACHY)
        page = (await admin.get("/satellites")).text
        assert "reachy-salon" in page and "reachy-mini" in page and "salon" in page
        assert "détection de personnes" in page and 'value="audio.playback" checked' in page
        assert "expire dans" in page
        assert ticket.code not in page


async def test_the_right_code_pairs_the_device_which_then_gets_its_token(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        pairing = admin.nestor.pairing
        ticket = await pairing.request(REACHY)
        await admin.get("/satellites")
        everything = ["audio.capture", "audio.playback", "vision.person_detection"]
        response = await admin.post(
            "/satellites/approve",
            {"code": f" {ticket.code[:3]} {ticket.code[3:]}", "capability": everything, "by": "mathis"},
        )
        assert response.headers["location"] == "/satellites"

        state = pairing.poll(ticket.id)
        assert state.status is PairingStatus.APPROVED and state.token
        assert pairing.authenticate("reachy-salon", state.token) is not None
        page = (await admin.get("/satellites")).text
        assert "Satellite reachy-salon (pièce « salon ») appairé" in page and "par Mathis" in page
        assert "Aucun appareil n'attend" in page


async def test_a_wrong_code_shows_an_error_and_pairs_nothing(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        ticket = await admin.nestor.pairing.request(REACHY)
        await admin.get("/satellites")
        wrong = "000000" if ticket.code != "000000" else "111111"
        for code, said in ((wrong, "faux ou a expiré"), ("12ab", "6 chiffres")):
            response = await admin.post("/satellites/approve", {"code": code, "capability": ["audio.capture"]})
            assert response.status_code == 400 and said in response.text
        assert admin.nestor.pairing.satellites() == []
        assert admin.nestor.pairing.poll(ticket.id).status is PairingStatus.PENDING
        stranger = await admin.post("/satellites/approve", {"code": ticket.code, "by": "intruder"})
        assert stranger.status_code == 400 and admin.nestor.pairing.satellites() == []


async def test_capabilities_left_unchecked_are_not_granted(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        ticket = await admin.nestor.pairing.request(REACHY)
        await admin.get("/satellites")
        await admin.post(
            "/satellites/approve", {"code": ticket.code, "capability": ["audio.capture", "audio.playback"]}
        )
        (satellite,) = admin.nestor.pairing.satellites()
        assert satellite.capabilities == {Capability("audio.capture"), Capability("audio.playback")}
        page = (await admin.get("/satellites")).text
        assert "haut-parleur" in page and "détection de personnes" not in page


async def test_a_paired_satellite_is_revoked_after_confirmation(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        pairing = admin.nestor.pairing
        await pairing.approve((await pairing.request(REACHY)).code)
        await admin.get("/satellites")
        unconfirmed = await admin.post("/satellites/reachy-salon/revoke")
        assert unconfirmed.status_code == 400 and len(pairing.satellites()) == 1

        response = await admin.post("/satellites/reachy-salon/revoke", {"confirm": "yes"})
        assert response.headers["location"] == "/satellites"
        assert pairing.satellites() == []
        assert len(await admin.nestor.journal.history(SatelliteRevoked)) == 1
        assert "révoqué" in (await admin.get("/satellites")).text
        assert (await admin.post("/satellites/reachy-salon/revoke", {"confirm": "yes"})).status_code == 404


class Voice(InMemoryChannel):
    """A spoken channel with a live session in the salon, as the voice channel reports it."""

    medium = Medium.SPOKEN

    @property
    def rooms(self) -> frozenset[str]:
        return frozenset({"salon"})


async def test_paired_satellites_show_whether_their_room_is_connected(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        pairing = admin.nestor.pairing
        await pairing.approve((await pairing.request(REACHY)).code)
        unknown = (await admin.get("/satellites")).text.split("Appairés")[1]
        assert "connecté" not in unknown and "hors ligne" not in unknown, "no spoken channel: nobody can tell"
        admin.nestor.channels.append(Voice())
        assert '<span class="status">connecté</span>' in (await admin.get("/satellites")).text
        await pairing.approve((await pairing.request(Manifest(Device("mic-bureau", "esp32", "bureau")))).code)
        assert "hors ligne" in (await admin.get("/satellites")).text


async def test_the_journal_tells_satellite_events_in_french(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        pairing = admin.nestor.pairing
        await pairing.approve((await pairing.request(REACHY)).code, by=PersonId("mathis"))
        await pairing.revoke("reachy-salon", by=PersonId("mathis"))
        journal = admin.nestor.journal
        for event in (
            SatelliteConnected(source="voice", device_id="reachy-salon", room="salon"),
            SatelliteDisconnected(source="voice", device_id="reachy-salon", room="salon"),
            PersonDetected(source="voice", device_id="reachy-salon", room="salon", count=2, confidence=0.87),
            PersonDetected(source="voice", device_id="reachy-salon", room="salon", count=1, confidence=0.5),
            SpeechActivityObserved(source="voice", device_id="reachy-salon", room="salon", active=True),
            SpeechActivityObserved(source="voice", device_id="reachy-salon", room="salon", active=False),
        ):
            await journal.publish(event)
        page = (await admin.get("/journal")).text
        for said in (
            "Le satellite reachy-salon (reachy-mini, pièce « salon ») demande l&#39;appairage",
            "Déclare : micro, haut-parleur, détection de personnes",
            "Satellite reachy-salon appairé (pièce « salon »)",
            "Satellite reachy-salon révoqué",
            "Satellite reachy-salon connecté",
            "Satellite reachy-salon déconnecté",
            "2 personnes vues par reachy-salon",
            "Confiance : 87%",
            "1 personne vue par reachy-salon",
            "Parole détectée près de reachy-salon",
            "Fin de parole près de reachy-salon",
        ):
            assert said in page, said
        observations = (await admin.get("/journal", type="observation")).text
        assert "Parole détectée" in observations and "appairé" not in observations
        assert "Satellite reachy-salon révoqué" in (await admin.get("/journal", person="mathis")).text


# -- the command line against a running instance ----------------------------------------------------------


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def run(*argv: str) -> int:
    return await asyncio.to_thread(main, list(argv))


async def test_the_command_line_pairs_and_revokes_through_the_running_admin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    port = free_port()
    config = tmp_path / "nestor.yaml"
    config.write_text(CONFIG.format(data_dir=tmp_path, admin={"port": port}))
    async with Harness(tmp_path) as admin:
        server = AdminServer(admin.nestor, AdminSettings(port=port))
        ticket = await admin.nestor.pairing.request(REACHY)
        async with server:
            path = token_path(tmp_path)
            assert stat.S_IMODE(path.stat().st_mode) == 0o600 and read_token(path)
            assert await run("-c", str(config), "satellites", "approve", ticket.code, "--only", "audio.capture") == 0
            assert "paired reachy-salon (reachy-mini) in salon: may use audio.capture" in capsys.readouterr().out
            (satellite,) = admin.nestor.pairing.satellites()
            assert satellite.capabilities == {Capability("audio.capture")}

            assert await run("-c", str(config), "satellites", "approve", "000000") == 2
            assert "Aucun appareil n'attend ce code" in capsys.readouterr().err
            assert await run("-c", str(config), "satellites", "revoke", "reachy-salon") == 0
            assert "revoked reachy-salon" in capsys.readouterr().out
            assert admin.nestor.pairing.satellites() == []

            path.write_text("stale-token")
            assert await run("-c", str(config), "satellites", "revoke", "reachy-salon") == 2
            assert "refused the token" in capsys.readouterr().err
        assert not path.exists(), "the token goes away with the server"


async def test_the_command_line_says_when_nestor_is_not_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "nestor.yaml"
    config.write_text(CONFIG.format(data_dir=tmp_path, admin={"port": free_port()}))
    assert await run("-c", str(config), "satellites", "approve", "123456") == 2
    assert "no admin token" in capsys.readouterr().err
    token_path(tmp_path).write_text("left-over")
    assert await run("-c", str(config), "satellites", "approve", "123456") == 2
    assert "Nestor is not running" in capsys.readouterr().err
    token_path(tmp_path).write_text("")
    assert await run("-c", str(config), "satellites", "approve", "123456") == 2
    assert "empty" in capsys.readouterr().err

    config.write_text(CONFIG.format(data_dir=tmp_path, admin="null"))
    assert await run("-c", str(config), "satellites", "revoke", "x") == 2
    assert "no `admin` section" in capsys.readouterr().err


def test_the_command_line_writes_the_wire_schemas(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["satellites", "schemas", "--out", str(tmp_path / "schemas")]) == 0
    written = sorted(p.name for p in (tmp_path / "schemas").iterdir())
    assert "manifest.json" in written and "hello.json" in written
    manifest = json.loads((tmp_path / "schemas" / "manifest.json").read_text())
    assert manifest["properties"]["protocol"]["const"] == "nestor.satellite/1"
    assert f"wrote {tmp_path / 'schemas' / 'manifest.json'}" in capsys.readouterr().out


@respx.mock
def test_the_command_line_reports_an_answer_that_is_not_the_admin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    port = free_port()
    respx.delete(f"http://127.0.0.1:{port}/api/v1/satellites/x").respond(502, text="<html>Bad gateway</html>")
    config = tmp_path / "nestor.yaml"
    config.write_text(CONFIG.format(data_dir=tmp_path, admin={"port": port}))
    token_path(tmp_path).write_text("tok")
    assert main(["-c", str(config), "satellites", "revoke", "x"]) == 2
    assert "the admin answered HTTP 502" in capsys.readouterr().err
