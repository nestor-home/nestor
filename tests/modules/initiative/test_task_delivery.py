"""Task results reach whoever asked: in the conversation, in writing, or as soon as Nestor is back."""

import pytest

from nestor.core import PersonId, ProviderError
from nestor.modules.channels import Address
from nestor.modules.cognition import Notify, TaskDelivered, TaskEnded, TaskStarted, TaskStatus
from nestor.modules.cognition.tools import Toolbox
from nestor.modules.conversation import Agent, AssistantTurn, Persona
from nestor.modules.household import Account, Household, Person
from nestor.modules.initiative import Courier, Delivered, DeliveryFailed, TaskAnnouncer
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.journal import MemoryEventLog

TELEGRAM = Address("telegram", "42")
VOICE = Address("voice", "salon")
MATHIS = Person(
    id=PersonId("mathis"),
    name="Mathis",
    accounts=(Account.parse("telegram:42"), Account.parse("voice:*")),
    reach=TELEGRAM,
)


class VoiceChannel(InMemoryChannel):
    """A voice channel nobody may be listening to."""

    def __init__(self, *, connected: bool = True, broken: bool = False) -> None:
        super().__init__("voice")
        self.connected, self.broken = connected, broken

    def reachable(self, to: Address) -> bool:
        return self.connected and super().reachable(to)

    async def send(self, to: Address, text: str) -> None:
        if self.broken:
            raise ProviderError("voice", "speaker unplugged", transient=True)
        await super().send(to, text)


class Home:
    def __init__(self, *, voice: VoiceChannel | None = None, model: ScriptedModel | None = None) -> None:
        self.journal = Journal(MemoryEventLog())
        self.household = Household([MATHIS])
        self.model = model or ScriptedModel(*["Ton analyse est finie : tout est vert."] * 3)
        self.agent = Agent(
            model=self.model,
            persona=Persona(name="Richie", character="Tu es Richie."),
            journal=self.journal,
            household=self.household,
            toolbox=Toolbox(self.journal),
        )
        self.voice = voice or VoiceChannel()
        self.telegram = InMemoryChannel("telegram")
        self.courier = Courier(self.journal, self.agent, [self.voice, self.telegram])

    def announcer(self) -> TaskAnnouncer:
        return TaskAnnouncer(self.journal, self.household, self.courier)

    async def task(
        self, task_id: str, *, notify: Notify = Notify.AUTO, status: TaskStatus = TaskStatus.COMPLETED
    ) -> None:
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
    async with home.announcer():
        await home.task("t1")
        await home.journal.subscribe(TaskDelivered).next(timeout_s=1) if not await home.journal.history(
            TaskDelivered
        ) else None

    assert home.voice.sent == [(VOICE, "Ton analyse est finie : tout est vert.")]
    assert home.telegram.sent == []
    turn = (await home.journal.history(AssistantTurn))[0]
    assert (turn.address, turn.text) == (VOICE, "Ton analyse est finie : tout est vert.")
    assert "tout est vert" in home.model.requests[0].messages[-1].content


async def test_a_result_asked_in_writing_goes_where_the_person_reads() -> None:
    home = Home()
    await home.task("t1", notify=Notify.MESSAGE)
    async with home.announcer():
        pass
    assert home.telegram.sent == [(TELEGRAM, "Ton analyse est finie : tout est vert.")]
    assert "in writing" in home.model.requests[0].messages[-1].content


async def test_nobody_listening_on_voice_means_a_message() -> None:
    home = Home(voice=VoiceChannel(connected=False))
    await home.task("t1")
    async with home.announcer():
        pass
    assert [d.address for d in await home.journal.history(Delivered)] == [TELEGRAM]


async def test_a_failed_send_falls_back_to_the_next_channel() -> None:
    home = Home(voice=VoiceChannel(broken=True))
    await home.task("t1")
    async with home.announcer():
        pass
    assert home.telegram.sent and [t.address for t in await home.journal.history(AssistantTurn)] == [TELEGRAM]


async def test_a_result_is_delivered_once_even_across_restarts() -> None:
    home = Home()
    await home.task("t1")
    async with home.announcer():
        pass
    async with home.announcer():
        pass
    assert len(home.voice.sent) == 1
    assert [d.task_id for d in await home.journal.history(TaskDelivered)] == ["t1"]


async def test_a_cancelled_task_is_not_announced_and_a_failure_is() -> None:
    home = Home()
    await home.task("t1", status=TaskStatus.CANCELLED)
    await home.task("t2", status=TaskStatus.FAILED)
    async with home.announcer():
        pass
    assert len(home.voice.sent) == 1
    assert "Failure: boom" in home.model.requests[0].messages[-1].content


async def test_an_undeliverable_result_is_logged_and_retried_later() -> None:
    home = Home(voice=VoiceChannel(connected=False))
    home.courier.channels = {}  # nothing plugged at all
    await home.task("t1")
    async with home.announcer():
        pass
    assert len(await home.journal.history(DeliveryFailed)) == 1
    assert await home.journal.history(TaskDelivered) == []

    home.courier.channels = {"voice": home.voice, "telegram": home.telegram}
    async with home.announcer():
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
    async with home.announcer():
        pass
    assert len(home.telegram.sent) == (1 if known else 0)
