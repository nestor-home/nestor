"""Conversations as Assist counts them: turns close in time form one, a long silence opens another, and
every event of a turn carries the conversation and the turn it belongs to."""

from datetime import datetime, timedelta

import pytest

from nestor.core import ContractError, Event, PersonId, ProviderError, utc_now
from nestor.core.events import JSON
from nestor.modules.channels import Exchange
from nestor.modules.cognition import TaskStarted
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.model import Role, ToolCall
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
from nestor.modules.conversation import (
    AnswerCut,
    AssistantTurn,
    Conversations,
    FallbackReason,
    FallbackSpoken,
    UserTurn,
)
from nestor.modules.household import Household
from nestor.modules.initiative import WatchCreated
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories, MemoryCorrected, MemoryForgotten, MemoryRecorded
from nestor.modules.memory.assistant import MemoryTools
from nestor.testing.cognition import ScriptedExecutor
from nestor.testing.cognition.model import ScriptedModel
from nestor.testing.memory import InMemoryMemoryStore

from .conftest import MATHIS, TELEGRAM, VOICE, MakeAgent, message

TELEGRAM_42: dict[str, JSON] = {"channel": "telegram", "conversation": "42"}


class Clock:
    def __init__(self) -> None:
        self.now = utc_now()

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def conversations(journal: Journal, clock: Clock) -> Conversations:
    return Conversations(journal, ends_after_s=300, clock=clock)


async def conversation_of_each_turn(journal: Journal) -> list[str | None]:
    return [t.exchange.conversation_id if t.exchange else None for t in await journal.history(UserTurn)]


async def test_a_quick_follow_up_stays_in_the_conversation_and_sees_it(
    make_agent: MakeAgent, journal: Journal, clock: Clock, conversations: Conversations
) -> None:
    model = ScriptedModel("Il fait 21 degrés.", "Dans le salon.")
    agent = make_agent(model=model, conversations=conversations)
    await agent.respond(message("Quelle température ?")).collect()
    clock.now += timedelta(seconds=299)
    await agent.respond(message("Où ça ?")).collect()

    first, second = await conversation_of_each_turn(journal)
    assert first == second
    assert [m.content for m in model.requests[1].messages[1:]] == [
        "Quelle température ?",
        "Il fait 21 degrés.",
        "Où ça ?",
    ]


async def test_a_turn_after_the_silence_opens_a_new_conversation_without_the_earlier_turns(
    make_agent: MakeAgent, journal: Journal, clock: Clock, conversations: Conversations
) -> None:
    model = ScriptedModel("Il fait 21 degrés.", "Bonjour.")
    agent = make_agent(model=model, conversations=conversations)
    await agent.respond(message("Quelle température ?")).collect()
    clock.now += timedelta(seconds=301)
    await agent.respond(message("Bonjour")).collect()

    first, second = await conversation_of_each_turn(journal)
    assert first != second
    assert [m.content for m in model.requests[1].messages[1:]] == ["Bonjour"]


async def test_the_silence_counts_from_the_end_of_the_reply(
    make_agent: MakeAgent, journal: Journal, clock: Clock, conversations: Conversations
) -> None:
    class Slow(ScriptedModel):
        """Six minutes go by while it answers the first message."""

        async def stream(self, request):  # type: ignore[override]
            async for output in super().stream(request):
                yield output
            if len(self.requests) == 1:
                clock.now += timedelta(minutes=6)

    agent = make_agent(model=Slow("Voilà le résumé.", "De rien."), conversations=conversations)
    await agent.respond(message("Résume ce long document")).collect()
    clock.now += timedelta(seconds=60)
    await agent.respond(message("Merci")).collect()

    first, second = await conversation_of_each_turn(journal)
    assert first == second


async def test_sessions_hold_their_own_conversations(
    make_agent: MakeAgent, journal: Journal, conversations: Conversations
) -> None:
    agent = make_agent("Oui.", "Oui.", conversations=conversations)
    await agent.respond(message("Salut")).collect()
    await agent.respond(message("Salut", VOICE, "mic")).collect()

    telegram, voice = await conversation_of_each_turn(journal)
    assert telegram != voice


async def test_the_open_conversation_survives_a_restart(make_agent: MakeAgent, journal: Journal, clock: Clock) -> None:
    await make_agent("Noté.", conversations=Conversations(journal, clock=clock)).respond(message("Note ça")).collect()
    clock.now += timedelta(seconds=30)
    await make_agent("Oui.", conversations=Conversations(journal, clock=clock)).respond(message("Et ça")).collect()
    clock.now += timedelta(minutes=10)
    await make_agent("Oui.", conversations=Conversations(journal, clock=clock)).respond(message("Plus tard")).collect()

    first, second, third = await conversation_of_each_turn(journal)
    assert first == second != third


async def test_every_event_of_a_turn_carries_its_conversation_and_its_turn(
    make_agent: MakeAgent, journal: Journal
) -> None:
    memories = MemoryTools(Memories(journal, InMemoryMemoryStore()), Household([MATHIS]))
    async with TaskManager(journal, [ScriptedExecutor()]) as tasks:
        model = ScriptedModel(
            ToolCall("c1", "remember", {"text": "Mathis aime le thé", "about": "mathis"}),
            ToolCall("c2", "delegate_task", {"objective": "Comparer les théières"}),
            "C'est noté, et je compare les théières.",
        )
        agent = make_agent(model=model, tools=[*memories.tools(), *Delegation(tasks).tools()])
        await agent.respond(message("J'aime le thé, trouve-moi une théière")).collect()
        await agent.respond(message("Merci")).collect()

    [opening, thanks] = await journal.history(UserTurn)
    turn = opening.exchange
    assert turn is not None and thanks.exchange is not None
    assert thanks.exchange.conversation_id == turn.conversation_id and thanks.exchange.turn_id != turn.turn_id
    of_the_turn: list[Event] = [
        *await journal.history(ToolCalled, ToolCompleted),
        *await journal.history(MemoryRecorded),
        *await journal.history(TaskStarted),
    ]
    [answer, _] = await journal.history(AssistantTurn)
    assert len(of_the_turn) == 6
    assert {getattr(e, "exchange", None) for e in [*of_the_turn, answer]} == {turn}


async def test_a_fallback_and_a_cut_belong_to_the_turn_they_happened_in(
    make_agent: MakeAgent, journal: Journal
) -> None:
    down = ScriptedModel(fail=ProviderError("openrouter", "503", transient=True))
    await make_agent(model=down).respond(message("Allô ?")).collect()
    reply = make_agent("Une longue réponse.").respond(message("Dis", VOICE, "mic"))
    await reply.collect()
    await reply.interrupt("Une")

    failed, said = await journal.history(UserTurn)
    [fallback] = await journal.history(FallbackSpoken)
    [cut] = await journal.history(AnswerCut)
    assert fallback.reason is FallbackReason.MODEL_UNAVAILABLE and fallback.exchange == failed.exchange
    assert cut.exchange == said.exchange
    assert cut.answer == (await journal.history(AssistantTurn))[-1].id


async def test_a_composed_message_sees_only_the_open_conversation(
    make_agent: MakeAgent, journal: Journal, clock: Clock, conversations: Conversations
) -> None:
    await make_agent("Je lance l'analyse.", conversations=conversations).respond(message("Analyse")).collect()
    model = ScriptedModel("C'est fini.", "C'est fini.")
    agent = make_agent(model=model, conversations=conversations)
    await agent.compose(TELEGRAM, MATHIS, "Task finished.")
    clock.now += timedelta(minutes=6)
    await agent.compose(TELEGRAM, MATHIS, "Task finished.")

    soon, late = ([m.role for m in r.messages] for r in model.requests)
    assert soon == [Role.SYSTEM, Role.USER, Role.ASSISTANT, Role.SYSTEM]
    assert late == [Role.SYSTEM, Role.SYSTEM]
    assert len(await journal.history(UserTurn)) == 1, "composing is not a turn"


def test_a_conversation_lasts_some_time() -> None:
    with pytest.raises(ContractError):
        Conversations(Journal.__new__(Journal), ends_after_s=0)


# Records written before conversations were counted.


def test_turns_recorded_in_version_1_belong_to_no_conversation() -> None:
    at = utc_now().isoformat()
    envelope: dict[str, JSON] = {"id": "e1", "at": at, "source": "agent", "session": "telegram:42", "version": 1}
    said: dict[str, JSON] = {"address": TELEGRAM_42, "text": "Salut", "person": "mathis"}
    user = Event.from_record({**envelope, "type": "conversation.turn.user", "payload": said})
    cut = Event.from_record({**envelope, "type": "conversation.turn.cut", "payload": {"turn": "a1", "heard": "Bon"}})
    assert isinstance(user, UserTurn) and (user.text, user.person, user.exchange) == ("Salut", PersonId("mathis"), None)
    assert isinstance(cut, AnswerCut) and (cut.answer, cut.heard, cut.exchange) == ("a1", "Bon", None)


@pytest.mark.parametrize(
    ("cls", "payload"),
    [
        (AssistantTurn, {"address": TELEGRAM_42, "text": "Oui"}),
        (FallbackSpoken, {"address": TELEGRAM_42, "reason": "model_slow"}),
        (ToolCalled, {"address": TELEGRAM_42, "call_id": "c", "name": "t", "arguments": {}}),
        (ToolCompleted, {"call_id": "c", "name": "t", "output": "", "ok": True, "duration_s": 0.1}),
        (MemoryRecorded, {"memory_id": "m", "text": "Mathis aime le thé"}),
        (MemoryCorrected, {"memory_id": "m", "text": "Mathis aime le café"}),
        (MemoryForgotten, {"memory_id": "m"}),
        (TaskStarted, {"task_id": "t", "objective": "o", "executor": "hermes", "origin": TELEGRAM_42}),
        (WatchCreated, {"watch_id": "w", "what": "le colis", "keywords": [], "kinds": ["mail"], "once": True}),
    ],
    ids=lambda value: getattr(value, "event_type", ""),
)
def test_older_records_of_events_of_a_turn_still_read(cls: type[Event], payload: dict[str, object]) -> None:
    record = {"type": cls.event_type, "version": 1, "id": "e1", "at": utc_now().isoformat(), "source": "x",
              "session": None, "payload": payload}  # fmt: skip
    event = Event.from_record(record)  # ty: ignore[invalid-argument-type]
    assert isinstance(event, cls) and event.version == 2 and getattr(event, "exchange", "missing") is None
    assert Event.from_record(event.to_record()) == event


def test_an_exchange_is_written_as_plain_data() -> None:
    turn = UserTurn(
        source="agent",
        address=TELEGRAM,
        text="Salut",
        exchange=Exchange(conversation_id="c1", turn_id="t1"),
    )
    record = turn.to_record()
    payload = record["payload"]
    assert isinstance(payload, dict) and payload["exchange"] == {"conversation_id": "c1", "turn_id": "t1"}
    assert Event.from_record(record) == turn
