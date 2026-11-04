"""Installs a release of Nestor from PyPI into the Python environment it runs from (uv or pip).

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

from nestor.core import ProviderError
from nestor.modules.system import Installer

PROVIDER = "installer"
DISTRIBUTION = "nestor-home"
TIMEOUT_S = 600.0
_NAME = re.compile(r"^[A-Za-z0-9._-]+")  # a requirement's project name

type Run = Callable[[Sequence[str]], Awaitable[bool]]  # runs a command, says whether it succeeded


class PipInstaller(Installer):
    def __init__(self, config: Path, running: str, *, run: Run | None = None) -> None:
        self._config, self._running = config, running
        self._run = run or _run

    @staticmethod
    def possible() -> bool:
        """Whether this environment can be updated from here: not a container, not an editable checkout."""
        if Path("/.dockerenv").exists():
            return False
        direct = metadata.distribution(DISTRIBUTION).read_text("direct_url.json")
        return not (direct and json.loads(direct).get("dir_info", {}).get("editable"))

    async def install(self, version: str) -> None:
        if await self._pip(version) and await self._checks():
            return
        await self._pip(self._running)
        raise ProviderError(PROVIDER, f"{DISTRIBUTION} {version} did not install or refused the configuration",
                            transient=False)  # fmt: skip

    async def _pip(self, version: str) -> bool:
        extras = _installed_extras()
        wanted = f"{DISTRIBUTION}{f'[{",".join(extras)}]' if extras else ''}=={version}"
        uv = shutil.which("uv")
        command = [uv, "pip", "install", "--python", sys.executable, wanted] if uv else [
            sys.executable, "-m", "pip", "install", wanted]  # fmt: skip
        return await self._run(command)

    async def _checks(self) -> bool:
        nestor = Path(sys.executable).with_name("nestor")
        return await self._run([str(nestor), "-c", str(self._config), "check"])


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
