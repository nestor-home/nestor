"""The map of Nestor built from what is installed and what the configuration plugs in: each plugin plugged (by its
configured names), installed but not configured, or missing what it imports; the ecosystem's packages beside them."""

from pathlib import Path

import pytest

from nestor.core import Component, ContractError, Health
from nestor.modules.system.selfmap import Capability, Card, Standing, describe
from nestor.runtime import Nestor
from nestor.runtime.plugins import Family, Plugin
from nestor.runtime.selfmap import satisfied, survey
from nestor.testing.system import DOUBLE

from .fakes import Fakes, NoSettings
from .test_app import config


def test_the_map_says_what_is_plugged_installed_or_missing(tmp_path: Path) -> None:
    registry = Fakes().registry()
    registry.register(Plugin(Family.TOOLS, "idle", NoSettings, lambda s, n, x: Component(), card=DOUBLE))
    absent = Plugin(
        Family.CHANNEL, "needy", NoSettings, lambda s, n, x: Component(), requires="nestor-absent[x]", card=DOUBLE
    )
    registry.register(absent)
    nestor = Nestor(config(tmp_path, []), registry)
    assert "about_nestor" in {s.name for s in nestor.toolbox.specs()}

    parts = {p.id: p for p in survey(nestor.registry, nestor.plugged).parts}
    plugged = parts["memory"]
    assert (plugged.standing, plugged.names) == (Standing.PLUGGED, ("memory",))
    assert (parts["remote"].standing, parts["remote"].names) == (Standing.PLUGGED, ("hermes",))
    assert (parts["idle"].standing, parts["idle"].install) == (Standing.INSTALLED, None)
    assert (parts["needy"].standing, parts["needy"].install) == (Standing.MISSING, "pip install 'nestor-absent[x]'")
    reachy = parts["nestor-reachy"]
    assert (reachy.capability, reachy.standing) == (Capability.SATELLITE, Standing.ELSEWHERE)

    nestor.channels[0].health = lambda: Health.DEGRADED
    assert describe(plugged).startswith("- memory (channel; plugged in as memory, degraded): A test double.")


def test_a_requirement_is_satisfied_when_its_package_and_its_extras_are_installed() -> None:
    assert satisfied("nestor-home")
    assert not satisfied("nestor-absent-package")
    assert not satisfied("nestor-absent-package[voice]")
    assert satisfied("nestor-home[no-such-extra]"), "an extra that adds nothing needs nothing"


@pytest.mark.parametrize(
    ("summary", "docs"),
    [("Two\nlines.", "tools"), (" ", "tools"), ("One line.", "https://nestorhome.dev/docs/tools/"), ("A.", "Tools")],
)
def test_a_card_is_one_line_and_names_a_page_of_the_docs(summary: str, docs: str) -> None:
    with pytest.raises(ContractError):
        Card(summary=summary, docs=docs)


def test_a_card_links_its_page_at_its_section() -> None:
    assert Card(summary="A.", docs="tools#search").url == "https://nestorhome.dev/docs/tools/#search"
    assert Card(summary="A.", docs="agent/memory").url == "https://nestorhome.dev/docs/agent/memory/"
    assert Card(summary="A.", docs="index").url == "https://nestorhome.dev/docs/"
