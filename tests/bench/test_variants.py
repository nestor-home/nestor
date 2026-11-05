"""Variants: a fragment of nestor.yaml over a minimal configuration, plus the suite's knobs under `bench`."""

from pathlib import Path
from typing import Any

import pytest

from nestor.bench import BenchError
from nestor.bench.variants import Variant, load_variant
from nestor.core import Component, ContractError
from nestor.runtime.config import ConfigError
from nestor.runtime.plugins import AdapterSettings, Family, ModelType, Plugin, Registry
from nestor.testing.i18n import EchoLocalizer

from .kit import ORACLE, Quiz, registry, write_variant


def load(path: Path, plugins: Registry | None = None) -> Variant[Any]:
    suite = Quiz()
    return load_variant(path, suite, plugins or registry(suite), EchoLocalizer(), environ={})


def test_a_variant_naming_only_the_model_under_test_runs_it_with_the_suites_knobs(tmp_path: Path) -> None:
    variant = load(write_variant(tmp_path, "small", "models: {m: {kind: oracle}}\nbench: {shout: true}\n"))
    assert variant.name == "small"
    assert variant.knobs.shout
    assert variant.config.models["m"].kind == "oracle"
    assert set(variant.models) == {"watches"}


def test_a_section_of_the_fragment_completes_the_defaults_rather_than_replacing_them(tmp_path: Path) -> None:
    text = "models: {m: {kind: oracle}}\npersona: {language: French, locale: fr-FR}\nbench: {name: french}\n"
    variant = load(write_variant(tmp_path, "v", text))
    assert (variant.name, variant.config.persona.language, variant.config.persona.name) == (
        "french",
        "French",
        "Nestor",
    )


def test_a_whole_configuration_is_a_variant_and_its_roles_take_the_models_it_gives_them(tmp_path: Path) -> None:
    text = """
persona: {name: Alfred, character: calm}
household: [{id: lea, name: Léa}]
models:
  big: {kind: oracle, served: big}
  small: {kind: oracle, served: small}
agent: {written: big}
watches: {model: small}
channels: [{kind: telegram}]
"""
    variant = load(write_variant(tmp_path, "nestor", text))
    assert (variant.described["watches"]["name"], variant.described["watches"]["served"]) == ("small", "small")


def test_what_a_run_keeps_of_a_variant_never_holds_a_secret(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ORACLE_KEY=sk-live-123456\n")
    text = "models: {m: {kind: oracle, api_key: '${ORACLE_KEY}'}}\n"
    variant = load_variant(write_variant(tmp_path, "keyed", text), Quiz(), Registry([ORACLE]), EchoLocalizer())
    kept = str(variant.record())
    assert "sk-live-123456" not in kept
    assert variant.record()["models"]["watches"]["api_key"] == "**********"


def test_a_variant_without_models_is_refused_as_a_configuration_would_be(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="models"):
        load(write_variant(tmp_path, "v", "persona: {language: French}\n"))


def test_a_missing_variable_is_named_as_in_a_configuration(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ORACLE_KEY"):
        load(write_variant(tmp_path, "v", "models: {m: {kind: oracle, api_key: '${ORACLE_KEY}'}}\n"))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("- not a mapping\n", "bench-variant-unreadable"),
        ("models: [unclosed\n", "bench-variant-unreadable"),
        ("models: {m: {kind: oracle}}\nbench: {loud: true}\n", "bench-variant-invalid"),
    ],
)
def test_a_variant_that_cannot_be_used_says_why(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(BenchError) as raised:
        load(write_variant(tmp_path, "v", text))
    assert raised.value.message.id == message


def test_an_unreadable_variant_file_says_so(tmp_path: Path) -> None:
    with pytest.raises(BenchError, match="bench-variant-unreadable"):
        load(tmp_path / "missing.yaml")


def test_an_unknown_model_kind_lists_the_installed_ones(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="available: oracle"):
        load(write_variant(tmp_path, "v", "models: {m: {kind: gpt}}\n"))


def test_a_model_kind_that_builds_something_else_is_refused(tmp_path: Path) -> None:
    class Lamp(Component):
        name = "lamp"

    odd = Plugin(
        Family.MODEL, "lamp", AdapterSettings, lambda settings, name, services: Lamp(), model_type=ModelType.LANGUAGE
    )
    with pytest.raises(ContractError, match="plugin 'lamp' built a Lamp, not a language model"):
        load(write_variant(tmp_path, "v", "models: {m: {kind: lamp}}\n"), Registry([odd]))
