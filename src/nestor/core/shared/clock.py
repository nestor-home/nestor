"""Time helpers: every timestamp in Nestor is timezone-aware UTC; days of the week are named in the household's
clock."""

from datetime import UTC, datetime
from enum import StrEnum


class Day(StrEnum):
    """A day of the week, Monday first (`list(Day)[date.weekday()]`)."""

    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


def utc_now() -> datetime:
    return datetime.now(UTC)
