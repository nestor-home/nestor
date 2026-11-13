"""Google Calendar tools: the events of the person's main calendar, and adding one."""

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from nestor.adapters.common.text import cap
from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.moments import INSTANT, MOMENT, instant, span
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.google.api import GoogleApi, Json
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
MAX_RESULTS = 50
DESCRIPTION_CHARS = 1_000

EVENTS = ToolSpec(
    "google_calendar_events",
    "List the events of the person's Google Calendar between two moments, optionally only those matching words. "
    f"Returns title, start, end, location, description, attendees and id of each. {SHARED}",
    {
        "type": "object",
        "properties": {
            "since": {"type": "string", "description": INSTANT},
            "until": {"type": "string", "description": INSTANT},
            "query": {"type": "string", "description": "words the events must contain"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 20},
        },
        "required": ["since", "until"],
    },
)
CREATE = ToolSpec(
    "google_calendar_create",
    "Add an event to the person's Google Calendar. A timed event has a start and an end with their offset; a "
    "whole-day event has dates, its end being the day after the last one.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": MOMENT},
            "end": {"type": "string", "description": MOMENT},
            "location": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["title", "start", "end"],
    },
)


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
            ("maxResults", str(bounded(arguments.get("max_results"), default=20, maximum=MAX_RESULTS))),
        ]
        if query := str(arguments.get("query") or "").strip():
            params.append(("q", query))
        found = await ask("Google Calendar", self._api().get(EVENTS_URL, params))
        events = [_event(item) for item in found.get("items", []) if isinstance(item, dict)]
        return {"account": self._account, "events": events, "note": SHARED}

    async def create(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        title = str(arguments.get("title") or "").strip()
        if not title:
            raise ToolFailed("give the event a title")
        start, end = span(arguments.get("start"), arguments.get("end"))
        body: Json = {"summary": title, "start": _google(start), "end": _google(end)}
        for key in ("location", "description"):
            if value := str(arguments.get(key) or "").strip():
                body[key] = value
        made = await ask("Adding to Google Calendar", self._api().send("POST", EVENTS_URL, body))
        return {"account": self._account, "event": _event(made)}


def _google(moment: date) -> dict[str, str]:
    """A start or an end as Google takes it: `{"dateTime": …}` for an instant, `{"date": …}` for a whole day."""
    return {"dateTime" if isinstance(moment, datetime) else "date": moment.isoformat()}


def _event(item: Mapping[str, Any]) -> dict[str, object]:
    def when(key: str) -> str:
        moment = item.get(key) or {}
        return str(moment.get("dateTime") or moment.get("date") or "")

    attendees = [a.get("email") for a in item.get("attendees") or [] if isinstance(a, dict) and a.get("email")]
    return {
        "id": item.get("id"),
        "title": item.get("summary", ""),
        "start": when("start"),
        "end": when("end"),
        "all_day": "date" in (item.get("start") or {}),
        "location": item.get("location", ""),
        "description": cap(str(item.get("description") or ""), DESCRIPTION_CHARS),
        "attendees": attendees,
    }
