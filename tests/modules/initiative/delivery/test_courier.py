"""The courier: presence-aware delivery, its logged reason, and the written follow-up."""

import asyncio

from nestor.core import PersonId
from nestor.modules.channels import Address, Medium
from nestor.modules.cognition.tools import Toolbox
from nestor.modules.conversation import Agent, Persona, UserTurn
from nestor.modules.home import Granularity
from nestor.modules.household import Account, Household, Person
from nestor.modules.initiative import Courier, DeliveryConsidered, DeliveryPolicy
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.home import StaticPresence
from nestor.testing.journal import MemoryEventLog

TELEGRAM = Address("telegram", "42")
SALON = Address("voice", "salon")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),), reach=TELEGRAM)


class Satellite(InMemoryChannel):
    medium = Medium.SPOKEN
    room = "salon"


def courier(
    presence: StaticPresence, *, follow_up_after_s: float = 0.02
) -> tuple[Courier, Journal, Satellite, InMemoryChannel]:
    journal = Journal(MemoryEventLog())
    agent = Agent(
        model=ScriptedModel(*["Ton colis est arrivé."] * 4),
        persona=Persona(name="Richie", character="Tu es Richie."),
        journal=journal,
        household=Household([MATHIS]),
        toolbox=Toolbox(journal),
    )
    voice, telegram = Satellite("voice"), InMemoryChannel("telegram")
    return (
        Courier(
            journal,
            agent,
            [voice, telegram],
            policy=DeliveryPolicy(main_room="salon"),
            presence=presence,
            follow_up_after_s=follow_up_after_s,
        ),
        journal,
        voice,
        telegram,
    )


async def test_an_unanswered_announcement_is_followed_by_a_message() -> None:
    sender, journal, voice, telegram = courier(StaticPresence().set("mathis", home=True))
    async with sender:
        assert await sender.deliver(MATHIS, "Le colis est arrivé.", about="watch colis") == SALON
        await asyncio.sleep(0.05)
    assert [a for a, _ in voice.sent] == [SALON]
    assert [a for a, _ in telegram.sent] == [TELEGRAM]
    considered = (await journal.history(DeliveryConsidered))[0]
    assert considered.reason == "Mathis is home, room unknown: main satellite"


async def test_a_reaction_cancels_the_follow_up() -> None:
    sender, journal, _, telegram = courier(StaticPresence().set("mathis", home=True))
    async with sender:
        await sender.deliver(MATHIS, "Le colis est arrivé.", about="watch colis")
        await journal.publish(UserTurn(source="voice", session=SALON.session, address=SALON, text="Super, merci"))
        await asyncio.sleep(0.05)
    assert telegram.sent == []


async def test_closing_drops_pending_follow_ups() -> None:
    sender, _, _, telegram = courier(StaticPresence().set("mathis", home=True), follow_up_after_s=10)
    async with sender:
        await sender.deliver(MATHIS, "Le colis est arrivé.", about="watch colis")
    assert telegram.sent == []


async def test_someone_away_gets_a_message_straight_away() -> None:
    sender, _, voice, telegram = courier(StaticPresence(Granularity.HOME).set("mathis", home=False))
    async with sender:
        assert await sender.deliver(MATHIS, "Le colis est arrivé.", about="watch colis") == TELEGRAM
    assert voice.sent == [] and len(telegram.sent) == 1
