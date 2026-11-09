"""The home system as the admin shows it: whether it answers, how finely it places people, its rooms, who it knows
and how the household is tied to it, and the actions it offers the agent."""

from pydantic import BaseModel

from nestor.admin.api.v1.household.schemas import PresenceOut
from nestor.admin.api.v1.shared import People, PersonRef
from nestor.admin.presentation import Phrasebook
from nestor.core import Health, PersonId
from nestor.modules.cognition.tools import Risk, Tool
from nestor.modules.home import Granularity, Home, Presence
from nestor.modules.household import Household


class RoomOut(BaseModel):
    id: str
    name: str
    occupied: bool | None  # None: nothing in it tells
    people: list[PersonRef]  # who is in it, when the home places people in rooms


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
    name: str  # the configured instance
    brand: str | None
    health: Health
    health_detail: str | None
    connected: bool
    granularity: Granularity  # 1 home or away, 2 occupied rooms, 3 who is in which room
    rooms: list[RoomOut]
    residents: list[ResidentOut]
    people: list[TiedPersonOut]  # every household person, tied or not
    unplaced_sensors: list[str]  # occupancy sensors it ignores: no room in the home system
    tools: list[HomeToolOut]

    @classmethod
    def of(cls, home: Home, household: Household, words: Phrasebook) -> "HomeOut":
        overview, presence, people = home.overview(), home.presence.presence(), People(household)
        tied = {entity: person for person, entity in overview.people.items()}
        detail = home.health_detail()
        return cls(
            name=home.name,
            brand=home.brand,
            health=home.health(),
            health_detail=words.text(detail) if detail else None,
            connected=overview.connected,
            granularity=overview.granularity,
            rooms=[
                RoomOut(id=r.id, name=r.name, occupied=r.occupied, people=_in(r.id, presence, people))
                for r in overview.rooms
            ],
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
            tools=[HomeToolOut.of(t) for t in sorted(home.tools.tools(), key=lambda t: t.name)],
        )


def _in(room: str, presence: Presence, people: People) -> list[PersonRef]:
    return [ref for p, w in presence.people.items() if w.room == room and (ref := people.ref(PersonId(p)))]
