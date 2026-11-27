"""What a Home Assistant installation shows its assistant, room by room: the entities exposed to Assist (Settings →
Voice assistants → Expose), as Assist's own static context lists them, grouped by device.

Reading rules, Home Assistant's own:
- an entity is shown when it is exposed to the `conversation` assistant;
- its name is its friendly name, its aliases its registry's; its room, its own area or its device's;
- the entities of one device in one room make one device, named as the device is (`name_by_user`, else `name`), each
  other entity a part named by what follows the device's name in its own, or by its whole name; an entity alone, even
  of a device, keeps its own name, the one Assist's intents answer to; entities of a device set in different rooms
  (a dual relay) are a device in each;
- a device is sensitive when acting on one of its entities would be: what only reports (a sensor) acts on nothing.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from nestor.modules.home import Device

type Covers = Callable[[str, str | None, str], bool]  # domain, device class, name → acting on it is sensitive
REPORTS = frozenset({"sensor", "binary_sensor", "weather", "event"})  # domains that only report: nothing to act on


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
    groups: dict[tuple[str, str | None], list[Shown]] = defaultdict(list)
    for entity in shown:
        owned = entity.device_id if entity.device_id is not None and entity.device_id in owners else None
        area = entity.area_id or (owners[owned].area_id if owned else None)
        groups[owned or entity.entity_id, area].append(entity)
    known = set(areas)
    rooms: dict[str, list[Device]] = defaultdict(list)
    elsewhere: list[Device] = []
    for (key, area), entities in groups.items():
        device = _device(entities, owners.get(key), covers)
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
    sensitive = any(covers(e.domain, e.device_class, e.name) for e in entities if e.domain not in REPORTS)
    first = entities[0].entity_id  # stable while the device keeps it: its id in the map
    if owner is None or len(entities) == 1:
        [entity] = entities
        return Device(id=first, name=entity.name, kinds=kinds, aliases=entity.aliases, sensitive=sensitive)
    aliases = tuple(dict.fromkeys(a for e in entities if e.name == owner.name for a in e.aliases))
    parts = tuple(sorted(dict.fromkeys(_part(e.name, owner.name) for e in entities if e.name != owner.name)))
    return Device(id=first, name=owner.name, kinds=kinds, parts=parts, aliases=aliases, sensitive=sensitive)


def _part(name: str, device: str) -> str:
    """What an entity's name says beyond its device's: `Lave Linge Phase` of `Lave Linge` is `Phase`."""
    prefix = f"{device} "
    return name[len(prefix) :] if name.casefold().startswith(prefix.casefold()) and len(name) > len(prefix) else name


def _sorted(devices: Iterable[Device]) -> tuple[Device, ...]:
    return tuple(sorted(devices, key=lambda d: d.name.casefold()))
