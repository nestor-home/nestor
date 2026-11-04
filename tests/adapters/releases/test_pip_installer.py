"""Installing a release of Nestor into the environment it runs from: what is run, and the way back."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from nestor.adapters.releases import PipInstaller, pip_installer, probe
from nestor.adapters.releases.pip_installer import CHECK, in_container, installer_command
from nestor.core import ProviderError
from nestor.modules.system import Installation, InstallKind

UV = ("uv", "pip", "install", "--python", "python")


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
    await PipInstaller(Path("/home/nestor.yaml"), "0.7.0", UV, run=commands).install("0.8.0")
    assert requested(commands) == ["0.8.0", "check"]
    install, check = commands.ran
    assert install[: len(UV)] == list(UV) and install[-1].startswith("nestor-home[voice]==")
    assert check[1:] == ["-c", CHECK, "-c", "/home/nestor.yaml", "check"], "the interpreter runs the check"


@pytest.mark.parametrize("failing", ["==0.8.0", "check"], ids=["install fails", "configuration refused"])
async def test_a_failure_puts_the_running_version_back(failing: str) -> None:
    commands = Commands(failing)
    with pytest.raises(ProviderError, match="the running version stays"):
        await PipInstaller(Path("nestor.yaml"), "0.7.0", UV, run=commands).install("0.8.0")
    assert requested(commands)[-1] == "0.7.0"


async def test_a_running_version_that_cannot_be_put_back_is_said() -> None:
    with pytest.raises(ProviderError, match=r"0\.7\.0 could not be put back"):
        await PipInstaller(Path("nestor.yaml"), "0.7.0", UV, run=Commands("nestor-home")).install("0.8.0")


async def test_a_command_that_cannot_start_fails_instead_of_raising() -> None:
    assert await pip_installer._run(["/nonexistent/uv", "pip", "install"]) is False


async def test_a_stopped_install_kills_its_command() -> None:
    import asyncio

    started = asyncio.create_task(pip_installer._run(["sleep", "30"]))
    await asyncio.sleep(0.2)
    started.cancel()
    with pytest.raises(asyncio.CancelledError):
        await started


@pytest.mark.parametrize(("variable", "value"), [("container", "podman"), ("KUBERNETES_SERVICE_HOST", "10.0.0.1")])
def test_other_container_runtimes_are_containers_too(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    assert not in_container()
    monkeypatch.setenv(variable, value)
    assert in_container() and probe().kind is InstallKind.CONTAINER


def test_an_environment_without_uv_nor_pip_cannot_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pip_installer.shutil, "which", lambda _: None)
    monkeypatch.setattr(pip_installer, "UV_HOMES", (tmp_path / "uv",))
    monkeypatch.setattr(pip_installer.importlib.util, "find_spec", lambda _: None)
    assert installer_command() is None and PipInstaller.found(Path("nestor.yaml"), "0.7.0") is None
    (tmp_path / "uv").write_text("")
    assert installer_command() == (str(tmp_path / "uv"), "pip", "install", "--python", pip_installer.sys.executable)


def test_a_developers_editable_checkout_is_never_updated_from_the_admin() -> None:
    installation = probe()  # this checkout is installed editable
    assert installation == Installation(InstallKind.EDITABLE, ()) and not installation.installable


def test_a_container_is_updated_by_pulling_its_image(monkeypatch: pytest.MonkeyPatch) -> None:
    real = Path.exists
    monkeypatch.setattr(Path, "exists", lambda path: str(path) == "/.dockerenv" or real(path))
    installation = probe()
    assert installation.kind is InstallKind.CONTAINER and not installation.installable
    assert installation.commands == ("docker compose pull", "docker compose up -d")
