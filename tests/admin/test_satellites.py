"""Pairing satellites from the command line, through the running admin (the API itself: `api/v1/test_satellites`)."""

import asyncio
import json
import socket
import stat
from pathlib import Path

import pytest
import respx

from nestor.admin import AdminServer, AdminSettings, read_token, token_path
from nestor.cli import main
from nestor.core import Capability
from nestor.modules.satellites import (
    DeclaredCapability,
    Device,
    Manifest,
)

from .harness import CONFIG, Harness

REACHY = Manifest(
    Device("reachy-salon", "reachy-mini", "salon"),
    (
        DeclaredCapability(Capability("audio.capture")),
        DeclaredCapability(Capability("audio.playback")),
        DeclaredCapability(Capability("vision.person_detection")),
    ),
)


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
            assert ticket.device_code is not None
            approve = ("satellites", "approve", ticket.device_code, "--only", "audio.capture")
            assert await run("-c", str(config), *approve) == 0
            assert "paired reachy-salon (reachy-mini) in salon: may use audio.capture" in capsys.readouterr().out
            (satellite,) = admin.nestor.pairing.satellites()
            assert satellite.capabilities == {Capability("audio.capture")}

            assert await run("-c", str(config), "satellites", "approve", "000000") == 2
            assert "Aucun appareil n'attend ce code" in capsys.readouterr().err
            assert await run("-c", str(config), "satellites", "revoke", "reachy-salon") == 0
            assert "revoked reachy-salon" in capsys.readouterr().out
            assert admin.nestor.pairing.satellites() == []

            assert await run("-c", str(config), "satellites", "add", "--room", "bureau", "--name", "Capteur") == 0
            said = capsys.readouterr().out
            (addition,) = admin.nestor.pairing.additions()
            assert (addition.room, addition.name, addition.method.value) == (
                "bureau",
                "Capteur",
                "enrollment.provisioning",
            )
            assert "enrollment code " in said and "-" in said.split("enrollment code ")[1][:9]

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
    assert {"manifest.json", "hello.json", "intent.identify.json", "pairing.request.json"} <= set(written)
    manifest = json.loads((tmp_path / "schemas" / "manifest.json").read_text())
    assert manifest["properties"]["protocol"]["const"] == "nestor.satellite/2"
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
