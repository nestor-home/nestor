"""CalDAV calendar tools: the events of every calendar of the account, and adding one."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from xml.sax.saxutils import quoteattr

from nestor.adapters.common.text import cap
from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.moments import INSTANT, MOMENT, instant, span
from nestor.adapters.connectors.common.tools import ask, failed
from nestor.adapters.connectors.dav import cards
from nestor.adapters.connectors.dav.dav import Collection, Dav, DavError
from nestor.core import ProviderError, utc_now
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded

MAX_RESULTS = 50
DESCRIPTION_CHARS = 1_000

EVENTS = ToolSpec(
    "dav_calendar_events",
    "List the events of the person's calendars (CalDAV: iCloud, Fastmail, Nextcloud…) between two moments, "
    "optionally only those matching words. Returns calendar, title, start, end, location, description and "
    f"attendees of each. {SHARED}",
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
    "dav_calendar_create",
    "Add an event to one of the person's calendars (CalDAV). A timed event has a start and an end with their "
    "offset; a whole-day event has dates, its end being the day after the last one.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": MOMENT},
            "end": {"type": "string", "description": MOMENT},
            "location": {"type": "string"},
            "description": {"type": "string"},
            "calendar": {"type": "string", "description": "the calendar's name; the first one when not given"},
        },
        "required": ["title", "start", "end"],
    },
)


class CalendarTools:
    def __init__(self, account: str, dav: Callable[[], Awaitable[Dav]]) -> None:
        self._account, self._dav = account, dav

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=EVENTS, run=self.events, risk=Risk.READ, timeout_s=30.0),
            Tool(spec=CREATE, run=self.create, risk=Risk.WRITE, timeout_s=20.0),
        )

    async def events(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        since, until = instant(arguments.get("since")), instant(arguments.get("until"))
        dav = await ask("the calendar server", self._dav())
        calendars = await ask("Listing the calendars", dav.calendars())
        query = _query(_stamp(since), _stamp(until))
        answers = await asyncio.gather(*(dav.report(c.url, query) for c in calendars), return_exceptions=True)
        read = [(c, a) for c, a in zip(calendars, answers, strict=True) if not isinstance(a, BaseException)]
        unread = [c.name for c, a in zip(calendars, answers, strict=True) if isinstance(a, DavError)]
        if not read and calendars:  # none could be read: say why, as for any failed call
            error = next(a for a in answers if isinstance(a, BaseException))
            raise failed("Reading the calendars", error) if isinstance(error, ProviderError) else error
        events = [
            _event(event, calendar)
            for calendar, answer in read
            for _, data in answer
            for event in cards.parse(data).find("VEVENT")
        ]
        if words := str(arguments.get("query") or "").strip().lower():
            events = [e for e in events if words in f"{e['title']} {e['location']} {e['description']}".lower()]
        events.sort(key=lambda e: str(e["start"]))
        limit = bounded(arguments.get("max_results"), default=20, maximum=MAX_RESULTS)
        found: dict[str, object] = {"account": self._account, "events": events[:limit], "note": SHARED}
        if unread:
            found["unreadable_calendars"] = unread  # shared or forbidden ones: the others are read
        return found

    async def create(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        title = str(arguments.get("title") or "").strip()
        if not title:
            raise ToolFailed("give the event a title")
        start, end = span(arguments.get("start"), arguments.get("end"))
        dav = await ask("the calendar server", self._dav())
        calendars = await ask("Listing the calendars", dav.calendars())
        named = str(arguments.get("calendar") or "").strip()
        uid = str(uuid.uuid4())
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Nestor//Nestor//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_stamp(utc_now())}",
            _line("DTSTART", start),
            _line("DTEND", end),
            f"SUMMARY:{cards.escape(title)}",
            *(
                f"{name}:{cards.escape(value)}"
                for name, key in (("LOCATION", "location"), ("DESCRIPTION", "description"))
                if (value := str(arguments.get(key) or "").strip())
            ),
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        body = "\r\n".join(cards.fold(line) for line in lines) + "\r\n"
        # the one named; else the first that takes it (a shared or subscribed calendar may be read-only)
        candidates = [_chosen(calendars, named)] if named else calendars
        if not candidates:
            raise ToolFailed("this account has no calendar for events")
        for i, calendar in enumerate(candidates):
            try:
                await dav.put(f"{calendar.url.rstrip('/')}/{uid}.ics", body, "text/calendar; charset=utf-8")
            except DavError as error:
                if error.status == 403 and i < len(candidates) - 1:
                    continue
                raise failed("Adding to the calendar", error) from None
            return {"account": self._account, "event": _event(cards.parse(body).find("VEVENT")[0], calendar)}
        raise ToolFailed("no calendar of this account takes new events")


def _chosen(calendars: list[Collection], name: str) -> Collection:
    found = next((c for c in calendars if c.name.casefold() == name.casefold()), None)
    if found is None:
        raise ToolFailed(f"no calendar named {name!r}: {', '.join(c.name for c in calendars)}")
    return found


def _query(start: str, end: str) -> str:
    """The events overlapping [start, end), each occurrence of a recurring one on its own, in UTC (`expand`)."""
    span_ = f"start={quoteattr(start)} end={quoteattr(end)}"
    return (
        '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        f"<d:prop><c:calendar-data><c:expand {span_}/></c:calendar-data></d:prop>"
        '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
        f"<c:time-range {span_}/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>"
    )


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _line(name: str, moment: date) -> str:
    if isinstance(moment, datetime):
        return f"{name}:{_stamp(moment)}"
    return f"{name};VALUE=DATE:{moment.strftime('%Y%m%d')}"


def _event(event: cards.Block, calendar: Collection) -> dict[str, object]:
    start, end = cards.moment(event.first("DTSTART")), cards.moment(event.first("DTEND"))
    attendees = [a.value.removeprefix("mailto:").removeprefix("MAILTO:") for a in event.all("ATTENDEE")]
    return {
        "calendar": calendar.name,
        "title": event.text("SUMMARY"),
        "start": start.isoformat() if start else "",
        "end": end.isoformat() if end else "",
        "all_day": start is not None and not isinstance(start, datetime),
        "location": event.text("LOCATION"),
        "description": cap(event.text("DESCRIPTION"), DESCRIPTION_CHARS),
        "attendees": attendees,
    }
