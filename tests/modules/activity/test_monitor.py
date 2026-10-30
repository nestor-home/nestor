"""What the agent is doing, added up from what really runs: answers, speech a satellite hears, delegated
tasks and the quiet hours, each change waking whoever waits for it."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nestor.core import utc_now
from nestor.modules.activity import Activity, ActivityMonitor
from nestor.modules.channels import Address, InboundMessage, Sender
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.model import ToolCall, ToolSpec
from nestor.modules.cognition.tools import Tool, Toolbox
from nestor.modules.conversation import Agent, Persona
from nestor.modules.household import Account, Household, Person
from nestor.modules.initiative import QuietHours
from nestor.modules.journal import Journal
from nestor.modules.satellites import SatelliteDisconnected, SpeechActivityObserved
from nestor.testing.cognition import ScriptedExecutor, ScriptedModel
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryEventLog

PARIS = ZoneInfo("Europe/Paris")
TELEGRAM = Address("telegram", "42")
MATHIS = Person(id="mathis", name="Mathis", accounts=(Account.parse("telegram:42"),))  # ty: ignore[invalid-argument-type]


async def weather(arguments: object, context: object) -> str:
    return "21 °C"


def paris(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 30, hour, minute, tzinfo=PARIS)


class World:
    def __init__(self, model: ScriptedModel, *, quiet: str | None, clock: Callable[[], datetime]) -> None:
        self.journal = Journal(MemoryEventLog())
        self.tasks = TaskManager(self.journal, [ScriptedExecutor(duration_s=10)])
        self.agent = Agent(
            model=model,
            persona=Persona(name="Richie", character="Tu es Richie."),
            journal=self.journal,
            household=Household([MATHIS]),
            localizer=EchoLocalizer(),
            toolbox=Toolbox(self.journal, [Tool(spec=ToolSpec("weather", "the weather"), run=weather)]),
        )
        self.monitor = ActivityMonitor(
            self.journal,
            self.agent.replies,
            self.tasks,
            quiet_hours=QuietHours.parse(quiet) if quiet else None,
            timezone="Europe/Paris",
            clock=clock,
        )

    async def changed(self, action: Callable[[], object]) -> Activity:
        """Run `action` and wait for the change it brings."""
        change = self.monitor.changes()
        result = action()
        if asyncio.iscoroutine(result):
            await result
        await asyncio.wait_for(change.wait(), 1)
        return self.monitor.current().state


@pytest.fixture
async def world() -> AsyncIterator[World]:
    world = World(
        ScriptedModel(ToolCall(id="c1", name="weather", arguments={}), "Il fait vingt et un degrés.", "Bien reçu."),
        quiet=None,
        clock=utc_now,
    )
    async with world.tasks, world.monitor:
        yield world


async def test_an_answer_is_thought_then_spoken_then_the_agent_is_idle_again(world: World) -> None:
    states: list[Activity] = []
    world.agent.replies.listen(lambda: states.append(world.monitor.current().state))
    assert world.monitor.current().state is Activity.IDLE
    reply = world.agent.respond(InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Quel temps ?"))
    assert await reply.collect() == "Il fait vingt et un degrés."
    assert states == [Activity.THINKING, Activity.SPEAKING, Activity.IDLE], "the tool call is thought, not said"
    assert world.monitor.current().replies == 0


async def test_an_unprompted_message_being_written_is_thought_not_spoken(world: World) -> None:
    states: list[Activity] = []
    world.agent.replies.listen(lambda: states.append(world.monitor.current().state))
    await world.agent.compose(TELEGRAM, MATHIS, "Dis bonjour.")
    assert states == [Activity.THINKING, Activity.IDLE]


async def test_someone_heard_by_a_satellite_comes_first_until_they_stop_or_it_leaves(world: World) -> None:
    def heard(active: bool, device: str = "reachy") -> SpeechActivityObserved:
        return SpeechActivityObserved(source="satellite", device_id=device, room="salon", active=active)

    publish = world.journal.publish
    assert await world.changed(lambda: publish(heard(True))) is Activity.LISTENING
    assert world.monitor.current().listening_rooms == ("salon",)
    assert await world.changed(lambda: publish(heard(False))) is Activity.IDLE
    await world.changed(lambda: publish(heard(True)))
    gone = SatelliteDisconnected(source="satellite", device_id="reachy", room="salon")
    assert await world.changed(lambda: publish(gone)) is Activity.IDLE, "a device that leaves hears no one"


async def test_a_delegated_task_keeps_it_working_until_it_ends() -> None:
    world = World(ScriptedModel(), quiet=None, clock=utc_now)
    async with world.tasks, world.monitor:
        since = world.monitor.current().since
        assert (
            await world.changed(lambda: world.tasks.delegate("Réserver le restaurant", origin=TELEGRAM))
            is Activity.WORKING
        )
        working = world.monitor.current()
        assert (working.state, working.tasks) == (Activity.WORKING, 1) and working.since >= since
        (running,) = world.tasks.running()
        assert await world.changed(lambda: world.tasks.cancel(running.id)) is Activity.IDLE


async def test_quiet_hours_put_it_to_sleep_and_their_turn_wakes_whoever_waits() -> None:
    start = time.monotonic()
    almost = paris(22, 0) - timedelta(seconds=0.05)
    world = World(
        ScriptedModel(), quiet="22:00-07:00", clock=lambda: almost + timedelta(seconds=time.monotonic() - start)
    )
    async with world.tasks, world.monitor:
        before = world.monitor.current()
        assert before.state is Activity.IDLE and not before.quiet
        await asyncio.wait_for(world.monitor.changes().wait(), 1)
        after = world.monitor.current()
        assert after.state is Activity.SLEEPING and after.quiet and after.since > before.since


async def test_without_quiet_hours_nothing_turns_and_closing_stops_following() -> None:
    world = World(ScriptedModel(), quiet=None, clock=lambda: paris(3))
    async with world.tasks:
        async with world.monitor:
            assert world.monitor.current().state is Activity.IDLE, "no quiet hours: never asleep"
        change = world.monitor.changes()
        await world.journal.publish(SpeechActivityObserved(source="s", device_id="d", room="salon", active=True))
        await asyncio.sleep(0.01)
        assert not change.is_set(), "once closed, it follows nothing"
