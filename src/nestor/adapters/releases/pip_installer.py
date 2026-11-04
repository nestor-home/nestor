"""How this Nestor is installed (`probe`), and installing a release of it from PyPI into the Python
environment it runs from (uv or pip).

    nestor-home[voice]==0.8.0   then   nestor -c <config> check   with that version

The extras installed now are kept. When the install or the check fails, the running version is
installed back. It never applies to an editable checkout (a developer's) or to a container, where the
image is what gets updated.
"""

import asyncio
import importlib.util
import json
import os
import re
import shutil
import sys
from collections.abc import Awaitable, Callable, Sequence
from importlib import metadata
from pathlib import Path

from nestor import DISTRIBUTION
from nestor.core import ProviderError
from nestor.modules.system import Installation, Installer, InstallKind

PROVIDER = "installer"
TIMEOUT_S = 600.0
_NAME = re.compile(r"^[A-Za-z0-9._-]+")  # a requirement's project name

type Run = Callable[[Sequence[str]], Awaitable[bool]]  # runs a command, says whether it succeeded


def in_container() -> bool:
    """Docker, Podman and Kubernetes each leave a mark; systemd-nspawn and Podman also set `container`."""
    marks = (Path("/.dockerenv"), Path("/run/.containerenv"))
    variables = ("container", "KUBERNETES_SERVICE_HOST")  # `container` is lowercase by convention
    return any(m.exists() for m in marks) or any(os.environ.get(v) for v in variables)


def probe() -> Installation:
    """How this Nestor is installed, and the commands that update it by hand: looked at once, at start."""
    if in_container():
        return Installation(InstallKind.CONTAINER, ("docker compose pull", "docker compose up -d"))
    direct = metadata.distribution(DISTRIBUTION).read_text("direct_url.json")
    if direct and json.loads(direct).get("dir_info", {}).get("editable"):
        return Installation(InstallKind.EDITABLE, ())
    if Path(sys.prefix).parent.name == "tools" and Path(sys.prefix).parent.parent.name == "uv":
        return Installation(InstallKind.UV_TOOL, (f"uv tool upgrade {DISTRIBUTION}",))
    return Installation(InstallKind.PIP, (f"pip install --upgrade '{_requirement()}'",))


# Where uv puts itself when it is not on PATH (a systemd unit's PATH rarely has ~/.local/bin).
UV_HOMES = (Path.home() / ".local" / "bin" / "uv", Path.home() / ".cargo" / "bin" / "uv")
# `nestor -c <config> check` with the interpreter Nestor runs on, wherever its console script is.
CHECK = "import sys; from nestor.cli import main; sys.exit(main(sys.argv[1:]))"


def installer_command() -> tuple[str, ...] | None:
    """What installs a package into this environment: uv (found on PATH or where it installs itself),
    else this interpreter's pip; `None` when neither is there (uv-made environments have no pip)."""
    uv = shutil.which("uv") or next((str(p) for p in UV_HOMES if p.is_file()), None)
    if uv:
        return (uv, "pip", "install", "--python", sys.executable)
    return (sys.executable, "-m", "pip", "install") if importlib.util.find_spec("pip") else None


class PipInstaller(Installer):
    def __init__(self, config: Path, running: str, command: tuple[str, ...], *, run: Run | None = None) -> None:
        self._config, self._running, self._command = config, running, command
        self._run = run or _run

    @classmethod
    def found(cls, config: Path, running: str) -> "PipInstaller | None":
        """The installer for this environment, `None` when nothing here can install a package."""
        command = installer_command()
        return cls(config, running, command) if command else None

    async def install(self, version: str) -> None:
        if await self._pip(version) and await self._checks():
            return
        back = await self._pip(self._running)
        stays = "the running version stays" if back else f"and {self._running} could not be put back"
        raise ProviderError(PROVIDER, f"{DISTRIBUTION} {version} did not install or refused the configuration, "
                            f"{stays}", transient=False)  # fmt: skip

    async def _pip(self, version: str) -> bool:
        return await self._run([*self._command, f"{_requirement()}=={version}"])

    async def _checks(self) -> bool:
        return await self._run([sys.executable, "-c", CHECK, "-c", str(self._config), "check"])


def _requirement() -> str:
    """nestor-home with the extras installed now (`nestor-home[voice]`)."""
    extras = _installed_extras()
    return f"{DISTRIBUTION}[{','.join(extras)}]" if extras else DISTRIBUTION


def _installed_extras() -> list[str]:
    """The extras of nestor-home whose every requirement is installed (`voice` when Pipecat is there)."""
    found: dict[str, bool] = {}
    for requirement in metadata.requires(DISTRIBUTION) or []:
        name, _, marker = requirement.partition(";")
        if "extra ==" not in marker:
            continue
        extra = marker.split("extra ==")[1].strip().strip("'\"")
        package = _NAME.match(name.strip())
        try:
            metadata.version(package.group() if package else name)
            installed = True
        except metadata.PackageNotFoundError:
            installed = False
        found[extra] = found.get(extra, True) and installed
    return sorted(e for e, installed in found.items() if installed)


async def _run(command: Sequence[str]) -> bool:
    """Whether `command` succeeded; one that cannot start fails. Stopped (timeout, or Nestor stopping),
    the process is killed rather than left changing the environment behind Nestor's back."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
    except OSError:
        return False
    try:
        return await asyncio.wait_for(process.wait(), TIMEOUT_S) == 0
    except (TimeoutError, asyncio.CancelledError) as stopped:
        process.kill()
        await asyncio.shield(process.wait())
        if isinstance(stopped, asyncio.CancelledError):
            raise
        return False
