"""What every calendar connector shares: its two tools as the model sees them, and an event as it reads one."""

from collections.abc import Iterable
from dataclasses import dataclass

from nestor.adapters.common.text import cap
from nestor.adapters.connectors.common.moments import INSTANT, MOMENT
from nestor.modules.cognition.model import ToolSpec

NO_TITLE = "give the event a title"

MAX_EVENTS = 50
DESCRIPTION_CHARS = 1_000


def calendar_specs(prefix: str, calendar: str, shared: str, *, several: bool = False) -> tuple[ToolSpec, ToolSpec]:
    """`<prefix>_events` and `<prefix>_create` for `calendar` ("the person's Google Calendar"); `several`: the account
    has several calendars, named in each event and chosen when adding one."""
    which = "calendar, " if several else ""
    events = ToolSpec(
        f"{prefix}_events",
        f"List the events of {calendar} between two moments, optionally only those matching words. Returns "
        f"{which}title, start, end, location, description, attendees and id of each. {shared}",
        {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": INSTANT},
                "until": {"type": "string", "description": INSTANT},
                "query": {"type": "string", "description": "words the events must contain"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_EVENTS, "default": 20},
            },
            "required": ["since", "until"],
        },
    )
    chosen = {"calendar": {"type": "string", "description": "the calendar's name; the first one when not given"}}
    create = ToolSpec(
        f"{prefix}_create",
        f"Add an event to {calendar}. A timed event has a start and an end with their offset; a whole-day event has "
        "dates, its end being the day after the last one.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start": {"type": "string", "description": MOMENT},
                "end": {"type": "string", "description": MOMENT},
                "location": {"type": "string"},
                "description": {"type": "string"},
                **(chosen if several else {}),
            },
            "required": ["title", "start", "end"],
        },
    )
    return events, create


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """An event as the model reads it, whatever the calendar: a whole day's start and end are dates, a timed one's
    are times as the calendar gives them (with their offset, or in its time zone, which the answer then names)."""

    title: str
    start: str
    end: str
    all_day: bool
    location: str = ""
    description: str = ""
    attendees: tuple[str, ...] = ()
    id: str | None = None
    calendar: str | None = None  # an account with several calendars

    def shown(self) -> dict[str, object]:
        found = {
            "id": self.id,
            "calendar": self.calendar,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "all_day": self.all_day,
            "location": self.location,
            "description": cap(self.description, DESCRIPTION_CHARS),
            "attendees": list(self.attendees),
        }
        return {k: v for k, v in found.items() if v is not None}


def matching(events: Iterable[Event], words: object) -> list[Event]:
    """The events whose title, place or description holds `words` (all of them when there are none)."""
    wanted = str(words or "").strip().lower()
    return [e for e in events if wanted in f"{e.title} {e.location} {e.description}".lower()]
