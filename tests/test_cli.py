"""The command line on the configuration's secrets (straight on the vault, no instance running), on
restarting a running instance, and on checking a satellite program against the standard."""

import asyncio
import io
import json
import sys
from pathlib import Path

import pytest

from nestor.admin import AdminServer, AdminSettings
from nestor.cli import main
from nestor.core import Capability
from nestor.modules.journal import Journal
from nestor.modules.satellites import Device, Manifest
from nestor.modules.satellites.types import DeclaredCapability
from nestor.modules.system import SecretChanged
from nestor.runtime.app import Restart
from nestor.runtime.config import ConfigError, load_config
from nestor.runtime.secrets import open_secrets

from .admin.harness import CONFIG, SECRET_KEY, Harness
from .admin.test_satellites import free_port

VALUE = "123:telegram-bot-token"
SPEAKER = Manifest(
    Device("enceinte-salon", "raspberry-pi-zero", "salon"),
    (DeclaredCapability(Capability("audio.capture")), DeclaredCapability(Capability("audio.playback"))),
)


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


@pytest.fixture
def english(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")


@pytest.mark.usefixtures("english")
def test_a_conformant_satellite_program_passes_every_check(capsys: pytest.CaptureFixture[str]) -> None:
    satellite = [sys.executable, "-m", "tests.adapters.channels.satellites.reference", "{url}", "{state}",
                 json.dumps(SPEAKER.to_json())]  # fmt: skip
    assert main(["satellites", "conformance", "--deadline", "15", "--", *satellite]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "PASS  pairs with the enrollment code of NESTOR_PAIRING_URI, no code typed (P3, P4)" in lines
    assert "PASS  reconnects with the same token after the core closes its link (L5)" in lines
    assert not [line for line in lines if line.startswith("FAIL")]
    assert lines[-1] == f"conformant: {len(lines) - 1} checks passed"


def test_a_satellite_program_that_exits_fails_with_what_went_wrong_in_the_readers_language(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
    assert main(["satellites", "conformance", "--deadline", "1", "--", sys.executable, "-c", "pass"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "ÉCHEC  demande à être appairé",
        "ÉCHEC  tourne sans planter (terminé avec le code 0)",
        "2 vérifications échouées sur 2",
    ]


@pytest.mark.usefixtures("english")
@pytest.mark.parametrize(
    ("command", "said"),
    [
        ([], "give the satellite's command after --"),
        (["--", "./no-such-satellite"], "./no-such-satellite cannot be run"),
    ],
    ids=["no command", "no such program"],
)
def test_a_satellite_that_cannot_be_launched_is_a_usage_error(
    command: list[str], said: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["satellites", "conformance", *command]) == 2
    assert said in capsys.readouterr().err


@pytest.mark.usefixtures("english")
@pytest.mark.usefixtures("english")
def test_without_the_voice_extra_the_suite_says_audio_cannot_be_checked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in [m for m in sys.modules if m.startswith("pipecat")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "pipecat", None)  # as if the extra were not installed
    satellite = [sys.executable, "-m", "tests.adapters.channels.satellites.reference", "{url}", "{state}",
                 json.dumps(SPEAKER.to_json())]  # fmt: skip
    assert main(["satellites", "conformance", "--deadline", "15", "--", *satellite]) == 1
    failed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL")]
    assert failed == [
        "FAIL  exchanges audio, as allowed (A1, A2) (audio cannot be checked without the voice extra "
        "(pipecat is missing))"
    ]


def test_every_command_reads_the_dot_env_next_to_the_configuration_and_the_shell_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config = home / "nestor.yaml"
    config.write_text(
        CONFIG.format(data_dir="${NESTOR_DATA}", admin="null")
        .replace(
            "kind: scripted",
            "kind: openai-compatible, api_key: '${OPENROUTER_API_KEY}', model: m, base_url: 'http://x'",
        )
        .replace("[{kind: remote, name: hermes}]", "[]")
        .replace("[{kind: memory, name: telegram}]", "[{kind: telegram, token: '${secret:bot}'}]")
        .replace("presence: {kind: static}\n", "")
    )
    (home / ".env").write_text(
        f"# from nestor init\nexport NESTOR_SECRET_KEY={SECRET_KEY}\nNESTOR_DATA='{tmp_path / 'state'}'\n"
        "OPENROUTER_API_KEY=sk-from-file\n"
    )
    for name in ("NESTOR_SECRET_KEY", "NESTOR_DATA", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sys, "stdin", io.StringIO(VALUE))
    assert main(["-c", str(config), "secrets", "set", "bot", "--from-stdin"]) == 0  # the vault opens
    assert (tmp_path / "state" / "nestor.db").exists()
    assert main(["-c", str(config), "check"]) == 0
    assert f"{config}: OK" in capsys.readouterr().out

    assert main(["-c", str(config), "secrets", "list"]) == 0
    assert "bot  set" in capsys.readouterr().out

    monkeypatch.setenv("NESTOR_DATA", str(tmp_path / "elsewhere"))  # the shell wins over the file
    assert main(["-c", str(config), "secrets", "list"]) == 0
    assert "bot  not set" in capsys.readouterr().out
    assert (tmp_path / "elsewhere" / "nestor.db").exists()


def test_a_configuration_that_cannot_be_read_is_reported_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["-c", str(tmp_path / "absent.yaml"), "check"]) == 2
    assert capsys.readouterr().err.count("nestor:") == 1
