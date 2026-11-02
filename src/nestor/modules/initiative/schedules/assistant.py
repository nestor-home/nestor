"""What the central agent sees of wake-ups: tools to schedule, list and cancel them, and the active ones."""

from collections.abc import Mapping, Sequence
from datetime import datetime, time
from zoneinfo import ZoneInfo

from nestor.core import ContractError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation import ContextProvider, Layer, Sections, TurnContext
from nestor.modules.initiative.schedules.book import ScheduleBook
from nestor.modules.initiative.schedules.types import DAYS, Schedule

HOW_TO_SCHEDULE = (
    'When someone asks you to do something later or regularly ("every morning at 8, send me the news", '
    '"remind me tomorrow at 9 to call the plumber"), call schedule with the instruction you will follow then, '
    "complete enough to act on alone (who to tell, how, what to look up), and either `at` for once or `times` with "
    "`days` to repeat. When it is due, you wake up with your tools; to tell someone, you use message_person. "
    "Times are in the household's clock. Confirm briefly when it is set."
)


class ScheduleTools(ToolProvider, ContextProvider):
    name = "schedule-tools"

    def __init__(self, book: ScheduleBook) -> None:
        self.book = book

    def tools(self) -> Sequence[Tool]:
        create = {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "what you will do when it is due, for whom"},
                "at": {"type": "string", "description": "once, at this local date and time: 2026-11-03T09:00"},
                "times": {"type": "array", "items": {"type": "string"}, "description": "to repeat, at these: 08:00"},
                "days": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(DAYS)},
                    "description": "the days to repeat on; every day when left out",
                },
            },
            "required": ["instruction"],
        }
        cancel = {"type": "object", "properties": {"schedule_id": {"type": "string"}}, "required": ["schedule_id"]}
        return (
            Tool(
                spec=ToolSpec("schedule", "Do something later, once or regularly.", create),
                run=self._create,
                risk=Risk.WRITE,
            ),
            Tool(spec=ToolSpec("list_schedules", "The wake-ups set."), run=self._list),
            Tool(spec=ToolSpec("cancel_schedule", "Cancel a wake-up.", cancel), run=self._cancel, risk=Risk.WRITE),
        )

    def guidance(self) -> str:
        return HOW_TO_SCHEDULE

    async def context(self, turn: TurnContext) -> Sections:
        if not self.book.schedules:
            return {}
        listed = "\n".join(f"- [{s.id}] {self._when(s)}: {s.instruction}" for s in self.book.schedules.values())
        return {Layer.HOUSEHOLD: f"Wake-ups set:\n{listed}"}  # they change when one is set, ends or is cancelled

    async def _create(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        zone = ZoneInfo(self.book.timezone)
        try:
            at = datetime.fromisoformat(str(arguments["at"])) if arguments.get("at") else None
            times = tuple(time.fromisoformat(str(t)) for t in _listed(arguments.get("times")))
        except ValueError as error:
            raise ToolFailed(f"cannot read the time: {error}") from None
        if at is not None:
            at = at.replace(tzinfo=zone) if at.tzinfo is None else at
            if at <= self.book.clock():
                raise ToolFailed(f"{at:%Y-%m-%d %H:%M} has already passed")
        try:
            schedule = await self.book.create(
                str(arguments["instruction"]),
                owner=context.person,
                created_in=context.address,
                at=at,
                times=times,
                days=tuple(str(d) for d in _listed(arguments.get("days"))),
                exchange=context.exchange,
            )
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        return {"schedule_id": schedule.id, "when": self._when(schedule)}

    async def _list(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        return {
            "schedules": [
                {"schedule_id": s.id, "when": self._when(s), "instruction": s.instruction}
                for s in self.book.schedules.values()
            ]
        }

    async def _cancel(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        schedule_id = str(arguments["schedule_id"])
        if schedule_id not in self.book.schedules:
            raise ToolFailed(f"no wake-up {schedule_id}")
        await self.book.cancel(schedule_id, by=context.person)
        return {"cancelled": schedule_id}

    def _when(self, schedule: Schedule) -> str:
        zone = ZoneInfo(self.book.timezone)
        if schedule.at is not None:
            return f"once, {schedule.at.astimezone(zone):%A %d %B %Y %H:%M}"
        times = ", ".join(t.strftime("%H:%M") for t in sorted(schedule.times))
        days = ", ".join(schedule.days) if schedule.days else "every day"
        due = self.book.next_due(schedule)
        upcoming = f" (next: {due.astimezone(zone):%A %d %B %H:%M})" if due else ""
        return f"{days} at {times}{upcoming}"


def _listed(value: object) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ToolFailed("times and days are lists")
    return value
