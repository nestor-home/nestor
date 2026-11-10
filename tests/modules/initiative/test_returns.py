"""What comes back by itself, an ended task or a tool slower than its turn, reaches whoever asked: in the
conversation, in writing, or as soon as Nestor is back."""

import asyncio
from collections.abc import Iterable, Mapping

import pytest

from nestor.core import Event, PersonId, ProviderError
from nestor.modules.channels import Address, InboundMessage, Medium, Sender
from nestor.modules.cognition import Notify, TaskDelivered, TaskEnded, TaskStarted, TaskStatus
from nestor.modules.cognition.model import Role, ToolCall, ToolSpec
from nestor.modules.cognition.tools import Tool, Toolbox, ToolCalled, ToolContext, ToolDeferred, ToolReturned
from nestor.modules.conversation import (
    About,
    Agent,
    AgentSettings,
    AssistantTurn,
    ModelChoice,
    NotificationTurn,
    Persona,
    Source,
)
from nestor.modules.household import Account, Household, Person
from nestor.modules.initiative import Courier, Delivered, DeliveryFailed, Returns, ToolResultDelivered
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryEventLog

TELEGRAM = Address("telegram", "42")
VOICE = Address("voice", "salon")
MATHIS = Person(
    id=PersonId("mathis"),
    name="Mathis",
    accounts=(Account.parse("telegram:42"),),
    reach=TELEGRAM,
)


class VoiceChannel(InMemoryChannel):
    """A voice satellite in the living room, nobody may be listening to."""

    media = frozenset({Medium.SPOKEN})
    room = "salon"

    def __init__(self, *, connected: bool = True, broken: bool = False) -> None:
        super().__init__("voice")
        self.connected, self.broken = connected, broken

    def reachable(self, to: Address, medium: Medium) -> bool:
        return self.connected and super().reachable(to, medium)

    async def send(self, to: Address, text: str, medium: Medium) -> None:
        if self.broken:
            raise ProviderError("voice", "speaker unplugged", transient=True)
        await super().send(to, text, medium)


class Home:
    def __init__(
        self,
        *,
        voice: VoiceChannel | None = None,
        model: ScriptedModel | None = None,
        journal: Journal | None = None,
        tools: Iterable[Tool] = (),
        tool_wait_s: float = 0.05,
    ) -> None:
        """`journal`: another home's, to start again on what it wrote (a restart)."""
        self.journal = journal or Journal(MemoryEventLog())
        self.household = Household([MATHIS])
        self.model = model or ScriptedModel(*["Ton analyse est finie : tout est vert."] * 3)
        self.agent = Agent(
            models=ModelChoice.single(self.model),
            persona=Persona(name="Richie", character="Tu es Richie."),
            journal=self.journal,
            household=self.household,
            localizer=EchoLocalizer(),
            toolbox=Toolbox(self.journal, tools),
            settings=AgentSettings(written_tool_wait_s=tool_wait_s),
        )
        self.voice = voice or VoiceChannel()
        self.telegram = InMemoryChannel("telegram")
        self.courier = Courier(self.journal, self.agent, [self.voice, self.telegram])

    def returns(self) -> Returns:
        return Returns(self.journal, self.household, self.courier)

    async def task(
        self,
        task_id: str,
        *,
        notify: Notify = Notify.AUTO,
        status: TaskStatus = TaskStatus.COMPLETED,
        still_talking: bool = True,
    ) -> None:
        """A task asked aloud; `still_talking`: its spoken conversation goes on when it ends."""
        if still_talking:
            await self.agent.conversations.turn(VOICE, Medium.SPOKEN)
        await self.journal.publish(
            TaskStarted(
                source="t",
                task_id=task_id,
                objective="Analyse le dépôt",
                executor="hermes",
                origin=VOICE,
                requested_by=MATHIS.id,
                notify=notify,
            )
        )
        await self.journal.publish(
            TaskEnded(
                source="t",
                task_id=task_id,
                status=status,
                result="tout est vert",
                error=None if status is TaskStatus.COMPLETED else "boom",
                duration_s=3.0,
            )
        )


async def test_a_result_is_said_in_the_conversation_it_was_asked_in() -> None:
    home = Home()
    async with home.returns():
        await home.task("t1")
        await home.journal.subscribe(TaskDelivered).next(timeout_s=1) if not await home.journal.history(
            TaskDelivered
        ) else None

    assert home.voice.sent == [(VOICE, "Ton analyse est finie : tout est vert.")]
    assert home.telegram.sent == []
    turn = (await home.journal.history(AssistantTurn))[0]
    assert (turn.address, turn.text) == (VOICE, "Ton analyse est finie : tout est vert.")
    assert "tout est vert" in home.model.requests[0].messages[-1].content


async def test_a_result_after_the_spoken_conversation_is_over_is_written() -> None:
    """Nestor speaks unprompted only when it is sure someone listens: here nothing says who is in the room."""
    home = Home()
    await home.task("t1", still_talking=False)
    async with home.returns():
        pass
    assert home.voice.sent == [] and home.telegram.sent == [(TELEGRAM, "Ton analyse est finie : tout est vert.")]


async def test_the_person_answering_a_result_is_answered_with_it_in_mind() -> None:
    """The result comes back into the conversation it is delivered in, as a tool's result does: the person's next
    message is answered knowing it, even after a restart."""
    home = Home(model=ScriptedModel("Ton analyse est finie : tout est vert.", "Oui, tout est vert."))
    await home.task("t1", still_talking=False)
    async with home.returns():
        pass
    restarted = Home(model=home.model, journal=home.journal)
    reply = InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Tout ? Même les tests ?")
    assert await restarted.agent.respond(reply).collect() == ("Oui, tout est vert.",)
    history = home.model.requests[1].messages[1:]
    assert [m.role for m in history] == [Role.USER, Role.ASSISTANT, Role.USER]
    assert "Result: tout est vert" in history[0].content and "not said by anyone here" in history[0].content
    [internal] = await home.journal.history(NotificationTurn)
    assert (internal.about, internal.person, internal.address) == (
        About(Source.TASK, "t1", "completed"),
        MATHIS.id,
        TELEGRAM,
    )
    [said] = [t for t in await home.journal.history(AssistantTurn) if t.exchange == internal.exchange]
    assert said.text == "Ton analyse est finie : tout est vert.", "the message and what caused it share their turn"


async def test_a_result_asked_in_writing_goes_where_the_person_reads() -> None:
    home = Home()
    await home.task("t1", notify=Notify.MESSAGE)
    async with home.returns():
        pass
    assert home.telegram.sent == [(TELEGRAM, "Ton analyse est finie : tout est vert.")]
    assert "in writing" in home.model.requests[0].messages[-1].content


async def test_nobody_listening_on_voice_means_a_message() -> None:
    home = Home(voice=VoiceChannel(connected=False))
    await home.task("t1")
    async with home.returns():
        pass
    assert [d.address for d in await home.journal.history(Delivered)] == [TELEGRAM]


async def test_a_failed_send_falls_back_to_the_next_channel() -> None:
    home = Home(voice=VoiceChannel(broken=True))
    await home.task("t1")
    async with home.returns():
        pass
    assert home.telegram.sent and [t.address for t in await home.journal.history(AssistantTurn)] == [TELEGRAM]


async def test_a_result_is_delivered_once_even_across_restarts() -> None:
    home = Home()
    await home.task("t1")
    async with home.returns():
        pass
    async with home.returns():
        pass
    assert len(home.voice.sent) == 1
    assert [d.task_id for d in await home.journal.history(TaskDelivered)] == ["t1"]


async def test_a_cancelled_task_is_not_announced_and_a_failure_is() -> None:
    home = Home()
    await home.task("t1", status=TaskStatus.CANCELLED)
    await home.task("t2", status=TaskStatus.FAILED)
    async with home.returns():
        pass
    assert len(home.voice.sent) == 1
    assert "Failure: boom" in home.model.requests[0].messages[-1].content


async def test_an_undeliverable_result_is_logged_and_retried_later() -> None:
    home = Home(voice=VoiceChannel(connected=False))
    home.courier.channels = {}  # nothing plugged at all
    await home.task("t1")
    async with home.returns():
        pass
    assert len(await home.journal.history(DeliveryFailed)) == 1
    assert await home.journal.history(TaskDelivered) == []

    home.courier.channels = {"voice": home.voice, "telegram": home.telegram}
    async with home.returns():
        pass
    assert len(home.telegram.sent) == 1


@pytest.mark.parametrize("known", [True, False])
async def test_a_task_from_an_unknown_person_stays_in_its_conversation(known: bool) -> None:
    home = Home()
    await home.journal.publish(
        TaskStarted(
            source="t",
            task_id="t1",
            objective="x",
            executor="h",
            origin=VOICE,
            requested_by=MATHIS.id if known else None,
        )
    )
    await home.journal.publish(
        TaskEnded(source="t", task_id="t1", status=TaskStatus.COMPLETED, result="ok", duration_s=1)
    )
    home.voice.connected = False
    async with home.returns():
        pass
    assert len(home.telegram.sent) == (1 if known else 0)


def slow_tool(done: asyncio.Event, result: str = "12 mails non lus") -> Tool:
    async def count(arguments: Mapping[str, object], context: ToolContext) -> str:
        await done.wait()
        return result

    return Tool(spec=ToolSpec("count_mails", "Count unread mails"), run=count)


async def until(journal: Journal, event: type[Event]) -> None:
    if not await journal.history(event):
        await journal.subscribe(event).next(timeout_s=1)


async def test_a_tool_slower_than_the_turn_answers_in_the_conversation_once_done() -> None:
    """The turn does not wait: the model hears the call goes on, the person is answered at once, and the result
    comes back into the conversation as a notification, answered like a message."""
    done = asyncio.Event()
    model = ScriptedModel(ToolCall("c1", "count_mails"), "Je regarde, je te dis ça.", "Tu as 12 mails non lus.")
    home = Home(model=model, tools=[slow_tool(done)])
    async with home.returns():
        asked = InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Combien de mails ?")
        assert await home.agent.respond(asked).collect() == ("Je regarde, je te dis ça.",)
        assert "still running" in model.requests[1].messages[-1].content
        assert home.telegram.sent == []
        done.set()
        await until(home.journal, ToolResultDelivered)

    assert home.telegram.sent == [(TELEGRAM, "Tu as 12 mails non lus.")]
    notification = model.requests[2].messages[-1].content
    assert "Result: 12 mails non lus" in notification and "count_mails" in notification
    [returned] = await home.journal.history(NotificationTurn)
    assert (returned.about, returned.person) == (About(Source.TOOL, "c1", "returned"), MATHIS.id)


async def test_a_call_cut_short_by_a_restart_is_said_to_have_failed() -> None:
    model = ScriptedModel(ToolCall("c1", "count_mails"), "Je regarde.", "Je n'ai pas pu compter tes mails.")
    home = Home(model=model, tools=[slow_tool(asyncio.Event())])
    asked = InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Combien de mails ?")
    await home.agent.respond(asked).collect()
    await home.agent.toolbox.close()  # the process stops while the call runs

    restarted = Home(model=model, journal=home.journal)
    async with restarted.returns():
        await until(restarted.journal, ToolResultDelivered)
    async with restarted.returns():  # once only
        pass

    assert restarted.telegram.sent == [(TELEGRAM, "Je n'ai pas pu compter tes mails.")]
    [returned] = await home.journal.history(ToolReturned)
    assert not returned.ok and "restarted" in returned.output
    assert "Failure:" in model.requests[2].messages[-1].content


async def test_a_result_that_came_back_while_nobody_listened_is_delivered_once_at_the_next_start() -> None:
    done = asyncio.Event()
    model = ScriptedModel(ToolCall("c1", "count_mails"), "Je regarde.", "Tu as 12 mails non lus.")
    home = Home(model=model, tools=[slow_tool(done)])
    asked = InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Combien de mails ?")
    await home.agent.respond(asked).collect()
    done.set()  # it ends while Returns is not running: only the journal keeps it
    await until(home.journal, ToolReturned)

    restarted = Home(model=model, journal=home.journal)
    async with restarted.returns():
        await until(restarted.journal, ToolResultDelivered)
    async with restarted.returns():  # once only
        pass

    assert restarted.telegram.sent == [(TELEGRAM, "Tu as 12 mails non lus.")]
    assert "Result: 12 mails non lus" in model.requests[2].messages[-1].content


async def test_a_cut_turn_stops_the_call_it_was_waiting_for() -> None:
    """Someone who cuts Nestor off drops what they asked: the call stops and nothing comes back later."""
    stopped = asyncio.Event()

    async def count(arguments: Mapping[str, object], context: ToolContext) -> str:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            stopped.set()
            raise
        return "12 mails non lus"

    tool = Tool(spec=ToolSpec("count_mails", "Count unread mails"), run=count)
    home = Home(model=ScriptedModel(ToolCall("c1", "count_mails")), tools=[tool], tool_wait_s=5)
    async with home.returns():
        reply = home.agent.respond(InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Mes mails ?"))
        reading = asyncio.create_task(reply.collect())
        await until(home.journal, ToolCalled)
        await reply.interrupt("")
        await reading
        await asyncio.wait_for(stopped.wait(), 1)

    assert await home.journal.history(ToolDeferred, ToolReturned) == []
    assert home.telegram.sent == []


async def test_the_history_keeps_what_the_model_heard_when_the_call_went_on() -> None:
    done = asyncio.Event()
    model = ScriptedModel(ToolCall("c1", "count_mails"), "Je regarde.", "Tu as 12 mails.", "De rien.")
    home = Home(model=model, tools=[slow_tool(done)])
    async with home.returns():
        await home.agent.respond(InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Mes mails ?")).collect()
        done.set()
        await until(home.journal, ToolResultDelivered)
    await home.agent.respond(InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Merci")).collect()

    replayed = [m for m in model.requests[3].messages if m.role is Role.TOOL]
    assert len(replayed) == 1 and "still running" in replayed[0].content
    assert [d.call_id for d in await home.journal.history(ToolDeferred)] == ["c1"]
