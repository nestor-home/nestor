"""The configuration file: validated before anything starts, secrets from the environment."""

from pathlib import Path

import pytest

from nestor.modules.channels import Address
from nestor.runtime import ConfigError, load_config
from nestor.runtime.config import parse_config

VALID = """
persona:
  name: Richie
  character: Tu es Richie.
household:
  - id: mathis
    name: Mathis
    accounts: ["telegram:42", "voice:*"]
    reach: telegram:42
model:
  kind: openai-compatible
  api_key: ${OPENROUTER_API_KEY}
  model: anthropic/claude-haiku-5.5
channels:
  - kind: telegram
    token: ${TELEGRAM_TOKEN}
"""
ENV = {"OPENROUTER_API_KEY": "sk-test", "TELEGRAM_TOKEN": "123:abc"}


def test_a_valid_file_gives_people_adapters_and_secrets() -> None:
    config = parse_config(VALID, ENV)

    person = config.household[0].to_person()
    assert (person.name, person.reach) == ("Mathis", Address("telegram", "42"))
    assert [str(a) for a in person.accounts] == ["telegram:42", "voice:*"]
    assert config.model.kind == "openai-compatible"
    assert config.model.settings() == {"api_key": "sk-test", "model": "anthropic/claude-haiku-5.5"}
    assert config.channels[0].settings() == {"token": "123:abc"}


def test_a_missing_secret_is_named() -> None:
    with pytest.raises(ConfigError, match="TELEGRAM_TOKEN is not set"):
        parse_config(VALID, {"OPENROUTER_API_KEY": "sk"})


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("persona: [unclosed", "not valid YAML"),
        (VALID.replace("household:", "people:"), "household: Field required"),
        (VALID.replace("  name: Richie", "  name: Richie\n  mood: grumpy"), "persona.mood: Extra inputs"),
        (VALID.replace('"voice:*"', '"voice"'), "invalid account 'voice'"),
        (VALID.replace("channels:\n  - kind: telegram\n    token: ${TELEGRAM_TOKEN}", "channels: []"), "channels"),
    ],
    ids=["yaml", "missing-section", "unknown-key", "bad-account", "no-channel"],
)
def test_an_invalid_file_says_where_and_why(text: str, reason: str) -> None:
    with pytest.raises(ConfigError, match=reason):
        parse_config(text, ENV)


def test_a_file_is_read_with_the_environment(tmp_path: Path) -> None:
    path = tmp_path / "nestor.yaml"
    path.write_text(VALID)
    assert load_config(path, ENV).persona.name == "Richie"
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "absent.yaml")
