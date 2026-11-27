"""What one Home Assistant installation knows: its floors and areas, which entity sits in which area, what it exposes
to its assistant (`layout`), and the live states of the entities that matter. Pure data, fed by the WebSocket session.

Reading rules (nothing is inferred beyond what Home Assistant states):
- a person entity (`person.*`, or any tracker with the same states) is home when its state is
  `home`, unknown when `unknown`/`unavailable`, away otherwise (`not_home` or another zone);
- a room tracker's state is an area id, name or alias; anything else means the room is unknown;
- an occupancy sensor marks its area occupied when its state is `on`; its area is the entity's
  own or, failing that, its device's.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from nestor.adapters.home.home_assistant.client import SessionLost
from nestor.adapters.home.home_assistant.layout import Covers, Layout, Owner, Shown, lay_out
from nestor.core import PersonId
from nestor.modules.home import Device, Granularity, Presence, Resident, Room, Whereabouts

OCCUPANCY_CLASSES = frozenset({"occupancy", "presence", "motion"})
UNKNOWN_STATES = frozenset({"unknown", "unavailable"})


class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class State(_Payload):
    entity_id: str
    state: str
    attributes: dict[str, Any] = {}
    last_updated: datetime
    last_changed: datetime | None = None  # when the state itself last changed (attributes aside)


class Floor(_Payload):
    floor_id: str
    name: str


class Area(_Payload):
    area_id: str
    name: str
    aliases: list[str | None] = []
    floor_id: str | None = None


class RegisteredDevice(_Payload):
    id: str
    area_id: str | None = None
    name: str | None = None
    name_by_user: str | None = None


class Entity(_Payload):
    entity_id: str
    area_id: str | None = None
    device_id: str | None = None


class Entry(Entity):
    """An entity's whole registry entry (`config/entity_registry/get_entries`): its aliases and class too."""

    aliases: list[str | None] = []  # `None` stands for the entity's own name
    device_class: str | None = None
    original_device_class: str | None = None


class Exposure(_Payload):
    exposed_entities: dict[str, dict[str, bool]] = {}

    def to(self, assistant: str) -> list[str]:
        return [entity for entity, assistants in self.exposed_entities.items() if assistants.get(assistant)]


class _StateChangedData(_Payload):
    entity_id: str
    new_state: State | None = None


class StateChanged(_Payload):
    data: _StateChangedData


FLOORS = TypeAdapter(list[Floor])
AREAS = TypeAdapter(list[Area])
DEVICES = TypeAdapter(list[RegisteredDevice])
ENTITIES = TypeAdapter(list[Entity])
ENTRIES = TypeAdapter(dict[str, Entry | None])
EXPOSURE = TypeAdapter(Exposure)
STATES = TypeAdapter(list[State])
ASSISTANT = "conversation"  # Assist: what is exposed to it is what an assistant of the home may see


def parse[T](schema: TypeAdapter[T], payload: object, what: str) -> T:
    """A command's result, validated; a malformed one ends the session like a broken connection."""
    try:
        return schema.validate_python(payload)
    except ValidationError as error:
        raise SessionLost(f"unexpected {what}: {error.error_count()} invalid field(s)") from None


@dataclass(frozen=True, slots=True, kw_only=True)
class PresenceMapping:
    """Which Home Assistant entities speak for whom, from the adapter's settings."""

    people: Mapping[PersonId, str]  # person → person entity
    rooms: Mapping[PersonId, str] = field(default_factory=dict)  # person → room tracker entity
    occupancy_sensors: tuple[str, ...] | None = None  # `None`: discover them


@dataclass(frozen=True, slots=True, kw_only=True)
class Registries:
    """What the registries say of the installation, read at connection time and again when one of them changes.
    `entries`: the whole entries of the exposed entities, by entity id (`None`: an entity outside the registry)."""

    floors: tuple[Floor, ...] = ()
    areas: tuple[Area, ...] = ()
    devices: tuple[RegisteredDevice, ...] = ()
    entities: tuple[Entity, ...] = ()
    exposed: tuple[str, ...] = ()
    entries: Mapping[str, Entry | None] = field(default_factory=dict)


class Installation:
    """The registries and the live states, kept current by `apply` (a state) and `relist` (the registries).
    `covers`: whether acting on an entity needs the person's go-ahead (the household's sensitive targets)."""

    def __init__(
        self, mapping: PresenceMapping, registries: Registries, *, states: Iterable[State], covers: Covers
    ) -> None:
        self._mapping, self._covers = mapping, covers
        self._states = {state.entity_id: state for state in states}
        self.relist(registries)

    def relist(self, registries: Registries) -> None:
        """Takes the registries as they are now: rooms, what sits where and what is shown."""
        areas = registries.areas
        floors = {floor.floor_id: floor.name for floor in registries.floors}
        self._area_list = tuple(areas)
        self._floors = {area.area_id: floors.get(area.floor_id or "") for area in areas}
        self._areas = _AreaNames(areas)
        device_areas = {device.id: device.area_id for device in registries.devices}
        known_areas = {area.area_id for area in areas}
        self._entity_areas = {
            entity.entity_id: area
            for entity in registries.entities
            if (area := entity.area_id or device_areas.get(entity.device_id or "")) in known_areas
        }
        self._sensors = self._occupancy_sensors()
        self.granularity = self._granularity()
        self._registries = registries

    @property
    def unplaced_sensors(self) -> list[str]:
        """Configured occupancy sensors left out because Home Assistant gives them no area."""
        return [entity for entity in self._mapping.occupancy_sensors or () if entity not in self._sensors]

    def apply(self, event: StateChanged) -> None:
        """Takes a `state_changed` event into account, unless it is older than the state already known
        (events delivered while the initial snapshot was being read)."""
        entity_id, new_state = event.data.entity_id, event.data.new_state
        if new_state is None:
            self._states.pop(entity_id, None)
            return
        known = self._states.get(entity_id)
        if known is None or new_state.last_updated >= known.last_updated:
            self._states[entity_id] = new_state

    def presence(self) -> Presence:
        people = {person: self._whereabouts(person, entity) for person, entity in self._mapping.people.items()}
        return Presence(granularity=self.granularity, people=people, occupied_rooms=self._occupied())

    def _occupied(self) -> frozenset[str]:
        if not self.granularity.at_least(Granularity.OCCUPIED_ROOMS):
            return frozenset()
        return frozenset(area for entity, area in self._sensors.items() if self._state(entity) == "on")

    def room_of(self, label: str) -> str | None:
        """The area a label names: its id, name or alias."""
        return self._areas.resolve(label)

    def rooms(self) -> tuple[Room, ...]:
        """Every area, occupied or not when a sensor in it tells, with what it shows its assistant in it, in Home
        Assistant's order."""
        watched, occupied, layout = set(self._sensors.values()), self._occupied(), self._lay_out()
        return tuple(
            Room(
                id=area.area_id,
                name=area.name,
                occupied=area.area_id in occupied if area.area_id in watched else None,
                aliases=tuple(a for a in area.aliases if a),
                floor=self._floors.get(area.area_id),
                devices=layout.rooms.get(area.area_id, ()),
            )
            for area in self._area_list
        )

    def devices(self) -> tuple[Device, ...]:
        """What it shows its assistant outside any room."""
        return self._lay_out().elsewhere

    def _lay_out(self) -> Layout:
        """Laid out from the registries and the names the states carry now: an entity exposed before its first state
        arrives takes its name once it does."""
        registries = self._registries
        owners = {
            device.id: Owner(name=name, area_id=device.area_id)
            for device in registries.devices
            if (name := device.name_by_user or device.name)
        }
        shown = []
        for entity_id in registries.exposed:
            entry, state = registries.entries.get(entity_id), self._states.get(entity_id)
            attributes = state.attributes if state else {}
            shown.append(
                Shown(
                    entity_id=entity_id,
                    name=str(attributes.get("friendly_name") or entity_id.split(".", 1)[-1]),
                    aliases=tuple(a for a in entry.aliases if a) if entry else (),
                    device_id=entry.device_id if entry else None,
                    area_id=entry.area_id if entry else None,
                    device_class=(entry.device_class or entry.original_device_class if entry else None)
                    or attributes.get("device_class"),
                )
            )
        return lay_out(shown, owners, (area.area_id for area in registries.areas), self._covers)

    def residents(self) -> tuple[Resident, ...]:
        """The `person` entities, by their name in Home Assistant."""
        return tuple(
            Resident(
                entity=entity,
                name=str(state.attributes.get("friendly_name") or entity.removeprefix("person.")),
                home=None if state.state in UNKNOWN_STATES else state.state == "home",
            )
            for entity, state in sorted(self._states.items())
            if entity.startswith("person.")
        )

    def _whereabouts(self, person: PersonId, entity: str) -> Whereabouts:
        state = self._state(entity)
        home = None if state is None or state in UNKNOWN_STATES else state == "home"
        room, since = None, self._changed(entity)
        if home and self.granularity is Granularity.PERSON_ROOM and (tracker := self._mapping.rooms.get(person)):
            room = self._areas.resolve(self._state(tracker))
            moved = self._changed(tracker)
            since = max(since, moved) if since and moved and room else since
        return Whereabouts(home=home, room=room, since=since)

    def _changed(self, entity: str) -> datetime | None:
        state = self._states.get(entity)
        return None if state is None else state.last_changed or state.last_updated

    def _state(self, entity: str) -> str | None:
        state = self._states.get(entity)
        return None if state is None else state.state

    def _occupancy_sensors(self) -> dict[str, str]:
        """Sensor → area, for the sensors that have one."""
        if self._mapping.occupancy_sensors is not None:
            candidates: Iterable[str] = self._mapping.occupancy_sensors
        else:
            candidates = (
                entity
                for entity, state in self._states.items()
                if entity.startswith("binary_sensor.") and state.attributes.get("device_class") in OCCUPANCY_CLASSES
            )
        return {entity: self._entity_areas[entity] for entity in candidates if entity in self._entity_areas}

    def _granularity(self) -> Granularity:
        if any(tracker in self._states for tracker in self._mapping.rooms.values()):
            return Granularity.PERSON_ROOM
        if self._sensors:
            return Granularity.OCCUPIED_ROOMS
        return Granularity.HOME


class _AreaNames:
    """Area ids by id, name and alias, compared case-insensitively."""

    def __init__(self, areas: Iterable[Area]) -> None:
        self._ids: dict[str, str] = {}
        for area in areas:
            for label in (*(a for a in area.aliases if a), area.name, area.area_id):  # the id wins over a clash
                self._ids[label.casefold()] = area.area_id

    def resolve(self, label: str | None) -> str | None:
        return None if label is None else self._ids.get(label.strip().casefold())
