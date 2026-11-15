"""Google Calendar tools: the events of the person's main calendar, and adding one."""

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.calendar import MAX_EVENTS, NO_TITLE, Event, calendar_specs
from nestor.adapters.connectors.common.moments import instant, span
from nestor.adapters.connectors.common.tools import ask, required
from nestor.adapters.connectors.google.api import GoogleApi, Json
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, bounded

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

EVENTS, CREATE = calendar_specs("google_calendar", "the person's Google Calendar", SHARED)


class CalendarTools:
    def __init__(self, account: str, api: Callable[[], GoogleApi]) -> None:
        self._account, self._api = account, api

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=EVENTS, run=self.events, risk=Risk.READ, timeout_s=20.0),
            Tool(spec=CREATE, run=self.create, risk=Risk.WRITE, timeout_s=20.0),
        )

    async def events(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        since, until = instant(arguments.get("since")), instant(arguments.get("until"))
        params = [
            ("timeMin", since.isoformat()),
            ("timeMax", until.isoformat()),
            ("singleEvents", "true"),  # a recurring event comes as each of its occurrences
            ("orderBy", "startTime"),
            ("maxResults", str(bounded(arguments.get("max_results"), default=20, maximum=MAX_EVENTS))),
        ]
        if query := str(arguments.get("query") or "").strip():
            params.append(("q", query))
        found = await ask("Google Calendar", self._api().get(EVENTS_URL, params))
        events = [_event(item).shown() for item in found.get("items", []) if isinstance(item, dict)]
        return {"account": self._account, "events": events, "note": SHARED}

    async def create(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        start, end = span(arguments.get("start"), arguments.get("end"))
        body: Json = {"summary": required(arguments, "title", NO_TITLE), "start": _google(start), "end": _google(end)}
        for key in ("location", "description"):
            if value := str(arguments.get(key) or "").strip():
                body[key] = value
        made = await ask("Adding to Google Calendar", self._api().send("POST", EVENTS_URL, body))
        return {"account": self._account, "event": _event(made).shown()}


def _google(moment: date) -> dict[str, str]:
    """A start or an end as Google takes it: `{"dateTime": …}` for an instant, `{"date": …}` for a whole day."""
    return {"dateTime" if isinstance(moment, datetime) else "date": moment.isoformat()}


def _event(item: Mapping[str, Any]) -> Event:
    def when(key: str) -> str:
        moment = item.get(key) or {}
        return str(moment.get("dateTime") or moment.get("date") or "")

    return Event(
        id=item.get("id"),
        title=str(item.get("summary", "")),
        start=when("start"),
        end=when("end"),
        all_day="date" in (item.get("start") or {}),
        location=str(item.get("location", "")),
        description=str(item.get("description") or ""),
        attendees=tuple(a["email"] for a in item.get("attendees") or [] if isinstance(a, dict) and a.get("email")),
    )
