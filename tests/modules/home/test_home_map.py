"""The home's map as the agent gets it: rooms, what the home shows in each and Nestor's satellites, in the household
layer, never a state; who is home, only for someone of the household; bounded; and its devices named with `@`."""

from nestor.core import PersonId
from nestor.modules.channels import Address
from nestor.modules.conversation import Layer, MentionKind, Mentions, TurnContext
from nestor.modules.home import Device, Granularity, HomeContext, HomeMentions, Room
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Identified, Speaker
from nestor.testing.home import StaticHome, StaticPresence

MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),))
MATHILDE = Person(id=PersonId("mathilde"), name="Mathilde")
HOUSEHOLD = Household([MATHIS, MATHILDE])
TV = Device(name="TV LG C6", kinds=("media_player", "switch"), parts=("Écran TV LG C6",), aliases=("Télé",))
WASHER = Device(name="Lave Linge", kinds=("sensor", "switch"), parts=("Phase", "Time remaining"), sensitive=True)
ROOMS = [
    Room("salon", "Salon", aliases=("Séjour",), floor="Rez-de-chaussée", devices=(TV,)),
    Room("cuisine", "Cuisine", floor="Rez-de-chaussée", devices=(WASHER,)),
    Room("chambre", "Chambre", floor="Étage"),
]


def turn(speaker: Speaker) -> TurnContext:
    person = HOUSEHOLD.person(speaker.person) if speaker.person else None
    return TurnContext(person=person, speaker=speaker, address=Address("telegram", "42"), said="allume la télé")


def home(presence: StaticPresence | None = None, *, connected: bool = True) -> StaticHome:
    shared = (Device(name="Shopping list", kinds=("todo",)),)
    return StaticHome(presence, rooms=ROOMS, devices=shared, connected=connected)


async def test_the_map_names_each_room_what_is_in_it_and_nestors_satellites_without_a_state() -> None:
    presence = StaticPresence(Granularity.PERSON_ROOM).set("mathis", home=True, room="salon")
    presence.set("mathilde", home=False)
    context = HomeContext(home(presence), HOUSEHOLD, lambda: [("salon", "Reachy"), ("grenier", "Old speaker")])

    sections = await context.context(turn(Speaker.account(MATHIS.id)))

    assert sections[Layer.HOUSEHOLD].splitlines()[1:] == [
        "Rez-de-chaussée:",
        "- Salon (also Séjour): TV LG C6 (media_player, switch, also Télé): Écran TV LG C6; Nestor's satellite Reachy",
        "- Cuisine: Lave Linge (sensor, switch, sensitive): Phase, Time remaining",
        "Étage:",
        "- Chambre: nothing shown",
        "- No room: Shopping list (todo)",
    ], "a satellite in a room the home does not know is left out"
    assert sections[Layer.TURN] == "Who is home now:\n- Mathis: home, in Salon\n- Mathilde: away"


async def test_who_is_home_is_told_only_to_someone_of_the_household_and_nothing_when_the_home_is_gone() -> None:
    presence = StaticPresence().set("mathis", home=True)
    context = HomeContext(home(presence), HOUSEHOLD)

    stranger = await context.context(turn(Speaker.unknown()))
    named = await context.context(turn(Speaker(MATHIS.id, Identified.SAID)))
    gone = await HomeContext(home(presence, connected=False), HOUSEHOLD).context(turn(Speaker.account(MATHIS.id)))

    assert Layer.HOUSEHOLD in stranger and Layer.TURN not in stranger and Layer.TURN not in named
    assert gone == {}


async def test_a_map_too_long_drops_the_parts_then_says_what_it_left_out() -> None:
    async def shown(limit: int) -> str:
        sections = await HomeContext(home(), HOUSEHOLD, limit=limit).context(turn(Speaker.unknown()))
        return sections[Layer.HOUSEHOLD]

    full = await shown(10_000)
    brief = await shown(len(full) - 1)
    cut = await shown(len(brief) - 1)

    assert "Phase" in full and "Phase" not in brief and "Lave Linge (sensor, switch, sensitive)" in brief
    assert len(cut) <= len(brief) and cut.endswith("the home's tools list them)") and "Shopping list" not in cut


def test_devices_are_named_with_at_like_rooms() -> None:
    mentions = Mentions([HomeMentions(home())])

    named = mentions.named("@tv-lg-c6 dans le @salon, et @shopping-list", MATHIS)

    assert [(m.kind, m.label) for m in named] == [
        (MentionKind.DEVICE, "TV LG C6"),
        (MentionKind.ROOM, "Salon"),
        (MentionKind.DEVICE, "Shopping list"),
    ]
    assert "in Salon" in HomeMentions(home()).instruction(named[0])
