"""The Fluent localizer: Nestor's catalogues, plugins' catalogues, negotiation and fallbacks."""

from pathlib import Path

import pytest

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.core import ContractError
from nestor.core.i18n import Locale, Message, negotiate
from nestor.testing.i18n import EchoLocalizer, LocalizerContract

CONTRACT_EN = """contract-greeting = Hello { $name }
contract-count = { $count ->
    [one] one message
   *[other] { $count } messages
}
contract-default-only = only in English
"""
CONTRACT_FR = """contract-greeting = Bonjour { $name }
contract-count = { $count ->
    [one] un message
   *[other] { $count } messages
}
"""


def catalogues(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


class TestFluentLocalizer(LocalizerContract):
    @pytest.fixture(autouse=True)
    def _root(self, tmp_path: Path) -> None:
        self.root = catalogues(tmp_path / "locales", {"en/contract.ftl": CONTRACT_EN, "fr/contract.ftl": CONTRACT_FR})

    def localizer(self) -> FluentLocalizer:
        return FluentLocalizer([self.root])


class EchoSuite(LocalizerContract):
    """The double is only honest about ids and arguments: it must fail the contract on wording."""

    def localizer(self) -> EchoLocalizer:
        return EchoLocalizer("en", "fr")


def test_the_contract_rejects_a_localizer_that_ignores_the_locale() -> None:
    with pytest.raises(AssertionError):
        EchoSuite().test_a_message_is_rendered_in_the_closest_locale_with_its_arguments()


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [("fr-FR", "fr-FR"), ("fr-CA", "fr-FR"), ("fr", "fr-FR"), ("en_GB", "en"), ("de-DE", "en"), ("", "en")],
)
def test_negotiation_falls_back_from_region_to_language_to_default(wanted: str, expected: str) -> None:
    assert negotiate(wanted, [Locale("en"), Locale("fr-FR")], Locale("en")) == expected


def test_nestor_speaks_french_and_english_with_the_same_messages() -> None:
    localizer = FluentLocalizer(catalogue_dirs(["nestor"]))
    reason = Message.of("delivery-in-room", person="Mathis", room="bureau")
    assert localizer.format(reason, "fr-FR") == "Mathis est dans la pièce « bureau »"
    assert localizer.format(reason, "en") == "Mathis is in the bureau"
    assert localizer.format(Message.of("fallback-model-slow"), "fr") == "Hmm, je rame un peu, laisse-moi une seconde."


def test_every_message_of_nestor_exists_in_every_locale() -> None:
    folder = Path(__file__).resolve().parents[3] / "src" / "nestor" / "locales"
    ids = {
        locale.name: {
            line.split(" =")[0]
            for f in locale.glob("*.ftl")
            for line in f.read_text().splitlines()
            if line and not line.startswith(("#", " ")) and " =" in line
        }
        for locale in folder.iterdir()
        if locale.is_dir()
    }
    reference = ids["en"]
    assert all(found == reference for found in ids.values()), {k: reference ^ v for k, v in ids.items()}


def test_a_plugin_cannot_reword_a_message_of_the_core(tmp_path: Path) -> None:
    plugin = catalogues(tmp_path / "locales", {"en/plugin.ftl": "fallback-model-slow = Lag!\n"})
    with pytest.raises(ContractError, match="defined twice"):
        FluentLocalizer([*catalogue_dirs(["nestor"]), plugin])


def test_broken_catalogues_and_a_missing_default_are_refused(tmp_path: Path) -> None:
    broken = catalogues(tmp_path / "broken", {"en/x.ftl": "this is { not fluent\n"})
    with pytest.raises(ContractError, match="invalid Fluent syntax"):
        FluentLocalizer([broken])
    french_only = catalogues(tmp_path / "fr-only", {"fr/x.ftl": "x = y\n"})
    with pytest.raises(ContractError, match="default locale"):
        FluentLocalizer([french_only])


def test_catalogue_discovery_skips_packages_without_catalogues() -> None:
    assert len(catalogue_dirs(["nestor", "nestor", "json", "no_such_package_here"])) == 1
