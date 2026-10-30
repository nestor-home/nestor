"""What one Home Assistant installation knows about presence: its areas, which entity sits in which
area, and the live states of the entities that matter. Pure data, fed by the WebSocket session.

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
from nestor.core import PersonId
from nestor.modules.home import Granularity, Presence, Whereabouts

OCCUPANCY_CLASSES = frozenset({"occupancy", "presence", "motion"})
UNKNOWN_STATES = frozenset({"unknown", "unavailable"})


class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class State(_Payload):
    entity_id: str
    state: str
    attributes: dict[str, Any] = {}
    last_updated: datetime


class Area(_Payload):
    area_id: str
    name: str
    aliases: list[str] = []


class Device(_Payload):
    id: str
    area_id: str | None = None


class Entity(_Payload):
    entity_id: str
    area_id: str | None = None
    device_id: str | None = None


class _StateChangedData(_Payload):
    entity_id: str
    new_state: State | None = None


class StateChanged(_Payload):
    data: _StateChangedData


AREAS = TypeAdapter(list[Area])
DEVICES = TypeAdapter(list[Device])
ENTITIES = TypeAdapter(list[Entity])
STATES = TypeAdapter(list[State])


def parse[T](schema: TypeAdapter[list[T]], payload: object, what: str) -> list[T]:
    """A command's list result, validated; a malformed one ends the session like a broken connection."""
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


class Installation:
    """The registries read at connection time and the live states, kept current by `apply`."""

    def __init__(
        self,
        mapping: PresenceMapping,
        *,
        areas: Iterable[Area],
        devices: Iterable[Device],
        entities: Iterable[Entity],
        states: Iterable[State],
    ) -> None:
        self._mapping = mapping
        self._states = {state.entity_id: state for state in states}
        areas = list(areas)
        self._areas = _AreaNames(areas)
        device_areas = {device.id: device.area_id for device in devices}
        known_areas = {area.area_id for area in areas}
        self._entity_areas = {
            entity.entity_id: area
            for entity in entities
            if (area := entity.area_id or device_areas.get(entity.device_id or "")) in known_areas
        }
        self._sensors = self._occupancy_sensors()
        self.granularity = self._granularity()

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
        occupied = frozenset()
        if self.granularity >= Granularity.OCCUPIED_ROOMS:
            occupied = frozenset(area for entity, area in self._sensors.items() if self._state(entity) == "on")
        return Presence(granularity=self.granularity, people=people, occupied_rooms=occupied)

    def _whereabouts(self, person: PersonId, entity: str) -> Whereabouts:
        state = self._state(entity)
        home = None if state is None or state in UNKNOWN_STATES else state == "home"
        room = None
        if home and self.granularity is Granularity.PERSON_ROOM and (tracker := self._mapping.rooms.get(person)):
            room = self._areas.resolve(self._state(tracker))
        return Whereabouts(home=home, room=room)

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
            for label in (*area.aliases, area.name, area.area_id):  # the id wins over a clashing name
                self._ids[label.casefold()] = area.area_id

    def resolve(self, label: str | None) -> str | None:
        return None if label is None else self._ids.get(label.strip().casefold())
