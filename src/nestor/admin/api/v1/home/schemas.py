"""The home system as the admin shows it: whether it answers, how finely it places people, its rooms, who it knows
and how the household is tied to it, and the actions it offers the agent."""

from pydantic import BaseModel

from nestor.admin.api.v1.household.schemas import PresenceOut
from nestor.admin.api.v1.shared import People, PersonRef
from nestor.admin.api.v1.system.schemas import ComponentOut
from nestor.admin.presentation import Phrasebook
from nestor.modules.cognition.tools import Risk, Tool
from nestor.modules.home import Device, Granularity, Home
from nestor.runtime import Nestor, Plugged


class HomeDeviceOut(BaseModel):
    """Something the home shows its assistant, as the agent knows it (no state)."""

    name: str
    kinds: list[str]  # what it is, in the home system's words (`light`, `media_player`)
    parts: list[str]  # what else it shows (`Phase`, `Time remaining`)
    aliases: list[str]
    sensitive: bool  # acting on it waits for the person's go-ahead

    @classmethod
    def of(cls, device: Device) -> "HomeDeviceOut":
        return cls(
            name=device.name,
            kinds=list(device.kinds),
            parts=list(device.parts),
            aliases=list(device.aliases),
            sensitive=device.sensitive,
        )


class RoomOut(BaseModel):
    id: str
    name: str
    aliases: list[str]
    floor: str | None  # the floor it is on, when the home has floors
    occupied: bool | None  # None: nothing in it tells
    people: list[PersonRef]  # who is in it, when the home places people in rooms
    satellites: list[str]  # the paired satellites in it, by id
    devices: list[HomeDeviceOut]  # what the home shows its assistant in it


class ResidentOut(BaseModel):
    entity: str  # `person.alice`
    name: str
    home: bool | None
    person: PersonRef | None  # the household person tied to it


class TiedPersonOut(BaseModel):
    person: PersonRef
    entity: str | None  # the resident that stands for them; None: not tied, so their presence is unknown
    tracker: str | None  # the entity that tells their room
    presence: PresenceOut


class HomeToolOut(BaseModel):
    name: str
    description: str
    risk: Risk  # what the tool does by default
    confirmed_when: bool  # some of its calls need the person's go-ahead, by what they act on (a lock, a door)

    @classmethod
    def of(cls, tool: Tool) -> "HomeToolOut":
        return cls(
            name=tool.name,
            description=tool.spec.description,
            risk=tool.risk,
            confirmed_when=tool.assess is not None,
        )


class HomeOut(BaseModel):
    component: ComponentOut  # as the system page shows it: its plugin, brand, health
    connected: bool
    granularity: Granularity  # what it tells: who is home, which rooms are occupied, who is in which room
    rooms: list[RoomOut]
    devices: list[HomeDeviceOut]  # what the home shows its assistant outside any room
    residents: list[ResidentOut]
    people: list[TiedPersonOut]  # every household person, tied or not
    unplaced_sensors: list[str]  # occupancy sensors it ignores: no room in the home system
    tools: list[HomeToolOut] | None  # `None`: the home offers no actions (presence only)

    @classmethod
    def of(cls, plugged: Plugged, home: Home, nestor: Nestor, words: Phrasebook) -> "HomeOut":
        household, satellites = nestor.household, nestor.pairing.satellites()
        overview, presence, people = home.overview(), home.presence.presence(), People(household)
        tied = {entity: person for person, entity in overview.people.items()}
        return cls(
            component=ComponentOut.of(plugged, nestor, words),
            connected=overview.connected,
            granularity=overview.granularity,
            rooms=[
                RoomOut(
                    id=r.id,
                    name=r.name,
                    aliases=list(r.aliases),
                    floor=r.floor,
                    occupied=r.occupied,
                    people=[ref for p in presence.people_in(r.id) if (ref := people.ref(p))],
                    satellites=[s.id for s in satellites if home.room_of(s.room) == r.id],
                    devices=[HomeDeviceOut.of(d) for d in r.devices],
                )
                for r in overview.rooms
            ],
            devices=[HomeDeviceOut.of(d) for d in overview.devices],
            residents=[
                ResidentOut(entity=r.entity, name=r.name, home=r.home, person=people.ref(tied.get(r.entity)))
                for r in overview.residents
            ],
            people=[
                TiedPersonOut(
                    person=PersonRef(id=p.id, name=p.name),
                    entity=overview.people.get(p.id),
                    tracker=overview.trackers.get(p.id),
                    presence=PresenceOut.of(presence.of(p.id)),
                )
                for p in household.people
            ],
            unplaced_sensors=list(overview.unplaced_sensors),
            tools=None
            if home.tools is None
            else [HomeToolOut.of(t) for t in sorted(home.tools.tools(), key=lambda t: t.name)],
        )
