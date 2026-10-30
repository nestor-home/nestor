"""The command line on the configuration's secrets (straight on the vault, no instance running) and on
restarting a running instance."""

import asyncio
import io
import sys
from pathlib import Path

import pytest

from nestor.admin import AdminServer, AdminSettings
from nestor.cli import main
from nestor.modules.journal import Journal
from nestor.modules.system import SecretChanged
from nestor.runtime.app import Restart
from nestor.runtime.config import ConfigError, load_config
from nestor.runtime.secrets import open_secrets

from .admin.harness import CONFIG, SECRET_KEY, Harness
from .admin.test_satellites import free_port

VALUE = "123:telegram-bot-token"


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "nestor.yaml"
    text = CONFIG.format(data_dir=tmp_path, admin="null").replace(
        "channels: [{kind: memory, name: telegram}]",
        "channels: [{kind: memory, name: telegram, token: '${secret:bot}'}]",
    )
    path.write_text(text)
    monkeypatch.setenv("NESTOR_SECRET_KEY", SECRET_KEY)
    return path


def test_a_secret_is_set_from_a_hidden_prompt_listed_with_its_use_and_read_when_the_config_loads(
    config: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(ConfigError, match="secret bot is not set: `nestor secrets set bot`"):
        load_config(config)
    assert main(["-c", str(config), "secrets", "list"]) == 0
    assert "bot  not set  (channels.0.token)" in capsys.readouterr().out

    monkeypatch.setattr("getpass.getpass", lambda prompt: VALUE)
    assert main(["-c", str(config), "secrets", "set", "bot"]) == 0
    assert VALUE not in capsys.readouterr().out
    loaded = load_config(config)
    assert loaded.channels[0].settings()["token"] == VALUE
    assert main(["-c", str(config), "secrets", "list"]) == 0
    assert "bot  set     123…ken  (channels.0.token)" in capsys.readouterr().out

    monkeypatch.setattr(sys, "stdin", io.StringIO("short\n"))
    assert main(["-c", str(config), "secrets", "set", "spare", "--from-stdin"]) == 0
    assert main(["-c", str(config), "secrets", "list"]) == 0
    assert "spare  set     •••  (unused)" in capsys.readouterr().out


def test_a_secret_still_used_is_kept_unless_forced_and_every_change_is_journaled(
    config: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("getpass.getpass", lambda prompt: VALUE)
    main(["-c", str(config), "secrets", "set", "bot"])
    assert main(["-c", str(config), "secrets", "delete", "bot"]) == 2
    assert "still used by channels.0.token" in capsys.readouterr().err
    assert main(["-c", str(config), "secrets", "delete", "bot", "--force"]) == 0
    assert main(["-c", str(config), "secrets", "delete", "bot", "--force"]) == 2
    assert "no secret bot" in capsys.readouterr().err

    async def changes() -> list[SecretChanged]:
        async with open_secrets(config.parent, SECRET_KEY) as secrets:
            journal: Journal = secrets.journal
            return await journal.history(SecretChanged)

    found = asyncio.run(changes())
    assert [(c.name, c.by, c.removed) for c in found] == [("bot", "cli", False), ("bot", "cli", True)]


def test_secrets_need_the_instance_key(
    config: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NESTOR_SECRET_KEY")
    assert main(["-c", str(config), "secrets", "list"]) == 2
    assert "NESTOR_SECRET_KEY is not set" in capsys.readouterr().err
    with pytest.raises(ConfigError, match="NESTOR_SECRET_KEY is not set to open the vault"):
        load_config(config)


def test_a_restart_stops_the_process_cleanly_then_runs_the_same_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stopped: list[bool] = []
    restart = Restart(stop=lambda: stopped.append(True))
    restart.request()
    assert restart.requested and stopped == [True]

    executed: list[tuple[str, list[str]]] = []
    monkeypatch.setattr("os.execv", lambda path, argv: executed.append((path, list(argv))))

    async def serve_then_restart(nestor: object, extras: object) -> None:
        nestor.restart.requested = True  # ty: ignore[unresolved-attribute]

    monkeypatch.setattr("nestor.cli.run_until_stopped", serve_then_restart)
    config = tmp_path / "nestor.yaml"
    config.write_text(
        CONFIG.format(data_dir=tmp_path, admin="null")
        .replace("kind: scripted", "kind: openai-compatible, api_key: k, model: m, base_url: 'http://x'")
        .replace("[{kind: remote, name: hermes}]", "[]")
        .replace("[{kind: memory, name: telegram}]", "[{kind: telegram, token: '1:a'}]")
        .replace("presence: {kind: static}\n", "")
    )
    assert main(["-c", str(config), "run"]) == 0
    assert executed == [(sys.executable, sys.orig_argv)]


async def test_the_command_line_restarts_the_running_instance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    port = free_port()
    config = tmp_path / "nestor.yaml"
    config.write_text(CONFIG.format(data_dir=tmp_path, admin={"port": port}))
    async with Harness(tmp_path) as admin:
        server = AdminServer(admin.nestor, AdminSettings(port=port))
        restarted = asyncio.Event()
        server.app.state.admin.restart = restarted.set
        async with server:
            assert await asyncio.to_thread(main, ["-c", str(config), "restart"]) == 0
            await asyncio.wait_for(restarted.wait(), 2)
    assert "restarting" in capsys.readouterr().out
