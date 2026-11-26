"""What the central agent sees of alerts: tools to create, list and cancel them, and the active ones."""

from collections.abc import Mapping, Sequence
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from nestor.core import ContractError, Day, PersonId
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import TITLE, Risk, Tool, ToolContext, ToolFailed, ToolProvider, titled
from nestor.modules.conversation import ContextProvider, Layer, Sections, TurnContext
from nestor.modules.initiative.alerts.book import AlertBook
from nestor.modules.initiative.alerts.types import Alert, AlertEnd, Frequency, Trigger

HOW_TO_ALERT = (
    "When someone asks you to do something later or regularly, or to tell them when something happens, call "
    "create_alert. Its trigger is one of: `at` (once, at a local date and time), `times` with `days` (to repeat), or "
    "`kinds` (as items of these kinds arrive). The instruction is what you will do when it rings, complete enough to "
    "act on alone (what to look up, what to tell, to whom). A condition, in the person's words, is what must hold for "
    'it to be worth telling: "the price is under 135 $" is checked with your tools each time it rings; for a mail, '
    "a feed or a page it is what to recognise (sender, tracking number, the feed or page by its name, the threshold…). "
    'The frequency says when it ends by itself: `once` ("tell me when the parcel arrives"), `every_time` '
    '("every morning, the news"), `until_rung` ("tell me once the stock is under 135": checked each time, ended '
    "once you told them). Set `urgent` only if waiting until tomorrow could cause harm or miss a deadline. When it "
    "rings, you wake up with your tools and what you write reaches whoever set it, where they are; to tell someone "
    "else, use message_person. Times are in the household's clock. Confirm briefly.\n{kinds}"
)
KINDS = (
    "Items that can ring an alert:\n{kinds}\n"
    "Only these: a feed, a page or a webhook that is not listed is added to the configuration by the household, not "
    "by you. An event marked exact rings as it arrives; any other needs a condition to recognise it."
)
NO_SOURCE = "No inbound source is connected (no mailbox, feed, page or webhook): alerts can only ring at times."


class AlertTools(ToolProvider, ContextProvider):
    name = "alert-tools"

    def __init__(self, book: AlertBook) -> None:
        self.book = book

    def tools(self) -> Sequence[Tool]:
        properties: dict[str, object] = {
            "title": TITLE,
            "instruction": {"type": "string", "description": "what you will do when it rings, for whom"},
            "at": {"type": "string", "description": "once, at this local date and time: 2026-11-03T09:00"},
            "times": {"type": "array", "items": {"type": "string"}, "description": "to repeat, at these: 08:00"},
            "days": {
                "type": "array",
                "items": {"type": "string", "enum": list(Day)},
                "description": "the days `times` repeat on; every day when left out",
            },
            "condition": {"type": "string", "description": "what must hold to tell, in the person's words"},
            "frequency": {"type": "string", "enum": list(Frequency)},
            "until": {"type": "string", "description": "the local date and time it ends at the latest"},
            "urgent": {"type": "boolean", "description": "tell at once, even in quiet hours (default false)"},
        }
        if self.book.kinds:
            properties["kinds"] = {"type": "array", "items": {"type": "string", "enum": sorted(self.book.kinds)}}
        create = {"type": "object", "properties": properties, "required": ["title", "instruction", "frequency"]}
        cancel = {"type": "object", "properties": {"alert_id": {"type": "string"}}, "required": ["alert_id"]}
        return (
            Tool(
                spec=ToolSpec("create_alert", "Do something later, regularly, or when something happens.", create),
                run=self._create,
                risk=Risk.WRITE,
            ),
            Tool(
                spec=ToolSpec(
                    "list_alerts",
                    "The alerts set, with why each last rang; not the state of the home or of a device.",
                ),
                run=self._list,
            ),
            Tool(spec=ToolSpec("cancel_alert", "Cancel an alert.", cancel), run=self._cancel, risk=Risk.WRITE),
        )

    def guidance(self) -> str:
        if not self.book.kinds:
            return HOW_TO_ALERT.format(kinds=NO_SOURCE)
        kinds = (
            f"- {kind}{' (exact)' if kind in self.book.structured else ''}{': ' + ', '.join(f) if f else ''}"
            for kind, f in sorted(self.book.kinds.items())
        )
        return HOW_TO_ALERT.format(kinds=KINDS.format(kinds="\n".join(kinds)))

    async def context(self, turn: TurnContext) -> Sections:
        if not self.book.alerts:
            return {Layer.HOUSEHOLD: "No alert is set."}
        listed = "\n".join(f"- [{a.id}] {a.title}, {self._when(a)}: {a.instruction}" for a in self.book.alerts.values())
        return {Layer.HOUSEHOLD: f"Alerts set:\n{listed}"}  # they change when one is set, rings or ends

    async def _create(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        title = titled(arguments)
        try:
            at = self._moment(arguments.get("at"))
            until = self._moment(arguments.get("until"))
            times = tuple(time.fromisoformat(str(t)) for t in _listed(arguments.get("times")))
        except ValueError as error:
            raise ToolFailed(f"cannot read the time: {error}") from None
        if any(t.tzinfo or t.second or t.microsecond for t in times):
            raise ToolFailed("times are hours and minutes in the household's clock: 08:00")
        named = [str(d) for d in _listed(arguments.get("days"))]
        if unknown := sorted(set(named) - set(Day)):
            raise ToolFailed(f"unknown days {', '.join(unknown)}: use {', '.join(Day)}")
        kinds = tuple(str(k) for k in _listed(arguments.get("kinds")))
        if unknown := sorted(set(kinds) - self.book.kinds.keys()):
            raise ToolFailed(f"cannot wait for {', '.join(unknown)}: no such source connected")
        condition = str(arguments.get("condition") or "").strip() or None
        if kinds and condition is None and not set(kinds) <= self.book.structured:
            raise ToolFailed("a mail, a feed's entry or a page is recognised by a condition: say what to look for")
        if str(arguments.get("frequency")) not in set(Frequency):
            raise ToolFailed(f"frequency is one of {', '.join(Frequency)}")
        now = self.book.clock()
        for moment in (at, until):
            if moment is not None and moment <= now:
                raise ToolFailed(f"{moment:%Y-%m-%d %H:%M} has already passed")
        try:
            alert = Alert(
                title=title,
                instruction=str(arguments["instruction"]),
                at=at,
                times=times,
                days=tuple(Day(d) for d in named),
                kinds=kinds,
                condition=condition,
                frequency=Frequency(str(arguments["frequency"])),
                until=until,
                urgent=arguments.get("urgent") is True,
                owner=context.person,
                created_in=context.address,
            )
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        first = alert.next_due(now, self.book.timezone)
        if until is not None and first is not None and until <= first:
            raise ToolFailed(f"it would end before it first rings ({first:%Y-%m-%d %H:%M}): `until` comes after that")
        alert = await self.book.create(alert, exchange=context.exchange)
        return {"alert_id": alert.id, "title": alert.title, "when": self._when(alert)}

    async def _list(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        return {"alerts": [self._listed(a, context.person) for a in self.book.upcoming()]}

    async def _cancel(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        alert_id = str(arguments["alert_id"])
        if not await self.book.end(alert_id, AlertEnd.CANCELLED, by=context.person):
            raise ToolFailed(f"no active alert {alert_id!r}")
        return {"cancelled": alert_id}

    def _listed(self, alert: Alert, asker: PersonId | None) -> dict[str, Any]:
        listed: dict[str, Any] = {
            "alert_id": alert.id,
            "title": alert.title,
            "when": self._when(alert),
            "instruction": alert.instruction,
            "frequency": alert.frequency.value,
        }
        if alert.condition:
            listed["condition"] = alert.condition
        if alert.urgent:
            listed["urgent"] = True
        if alert.until:
            listed["until"] = f"{alert.until.astimezone(ZoneInfo(self.book.timezone)):%Y-%m-%d %H:%M}"
        if rings := self.book.rings.get(alert.id):
            last = rings[-1]
            zone = ZoneInfo(self.book.timezone)
            listed["rang"] = self.book.rang[alert.id]
            listed["last_rang"] = f"{last.at.astimezone(zone):%A %d %B %H:%M}"
            if alert.owner is None or alert.owner == asker:  # why says what rang it: a mail is its owner's
                listed["last_rang"] += f", because {last.why(self.book.timezone)}"
        return listed

    def _when(self, alert: Alert) -> str:
        zone = ZoneInfo(self.book.timezone)
        match alert.trigger:
            case Trigger.AT:
                assert alert.at is not None
                return f"once, {alert.at.astimezone(zone):%A %d %B %Y %H:%M}"
            case Trigger.TIMES:
                times = ", ".join(t.strftime("%H:%M") for t in sorted(alert.times))
                days = ", ".join(alert.days) if alert.days else "every day"
                due = self.book.next_due(alert)
                upcoming = f" (next: {due.astimezone(zone):%A %d %B %H:%M})" if due else ""
                return f"{days} at {times}{upcoming}"
            case Trigger.EVENTS:
                return f"when an item of {', '.join(alert.kinds)} arrives"

    def _moment(self, value: object) -> datetime | None:
        if not value:
            return None
        moment = datetime.fromisoformat(str(value))
        return moment.replace(tzinfo=ZoneInfo(self.book.timezone)) if moment.tzinfo is None else moment


def _listed(value: object) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ToolFailed("times, days and kinds are lists")
    return value
