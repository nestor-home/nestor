"""The configuration file: validated before anything starts, secrets from the environment and the
`.env` next to it."""

import logging
import re
from pathlib import Path

import pytest

from nestor.modules.channels import Address
from nestor.runtime import ConfigError, load_config
from nestor.runtime.config import environment, parse_config

VALID = """
persona:
  name: Richie
  character: Tu es Richie.
household:
  - id: mathis
    name: Mathis
    accounts: ["telegram:42", "voice:salon"]
    reach: telegram:42
models:
  haiku:
    type: language
    provider: openai-compatible
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
    assert [str(a) for a in person.accounts] == ["telegram:42", "voice:salon"]
    assert (config.models["haiku"].type, config.models["haiku"].provider) == ("language", "openai-compatible")
    assert config.models["haiku"].settings() == {"api_key": "sk-test", "model": "anthropic/claude-haiku-5.5"}
    assert config.channels[0].settings() == {"token": "123:abc"}


TWO_MODELS = VALID.replace(
    "channels:",
    "  local: {type: language, provider: openai-compatible, base_url: http://localhost:11434/v1, model: qwen3}"
    "\nchannels:",
)


def test_a_single_model_takes_every_role() -> None:
    roles = parse_config(VALID, ENV).roles(["haiku"])
    assert set(roles.values()) == {"haiku"} and set(roles) == {
        "spoken",
        "written",
        "titles",
        "watches",
        "consolidation",
    }


def test_roles_take_the_models_named_and_fall_back_on_each_other() -> None:
    def roles(extra: str) -> dict[str, str]:
        return parse_config(TWO_MODELS + extra, ENV).roles(["haiku", "local"])

    assert roles("agent: {spoken: haiku, written: local}\n") == {
        "spoken": "haiku",
        "written": "local",
        "titles": "local",
        "watches": "local",
        "consolidation": "local",
    }, "the titles, the watches and the consolidation take the written model by default"
    assert roles("agent: {spoken: haiku}\nmemory: {consolidation: local}\n") == {
        "spoken": "haiku",
        "written": "haiku",
        "titles": "haiku",
        "watches": "haiku",
        "consolidation": "local",
    }, "the written one takes the spoken one, and a role named takes its model"


@pytest.mark.parametrize(
    ("extra", "error"),
    [
        ("agent: {written: sonnet}\n", "agent: Value error, written: no model named 'sonnet' in models (haiku, local)"),
        ("agent: {written: local}\nwatches: {model: mini}\n", "watches: Value error, model: no model named 'mini'"),
    ],
)
def test_a_role_must_name_a_declared_model(extra: str, error: str) -> None:
    with pytest.raises(ConfigError, match=re.escape(error)):
        parse_config(TWO_MODELS + extra, ENV)


def test_with_several_models_that_answer_the_agent_says_which() -> None:
    config = parse_config(TWO_MODELS, ENV)
    with pytest.raises(ConfigError, match=re.escape("agent: several models can answer (haiku, local)")):
        config.roles(["haiku", "local"])
    assert config.roles(["haiku"])["written"] == "haiku", "a model that embeds is never a default"


def test_a_model_name_is_one_word() -> None:
    with pytest.raises(ConfigError, match="'claude haiku' cannot name a model"):
        parse_config(VALID.replace("  haiku:", "  claude haiku:"), ENV)


def test_a_household_that_says_nothing_is_english_speaking_on_utc() -> None:
    persona = parse_config(VALID + "admin: {}\n", ENV).persona
    assert (persona.locale, persona.language, persona.timezone) == ("en", "English", "UTC")


def test_a_missing_secret_is_named() -> None:
    with pytest.raises(ConfigError, match="TELEGRAM_TOKEN is not set"):
        parse_config(VALID, {"OPENROUTER_API_KEY": "sk"})


def test_without_a_dot_env_the_environment_is_used_as_is(tmp_path: Path) -> None:
    config = tmp_path / "nestor.yaml"
    config.write_text(VALID)
    assert environment(config, ENV) == ENV
    with pytest.raises(ConfigError, match=r"TELEGRAM_TOKEN is not set \(in the environment or the \.env next"):
        load_config(config, environment(config, {"OPENROUTER_API_KEY": "sk"}))
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "absent.yaml")


DOT_ENV = """# written by nestor init, then filled by hand
export OPENROUTER_API_KEY=sk-from-file
TELEGRAM_TOKEN="123:abc # inside quotes"
LITERAL='p$ss ${HOME}'
EMPTY=
INLINE=value # a comment after a value
"""


def test_the_dot_env_next_to_the_file_fills_what_the_environment_lacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "home" / "nestor.yaml"
    config.parent.mkdir()
    config.write_text(VALID)
    (config.parent / ".env").write_text(DOT_ENV)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "999:from-the-shell")
    monkeypatch.chdir(tmp_path)  # the file next to the configuration, not the one of the working directory

    found = environment(config)
    assert {k: found[k] for k in ("OPENROUTER_API_KEY", "LITERAL", "EMPTY", "INLINE")} == {
        "OPENROUTER_API_KEY": "sk-from-file",
        "LITERAL": "p$ss ${HOME}",
        "EMPTY": "",
        "INLINE": "value",
    }
    loaded = load_config(config)  # by default, the process environment completed by the file
    assert loaded.models["haiku"].settings()["api_key"] == "sk-from-file"
    assert loaded.channels[0].settings() == {"token": "999:from-the-shell"}  # the environment wins

    monkeypatch.delenv("TELEGRAM_TOKEN")
    assert load_config(config).channels[0].settings() == {"token": "123:abc # inside quotes"}


def test_a_line_the_dot_env_cannot_parse_is_skipped_with_its_line_named(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = tmp_path / "nestor.yaml"
    (tmp_path / ".env").write_text('OPENROUTER_API_KEY=sk\nnot a variable\n"unclosed\nTELEGRAM_TOKEN=1:a\n')
    with caplog.at_level(logging.WARNING):
        found = environment(config, {})
    assert found == {"OPENROUTER_API_KEY": "sk", "TELEGRAM_TOKEN": "1:a"}
    assert "line 2" in caplog.text


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("persona: [unclosed", "not valid YAML"),
        (VALID.replace("household:", "people:"), "household: Field required"),
        (VALID.replace("  name: Richie", "  name: Richie\n  mood: grumpy"), "persona.mood: Extra inputs"),
        (VALID.replace('"voice:salon"', '"voice"'), "invalid account 'voice'"),
        (VALID.replace('"voice:salon"', '"voice:*"'), "not anyone"),
        (VALID.replace("channels:\n  - kind: telegram\n    token: ${TELEGRAM_TOKEN}", "channels: []"), "channels"),
        (VALID + "initiative: {quiet_hours: late}\n", "initiative.quiet_hours: .*HH:MM-HH:MM"),
    ],
    ids=["yaml", "missing-section", "unknown-key", "bad-account", "anyone-account", "no-channel", "quiet-hours"],
)
def test_an_invalid_file_says_where_and_why(text: str, reason: str) -> None:
    with pytest.raises(ConfigError, match=reason):
        parse_config(text, ENV)
