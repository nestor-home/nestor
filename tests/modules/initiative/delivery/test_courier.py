"""The courier: presence-aware delivery, its logged reason, and the written follow-up."""

import asyncio

from nestor.core import PersonId, ProviderError, new_id
from nestor.core.i18n import Message
from nestor.modules.channels import Address, Exchange, InboundMessage, Medium, Sender
from nestor.modules.cognition.tools import Toolbox
from nestor.modules.conversation import (
    SILENT,
    About,
    Agent,
    AssistantTurn,
    Attachments,
    ModelChoice,
    Notification,
    NotificationTurn,
    Persona,
    Source,
    UserTurn,
)
from nestor.modules.home import Granularity
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Speaker
from nestor.modules.initiative import (
    Courier,
    Delivered,
    DeliveryConsidered,
    DeliveryFailed,
    DeliveryPolicy,
    DeliveryWithheld,
)
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.home import StaticPresence
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

TELEGRAM = Address("telegram", "42")
SALON = Address("voice", "salon")
PARCEL = About(Source.WATCH, "colis")
PRICE = About(Source.SCHEDULE, "prix")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),), reach=TELEGRAM)


class Satellite(InMemoryChannel):
    media = frozenset({Medium.SPOKEN})
    room = "salon"


def courier(
    presence: StaticPresence, *, follow_up_after_s: float = 0.02, model: ScriptedModel | None = None
) -> tuple[Courier, Journal, Satellite, InMemoryChannel]:
    journal = Journal(MemoryEventLog())
    agent = Agent(
        attachments=Attachments(MemoryBlobStore()),
        models=ModelChoice.single(model or ScriptedModel(*["Ton colis est arrivé."] * 4)),
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
        assert await sender.deliver(MATHIS, Notification("Le colis est arrivé.", PARCEL)) == SALON
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
            await sender.deliver(
                MATHIS, Notification("Mail de la banque.", About(Source.WATCH, "banque")), private=True
            )
            == TELEGRAM
        )
        assert sender.scheduled() == (), "already written: no follow-up"
    assert [a for a, _ in voice.sent] == [SALON] and [a for a, _ in telegram.sent] == [TELEGRAM]


async def test_a_reaction_cancels_the_follow_up() -> None:
    sender, journal, _, telegram = courier(StaticPresence().set("mathis", home=True))
    async with sender:
        await sender.deliver(MATHIS, Notification("Le colis est arrivé.", PARCEL))
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
        await sender.deliver(MATHIS, Notification("Le colis est arrivé.", PARCEL))
    assert telegram.sent == []


async def test_someone_away_gets_a_message_straight_away() -> None:
    sender, _, voice, telegram = courier(StaticPresence(Granularity.HOME).set("mathis", home=False))
    async with sender:
        assert await sender.deliver(MATHIS, Notification("Le colis est arrivé.", PARCEL)) == TELEGRAM
    assert voice.sent == [] and len(telegram.sent) == 1


async def test_a_pending_follow_up_is_listed_until_it_is_sent() -> None:
    sender, _, _, _ = courier(StaticPresence().set("mathis", home=True), follow_up_after_s=0.05)
    async with sender:
        await sender.deliver(MATHIS, Notification("Le colis est arrivé.", PARCEL))
        (pending,) = sender.scheduled()
        assert (pending.about, pending.person, pending.spoken, pending.written) == (
            PARCEL,
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
        assert await sender.deliver(MATHIS, Notification("Le colis est arrivé.", PARCEL)) == TELEGRAM
        await reply

    turns = await journal.history(UserTurn, NotificationTurn, AssistantTurn)
    assert [type(t).__name__ for t in turns] == ["UserTurn", "AssistantTurn", "NotificationTurn", "AssistantTurn"]
    assert [text for _, text in telegram.sent] == ["Ton colis est arrivé."]


async def test_a_check_that_found_nothing_is_withheld_and_says_so_in_the_journal() -> None:
    """Nothing reaches the person, nothing enters the conversation, and the journal shows that it ran."""
    sender, journal, voice, telegram = courier(StaticPresence(Granularity.HOME).set("mathis", home=False))
    sender.agent.models = ModelChoice.single(ScriptedModel(SILENT))
    async with sender:
        reminder = Notification("A wake-up is due now: check the price of the TV.", PRICE, quiet=True)
        assert await sender.deliver(MATHIS, reminder) == TELEGRAM

    assert voice.sent == telegram.sent == []
    assert [(w.about, w.address) for w in await journal.history(DeliveryWithheld)] == [(PRICE, TELEGRAM)]
    assert await journal.history(Delivered, DeliveryFailed, NotificationTurn, AssistantTurn) == []


async def test_a_notification_that_must_be_told_is_never_dropped_silently() -> None:
    """Saying nothing to a parcel that arrived is a failure: the next place is tried, then it is journaled."""
    sender, journal, voice, telegram = courier(
        StaticPresence().set("mathis", home=True), model=ScriptedModel(SILENT, "")
    )
    async with sender:
        assert await sender.deliver(MATHIS, Notification("Le colis est arrivé.", PARCEL)) is None

    assert voice.sent == telegram.sent == []
    assert await journal.history(DeliveryWithheld) == []
    (failed,) = await journal.history(DeliveryFailed)
    assert (failed.about, failed.tried) == (PARCEL, (SALON, TELEGRAM))


async def test_a_model_down_fails_the_delivery_instead_of_sending_an_excuse() -> None:
    sender, journal, _, telegram = courier(
        StaticPresence(Granularity.HOME).set("mathis", home=False),
        model=ScriptedModel(fail=ProviderError("model", "down", transient=True)),
    )
    async with sender:
        assert await sender.deliver(MATHIS, Notification("Le colis est arrivé.", PARCEL)) is None

    assert telegram.sent == []
    assert [f.about for f in await journal.history(DeliveryFailed)] == [PARCEL]
