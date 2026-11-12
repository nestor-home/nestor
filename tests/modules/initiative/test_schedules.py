"""Wake-ups: when they are due, run once each time even across restarts, with the agent's tools, and what they find
reaches whoever set them, as a task's result does."""

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from nestor.core import PersonId, ProviderError
from nestor.modules.channels import Address
from nestor.modules.cognition.model import ModelRequest, ToolCall
from nestor.modules.cognition.tools import Toolbox, ToolContext, ToolFailed
from nestor.modules.conversation import (
    Agent,
    AssistantTurn,
    Attachments,
    ModelChoice,
    NotificationTurn,
    Persona,
    TurnContext,
)
from nestor.modules.household import Household, Person
from nestor.modules.identity import Speaker
from nestor.modules.initiative import (
    Courier,
    Day,
    DeliveryFailed,
    Schedule,
    ScheduleBook,
    ScheduleCancelled,
    ScheduleFired,
    Scheduler,
    ScheduleTools,
)
from nestor.modules.journal import Journal
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.cognition.model import Reply
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

PARIS = ZoneInfo("Europe/Paris")
CHAT = Address("telegram", "42")
MATHIS = Person(id=PersonId("mathis"), name="Mathis")


def paris(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=PARIS)  # the 2nd is a Monday


def test_a_recurring_wake_up_is_next_due_at_its_first_time_on_one_of_its_days() -> None:
    weekdays = Schedule(
        id="s", instruction="x", times=(time(8), time(18)), days=(Day.MON, Day.TUE, Day.WED, Day.THU, Day.FRI)
    )
    assert weekdays.next_due(paris(2, 7), "Europe/Paris") == paris(2, 8)
    assert weekdays.next_due(paris(2, 8), "Europe/Paris") == paris(2, 18), "strictly after"
    assert weekdays.next_due(paris(6, 19), "Europe/Paris") == paris(9, 8), "Friday evening, then Monday"
    once = Schedule(id="o", instruction="x", at=paris(3, 9))
    assert (once.next_due(paris(2, 9), "UTC"), once.next_due(paris(3, 9), "UTC")) == (paris(3, 9), None)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Home:
    def __init__(self, *replies: Reply, now: datetime) -> None:
        self.journal = Journal(MemoryEventLog())
        self.clock = Clock(now)
        self.model = ScriptedModel(*replies)
        self.build()

    def build(self) -> None:
        self.book = ScheduleBook(self.journal, timezone="Europe/Paris", clock=self.clock)
        self.tools = ScheduleTools(self.book)
        household = Household([MATHIS])
        self.agent = Agent(
            attachments=Attachments(MemoryBlobStore()),
            models=ModelChoice.single(self.model),
            persona=Persona(name="Richie", character="Tu es Richie.", timezone="Europe/Paris"),
            journal=self.journal,
            household=household,
            localizer=EchoLocalizer(),
            toolbox=Toolbox(self.journal, providers=[self.tools]),
            context=[self.tools],
        )
        self.telegram = InMemoryChannel("telegram")
        self.courier = Courier(self.journal, self.agent, [self.telegram])
        self.scheduler = Scheduler(self.book, household, self.courier)

    async def schedule(self, **arguments: object) -> Any:
        tool = next(t for t in self.tools.tools() if t.spec.name == "schedule")
        return await tool.run(arguments, ToolContext(address=CHAT, speaker=Speaker.account(MATHIS.id)))


async def test_a_wake_up_runs_once_each_time_it_is_due_with_its_tools_and_tells_whoever_set_it() -> None:
    home = Home(
        ToolCall("c1", "list_schedules", {}),
        "Voici les nouvelles.",
        ToolCall("c2", "list_schedules", {}),
        "Et celles du jour.",
        now=paris(2, 7),
    )
    async with home.book:
        await home.schedule(instruction="Envoie à Mathis les nouvelles", times=["08:00"])
        assert await home.scheduler.wake_due() == 0
        home.clock.now = paris(2, 8, 1)
        assert await home.scheduler.wake_due() == 1
        assert await home.scheduler.wake_due() == 0, "once for each time it is due"
        home.clock.now = paris(3, 8)
        assert await home.scheduler.wake_due() == 1

    assert [e.due_at for e in await home.journal.history(ScheduleFired)] == [paris(2, 8), paris(3, 8)]
    woken = home.model.requests[0].messages[-1].content
    assert "Mathis set is due now (Monday 08:00): Envoie à Mathis les nouvelles" in woken
    assert len(home.model.requests) == 4, "its tools run as in any turn"
    assert home.telegram.sent == [(CHAT, "Voici les nouvelles."), (CHAT, "Et celles du jour.")], "where it was set"
    assert len(await home.journal.history(NotificationTurn)) == 2, "each one a turn of that conversation"


async def test_a_wake_up_with_nothing_to_tell_sends_nothing_and_leaves_no_turn() -> None:
    home = Home(ToolCall("c1", "list_schedules", {}), "", now=paris(2, 7))
    async with home.book:
        await home.schedule(instruction="Si le prix passe sous 1 600 €, dis-le à Mathis", times=["10:00"])
        home.clock.now = paris(2, 10, 1)
        assert await home.scheduler.wake_due() == 1

    assert len(home.model.requests) == 2, "it checked once, and nothing was tried anywhere else"
    assert home.telegram.sent == []
    assert await home.journal.history(NotificationTurn, AssistantTurn, DeliveryFailed) == []


@pytest.mark.parametrize(
    "failure", [ProviderError("openrouter", "503", transient=True), RuntimeError("bug")], ids=["model down", "bug"]
)
async def test_a_wake_up_that_fails_does_not_stop_the_others_nor_runs_again(failure: Exception) -> None:
    def fails(request: ModelRequest) -> str:
        raise failure

    home = Home(fails, "Volets ouverts.", now=paris(2, 7))
    async with home.book:
        await home.schedule(instruction="Arrose les plantes", times=["08:00"])
        await home.schedule(instruction="Ouvre les volets", times=["08:00"])
        home.clock.now = paris(2, 8, 1)
        assert await home.scheduler.wake_due() == 2
        assert await home.scheduler.wake_due() == 0, "a failed wake-up is not retried in a loop"

    woken = [r.messages[-1].content for r in home.model.requests]
    assert "Ouvre les volets" in woken[-1]
    assert (CHAT, "Volets ouverts.") in home.telegram.sent
    assert len(await home.journal.history(ScheduleFired)) == 2


async def test_a_wake_up_missed_while_stopped_runs_once_when_back_then_follows_its_times() -> None:
    home = Home(*["Fait."] * 3, now=paris(2, 7))
    async with home.book:
        await home.schedule(instruction="Arrose les plantes", times=["08:00"])
    home.clock.now = paris(5, 12)  # stopped for three days
    home.build()
    async with home.book:
        assert await home.scheduler.wake_due() == 1
        assert await home.scheduler.wake_due() == 0
        assert home.book.next_due(next(iter(home.book.schedules.values()))) == paris(6, 8)


async def test_a_one_off_ends_once_run_and_a_cancelled_one_never_runs() -> None:
    home = Home("Fait.", now=paris(2, 7))
    async with home.book:
        once = await home.schedule(instruction="Rappelle à Mathis d'appeler le plombier", at="2026-11-03T09:00")
        daily = await home.schedule(instruction="Arrose les plantes", times=["08:00"])
        cancel = next(t for t in home.tools.tools() if t.spec.name == "cancel_schedule")
        await cancel.run(
            {"schedule_id": daily["schedule_id"]}, ToolContext(address=CHAT, speaker=Speaker.account(MATHIS.id))
        )
        home.clock.now = paris(3, 9, 5)
        assert await home.scheduler.wake_due() == 1
        assert home.book.schedules == {}
    home.build()
    async with home.book:
        assert home.book.schedules == {}, "rebuilt from the journal"
    assert [e.schedule_id for e in await home.journal.history(ScheduleCancelled)] == [daily["schedule_id"]]
    assert "once, Tuesday 03 November 2026 09:00" in str(once["when"])


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        ({"instruction": "x", "at": "2026-11-01T09:00"}, "has already passed"),
        ({"instruction": "x", "at": "demain"}, "cannot read the time"),
        ({"instruction": "x", "times": ["08:00"], "days": ["lundi"]}, "unknown days lundi"),
        ({"instruction": "x"}, "either once"),
        ({"instruction": "x", "at": "2026-11-03T09:00", "times": ["08:00"]}, "either once"),
    ],
)
async def test_a_wake_up_that_cannot_be_set_says_why(arguments: dict[str, object], error: str) -> None:
    home = Home(now=paris(2, 7))
    async with home.book:
        with pytest.raises(ToolFailed, match=error):
            await home.schedule(**arguments)
        assert home.book.schedules == {}


async def test_the_wake_ups_set_are_in_the_instructions_with_when_they_are_next_due() -> None:
    home = Home("D'accord.", now=paris(2, 7))
    async with home.book:
        await home.schedule(instruction="Arrose les plantes", times=["08:00"], days=["sat", "sun"])
        section = str(
            await home.tools.context(
                TurnContext(person=MATHIS, speaker=Speaker.account(MATHIS.id), address=CHAT, said=None)
            )
        )
    assert "sat, sun at 08:00 (next: Saturday 07 November 08:00): Arrose les plantes" in section
