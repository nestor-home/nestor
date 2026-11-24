"""What comes back by itself, a turn of a task that ended (its report, its question, its failure) or a tool slower
than its turn, reaches whoever asked: in the conversation, in writing, or as soon as Nestor is back."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Iterable, Mapping, Sequence
from datetime import timedelta

import pytest

from nestor.core import Event, PersonId, ProviderError
from nestor.modules.channels import Address, Attachment, AttachmentKind, InboundMessage, Medium, Sender
from nestor.modules.cognition import Executor, Notify, Outcome, Progress, TaskState
from nestor.modules.cognition.delegation import Assignment, TaskReminded, TurnDelivered, TurnEnded
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.model import Role, ToolCall, ToolSpec
from nestor.modules.cognition.tools import Made, Tool, Toolbox, ToolCalled, ToolContext, ToolDeferred, ToolReturned
from nestor.modules.conversation import (
    SILENT,
    About,
    Agent,
    AgentSettings,
    AnswerAttached,
    AssistantTurn,
    Attachments,
    ModelChoice,
    Notification,
    NotificationTurn,
    Persona,
    Source,
)
from nestor.modules.conversation.persona import MUST_TELL
from nestor.modules.household import Account, Household, Person
from nestor.modules.initiative import Courier, Delivered, DeliveryFailed, DeliveryWithheld, Returns, ToolResultDelivered
from nestor.modules.initiative.returns import REMINDERS, TICK_S
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedExecutor, ScriptedModel
from nestor.testing.cognition.images import PNG
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

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

    async def send(self, to: Address, text: str, medium: Medium, attachments: tuple[Attachment, ...]) -> None:
        if self.broken:
            raise ProviderError("voice", "speaker unplugged", transient=True)
        await super().send(to, text, medium, attachments)


class Home:
    def __init__(
        self,
        *,
        voice: VoiceChannel | None = None,
        model: ScriptedModel | None = None,
        journal: Journal | None = None,
        tools: Iterable[Tool] = (),
        tool_wait_s: float = 0.05,
        executors: Iterable[Executor] = (),
    ) -> None:
        """`journal`: another home's, to start again on what it wrote (a restart); `executors` beside the scripted
        ones: one that reports, one that fails, one that asks."""
        self.journal = journal or Journal(MemoryEventLog())
        self.household = Household([MATHIS])
        self.model = model or ScriptedModel(*["Ton analyse est finie : tout est vert."] * 3)
        self.blobs = MemoryBlobStore()
        self.agent = Agent(
            attachments=Attachments(self.blobs),
            models=ModelChoice.single(self.model),
            persona=Persona(name="Richie", character="Tu es Richie."),
            journal=self.journal,
            household=self.household,
            localizer=EchoLocalizer(),
            toolbox=Toolbox(self.journal, tools, blobs=self.blobs),
            settings=AgentSettings(written_tool_wait_s=tool_wait_s),
        )
        self.voice = voice or VoiceChannel()
        self.telegram = InMemoryChannel("telegram")
        self.courier = Courier(self.journal, self.agent, [self.voice, self.telegram])
        reports, fails, asks = (
            ScriptedExecutor("tout est vert"),
            ScriptedExecutor(error="boom"),
            ScriptedExecutor(asks="Quelle branche ?"),
        )
        reports.name, fails.name, asks.name = "reports", "fails", "asks"
        self.executors = [reports, fails, asks, *executors]
        self.tasks: TaskManager | None = None  # the running one, inside `returns()`

    @contextlib.asynccontextmanager
    async def returns(
        self, *, reminders: Sequence[timedelta] = REMINDERS, tick_s: float = TICK_S
    ) -> AsyncGenerator[Returns]:
        """Nestor running: its tasks, rebuilt from the journal, then what comes back from them."""
        tasks = TaskManager(self.journal, self.executors, blobs=self.blobs)
        async with tasks:
            self.tasks = tasks
            try:
                returns = Returns(self.journal, self.household, self.courier, tasks, reminders=reminders, tick_s=tick_s)
                async with returns:
                    yield returns
            finally:
                self.tasks = None

    async def task(
        self,
        *,
        notify: Notify = Notify.AUTO,
        executor: str = "reports",
        still_talking: bool = True,
        by_mathis: bool = False,
        owner: PersonId | None = MATHIS.id,
    ) -> str:
        """A task asked aloud, its first turn run to its end; `still_talking`: its spoken conversation goes on when it
        ends; `by_mathis`: in his own turn, rather than in one Nestor opened (a wake-up that delegates). Run by the
        Nestor running, or by one that stops right after (what comes back is then delivered at the next start)."""
        if still_talking:
            await self.agent.conversations.turn(VOICE, Medium.SPOKEN)
        async with contextlib.AsyncExitStack() as stack:
            tasks = self.tasks or await stack.enter_async_context(
                TaskManager(self.journal, self.executors, blobs=self.blobs)
            )
            task = await tasks.start_task(
                "Analyse le dépôt",
                title="Analyse du dépôt",
                origin=VOICE,
                owner=owner,
                executor=executor,
                notify=notify,
                asked=by_mathis,
            )
            await tasks.wait(task.id)
        return task.id


async def delivered(journal: Journal, count: int = 1) -> None:
    for _ in range(500):
        if len(await journal.history(TurnDelivered)) >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("nothing was delivered")


async def test_a_result_is_said_in_the_conversation_it_was_asked_in() -> None:
    home = Home()
    async with home.returns():
        await home.task()
        await delivered(home.journal)

    assert home.voice.sent == [(VOICE, "Ton analyse est finie : tout est vert.")]
    assert home.telegram.sent == []
    turn = (await home.journal.history(AssistantTurn))[0]
    assert (turn.address, turn.text) == (VOICE, "Ton analyse est finie : tout est vert.")
    assert "tout est vert" in home.model.requests[0].messages[-1].content


async def test_a_result_after_the_spoken_conversation_is_over_is_written() -> None:
    """Nestor speaks unprompted only when it is sure someone listens: here nothing says who is in the room."""
    home = Home()
    await home.task(still_talking=False)
    async with home.returns():
        pass
    assert home.voice.sent == [] and home.telegram.sent == [(TELEGRAM, "Ton analyse est finie : tout est vert.")]


async def test_the_person_answering_a_result_is_answered_with_it_in_mind() -> None:
    """The result comes back into the conversation it is delivered in, as a tool's result does: the person's next
    message is answered knowing it, even after a restart."""
    home = Home(model=ScriptedModel("Ton analyse est finie : tout est vert.", "Oui, tout est vert."))
    task_id = await home.task(still_talking=False)
    async with home.returns():
        pass
    restarted = Home(model=home.model, journal=home.journal)
    reply = InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Tout ? Même les tests ?")
    assert await restarted.agent.respond(reply).collect() == ("Oui, tout est vert.",)
    history = home.model.requests[1].messages[1:]
    assert [m.role for m in history] == [Role.USER, Role.ASSISTANT, Role.USER]
    assert "Report: tout est vert" in history[0].content and "not said by anyone here" in history[0].content
    [internal] = await home.journal.history(NotificationTurn)
    assert (internal.about, internal.person, internal.address) == (
        About(Source.TASK, task_id, "completed"),
        MATHIS.id,
        TELEGRAM,
    )
    [said] = [t for t in await home.journal.history(AssistantTurn) if t.exchange == internal.exchange]
    assert said.text == "Ton analyse est finie : tout est vert.", "the message and what caused it share their turn"


async def test_a_result_asked_in_writing_goes_where_the_person_reads() -> None:
    home = Home()
    await home.task(notify=Notify.MESSAGE)
    async with home.returns():
        pass
    assert home.telegram.sent == [(TELEGRAM, "Ton analyse est finie : tout est vert.")]
    assert "as a message" in home.model.requests[0].messages[-1].content


async def test_nobody_listening_on_voice_means_a_message() -> None:
    home = Home(voice=VoiceChannel(connected=False))
    await home.task()
    async with home.returns():
        pass
    assert [d.address for d in await home.journal.history(Delivered)] == [TELEGRAM]


async def test_a_failed_send_falls_back_to_the_next_channel() -> None:
    home = Home(voice=VoiceChannel(broken=True))
    await home.task()
    async with home.returns():
        pass
    assert home.telegram.sent and [t.address for t in await home.journal.history(AssistantTurn)] == [TELEGRAM]


async def test_a_result_is_delivered_once_even_across_restarts() -> None:
    home = Home()
    await home.task()
    async with home.returns():
        pass
    async with home.returns():
        pass
    assert len(home.voice.sent) == 1
    assert len(await home.journal.history(TurnDelivered)) == 1


async def test_a_stopped_turn_is_not_announced_and_a_failure_is() -> None:
    home = Home(executors=[ScriptedExecutor(duration_s=30)])
    async with home.returns():
        assert home.tasks is not None
        task = await home.tasks.start_task("x", title="X", origin=VOICE, owner=MATHIS.id, executor="scripted-executor")
        await asyncio.sleep(0.01)
        await home.tasks.stop(task.id)
        await home.task(executor="fails")
        await delivered(home.journal)
    assert len(home.voice.sent) == 1
    assert "Failure: boom" in home.model.requests[0].messages[-1].content


async def test_a_question_is_always_told_with_how_to_pass_its_answer_on() -> None:
    home = Home(model=ScriptedModel("Quelle branche veux-tu ?"))
    async with home.returns():
        task_id = await home.task(executor="asks")
        await delivered(home.journal)
    told = str(home.model.requests[-1].messages[-1].content)
    assert "Quelle branche ?" in told and f"continue_task(task={task_id!r})" in told
    assert MUST_TELL in str(home.model.requests[-1].messages[0].content), "a question is never kept to oneself"


async def test_each_turn_of_a_task_is_delivered_once() -> None:
    home = Home()
    async with home.returns():
        task_id = await home.task()
        await delivered(home.journal)
        assert home.tasks is not None
        await home.tasks.direct(task_id, "Et les tests ?", by=MATHIS.id)
        await home.tasks.wait(task_id)
        await delivered(home.journal, 2)
    async with home.returns():  # a restart
        pass
    assert len({e.turn_id for e in await home.journal.history(TurnDelivered)}) == 2
    assert len(home.voice.sent) == 2


async def test_a_question_left_unanswered_is_recalled_a_few_times_then_waits() -> None:
    home = Home(model=ScriptedModel(*["Ton analyse attend ta réponse."] * 5))
    async with home.returns(reminders=(timedelta(hours=3), timedelta(hours=24)), tick_s=3600) as returns:
        task_id = await home.task(executor="asks", still_talking=False)
        await delivered(home.journal)
        assert home.tasks is not None
        asked_at = home.tasks.tasks[task_id].turn.ended_at
        assert asked_at is not None
        await returns.remind(asked_at + timedelta(hours=1))
        assert await home.journal.history(TaskReminded) == [], "too soon"
        await returns.remind(asked_at + timedelta(hours=3, minutes=1))
        await returns.remind(asked_at + timedelta(hours=4))  # nothing more is due
        await returns.remind(asked_at + timedelta(days=5))
        await returns.remind(asked_at + timedelta(days=9))  # past the last reminder: it waits
        assert home.tasks.tasks[task_id].state is TaskState.WAITING
    assert [e.count for e in await home.journal.history(TaskReminded)] == [1, 2]
    assert "still waits for their answer to: Quelle branche ?" in str(home.model.requests[-1].messages[-1].content)


async def test_an_archived_task_s_question_is_no_longer_recalled() -> None:
    home = Home()
    async with home.returns(reminders=(timedelta(hours=3),), tick_s=3600) as returns:
        task_id = await home.task(executor="asks", still_talking=False)
        await delivered(home.journal)
        assert home.tasks is not None
        await home.tasks.archive(task_id)
        ended = home.tasks.tasks[task_id].turn.ended_at
        assert ended is not None
        await returns.remind(ended + timedelta(days=1))
    assert await home.journal.history(TaskReminded) == []


async def test_an_undeliverable_result_is_logged_and_retried_later() -> None:
    home = Home(voice=VoiceChannel(connected=False))
    home.courier.channels = {}  # nothing plugged at all
    await home.task()
    async with home.returns():
        pass
    assert len(await home.journal.history(DeliveryFailed)) == 1
    assert await home.journal.history(TurnDelivered) == []

    home.courier.channels = {"voice": home.voice, "telegram": home.telegram}
    async with home.returns():
        pass
    assert len(home.telegram.sent) == 1


async def test_a_result_with_nothing_to_tell_is_withheld_once_and_never_brought_back() -> None:
    """A search that found nothing: nothing sent, the reason kept, and a restart does not ask again."""
    home = Home(model=ScriptedModel(f"{SILENT} aucune offre sous 500 €", "Rien à signaler."))
    await home.task(notify=Notify.MESSAGE, still_talking=False)
    async with home.returns():
        pass
    (withheld,) = await home.journal.history(DeliveryWithheld)
    assert withheld.reason == "aucune offre sous 500 €"

    async with Home(model=home.model, journal=home.journal).returns():  # Nestor restarted
        pass
    assert home.telegram.sent == home.voice.sent == []
    assert len(home.model.requests) == 1, "a withheld result is done: it is not written again"
    assert await home.journal.history(TurnDelivered) == [], "nothing was passed on: the journal does not say so"


async def test_a_failed_task_may_not_be_left_untold() -> None:
    """Silence on a failure is not "nothing to tell": the delivery fails, and it is tried again after a restart."""
    home = Home(model=ScriptedModel(f"{SILENT} rien de neuf"))
    await home.task(executor="fails", still_talking=False)
    async with home.returns():
        pass
    assert await home.journal.history(DeliveryWithheld) == await home.journal.history(TurnDelivered) == []
    assert len(await home.journal.history(DeliveryFailed)) == 1


async def test_what_a_person_asked_for_is_told_even_when_it_found_nothing() -> None:
    """They wait for it: the model is told it must answer, and silence is a failed delivery, not "nothing to tell"."""
    home = Home(model=ScriptedModel(f"{SILENT} rien d'autre à signaler"))
    await home.task(notify=Notify.MESSAGE, still_talking=False, by_mathis=True)
    async with home.returns():
        pass
    assert MUST_TELL in str(home.model.requests[0].messages[0].content)
    assert await home.journal.history(DeliveryWithheld) == [] and len(await home.journal.history(DeliveryFailed)) == 1


@pytest.mark.parametrize("known", [True, False])
async def test_a_task_from_an_unknown_person_stays_in_its_conversation(known: bool) -> None:
    home = Home()
    await home.task(owner=MATHIS.id if known else None, still_talking=False)
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


async def test_a_tool_slower_than_a_wake_up_s_turn_comes_back_in_the_wake_up_s_thread() -> None:
    """What a recurring wake-up starts and gets later is read back with it the next time it runs."""
    done = asyncio.Event()
    model = ScriptedModel(ToolCall("c1", "count_mails"), f"{SILENT} en cours", "Tu as 12 mails non lus.")
    home = Home(model=model, tools=[slow_tool(done)])
    woken = Notification("Compte les mails de Mathis.", About(Source.SCHEDULE, "s1"), thread="schedule:s1")
    async with home.returns():
        await home.courier.deliver(MATHIS, woken, origin=TELEGRAM)
        done.set()
        await until(home.journal, ToolResultDelivered)
    [returned] = await home.journal.history(NotificationTurn)
    assert (returned.about.source, returned.thread) == (Source.TOOL, "schedule:s1")


async def test_a_picture_drawn_after_the_turn_goes_with_the_answer_that_brings_it() -> None:
    done = asyncio.Event()

    async def draw(arguments: Mapping[str, object], context: ToolContext) -> Made:
        await done.wait()
        return Made("drawn", (Attachment(kind=AttachmentKind.IMAGE, data=PNG, media_type="image/png"),))

    model = ScriptedModel(ToolCall("c1", "draw"), "Je dessine, je te l'envoie.", "Voilà ton dessin.")
    home = Home(model=model, tools=[Tool(spec=ToolSpec("draw", "Draw a picture"), run=draw)])
    home.telegram.sends = frozenset({AttachmentKind.IMAGE})
    async with home.returns():
        await home.agent.respond(InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Dessine.")).collect()
        done.set()
        await until(home.journal, ToolResultDelivered)

    assert home.telegram.sent == [(TELEGRAM, "Voilà ton dessin.")]
    assert [[(a.kind, a.data) for a in files] for files in home.telegram.files] == [[(AttachmentKind.IMAGE, PNG)]]
    [attached] = await home.journal.history(AnswerAttached)
    assert [home.blobs.blobs[f.blob.digest] for f in attached.files] == [PNG]


class Seeing(ScriptedModel):
    vision = True


async def test_a_picture_a_slow_tool_took_is_shown_with_the_notification_that_brings_it() -> None:
    done = asyncio.Event()

    async def snap(arguments: Mapping[str, object], context: ToolContext) -> Made:
        await done.wait()
        return Made("taken", seen=(Attachment(kind=AttachmentKind.IMAGE, data=PNG, media_type="image/png"),))

    model = Seeing(ToolCall("c1", "snap"), "Je regarde.", "La lampe est allumée.")
    home = Home(model=model, tools=[Tool(spec=ToolSpec("snap", "Take a picture"), run=snap)])
    async with home.returns():
        await home.agent.respond(InboundMessage(address=TELEGRAM, sender=Sender("42"), text="La lampe ?")).collect()
        done.set()
        await until(home.journal, ToolResultDelivered)

    notification = model.requests[2].messages[-1]
    assert [i.data for i in notification.images] == [PNG]
    assert home.telegram.files == [()], "a picture taken for the model is not sent"


async def test_a_file_a_delegated_task_made_goes_with_the_answer_that_brings_its_result() -> None:
    pdf = b"%PDF-1.7 rapport"

    class Writer(Executor):
        name = "writer"

        async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
            return Outcome.completed(
                "rapport écrit",
                (Attachment(kind=AttachmentKind.FILE, data=pdf, media_type="application/pdf", name="rapport.pdf"),),
            )

    home = Home(model=ScriptedModel("Voici ton rapport."), executors=[Writer()])
    home.telegram.sends = frozenset({AttachmentKind.FILE})
    async with home.returns():
        assert home.tasks is not None
        await home.tasks.start_task(
            "Écris le rapport", title="Écris le rapport", origin=TELEGRAM, owner=MATHIS.id, executor="writer"
        )
        await delivered(home.journal)

    assert home.telegram.sent == [(TELEGRAM, "Voici ton rapport.")]
    assert [[(a.name, a.data) for a in files] for files in home.telegram.files] == [[("rapport.pdf", pdf)]]
    turn = str(home.model.requests[0].messages[0].content)
    assert "go with your answer" in turn and "rapport.pdf" in turn, "the model knows the file goes with its words"
    [ended] = await home.journal.history(TurnEnded)
    assert [home.blobs.blobs[f.blob.digest] for f in ended.files] == [pdf]


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


async def test_a_call_that_failed_may_not_be_left_untold() -> None:
    model = ScriptedModel(ToolCall("c1", "count_mails"), "Je regarde.", f"{SILENT} rien à dire")
    home = Home(model=model, tools=[slow_tool(asyncio.Event())])
    await home.agent.respond(InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Combien ?")).collect()
    await home.agent.toolbox.close()  # the process stops while the call runs: it failed

    restarted = Home(model=model, journal=home.journal)
    async with restarted.returns():
        await until(restarted.journal, DeliveryFailed)
    assert await home.journal.history(DeliveryWithheld, ToolResultDelivered) == []


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
