"""`nestor init`: a first configuration that validates, secrets generated, nothing ever overwritten."""

import stat
from pathlib import Path

import pytest

from nestor.admin import verify_password
from nestor.cli import main
from nestor.init import initialise
from nestor.runtime.config import load_config


def env_of(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#"))
    return {k: v or "filled-later" for k, v in pairs}


def test_a_new_home_gets_a_valid_configuration_and_private_secrets(tmp_path: Path) -> None:
    config = tmp_path / "data" / "nestor.yaml"
    written = initialise(config, name="Richie", person="Mathis Lambert", password="un-long-mot-de-passe")

    env = config.parent / ".env"
    assert written == [env, config]
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    secrets = env_of(env)
    assert len(secrets["NESTOR_SECRET_KEY"]) >= 32
    loaded = load_config(config, secrets)
    assert loaded.persona.name == "Richie"
    assert loaded.household[0].id == "mathis-lambert"
    assert loaded.admin is not None and verify_password("un-long-mot-de-passe", loaded.admin.password_hash)


def test_nothing_existing_is_ever_overwritten(tmp_path: Path) -> None:
    config = tmp_path / "nestor.yaml"
    config.write_text("# mine\n")
    (tmp_path / ".env").write_text("NESTOR_SECRET_KEY=keep-me\n")
    assert initialise(config, name="Nestor", person="Moi", password="un-long-mot-de-passe") == []
    assert config.read_text() == "# mine\n" and "keep-me" in (tmp_path / ".env").read_text()


def test_the_command_asks_then_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["Richie", "Mathis"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt: "un-long-mot-de-passe")
    config = tmp_path / "nestor.yaml"

    assert main(["-c", str(config), "init"]) == 0
    assert main(["-c", str(config), "init"]) == 0
    out = capsys.readouterr().out
    assert f"wrote {config}" in out and "already exists: nothing changed" in out


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
