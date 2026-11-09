"""Messages passed on: to whom, where, once even across restarts, questions answered back, and who may
have the agent write to whom."""

import asyncio
import re

import pytest

from nestor.core import PersonId
from nestor.modules.channels import Address, InboundMessage, Medium, Sender
from nestor.modules.cognition.model import ModelRequest, ToolCall
from nestor.modules.cognition.tools import Toolbox, ToolContext, ToolFailed
from nestor.modules.conversation import Agent, ModelChoice, Persona
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Speaker
from nestor.modules.initiative import (
    Courier,
    DeliveryPolicy,
    MessageBook,
    MessageDelivered,
    MessageRequested,
    MessageTools,
    MessageUndelivered,
    Messenger,
)
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.cognition.model import Reply
from nestor.testing.home import StaticPresence
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryEventLog

MATHIS_CHAT, MATHILDE_CHAT = Address("telegram", "42"), Address("telegram", "7")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),), reach=MATHIS_CHAT)
MATHILDE = Person(
    id=PersonId("mathilde"), name="Mathilde", accounts=(Account.parse("telegram:7"),), reach=MATHILDE_CHAT
)
LUCIE = Person(id=PersonId("lucie"), name="Lucie", may_message=("mathis",))
JULES = Person(id=PersonId("jules"), name="Jules", may_message=())  # may have the agent write to no one else
ODILE = Person(id=PersonId("odile"), name="Odile")  # no account anywhere: unreachable


class Satellite(InMemoryChannel):
    media = frozenset({Medium.SPOKEN})
    room = "salon"


def question_id(request: ModelRequest) -> str:
    found = re.search(r"^- \[([^\]]+)\] Mathis asked Mathilde", request.messages[0].text, re.MULTILINE)
    assert found, "the open question is in the context of the person asked"
    return found[1]


class Home:
    def __init__(self, *replies: Reply, presence: StaticPresence | None = None) -> None:
        self.journal = Journal(MemoryEventLog())
        self.household = Household([MATHIS, MATHILDE, LUCIE, ODILE, JULES])
        self.model = ScriptedModel(*replies)
        self.build(presence or StaticPresence().set("mathilde", home=False).set("mathis", home=False))

    def build(self, presence: StaticPresence) -> None:
        self.book = MessageBook(self.journal)
        self.tools = MessageTools(self.book, self.household)
        self.agent = Agent(
            models=ModelChoice.single(self.model),
            persona=Persona(name="Richie", character="Tu es Richie."),
            journal=self.journal,
            household=self.household,
            localizer=EchoLocalizer(),
            toolbox=Toolbox(self.journal, providers=[self.tools]),
            context=[self.tools],
        )
        self.voice, self.telegram = Satellite("voice"), InMemoryChannel("telegram")
        self.courier = Courier(
            self.journal,
            self.agent,
            [self.voice, self.telegram],
            policy=DeliveryPolicy(main_room="salon"),
            presence=presence,
        )
        self.messenger = Messenger(self.book, self.household, self.courier)

    async def __aenter__(self) -> "Home":
        for part in (self.courier, self.book, self.messenger):
            await part.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        for part in (self.messenger, self.book, self.courier):
            await part.__aexit__(None, None, None)

    async def say(self, person: Person, text: str) -> tuple[str, ...]:
        address = person.reach or Address("voice", "salon")
        message = InboundMessage(address=address, sender=Sender(address.session.split(":")[-1]), text=text)
        return await self.agent.respond(message).collect()

    async def settled(self, count: int) -> None:
        """Wait until `count` messages were delivered or given up on."""
        for _ in range(200):
            if len(await self.journal.history(MessageDelivered, MessageUndelivered)) >= count:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("the messages were not delivered")

    async def send(self, by: Person | None, at: Address = MATHIS_CHAT, /, **arguments: object) -> object:
        (tool,) = self.tools.tools()
        context = ToolContext(address=at, speaker=Speaker.account(by.id) if by else Speaker.unknown())
        return await tool.run(arguments, context)


async def test_a_question_is_passed_on_and_its_answer_comes_back_to_whoever_asked() -> None:
    home = Home(
        ToolCall(
            "c1",
            "message_person",
            {"person": "mathilde", "text": "Tu veux manger quoi ce soir ?", "expects_reply": True},
        ),
        "Je lui demande.",
        "Mathis demande ce que tu veux manger ce soir, je lui transmets ta réponse.",  # composed for Mathilde
        lambda r: ToolCall(
            "c2", "message_person", {"person": "mathis", "text": "Des pâtes.", "answers": question_id(r)}
        ),
        "Je lui dis.",
        "Mathilde a répondu : des pâtes.",  # composed for Mathis
        "Rien en attente.",
    )
    async with home:
        assert await home.say(MATHIS, "Demande à Mathilde ce qu'elle veut manger ce soir") == ("Je lui demande.",)
        await home.settled(1)
        assert await home.say(MATHILDE, "Des pâtes !") == ("Je lui dis.",)
        await home.settled(2)
        await home.say(MATHILDE, "Autre chose ?")

    assert home.telegram.sent == [
        (MATHILDE_CHAT, "Mathis demande ce que tu veux manger ce soir, je lui transmets ta réponse."),
        (MATHIS_CHAT, "Mathilde a répondu : des pâtes."),
    ]
    composed = home.model.requests[2].messages[-1].content
    assert "Mathis asked you to pass this on to Mathilde: Tu veux manger quoi ce soir ?" in composed
    assert "It is a question" in composed
    answered = home.model.requests[5].messages[-1].content
    assert (
        "Mathilde answered the question you passed on for Mathis (Tu veux manger quoi ce soir ?): Des pâtes."
        in answered
    )
    assert "Questions waiting" not in home.model.requests[6].messages[0].text, "an answered question is closed"


async def test_whoever_asked_sees_the_question_until_it_is_answered() -> None:
    home = Home("C'est envoyé.", "Pas encore de réponse.")
    async with home:
        await home.send(MATHIS, person="mathilde", text="Tu rentres à quelle heure ?", expects_reply=True)
        await home.settled(1)
        await home.say(MATHIS, "Elle a répondu ?")
    assert "asked Mathilde: Tu rentres à quelle heure ? (no answer yet)" in home.model.requests[1].messages[0].text


async def test_a_message_asked_for_before_a_restart_is_delivered_once_after_it() -> None:
    home = Home(*["Ton colis est là."] * 3)
    await home.book.__aenter__()
    await home.send(MATHIS, person="mathilde", text="Ton colis est arrivé.")
    await home.book.__aexit__(None, None, None)  # stopped before the messenger could deliver it

    home.build(StaticPresence().set("mathilde", home=False))
    async with home:
        await home.settled(1)
    assert [a for a, _ in home.telegram.sent] == [MATHILDE_CHAT]
    home.build(StaticPresence().set("mathilde", home=False))
    async with home:
        await asyncio.sleep(0.05)
    assert home.telegram.sent == [], "the second start finds nothing left to deliver"
    assert len(await home.journal.history(MessageDelivered)) == 1


async def test_a_channel_asked_for_is_where_it_is_written_whoever_is_home() -> None:
    home = Home("Les nouvelles du jour : …", presence=StaticPresence().set("mathis", home=True))
    async with home:
        await home.send(MATHIS, person="mathis", text="Les nouvelles du jour.", channel="telegram")
        await home.settled(1)
    assert [a for a, _ in home.telegram.sent] == [MATHIS_CHAT] and home.voice.sent == []


async def test_someone_nobody_recognised_has_a_message_passed_on_signed_by_the_room() -> None:
    home = Home("Quelqu'un au salon te fait dire que le dîner est prêt.")
    async with home:
        await home.send(None, Address("voice", "salon"), person="mathilde", text="Le dîner est prêt.")
        await home.settled(1)
    assert home.telegram.sent == [(MATHILDE_CHAT, "Quelqu'un au salon te fait dire que le dîner est prêt.")]
    composed = home.model.requests[0].messages[-1].content
    assert "Someone at home, in salon, asked you to pass this on to Mathilde: Le dîner est prêt." in composed
    assert "Mathis" not in composed, "nobody is named who did not ask"


async def test_a_message_that_cannot_get_through_is_told_to_whoever_asked() -> None:
    home = Home("Je n'ai pas pu joindre Odile.")
    async with home:
        await home.send(MATHIS, person="odile", text="Pense au gâteau.")
        await home.settled(1)
    assert len(await home.journal.history(MessageUndelivered)) == 1
    assert home.telegram.sent == [(MATHIS_CHAT, "Je n'ai pas pu joindre Odile.")]
    assert "could not reach Odile" in home.model.requests[0].messages[-1].content


@pytest.mark.parametrize(
    ("person", "arguments", "error"),
    [
        (None, {"person": "mathis", "text": "Tu viens ?", "expects_reply": True}, "ask who is asking first"),
        (LUCIE, {"person": "mathilde", "text": "Coucou"}, "Lucie may not have you write to Mathilde"),
        (JULES, {"person": "mathis", "text": "Coucou"}, "Jules may not have you write to Mathis"),
        (MATHIS, {"person": "Gaston", "text": "Coucou"}, "no one called Gaston"),
        (MATHIS, {"person": "odile", "text": "Coucou", "channel": "telegram"}, "Odile has no account on telegram"),
        (MATHIS, {"person": "mathis", "text": "Oui", "answers": "nope"}, "no open question nope"),
    ],
)
async def test_a_message_that_may_not_be_sent_is_refused_and_nothing_is_asked(
    person: Person | None, arguments: dict[str, object], error: str
) -> None:
    home = Home("Lucie est rentrée.")
    async with home:
        with pytest.raises(ToolFailed, match=error):
            await home.send(person, **arguments)
        assert await home.send(LUCIE, person="Mathis", text="Je suis rentrée.") is not None, "a name works too"
        await home.settled(1)
    assert [m.to for m in await home.journal.history(MessageRequested)] == ["mathis"]


async def test_anyone_may_have_a_message_written_to_themselves_whoever_else_they_may_write_to() -> None:
    home = Home()
    async with home:
        assert await home.send(JULES, person="jules", text="Pense au pain.") is not None
    assert [m.to for m in await home.journal.history(MessageRequested)] == ["jules"]
