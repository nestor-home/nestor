"""Outlook calendar tools: the events of the person's calendar, and adding one."""

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from nestor.adapters.common.text import cap
from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.moments import INSTANT, MOMENT, instant, span
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.microsoft.graph import GraphApi, Json, in_zone, mailbox_zone
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded

SEARCHED = 1000  # events read to search a span, Graph's largest page
MAX_RESULTS = 50
DESCRIPTION_CHARS = 1_000

EVENTS = ToolSpec(
    "outlook_calendar_events",
    "List the events of the person's Outlook calendar between two moments, optionally only those matching words. "
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
    "outlook_calendar_create",
    "Add an event to the person's Outlook calendar. A timed event has a start and an end with their offset; a "
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
    def __init__(self, account: str, api: Callable[[], GraphApi], known: dict[str, str]) -> None:
        """`known`: what the connector keeps about the account while it runs (its time zone)."""
        self._account, self._api, self._known = account, api, known

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=EVENTS, run=self.events, risk=Risk.READ, timeout_s=20.0),
            Tool(spec=CREATE, run=self.create, risk=Risk.WRITE, timeout_s=20.0),
        )

    async def events(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        since, until = instant(arguments.get("since")), instant(arguments.get("until"))
        limit = bounded(arguments.get("max_results"), default=20, maximum=MAX_RESULTS)
        words = str(arguments.get("query") or "").strip().lower()
        params = [
            ("startDateTime", since.isoformat()),
            ("endDateTime", until.isoformat()),  # each occurrence of a recurring event comes on its own
            ("$orderby", "start/dateTime"),
            # the calendar view has no search of its own: with words, the whole span is read, then sorted out here
            ("$top", str(SEARCHED if words else limit)),
            ("$select", "id,subject,start,end,isAllDay,location,bodyPreview,attendees"),
        ]
        api = self._api()
        zone = await mailbox_zone(api, self._known)
        found = await ask("Outlook calendar", api.get("/me/calendarView", params, in_zone(zone)))
        events = [_event(item) for item in found.get("value", []) if isinstance(item, dict)]
        if words:
            events = [e for e in events if words in f"{e['title']} {e['location']} {e['description']}".lower()]
        return {"account": self._account, "time_zone": zone, "events": events[:limit], "note": SHARED}

    async def create(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        title = str(arguments.get("title") or "").strip()
        if not title:
            raise ToolFailed("give the event a title")
        start, end = span(arguments.get("start"), arguments.get("end"))
        api = self._api()
        zone = await mailbox_zone(api, self._known)
        body: Json = {
            "subject": title,
            "start": _graph(start, zone),
            "end": _graph(end, zone),
            "isAllDay": not isinstance(start, datetime),
        }
        if location := str(arguments.get("location") or "").strip():
            body["location"] = {"displayName": location}
        if description := str(arguments.get("description") or "").strip():
            body["body"] = {"contentType": "text", "content": description}
        made = await ask("Adding to the Outlook calendar", api.send("POST", "/me/events", body, in_zone(zone)))
        return {"account": self._account, "time_zone": zone, "event": _event(made)}


def _graph(moment: date, zone: str) -> dict[str, str]:
    """A start or an end as Graph takes it, a time and its zone: an instant in UTC, a day at its midnight where the
    person lives."""
    if isinstance(moment, datetime):
        return {"dateTime": moment.astimezone(UTC).replace(tzinfo=None).isoformat(), "timeZone": "UTC"}
    return {"dateTime": f"{moment.isoformat()}T00:00:00", "timeZone": zone}


def _event(item: Mapping[str, Any]) -> dict[str, object]:
    whole_day = bool(item.get("isAllDay"))

    def when(key: str) -> str:  # in the mailbox's time zone, asked with `_in`
        moment = str((item.get(key) or {}).get("dateTime") or "")
        return moment[:10] if whole_day else moment[:19]

    attendees = [
        a["emailAddress"]["address"]
        for a in item.get("attendees") or []
        if isinstance(a, dict) and (a.get("emailAddress") or {}).get("address")
    ]
    return {
        "id": item.get("id"),
        "title": item.get("subject", ""),
        "start": when("start"),
        "end": when("end"),
        "all_day": whole_day,
        "location": (item.get("location") or {}).get("displayName", ""),
        "description": cap(str(item.get("bodyPreview") or ""), DESCRIPTION_CHARS),
        "attendees": attendees,
    }
