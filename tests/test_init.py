"""`nestor init`: a first configuration that validates, secrets generated, an owner who can sign in,
nothing ever overwritten; and `nestor accounts create-owner` for an install that predates accounts."""

import asyncio
import stat
from pathlib import Path

import pytest

from nestor.cli import main
from nestor.init import initialise
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
    written = initialise(config, name="Richie", person="Mathis Lambert", login="mathis@example.org", password=PASSWORD)

    env = config.parent / ".env"
    assert written == [env, config, config.parent.resolve() / "state" / "nestor.db"]
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    secrets = env_of(env)
    assert len(secrets["NESTOR_SECRET_KEY"]) >= 32
    loaded = load_config(config, secrets)
    assert loaded.persona.name == "Richie"
    assert loaded.household[0].id == "mathis-lambert"
    assert loaded.admin is not None and loaded.admin.password_hash is None
    owner = sign_in(loaded, "Mathis@Example.org")
    assert owner is not None and (owner.role, owner.person) == (Role.OWNER, "mathis-lambert")
    assert PASSWORD not in config.read_text()


def test_nothing_existing_is_ever_overwritten(tmp_path: Path) -> None:
    config = tmp_path / "nestor.yaml"
    config.write_text("# mine\n")
    (tmp_path / ".env").write_text("NESTOR_SECRET_KEY=keep-me\n")
    assert initialise(config, name="Nestor", person="Moi", login="moi", password=PASSWORD) == []
    assert config.read_text() == "# mine\n" and "keep-me" in (tmp_path / ".env").read_text()


def test_the_command_asks_then_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["Richie", "Mathis", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt: PASSWORD)
    config = tmp_path / "nestor.yaml"

    assert main(["-c", str(config), "init"]) == 0
    assert main(["-c", str(config), "init"]) == 0
    out = capsys.readouterr().out
    assert f"wrote {config}" in out and "owner account 'mathis' created" in out
    assert "already exists: nothing changed" in out
    assert sign_in(load_config(config, {"OPENROUTER_API_KEY": "k", "ELEVENLABS_API_KEY": "k"}), "mathis")


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
        initialise(tmp_path / "nestor.yaml", name="Nestor", person="Moi", login="moi !", password=PASSWORD)
    assert list(tmp_path.iterdir()) == []


EXISTING = """
data_dir: {data_dir}
persona: {{name: Richie, character: Tu es Richie.}}
household: [{{id: mathis, name: Mathis}}, {{id: lucie, name: Lucie}}]
model: {{kind: openai-compatible, api_key: k, model: m, base_url: "http://x"}}
channels: [{{kind: telegram, token: "1:a"}}]
admin: {{port: 8080, password_hash: "scrypt$from-before-accounts"}}
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
