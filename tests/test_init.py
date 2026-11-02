"""`nestor init`: a first configuration that validates, secrets generated, an owner who can sign in,
nothing ever overwritten; and `nestor accounts create-owner` for an install that predates accounts."""

import asyncio
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

from nestor.cli import main
from nestor.core import ContractError
from nestor.init import LANGUAGES, Setup, initialise, local_timezone
from nestor.modules.accounts import Account, Role
from nestor.runtime.app import open_accounts
from nestor.runtime.config import NestorConfig, load_config

PASSWORD = "un-long-mot-de-passe"


def sign_in(config: NestorConfig, login: str, password: str = PASSWORD) -> Account | None:
    async def attempt() -> Account | None:
        async with open_accounts(config.data_dir, [p.to_person() for p in config.household]) as accounts:
            return await accounts.authenticate(login, password)

    return asyncio.run(attempt())


def env_of(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#"))
    return {k: v or "filled-later" for k, v in pairs}


def test_a_new_home_gets_a_valid_configuration_and_private_secrets(tmp_path: Path) -> None:
    config = tmp_path / "data" / "nestor.yaml"
    written = initialise(
        config, Setup(name="Richie", person="Mathis Lambert"), login="mathis@example.org", password=PASSWORD
    )

    env = config.parent / ".env"
    assert written == [env, config, config.parent.resolve() / "state" / "nestor.db"]
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    secrets = env_of(env)
    assert len(secrets["NESTOR_SECRET_KEY"]) >= 32
    loaded = load_config(config, secrets)
    assert loaded.persona.name == "Richie"
    assert loaded.household[0].id == "mathis-lambert"
    assert loaded.admin is not None
    owner = sign_in(loaded, "Mathis@Example.org")
    assert owner is not None and (owner.role, owner.person) == (Role.OWNER, "mathis-lambert")
    assert PASSWORD not in config.read_text()


def test_a_first_configuration_is_in_english_unless_another_language_is_chosen(tmp_path: Path) -> None:
    initialise(tmp_path / "en" / "nestor.yaml", Setup(), login="me", password=PASSWORD)
    english = load_config(tmp_path / "en" / "nestor.yaml", env_of(tmp_path / "en" / ".env")).persona
    assert (english.locale, english.language, english.timezone) == ("en", "English", "UTC")

    chosen = Setup(locale="fr", timezone="Europe/Paris", voice=True)
    initialise(tmp_path / "fr" / "nestor.yaml", chosen, login="moi", password=PASSWORD)
    french = load_config(tmp_path / "fr" / "nestor.yaml", env_of(tmp_path / "fr" / ".env"))
    assert (french.persona.locale, french.persona.language, french.persona.timezone) == ("fr", "French", "Europe/Paris")
    assert french.channels[0].settings()["voice"]["speech"]["language"] == "fr", (
        "the transcription follows the household"
    )


def test_without_voice_satellites_write_and_telegram_asks_for_its_bot_token(tmp_path: Path) -> None:
    config = tmp_path / "nestor.yaml"
    initialise(config, Setup(voice=False), login="me", password=PASSWORD)
    secrets = env_of(tmp_path / ".env")
    assert set(secrets) == {"NESTOR_SECRET_KEY", "MODEL_API_KEY", "TELEGRAM_BOT_TOKEN"}
    assert [c.kind for c in load_config(config, secrets).channels] == ["satellites", "telegram"]


def test_with_voice_satellites_speak_and_the_configuration_asks_for_its_key(tmp_path: Path) -> None:
    config = tmp_path / "nestor.yaml"
    initialise(config, Setup(voice=True), login="me", password=PASSWORD)
    secrets = env_of(tmp_path / ".env")
    assert set(secrets) == {"NESTOR_SECRET_KEY", "MODEL_API_KEY", "ELEVENLABS_API_KEY"}
    loaded = load_config(config, secrets)
    assert [c.kind for c in loaded.channels] == ["satellites"]
    assert loaded.household[0].accounts == ("satellites:*",)


def test_a_local_model_passes_the_check_with_its_key_left_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "nestor.yaml"
    initialise(config, Setup(base_url="http://localhost:11434/v1", model="llama3.2"), login="me", password=PASSWORD)
    env = tmp_path / ".env"
    env.write_text(env.read_text().replace("TELEGRAM_BOT_TOKEN=\n", "TELEGRAM_BOT_TOKEN=123:abc\n"))
    assert main(["-c", str(config), "check"]) == 0
    assert "channels: satellites, telegram, admin on 0.0.0.0:8470" in capsys.readouterr().out


def test_a_hosted_model_with_its_key_left_empty_fails_the_check_naming_the_variable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "nestor.yaml"
    initialise(config, Setup(), login="me", password=PASSWORD)  # OpenRouter, Telegram: both keys empty
    assert main(["-c", str(config), "check"]) == 2
    err = capsys.readouterr().err
    assert "model 'main' (openai-compatible): api_key: openrouter.ai requires an API key" in err
    assert f"MODEL_API_KEY is empty (in {tmp_path / '.env'} or the environment), used by models.main.api_key" in err
    assert "TELEGRAM_BOT_TOKEN" not in err, "only the variables behind the error are named"


def test_every_language_nestor_speaks_can_be_chosen() -> None:
    from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs

    assert set(FluentLocalizer(catalogue_dirs(["nestor"])).locales) == set(LANGUAGES)


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        (lambda: Setup(locale="de"), "choose a language among en, fr"),
        (lambda: Setup(timezone="Mars/Olympus"), "unknown time zone 'Mars/Olympus'"),
        (lambda: Setup(model=""), "name the model"),
    ],
)
def test_an_impossible_setup_is_refused(setup: Callable[[], Setup], reason: str) -> None:
    with pytest.raises(ContractError, match=reason):
        setup()


def test_the_time_zone_offered_is_the_machines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    localtime = tmp_path / "localtime"
    localtime.symlink_to(tmp_path / "usr" / "share" / "zoneinfo" / "America" / "New_York")
    monkeypatch.delenv("TZ", raising=False)
    assert local_timezone(localtime) == "America/New_York"
    monkeypatch.setenv("TZ", ":Europe/Paris")
    assert local_timezone(localtime) == "Europe/Paris", "TZ wins"
    monkeypatch.setenv("TZ", "nowhere")
    assert local_timezone(tmp_path / "absent") == "UTC"


def test_nothing_existing_is_ever_overwritten(tmp_path: Path) -> None:
    config = tmp_path / "nestor.yaml"
    config.write_text("# mine\n")
    (tmp_path / ".env").write_text("NESTOR_SECRET_KEY=keep-me\n")
    assert initialise(config, Setup(), login="moi", password=PASSWORD) == []
    assert config.read_text() == "# mine\n" and "keep-me" in (tmp_path / ".env").read_text()


@pytest.mark.parametrize("installed", [True, False])
def test_the_command_asks_then_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], installed: bool
) -> None:
    # name, first name, language, time zone, model server, model, [voice,] login
    answers = iter(["Richie", "Mathis", "", "UTC", "", "", *(["n"] if installed else []), ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt: PASSWORD)
    monkeypatch.setattr("nestor.cli.voice_installed", lambda: installed)
    config = tmp_path / "nestor.yaml"

    assert main(["-c", str(config), "init"]) == 0
    assert main(["-c", str(config), "init"]) == 0
    out = capsys.readouterr().out
    assert f"wrote {config}" in out and "owner account 'mathis' created" in out
    assert "already exists: nothing changed" in out
    assert f"fill the keys in {tmp_path / '.env'}" in out
    assert ("pip install 'nestor-home[voice]'" in out) is not installed, "said only when voice is missing"
    assert next(answers, None) is None, "every question was asked"
    loaded = load_config(config, env_of(tmp_path / ".env"))
    assert sign_in(loaded, "mathis")
    assert (loaded.persona.locale, loaded.models["main"].settings()["base_url"]) == (
        "en",
        "https://openrouter.ai/api/v1",
    )
    assert [c.kind for c in loaded.channels] == ["satellites", "telegram"]


def test_voice_is_written_when_installed_and_wanted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["", "Ada", "", "", "http://localhost:1234/v1", "qwen3", "", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt: PASSWORD)
    monkeypatch.setattr("nestor.cli.voice_installed", lambda: True)
    config = tmp_path / "nestor.yaml"
    assert main(["-c", str(config), "init"]) == 0
    loaded = load_config(config, env_of(tmp_path / ".env"))
    assert [c.kind for c in loaded.channels] == ["satellites"]
    assert loaded.models["main"].settings()["model"] == "qwen3"


@pytest.mark.parametrize(
    ("first", "second", "reason"), [("court", "court", "at least 10"), ("a" * 12, "b" * 12, "differ")]
)
def test_a_bad_password_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    first: str,
    second: str,
    reason: str,
) -> None:
    passwords = iter([first, second])
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(passwords))
    assert main(["-c", str(tmp_path / "nestor.yaml"), "init"]) == 2
    assert reason in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_a_bad_login_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="a login is an email or a username"):
        initialise(tmp_path / "nestor.yaml", Setup(), login="moi !", password=PASSWORD)
    assert list(tmp_path.iterdir()) == []


EXISTING = """
data_dir: {data_dir}
persona: {{name: Richie, character: Tu es Richie.}}
household: [{{id: mathis, name: Mathis}}, {{id: lucie, name: Lucie}}]
models: {{main: {{kind: openai-compatible, api_key: k, model: m, base_url: "http://x"}}}}
channels: [{{kind: telegram, token: "1:a"}}]
admin: {{port: 8470}}
"""


def test_an_install_from_before_accounts_gets_its_owner_from_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "nestor.yaml"
    path.write_text(EXISTING.format(data_dir=tmp_path))
    monkeypatch.setattr("getpass.getpass", lambda prompt: PASSWORD)
    assert main(["-c", str(path), "accounts", "create-owner"]) == 0
    assert "owner account 'mathis' created for mathis" in capsys.readouterr().out
    assert main(["-c", str(path), "accounts", "create-owner", "--login", "lucie@example.org", "--person", "lucie"]) == 0
    config = load_config(path, {})
    first, second = sign_in(config, "mathis"), sign_in(config, "lucie@example.org")
    assert first and second and (first.person, second.person) == ("mathis", "lucie")
    assert {first.role, second.role} == {Role.OWNER}

    assert main(["-c", str(path), "accounts", "create-owner"]) == 2, "mathis already has an account"
    assert "already" in capsys.readouterr().err
    passwords = iter([PASSWORD, "typo-typo-typo"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(passwords))
    assert main(["-c", str(path), "accounts", "create-owner", "--login", "x", "--person", "lucie"]) == 2
