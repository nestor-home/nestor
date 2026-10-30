"""The admin served next to Nestor, and the runtime wiring that plugs connectors into the assistant."""

import asyncio
import os
import signal
import socket
from pathlib import Path

import httpx
import pytest

from nestor.admin import AdminServer, AdminSettings
from nestor.cli import main
from nestor.core import ContractError, ProviderError
from nestor.modules.initiative import Incoming, Watch, WatchTriggered
from nestor.runtime import ConfigError, Nestor
from nestor.runtime.app import run_until_stopped
from nestor.runtime.config import parse_config

from .harness import CONFIG, Harness


async def test_the_admin_listens_while_nestor_runs(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        server = AdminServer(admin.nestor, AdminSettings(port=0))
        async with server:
            await server.start()  # idempotent
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://127.0.0.1:{server.port}/health")
            assert response.json() == {"status": "ok"}
        await server.close()


async def test_a_busy_port_is_reported_clearly(tmp_path: Path) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        async with Harness(tmp_path) as admin:
            server = AdminServer(admin.nestor, AdminSettings(port=port))
            with pytest.raises(ProviderError, match=f"cannot listen on 127.0.0.1:{port}"):
                await server.start()
            assert server.port == port


async def test_the_command_line_serves_the_admin_until_stopped(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    await harness.browser.aclose()
    server = AdminServer.from_config(harness.nestor)
    seen: list[int] = []

    async def probe() -> None:
        while not server.port:
            await asyncio.sleep(0.01)
        async with httpx.AsyncClient() as client:
            seen.append((await client.get(f"http://127.0.0.1:{server.port}/health")).status_code)
        os.kill(os.getpid(), signal.SIGTERM)

    prober = asyncio.create_task(probe())
    await asyncio.wait_for(run_until_stopped(harness.nestor, [server]), timeout=5)
    await prober
    assert seen == [200]


def test_without_an_admin_section_there_is_no_server(tmp_path: Path) -> None:
    config = parse_config(CONFIG.format(data_dir=tmp_path, admin="null"), {})
    nestor = Nestor(config, Harness(tmp_path).registry())
    assert nestor.connections is None, "connectors are only installed by default when the admin is on"
    with pytest.raises(ContractError, match="no admin section"):
        AdminServer.from_config(nestor)


def test_connectors_need_the_instance_secret_key(tmp_path: Path) -> None:
    config = parse_config(CONFIG.format(data_dir=tmp_path, admin={}), {})
    with pytest.raises(ConfigError, match=r"NESTOR_SECRET_KEY is not set.*secrets\.token_urlsafe"):
        Nestor(config, Harness(tmp_path).registry(), environ={})


def test_a_service_configured_twice_is_refused(tmp_path: Path) -> None:
    text = CONFIG.format(data_dir=tmp_path, admin="null") + "connectors: [{kind: imap}, {kind: imap, name: other}]\n"
    with pytest.raises(ContractError, match="same kind"):
        Nestor(parse_config(text, {}), Harness(tmp_path).registry(), environ={"NESTOR_SECRET_KEY": "k" * 40})


async def test_a_mail_arriving_in_a_connected_mailbox_triggers_a_watch(tmp_path: Path) -> None:
    verdict = '{"matches": true, "urgent": false, "summary": "Colis livré."}'
    async with Harness(tmp_path, replies=(verdict, "Ton colis est arrivé.")) as admin:
        assert admin.nestor.connections
        assert admin.nestor.watch_book.kinds == {"mail"}, "watches may watch what connectors bring"
        await admin.nestor.connections.connect("imap", None, {"server": "s", "password": "p"})
        await admin.nestor.watch_book.create(Watch(what="le colis", keywords=("Colissimo",)))
        triggered = admin.nestor.journal.subscribe(WatchTriggered)
        await asyncio.sleep(0.05)
        admin.imap.inbox.deliver(Incoming(source="imap", kind="mail", title="Votre colis Colissimo"))
        event = await triggered.next(timeout_s=2)
        assert isinstance(event, WatchTriggered) and event.summary == "Colis livré."


def test_the_command_line_checks_a_configuration_with_the_admin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "nestor.yaml"
    path.write_text(
        CONFIG.format(data_dir=tmp_path, admin={"password_hash": "scrypt$left-from-before"})
        .replace("kind: scripted", "kind: openai-compatible, api_key: k, model: m, base_url: 'http://x'")
        .replace("[{kind: remote, name: hermes}]", "[]")
        .replace("[{kind: memory, name: telegram}]", "[{kind: telegram, token: '1:a'}]")
        .replace("presence: {kind: static}\n", "")
    )
    monkeypatch.setenv("NESTOR_SECRET_KEY", "k" * 40)
    assert main(["-c", str(path), "check"]) == 0
    out = capsys.readouterr().out
    assert "admin on 127.0.0.1:8080" in out
    assert "admin.password_hash is no longer used; run `nestor accounts create-owner`" in out, (
        "an older file still loads"
    )
