"""How this Nestor is installed (`probe`), and installing a release of it from PyPI into the Python
environment it runs from (uv or pip).

    nestor-home[voice]==0.8.0   then   nestor -c <config> check   with that version

The extras installed now are kept. When the install or the check fails, the running version is
installed back. It never applies to an editable checkout (a developer's) or to a container, where the
image is what gets updated.
"""

import asyncio
import json
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


def probe() -> Installation:
    """How this Nestor is installed, and the commands that update it by hand: looked at once, at start."""
    if Path("/.dockerenv").exists():
        return Installation(InstallKind.CONTAINER, ("docker compose pull", "docker compose up -d"))
    direct = metadata.distribution(DISTRIBUTION).read_text("direct_url.json")
    if direct and json.loads(direct).get("dir_info", {}).get("editable"):
        return Installation(InstallKind.EDITABLE, ())
    if Path(sys.prefix).parent.name == "tools" and Path(sys.prefix).parent.parent.name == "uv":
        return Installation(InstallKind.UV_TOOL, (f"uv tool upgrade {DISTRIBUTION}",))
    return Installation(InstallKind.PIP, (f"pip install --upgrade '{_requirement()}'",))


class PipInstaller(Installer):
    def __init__(self, config: Path, running: str, *, run: Run | None = None) -> None:
        self._config, self._running = config, running
        self._run = run or _run

    async def install(self, version: str) -> None:
        if await self._pip(version) and await self._checks():
            return
        await self._pip(self._running)
        raise ProviderError(PROVIDER, f"{DISTRIBUTION} {version} did not install or refused the configuration",
                            transient=False)  # fmt: skip

    async def _pip(self, version: str) -> bool:
        wanted = f"{_requirement()}=={version}"
        uv = shutil.which("uv")
        command = [uv, "pip", "install", "--python", sys.executable, wanted] if uv else [
            sys.executable, "-m", "pip", "install", wanted]  # fmt: skip
        return await self._run(command)

    async def _checks(self) -> bool:
        nestor = Path(sys.executable).with_name("nestor")
        return await self._run([str(nestor), "-c", str(self._config), "check"])


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
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        return await asyncio.wait_for(process.wait(), TIMEOUT_S) == 0
    except TimeoutError:
        process.kill()
        await process.wait()
        return False
