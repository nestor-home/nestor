"""Moments a model gives a calendar or a task: an instant with its offset, or a whole day."""

from datetime import date, datetime

from nestor.modules.cognition.tools import ToolFailed

INSTANT = "ISO 8601 with its offset, e.g. 2026-11-14T09:00:00+01:00"
MOMENT = f"{INSTANT}, or a date (2026-11-14) for a whole day"
DAY = "the day, YYYY-MM-DD"


def moment(value: object) -> date | datetime:
    """A day, or an instant (never a time without its offset, which no calendar could place)."""
    text = str(value or "").strip()
    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        found = datetime.fromisoformat(text)
    except ValueError:
        raise ToolFailed(f"{text!r} is not a moment: {MOMENT}") from None
    if found.tzinfo is None:
        raise ToolFailed(f"{text!r} has no offset: {MOMENT}")
    return found


def instant(value: object) -> datetime:
    """A bound of a search: an instant, as a day has no start until it is placed in a time zone."""
    found = moment(value)
    if not isinstance(found, datetime):
        raise ToolFailed(f"{value!r} is a date: give an instant, {INSTANT}")
    return found


def day(value: object) -> date:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        raise ToolFailed(f"{value!r} is not a day: {DAY}") from None


def span(start: object, end: object) -> tuple[date, date]:
    """An event's start and end: both days (the end being the day after the last) or both instants, in order."""
    first, last = moment(start), moment(end)
    if isinstance(first, datetime) != isinstance(last, datetime):
        raise ToolFailed("start and end are both dates (a whole day) or both times")
    if last <= first:
        raise ToolFailed("the end comes after the start")
    return first, last
