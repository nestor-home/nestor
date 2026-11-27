"""What a Home Assistant installation shows its assistant, room by room: the entities exposed to Assist (Settings →
Voice assistants → Expose), as Assist's own static context lists them, grouped by device.

Reading rules, Home Assistant's own:
- an entity is shown when it is exposed to the `conversation` assistant;
- its name is its friendly name, its aliases its registry's; its room, its own area or its device's;
- the entities of one device make one device, named as the device is (`name_by_user`, else `name`), each other entity
  a part named by what follows the device's name in its own, or by its whole name; an entity alone, even of a device,
  keeps its own name, the one Assist's intents answer to.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from nestor.modules.home import Device

type Covers = Callable[[str, str | None, str], bool]  # domain, device class, name → acting on it is sensitive


@dataclass(frozen=True, slots=True, kw_only=True)
class Shown:
    """One exposed entity, as its registry and its state describe it."""

    entity_id: str
    name: str
    aliases: tuple[str, ...] = ()
    device_id: str | None = None
    area_id: str | None = None
    device_class: str | None = None

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]


@dataclass(frozen=True, slots=True, kw_only=True)
class Owner:
    """A device of the registry: its name and its area."""

    name: str
    area_id: str | None = None


@dataclass(frozen=True, slots=True)
class Layout:
    """The devices shown in each area, by area id, and those in none."""

    rooms: Mapping[str, tuple[Device, ...]]
    elsewhere: tuple[Device, ...]


def lay_out(shown: Iterable[Shown], owners: Mapping[str, Owner], areas: Iterable[str], covers: Covers) -> Layout:
    """The exposed entities as devices, in the `areas` that exist (a device in an unknown area is in none)."""
    groups: dict[str, list[Shown]] = defaultdict(list)
    for entity in shown:
        owned = entity.device_id
        groups[owned if owned is not None and owned in owners else entity.entity_id].append(entity)
    known = set(areas)
    rooms: dict[str, list[Device]] = defaultdict(list)
    elsewhere: list[Device] = []
    for key, entities in groups.items():
        owner = owners.get(key)
        area = next((e.area_id for e in entities if e.area_id), None) or (owner.area_id if owner else None)
        device = _device(entities, owner, covers)
        if area is not None and area in known:
            rooms[area].append(device)
        else:
            elsewhere.append(device)
    return Layout(
        rooms={area: _sorted(devices) for area, devices in rooms.items()},
        elsewhere=_sorted(elsewhere),
    )


def _device(entities: list[Shown], owner: Owner | None, covers: Covers) -> Device:
    kinds = tuple(dict.fromkeys(e.domain for e in entities))
    sensitive = any(covers(e.domain, e.device_class, e.name) for e in entities)
    if owner is None or len(entities) == 1:
        [entity] = entities
        return Device(name=entity.name, kinds=kinds, aliases=entity.aliases, sensitive=sensitive)
    aliases = tuple(dict.fromkeys(a for e in entities if e.name == owner.name for a in e.aliases))
    parts = tuple(dict.fromkeys(_part(e.name, owner.name) for e in entities if e.name != owner.name))
    return Device(name=owner.name, kinds=kinds, parts=tuple(sorted(parts)), aliases=aliases, sensitive=sensitive)


def _part(name: str, device: str) -> str:
    """What an entity's name says beyond its device's: `Lave Linge Phase` of `Lave Linge` is `Phase`."""
    prefix = f"{device} "
    return name[len(prefix) :] if name.casefold().startswith(prefix.casefold()) and len(name) > len(prefix) else name


def _sorted(devices: Iterable[Device]) -> tuple[Device, ...]:
    return tuple(sorted(devices, key=lambda d: d.name.casefold()))
