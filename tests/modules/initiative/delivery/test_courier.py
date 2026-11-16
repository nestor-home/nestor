"""The courier: presence-aware delivery, its logged reason, and the written follow-up."""

import asyncio

from nestor.core import PersonId, ProviderError, new_id
from nestor.core.i18n import Message
from nestor.modules.channels import Address, Attachment, AttachmentKind, Exchange, InboundMessage, Medium, Sender
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
from nestor.modules.initiative.delivery.courier import FILES_NOTICE
from nestor.modules.journal import FileRef, Journal
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


class Messaging(InMemoryChannel):
    sends = frozenset(AttachmentKind)
    refuses = False  # nothing written gets through

    async def send(self, to: Address, text: str, medium: Medium, attachments: tuple[Attachment, ...]) -> None:
        if self.refuses:
            raise ProviderError(self.channel_id, "unreachable", transient=True)
        await super().send(to, text, medium, attachments)


def courier(
    presence: StaticPresence,
    *,
    follow_up_after_s: float = 0.02,
    model: ScriptedModel | None = None,
    blobs: MemoryBlobStore | None = None,
) -> tuple[Courier, Journal, Satellite, InMemoryChannel]:
    journal = Journal(MemoryEventLog())
    agent = Agent(
        attachments=Attachments(blobs or MemoryBlobStore()),
        models=ModelChoice.single(model or ScriptedModel(*["Ton colis est arrivé."] * 4)),
        persona=Persona(name="Richie", character="Tu es Richie."),
        journal=journal,
        household=Household([MATHIS]),
        localizer=EchoLocalizer(),
        toolbox=Toolbox(journal),
    )
    voice, telegram = Satellite("voice"), Messaging("telegram")
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


async def test_a_result_with_a_file_is_written_with_it_and_the_room_hears_what_it_brings() -> None:
    """A voice cannot carry a document: it would be lost if the result were only said."""
    blobs = MemoryBlobStore()
    devis = await blobs.put(b"%PDF devis", "application/pdf")
    model = ScriptedModel("Voici le devis corrigé.", "Le devis corrigé est arrivé, je te l'ai écrit.")
    sender, _, voice, telegram = courier(StaticPresence().set("mathis", home=True), model=model, blobs=blobs)
    async with sender:
        done = Notification(
            "Le devis est corrigé.", About(Source.TASK, "t1", "completed"), files=(FileRef(devis, "devis.pdf"),)
        )
        assert await sender.deliver(MATHIS, done) == TELEGRAM
    assert [a for a, _ in voice.sent] == [SALON] and [a for a, _ in telegram.sent] == [TELEGRAM]
    assert [(f.name, f.data) for f in telegram.files[0]] == [("devis.pdf", b"%PDF devis")]
    assert FILES_NOTICE in str(model.requests[1].messages[-1].content), "aloud, it says the files were written"


async def test_a_result_with_a_file_is_said_aloud_when_it_cannot_be_written() -> None:
    """What they asked for reaches them all the same, without what a voice cannot carry."""
    blobs = MemoryBlobStore()
    devis = await blobs.put(b"%PDF devis", "application/pdf")
    model = ScriptedModel("Voici le devis corrigé.", "Le devis corrigé est prêt.")
    sender, _, voice, telegram = courier(StaticPresence().set("mathis", home=True), model=model, blobs=blobs)
    assert isinstance(telegram, Messaging)
    telegram.refuses = True
    async with sender:
        done = Notification(
            "Le devis est corrigé.", About(Source.TASK, "t1", "completed"), files=(FileRef(devis, "devis.pdf"),)
        )
        assert await sender.deliver(MATHIS, done) == SALON
    assert voice.sent == [(SALON, "Le devis corrigé est prêt.")] and voice.files == [()]
    assert "devis.pdf" not in str(model.requests[-1].messages[0].content), "it is not told the file goes with it"


async def test_a_private_message_that_cannot_be_written_is_never_said_aloud_in_full() -> None:
    """Others may hear: it waits for a place to write, tried again later."""
    sender, journal, voice, telegram = courier(StaticPresence().set("mathis", home=True), follow_up_after_s=10)
    assert isinstance(telegram, Messaging)
    telegram.refuses = True
    async with sender:
        bank = Notification("Mail de la banque.", About(Source.WATCH, "banque"))
        assert await sender.deliver(MATHIS, bank, private=True) is None
    assert voice.sent == [] and len(await journal.history(DeliveryFailed)) == 1


async def test_a_private_message_with_nothing_to_tell_is_neither_written_nor_announced() -> None:
    """Its content decides, not the announcement: the room hears nothing either."""
    model = ScriptedModel(f"{SILENT} une publicité", "Mail de la banque.")
    sender, journal, voice, telegram = courier(StaticPresence().set("mathis", home=True), model=model)
    async with sender:
        bank = Notification("Mail de la banque.", About(Source.WATCH, "banque"))
        assert await sender.deliver(MATHIS, bank, private=True) == TELEGRAM
    assert voice.sent == telegram.sent == [] and len(model.requests) == 1
    assert [w.reason for w in await journal.history(DeliveryWithheld)] == ["une publicité"]


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


async def test_a_check_that_found_nothing_is_withheld_with_its_reason_in_the_journal() -> None:
    """Nothing reaches the person, nothing enters the conversation, and the journal shows that it ran, and why."""
    sender, journal, voice, telegram = courier(StaticPresence(Granularity.HOME).set("mathis", home=False))
    sender.agent.models = ModelChoice.single(ScriptedModel(f"{SILENT} toujours 1 799 €, au-dessus du seuil"))
    async with sender:
        reminder = Notification("A wake-up is due now: check the price of the TV.", PRICE)
        assert await sender.deliver(MATHIS, reminder) == TELEGRAM

    assert voice.sent == telegram.sent == []
    (withheld,) = await journal.history(DeliveryWithheld)
    assert (withheld.about, withheld.address) == (PRICE, TELEGRAM)
    assert withheld.reason == "toujours 1 799 €, au-dessus du seuil"
    assert await journal.history(Delivered, DeliveryFailed, NotificationTurn, AssistantTurn) == []


async def test_a_notification_that_must_be_told_is_never_dropped_silently() -> None:
    """Saying nothing to a message someone asked to pass on is a failure: the next place is tried, then it is
    journaled."""
    sender, journal, voice, telegram = courier(
        StaticPresence().set("mathis", home=True), model=ScriptedModel(SILENT, "")
    )
    async with sender:
        message = Notification("Léa asks you to call her back.", PARCEL, must_tell=True)
        assert await sender.deliver(MATHIS, message) is None

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
