"""Sensitive actions and someone's own data, whoever asks: confirmed in place on one's account, in writing when
asked aloud on a satellite; someone's own data serves them only, and what a voice nobody recognised asked for is
written to them rather than said in the room."""

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nestor.core import PersonId
from nestor.modules.channels import Address, Exchange, InboundMessage, Medium, Sender
from nestor.modules.cognition.model import ModelRequest, ToolCall, ToolSpec
from nestor.modules.cognition.tools import Risk, SensitiveWhen, Tool, Toolbox, ToolContext
from nestor.modules.conversation import Agent, ModelChoice, Persona
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Identified, Speaker
from nestor.modules.initiative import Courier, MessageBook, MessageRequested
from nestor.modules.initiative.confirmations import ConfirmationAnswered, ConfirmationRequested, Confirmations
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.cognition.model import Reply
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryEventLog

CHAT = Address("telegram", "42")
SALON = Address("voice", "salon")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),), reach=CHAT)
MAMIE = Person(id=PersonId("mamie"), name="Mamie")  # no written channel


class Satellite(InMemoryChannel):
    media = frozenset({Medium.SPOKEN})
    room = "salon"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 4, 18, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class Home:
    def __init__(self, *replies: Reply, journal: Journal | None = None) -> None:
        """`journal`: another home's, to start again on what it wrote (a restart)."""
        self.journal = journal or Journal(MemoryEventLog())
        self.household = Household([MATHIS, MAMIE])
        self.opened: list[Mapping[str, object]] = []
        self.clock = Clock()

        async def garage(arguments: Mapping[str, object], context: ToolContext) -> str:
            self.opened.append({**arguments, "by": context.person, "at": str(context.address)})
            return "ouvert"

        async def mail(arguments: Mapping[str, object], context: ToolContext) -> str:
            return "Facture EDF : 82 €"

        garage_rule = SensitiveWhen("turn_on", {"device_class": ("garage",)})

        def device(arguments: Mapping[str, object]) -> Risk:
            return Risk.SENSITIVE if garage_rule.matches(arguments) else Risk.WRITE

        self.book = MessageBook(self.journal)
        self.confirmations = Confirmations(self.journal, self.household, self.book, clock=self.clock)
        self.toolbox = Toolbox(
            self.journal,
            [
                Tool(spec=ToolSpec("turn_on", "Turn a device on.", {"type": "object"}), run=garage, assess=device),
                Tool(
                    spec=ToolSpec("read_mail", "Read the latest mail.", {"type": "object"}), run=mail, owner=MATHIS.id
                ),
            ],
            [self.confirmations],
            in_writing=self.confirmations,
        )
        self.model = ScriptedModel(*replies)
        self.agent = Agent(
            models=ModelChoice.single(self.model),
            persona=Persona(name="Richie", character="Tu es Richie."),
            journal=self.journal,
            household=self.household,
            localizer=EchoLocalizer(),
            toolbox=self.toolbox,
            context=[self.confirmations],
        )
        self.voice, self.telegram = Satellite("voice"), InMemoryChannel("telegram")
        self.courier = Courier(self.journal, self.agent, [self.voice, self.telegram])
        self.confirmations.attach(self.courier, lambda call, context: self.toolbox.call(call, context, confirmed=True))

    async def __aenter__(self) -> "Home":
        for part in (self.courier, self.book, self.confirmations):
            await part.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        for part in (self.confirmations, self.book, self.courier):
            await part.__aexit__(None, None, None)

    async def call(
        self, name: str, arguments: Mapping[str, object], speaker: Speaker, at: Address = SALON, live: bool = True
    ) -> Any:
        """`live`: in a conversation someone takes part in, not a wake-up."""
        exchange = Exchange(conversation_id="c", turn_id="t") if live else None
        context = ToolContext(address=at, speaker=speaker, exchange=exchange)
        output = await self.toolbox.call(ToolCall("c", name, dict(arguments)), context)
        return json.loads(output) if output.startswith("{") else output

    async def written(self, count: int) -> list[str]:
        for _ in range(200):
            if len(self.telegram.sent) >= count:
                return [text for _, text in self.telegram.sent]
            await asyncio.sleep(0.01)
        raise AssertionError(f"expected {count} written messages, got {self.telegram.sent}")


GARAGE = {"name": "Porte", "device_class": "garage"}
VOICE_OF_MATHIS = Speaker(MATHIS.id, Identified.VOICE, 0.9)


async def test_a_sensitive_action_asked_aloud_is_confirmed_in_writing_then_runs_where_it_was_asked() -> None:
    def confirm(request: ModelRequest) -> ToolCall:
        found = request.messages[0].text.split("- [", 1)[1].split("]", 1)[0]  # the confirmation waiting
        return ToolCall("a1", "answer_confirmation", {"confirmation_id": found, "approve": True})

    home = Home("Mathis, tu confirmes l'ouverture du garage ?", confirm, "C'est ouvert.", "Le garage s'ouvre.")
    async with home:
        waiting = await home.call("turn_on", GARAGE, VOICE_OF_MATHIS)
        assert waiting["status"] == "waiting for a confirmation in writing" and home.opened == []
        assert await home.written(1) == ["Mathis, tu confirmes l'ouverture du garage ?"]
        answer = InboundMessage(address=CHAT, sender=Sender("42"), text="Oui vas-y")
        assert await home.agent.respond(answer).collect() == ("C'est ouvert.",)
        for _ in range(100):
            if home.voice.sent:
                break
            await asyncio.sleep(0.01)
    assert home.opened == [{**GARAGE, "by": MATHIS.id, "at": str(SALON)}], "as theirs, in the room it was asked"
    assert home.voice.sent == [(SALON, "Le garage s'ouvre.")]
    assert [e.approved for e in await home.journal.history(ConfirmationAnswered)] == [True]


async def test_a_light_is_not_confirmed_and_a_refusal_does_nothing() -> None:
    home = Home("Confirmes-tu ?")
    async with home:
        light = await home.call("turn_on", {"name": "Salon", "device_class": "light"}, Speaker.unknown())
        await home.call("turn_on", GARAGE, VOICE_OF_MATHIS)
        [request] = await home.journal.history(ConfirmationRequested)
        refuse = {"confirmation_id": request.confirmation_id, "approve": False}
        refused = await home.call("answer_confirmation", refuse, Speaker.account(MATHIS.id), at=CHAT)
        again = await home.call("answer_confirmation", refuse, Speaker.account(MATHIS.id), at=CHAT)
    assert light == "ouvert" and len(home.opened) == 1, "a light needs no confirmation, the garage does"
    assert refused == {"status": "refused: nothing was done"} and "nothing waits" in again["error"]


async def test_only_the_person_asked_answers_on_their_account_before_it_expires() -> None:
    home = Home("Confirmes-tu ?")
    async with home:
        await home.call("turn_on", GARAGE, VOICE_OF_MATHIS)
        [request] = await home.journal.history(ConfirmationRequested)
        yes = {"confirmation_id": request.confirmation_id, "approve": True}
        aloud = await home.call("answer_confirmation", yes, VOICE_OF_MATHIS)
        home.clock.now += timedelta(minutes=6)
        late = await home.call("answer_confirmation", yes, Speaker.account(MATHIS.id), at=CHAT)
        assert home.confirmations.waiting(MATHIS.id) == ()
    assert "on their account" in aloud["error"] and "expired" in late["error"] and home.opened == []


async def test_a_confirmation_still_waiting_when_nestor_stops_is_answered_after_it_restarts() -> None:
    home = Home("Confirmes-tu ?", "Confirmes-tu ?")
    async with home:
        await home.call("turn_on", GARAGE, VOICE_OF_MATHIS)
        await home.call("turn_on", {**GARAGE, "name": "Portail"}, VOICE_OF_MATHIS)
        waiting, refused = await home.journal.history(ConfirmationRequested)
        no = {"confirmation_id": refused.confirmation_id, "approve": False}
        await home.call("answer_confirmation", no, Speaker.account(MATHIS.id), at=CHAT)

    restarted = Home("Le garage s'ouvre.", journal=home.journal)
    async with restarted:
        assert [c.confirmation_id for c in restarted.confirmations.waiting(MATHIS.id)] == [waiting.confirmation_id]
        yes = {"confirmation_id": waiting.confirmation_id, "approve": True}
        done = await restarted.call("answer_confirmation", yes, Speaker.account(MATHIS.id), at=CHAT)
        again = await restarted.call(
            "answer_confirmation", {**no, "approve": True}, Speaker.account(MATHIS.id), at=CHAT
        )
    assert done["status"] == "done" and restarted.opened == [{**GARAGE, "by": MATHIS.id, "at": str(SALON)}]
    assert "nothing waits" in again["error"], "an answered confirmation stays answered"


async def test_on_ones_account_it_is_confirmed_in_the_conversation() -> None:
    home = Home()
    async with home:
        first = await home.call("turn_on", GARAGE, Speaker.account(MATHIS.id), at=CHAT)
        then = await home.call("turn_on", {**GARAGE, "confirmed": True}, Speaker.account(MATHIS.id), at=CHAT)
    assert "ask the person to confirm" in first["error"] and then == "ouvert"
    assert await home.journal.history(ConfirmationRequested) == []
    spec = next(s for s in home.toolbox.specs() if s.name == "turn_on")
    properties = spec.parameters["properties"]
    assert isinstance(properties, dict) and "confirmed" in properties


async def test_a_wake_up_cannot_confirm_for_the_person_and_asks_in_writing() -> None:
    home = Home("Confirmes-tu ?")
    async with home:
        confirmed = {**GARAGE, "confirmed": True}
        asked = await home.call("turn_on", confirmed, Speaker.account(MATHIS.id), at=CHAT, live=False)
    assert asked["status"] == "waiting for a confirmation in writing" and home.opened == []


async def test_someone_nobody_knows_or_without_a_written_channel_cannot_open_the_garage() -> None:
    home = Home()
    async with home:
        nobody = await home.call("turn_on", GARAGE, Speaker.unknown())
        mamie = await home.call("turn_on", GARAGE, Speaker(MAMIE.id, Identified.SAID))
    assert "ask who is asking" in nobody["error"] and "no written channel" in mamie["error"]
    assert home.opened == []


@pytest.mark.parametrize(
    ("speaker", "said"),
    [
        (Speaker.account(MATHIS.id), "Facture EDF : 82 €"),
        (VOICE_OF_MATHIS, "Facture EDF : 82 €"),
    ],
)
async def test_someones_mail_is_read_to_them_on_their_account_or_to_their_voice(speaker: Speaker, said: str) -> None:
    home = Home()
    async with home:
        assert await home.call("read_mail", {}, speaker) == said


async def test_someones_mail_asked_by_name_only_is_written_to_them_and_others_get_nothing() -> None:
    home = Home()
    async with home:
        by_name = await home.call("read_mail", {}, Speaker(MATHIS.id, Identified.SAID))
        nobody = await home.call("read_mail", {}, Speaker.unknown())
        mamie = await home.call("read_mail", {}, Speaker(MAMIE.id, Identified.VOICE))
        [written] = await home.journal.history(MessageRequested)
    assert by_name == {"status": "written to them, not said in the room", "to": "Mathis"}
    assert written.to == MATHIS.id and written.in_writing and "Facture EDF" in written.text
    assert "ask who is asking" in nobody["error"] and "belongs to mathis" in mamie["error"]
