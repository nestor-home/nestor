"""The courier: presence-aware delivery, its logged reason, and the written follow-up."""

import asyncio

from nestor.core import PersonId, new_id
from nestor.core.i18n import Message
from nestor.modules.channels import Address, Exchange, InboundMessage, Medium, Sender
from nestor.modules.cognition.tools import Toolbox
from nestor.modules.conversation import (
    Agent,
    AssistantTurn,
    ModelChoice,
    Notification,
    NotificationTurn,
    Persona,
    UserTurn,
)
from nestor.modules.home import Granularity
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Speaker
from nestor.modules.initiative import Courier, DeliveryConsidered, DeliveryPolicy
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.home import StaticPresence
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryEventLog

TELEGRAM = Address("telegram", "42")
SALON = Address("voice", "salon")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),), reach=TELEGRAM)


class Satellite(InMemoryChannel):
    media = frozenset({Medium.SPOKEN})
    room = "salon"


def courier(
    presence: StaticPresence, *, follow_up_after_s: float = 0.02
) -> tuple[Courier, Journal, Satellite, InMemoryChannel]:
    journal = Journal(MemoryEventLog())
    agent = Agent(
        models=ModelChoice.single(ScriptedModel(*["Ton colis est arrivé."] * 4)),
        persona=Persona(name="Richie", character="Tu es Richie."),
        journal=journal,
        household=Household([MATHIS]),
        localizer=EchoLocalizer(),
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


async def followed(sender: Courier) -> None:
    """Wait until every follow-up has run (sent, or given up on a reaction), whatever the machine's load."""
    for _ in range(500):
        if not sender.scheduled():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the follow-ups did not run")


async def test_an_unanswered_announcement_is_followed_by_a_message() -> None:
    sender, journal, voice, telegram = courier(StaticPresence().set("mathis", home=True))
    async with sender:
        assert await sender.deliver(MATHIS, Notification("Le colis est arrivé.", "watch colis")) == SALON
        await followed(sender)
    assert [a for a, _ in voice.sent] == [SALON]
    assert [a for a, _ in telegram.sent] == [TELEGRAM]
    considered = (await journal.history(DeliveryConsidered))[0]
    assert considered.reason == Message.of("delivery-home-main-satellite", person="Mathis", room="salon")


async def test_a_private_message_is_only_announced_aloud_and_written_at_once() -> None:
    """Others may be in the room: they hear that something came, not what it says."""
    sender, _, voice, telegram = courier(StaticPresence().set("mathis", home=True), follow_up_after_s=10)
    async with sender:
        assert (
            await sender.deliver(MATHIS, Notification("Mail de la banque.", "watch banque"), private=True) == TELEGRAM
        )
        assert sender.scheduled() == (), "already written: no follow-up"
    assert [a for a, _ in voice.sent] == [SALON] and [a for a, _ in telegram.sent] == [TELEGRAM]


async def test_a_reaction_cancels_the_follow_up() -> None:
    sender, journal, _, telegram = courier(StaticPresence().set("mathis", home=True))
    async with sender:
        await sender.deliver(MATHIS, Notification("Le colis est arrivé.", "watch colis"))
        await journal.publish(
            UserTurn(
                medium=Medium.WRITTEN,
                exchange=Exchange(conversation_id="c1", turn_id=new_id()),
                source="voice",
                session=SALON.session,
                address=SALON,
                text="Super, merci",
                speaker=Speaker.unknown(),
            )
        )
        await followed(sender)
    assert telegram.sent == []


async def test_closing_drops_pending_follow_ups() -> None:
    sender, _, _, telegram = courier(StaticPresence().set("mathis", home=True), follow_up_after_s=10)
    async with sender:
        await sender.deliver(MATHIS, Notification("Le colis est arrivé.", "watch colis"))
    assert telegram.sent == []


async def test_someone_away_gets_a_message_straight_away() -> None:
    sender, _, voice, telegram = courier(StaticPresence(Granularity.HOME).set("mathis", home=False))
    async with sender:
        assert await sender.deliver(MATHIS, Notification("Le colis est arrivé.", "watch colis")) == TELEGRAM
    assert voice.sent == [] and len(telegram.sent) == 1


async def test_a_pending_follow_up_is_listed_until_it_is_sent() -> None:
    sender, _, _, _ = courier(StaticPresence().set("mathis", home=True), follow_up_after_s=0.05)
    async with sender:
        await sender.deliver(MATHIS, Notification("Le colis est arrivé.", "watch colis"))
        (pending,) = sender.scheduled()
        assert (pending.about, pending.person, pending.spoken, pending.written) == (
            "watch colis",
            "mathis",
            SALON,
            TELEGRAM,
        )
        await followed(sender)


async def test_a_notification_waits_for_the_answer_being_written() -> None:
    """Never in the middle of a turn: the message that comes by itself follows the answer in progress."""
    sender, journal, _, telegram = courier(StaticPresence())
    sender.agent.models = ModelChoice.single(
        ScriptedModel("Je regarde ça tout de suite.", "Ton colis est arrivé.", word_delay_s=0.02)
    )
    asked = InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Tu as vu mes mails ?")
    async with sender:
        reply = asyncio.create_task(sender.agent.respond(asked).collect())
        await asyncio.sleep(0.01)  # the answer is being written
        assert await sender.deliver(MATHIS, Notification("Le colis est arrivé.", "watch colis")) == TELEGRAM
        await reply

    turns = await journal.history(UserTurn, NotificationTurn, AssistantTurn)
    assert [type(t).__name__ for t in turns] == ["UserTurn", "AssistantTurn", "NotificationTurn", "AssistantTurn"]
    assert [text for _, text in telegram.sent] == ["Ton colis est arrivé."]
