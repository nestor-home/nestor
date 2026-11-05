"""Conversations as Assist counts them: turns close in time form one, a long silence opens another, and
every event of a turn carries the conversation and the turn it belongs to."""

from datetime import datetime, timedelta

import pytest

from nestor.core import Event, ProviderError, utc_now
from nestor.core.events import JSON
from nestor.modules.channels import Address, Exchange, Medium
from nestor.modules.cognition import TaskStarted
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.model import Role, ToolCall
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
from nestor.modules.conversation import (
    Agent,
    AnswerCut,
    AssistantTurn,
    ChannelProfile,
    FallbackReason,
    FallbackSpoken,
    Notification,
    UserTurn,
)
from nestor.modules.household import Household
from nestor.modules.identity import Speaker
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories, MemoryRecorded
from nestor.modules.memory.assistant import MemoryTools
from nestor.modules.memory.episodes import Episodes
from nestor.testing.cognition import ScriptedExecutor
from nestor.testing.cognition.model import ScriptedModel
from nestor.testing.memory import InMemoryEpisodeStore, InMemoryMemoryStore

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


async def conversation_of_each_turn(journal: Journal) -> list[str | None]:
    return [t.exchange.conversation_id if t.exchange else None for t in await journal.history(UserTurn)]


WHOLE_EXCHANGE = ["Quelle température ?", "Il fait 21 degrés.", "Et dehors ?"]


async def two_turns(agent: Agent, address: Address, sender: str, pause: timedelta, clock: Clock) -> None:
    await agent.respond(message("Quelle température ?", address, sender)).collect()
    clock.now += pause
    await agent.respond(message("Et dehors ?", address, sender)).collect()


async def test_a_spoken_follow_up_within_five_minutes_stays_in_the_conversation(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    model = ScriptedModel("Il fait 21 degrés.", "Douze.")
    await two_turns(make_agent(model=model, clock=clock), VOICE, "mic", timedelta(minutes=4), clock)

    first, second = await conversation_of_each_turn(journal)
    assert first == second
    assert [m.content for m in model.requests[1].messages[1:]] == [
        "Quelle température ?",
        "Il fait 21 degrés.",
        "Et dehors ?",
    ]


async def test_a_spoken_turn_after_six_minutes_opens_a_new_conversation_without_the_earlier_turns(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    model = ScriptedModel("Il fait 21 degrés.", "Douze.")
    await two_turns(make_agent(model=model, clock=clock), VOICE, "mic", timedelta(minutes=6), clock)

    first, second = await conversation_of_each_turn(journal)
    assert first != second
    assert [m.content for m in model.requests[1].messages[1:]] == ["Et dehors ?"]


async def test_a_written_reply_two_hours_later_stays_in_the_conversation_and_sees_it(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    model = ScriptedModel("Il fait 21 degrés.", "Douze.")
    await two_turns(make_agent(model=model, clock=clock), TELEGRAM, "42", timedelta(hours=2), clock)

    first, second = await conversation_of_each_turn(journal)
    assert first == second
    assert [m.content for m in model.requests[1].messages[1:]] == [
        "Quelle température ?",
        "Il fait 21 degrés.",
        "Et dehors ?",
    ]


async def test_a_written_reply_the_next_morning_opens_a_new_conversation(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    await two_turns(make_agent("Oui.", "Oui.", clock=clock), TELEGRAM, "42", timedelta(hours=9), clock)

    first, second = await conversation_of_each_turn(journal)
    assert first != second


async def test_a_channel_without_a_profile_gets_the_default_of_writing(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    web = Address("web", "x")
    agent = make_agent("Oui.", "Oui.", "Oui.", clock=clock)
    await two_turns(agent, web, "inconnu", timedelta(hours=3), clock)
    clock.now += timedelta(hours=5)
    await agent.respond(message("Encore", web, "inconnu")).collect()

    first, second, third = await conversation_of_each_turn(journal)
    assert first == second != third


async def test_a_channel_may_set_its_own_window(make_agent: MakeAgent, journal: Journal, clock: Clock) -> None:
    channels = {"telegram": ChannelProfile(conversation_ends_after_s=60)}
    await two_turns(
        make_agent("Oui.", "Oui.", clock=clock, channels=channels), TELEGRAM, "42", timedelta(minutes=2), clock
    )

    first, second = await conversation_of_each_turn(journal)
    assert first != second


async def test_the_silence_counts_from_the_end_of_the_reply(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    class Slow(ScriptedModel):
        """Six minutes go by while it answers the first message."""

        async def stream(self, request):  # type: ignore[override]
            async for output in super().stream(request):
                yield output
            if len(self.requests) == 1:
                clock.now += timedelta(minutes=6)

    agent = make_agent(model=Slow("Voilà le résumé.", "De rien."), clock=clock)
    await two_turns(agent, VOICE, "mic", timedelta(minutes=1), clock)

    first, second = await conversation_of_each_turn(journal)
    assert first == second


async def test_a_typed_follow_up_to_a_spoken_question_stays_in_its_conversation(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    agent = make_agent("Il fait 21 degrés.", "Dehors, 12.", clock=clock)
    await agent.respond(message("Quelle température ?", VOICE, "mic")).collect()
    clock.now += timedelta(minutes=30)
    await agent.respond(message("Et dehors ?", VOICE, "mic", Medium.WRITTEN)).collect()

    first, second = await conversation_of_each_turn(journal)
    assert first == second, "a typed turn waits as long as writing allows"


def test_a_conversation_is_over_once_no_medium_could_follow_it_up(make_agent: MakeAgent) -> None:
    channels = {"telegram": ChannelProfile(conversation_ends_after_s=60)}
    conversations = make_agent(channels=channels).conversations
    assert conversations.over_after_s(VOICE) == 4 * 3600, "a spoken question may still get a typed answer"
    assert conversations.over_after_s(TELEGRAM) == 60


async def test_a_spoken_turn_after_a_long_silence_opens_a_new_conversation(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    agent = make_agent("Noté.", "Oui.", clock=clock)
    await agent.respond(message("Note le pain", VOICE, "mic", Medium.WRITTEN)).collect()
    clock.now += timedelta(minutes=30)
    await agent.respond(message("Tu es là ?", VOICE, "mic")).collect()

    first, second = await conversation_of_each_turn(journal)
    assert first != second, "a spoken turn waits only as long as speech allows"


async def test_sessions_hold_their_own_conversations(make_agent: MakeAgent, journal: Journal) -> None:
    agent = make_agent("Oui.", "Oui.")
    await agent.respond(message("Salut")).collect()
    await agent.respond(message("Salut", VOICE, "mic")).collect()

    telegram, voice = await conversation_of_each_turn(journal)
    assert telegram != voice


async def test_the_open_conversation_survives_a_restart(make_agent: MakeAgent, journal: Journal, clock: Clock) -> None:
    await make_agent("Noté.", clock=clock).respond(message("Note ça", VOICE, "mic")).collect()
    clock.now += timedelta(seconds=30)
    await make_agent("Oui.", clock=clock).respond(message("Et ça", VOICE, "mic")).collect()
    clock.now += timedelta(minutes=10)
    await make_agent("Oui.", clock=clock).respond(message("Plus tard", VOICE, "mic")).collect()

    first, second, third = await conversation_of_each_turn(journal)
    assert first == second != third


async def test_every_event_of_a_turn_carries_its_conversation_and_its_turn(
    make_agent: MakeAgent, journal: Journal
) -> None:
    memories = MemoryTools(
        Memories(journal, InMemoryMemoryStore()),
        Episodes(journal, InMemoryEpisodeStore()),
        Household([MATHIS]),
        journal,
        assistant="Richie",
    )
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
    [answer] = await journal.history(AssistantTurn)  # "Merci" got no answer: nothing to log
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
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    await make_agent("Je lance l'analyse.", clock=clock).respond(message("Analyse")).collect()
    model = ScriptedModel("C'est fini.", "C'est fini.")
    agent = make_agent(model=model, clock=clock)
    notification = Notification("Task finished.", "task t1 completed")
    await agent.compose(TELEGRAM, MATHIS, notification, Medium.WRITTEN)
    clock.now += timedelta(hours=5)
    await agent.compose(TELEGRAM, MATHIS, notification, Medium.WRITTEN)

    soon, late = ([m.role for m in r.messages] for r in model.requests)
    assert soon == [Role.SYSTEM, Role.USER, Role.ASSISTANT, Role.USER]  # the conversation, then the notification
    assert late == [Role.SYSTEM, Role.USER]
    assert len(await journal.history(UserTurn)) == 1, "a draft is not a turn"


def test_a_cue_keeps_the_beginning_and_end_of_a_long_result() -> None:
    long = "début " + "x" * 20_000 + " fin"
    notification = Notification(long, "task t1 completed")
    assert (
        len(notification.text) < 8100
        and notification.text.startswith("début")
        and notification.text.endswith("fin")
        and "[… cut …]" in notification.text
    )
    assert Notification("court", "task t1 completed").text == "court"


async def test_a_delivered_message_keeps_its_conversation_open_across_a_restart(
    make_agent: MakeAgent, journal: Journal, clock: Clock
) -> None:
    delivered = await make_agent(clock=clock).delivered(
        TELEGRAM, MATHIS, Notification("Fini.", "task t1 completed"), Medium.WRITTEN, ["C'est fini."]
    )
    restarted = make_agent(clock=clock)
    assert await restarted.conversations.current(TELEGRAM, Medium.WRITTEN) == delivered.conversation_id


def test_an_exchange_is_written_as_plain_data() -> None:
    turn = UserTurn(
        medium=Medium.WRITTEN,
        source="agent",
        address=TELEGRAM,
        text="Salut",
        exchange=Exchange(conversation_id="c1", turn_id="t1"),
        speaker=Speaker.unknown(),
    )
    record = turn.to_record()
    payload = record["payload"]
    assert isinstance(payload, dict) and payload["exchange"] == {"conversation_id": "c1", "turn_id": "t1"}
    assert Event.from_record(record) == turn
