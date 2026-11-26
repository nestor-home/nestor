"""The map of Nestor itself, from what is installed and what the configuration plugged in: every plugin with its card,
and the packages of the ecosystem that run elsewhere (satellites)."""

import re
from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, distribution, requires

from nestor.core import Component
from nestor.modules.system.selfmap import Capability, Card, Need, Part, SelfMap, Standing
from nestor.runtime.plugins import Plugged, Registry

# Packages of the ecosystem that are not plugins of this server: each runs on a device of its own and pairs with it.
ECOSYSTEM = (
    Part(
        id="nestor-satellite (Python)",
        capability=Capability.SATELLITE,
        card=Card(
            summary="Makes any computer with a microphone and a speaker a satellite in a room (talk aloud or type), "
            "or writes one in Python.",
            docs="sdks/python",
            needs=(Need.HARDWARE,),
        ),
        standing=Standing.MISSING,
        install="uv tool install nestor-satellite, on that computer",
    ),
    Part(
        id="nestor-reachy",
        capability=Capability.SATELLITE,
        card=Card(
            summary="Makes a Reachy Mini robot a satellite: Nestor hears and speaks through it, its head and antennas "
            "following as it listens, thinks and speaks.",
            docs="satellites#ready-to-run",
            needs=(Need.HARDWARE,),
        ),
        standing=Standing.MISSING,
        install="uv tool install nestor-reachy, on the robot",
    ),
    Part(
        id="@nestor-home/satellite",
        capability=Capability.SATELLITE,
        card=Card(
            summary="A satellite in a browser tab or in Node (a tablet on the wall, a kiosk), written in TypeScript.",
            docs="sdks/typescript",
            needs=(Need.HARDWARE,),
        ),
        standing=Standing.MISSING,
        install="npm install @nestor-home/satellite",
    ),
    Part(
        id="nestor-satellite (Rust)",
        capability=Capability.SATELLITE,
        card=Card(
            summary="A satellite as a single binary for small boards (a Raspberry Pi with a microphone), or written "
            "in Rust.",
            docs="sdks/rust",
            needs=(Need.HARDWARE,),
        ),
        standing=Standing.MISSING,
        install="the nestor-satellite command from its installer, or cargo add nestor-satellite",
    ),
)

_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXTRAS = re.compile(r"\[([^\]]*)\]")


def survey(registry: Registry, plugged: Iterable[Plugged]) -> SelfMap:
    """Each installed plugin as plugged (its configured instances), installed or missing (what it imports is not
    installed), and the ecosystem's packages."""
    instances: dict[tuple[str, str], list[Plugged]] = {}
    for one in plugged:
        instances.setdefault((one.family, one.id), []).append(one)
    parts = []
    for plugin in registry.plugins():
        built = instances.get((plugin.family, plugin.id), [])
        if built:
            standing, install = Standing.PLUGGED, None
        elif plugin.requires is not None and not satisfied(plugin.requires):
            standing, install = Standing.MISSING, f"pip install '{plugin.requires}'"
        else:
            standing, install = Standing.INSTALLED, None
        parts.append(
            Part(
                id=plugin.id,
                capability=plugin.capability,
                card=plugin.card,
                standing=standing,
                install=install,
                names=tuple(p.name for p in built),
                built=tuple(p.component for p in built if isinstance(p.component, Component)),
            )
        )
    return SelfMap([*parts, *ECOSYSTEM])


def satisfied(requirement: str) -> bool:
    """Whether a pip requirement (`nestor-home[voice]`, `some-package`) is installed: the package, and every package
    its extras add."""
    name = _NAME.match(requirement)
    if name is None or not _installed(name.group(1)):
        return False
    extras = _EXTRAS.search(requirement)
    wanted = {e.strip() for e in extras.group(1).split(",")} if extras else set()
    for line in requires(name.group(1)) or ():
        spec, _, marker = line.partition(";")
        extra = re.search(r"extra\s*==\s*['\"]([^'\"]+)['\"]", marker)
        dependency = _NAME.match(spec)
        if extra is not None and extra.group(1) in wanted and dependency and not _installed(dependency.group(1)):
            return False
    return True


def _installed(package: str) -> bool:
    try:
        distribution(package)
    except PackageNotFoundError:
        return False
    return True
