"""Installing a release of Nestor into the environment it runs from: what is run, and the way back."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from nestor.adapters.releases import PipInstaller
from nestor.core import ProviderError


class Commands:
    """Records each command; `failing` names a word that makes the command containing it fail."""

    def __init__(self, failing: str | None = None) -> None:
        self.failing = failing
        self.ran: list[list[str]] = []

    async def __call__(self, command: Sequence[str]) -> bool:
        self.ran.append(list(command))
        return self.failing is None or not any(self.failing in part for part in command)


def requested(commands: Commands) -> list[str]:
    """What each command installs, or `check` for the configuration check."""
    return ["check" if c[-1] == "check" else c[-1].split("==")[1] for c in commands.ran]


async def test_a_release_is_installed_with_the_extras_in_use_then_checked_with_the_configuration() -> None:
    commands = Commands()
    await PipInstaller(Path("/home/nestor.yaml"), "0.7.0", run=commands).install("0.8.0")
    assert requested(commands) == ["0.8.0", "check"]
    install, check = commands.ran
    assert install[-1].startswith("nestor-home[voice]==") and check[1:] == ["-c", "/home/nestor.yaml", "check"]


@pytest.mark.parametrize("failing", ["==0.8.0", "check"], ids=["install fails", "configuration refused"])
async def test_a_failure_puts_the_running_version_back(failing: str) -> None:
    commands = Commands(failing)
    with pytest.raises(ProviderError):
        await PipInstaller(Path("nestor.yaml"), "0.7.0", run=commands).install("0.8.0")
    assert requested(commands)[-1] == "0.7.0"


def test_a_developers_editable_checkout_is_never_updated_from_the_admin() -> None:
    assert PipInstaller.possible() is False  # this checkout is installed editable
